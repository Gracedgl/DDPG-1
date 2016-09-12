# -*- coding: utf-8 -*-
"""
@author: Olivier Sigaud

"""

import math
import gym
from gym import spaces
from gym.utils import seeding
from gym.envs.classic_control import rendering
import numpy as np

verbose = False

from gym.envs.motor_control.ArmModel.ArmType import ArmType
from gym.envs.motor_control.Cost.Cost import Cost
from gym.envs.motor_control.ArmModel.MuscularActivation import getNoisyCommand, muscleFilter

from Utils.ReadXmlArmFile import ReadXmlArmFile

pathDataFolder = "./ArmParams/"

class ArmModelEnv(gym.Env):
    metadata = {
        'render.modes': ['human', 'rgb_array'],
        'video.frames_per_second': 30
    }
    def __init__(self):
        '''
    	Initializes parameters used to run functions below
     	'''
        self.rs = ReadXmlArmFile(pathDataFolder + "setupArm.xml")
        self.name = "ArmModel"
        self.arm = ArmType[self.rs.arm]()
        self.arm.setDT(self.rs.dt)
        self.delay = self.rs.delayUKF
        self.eval = Cost(self.rs)

        if(not self.rs.det and self.rs.noise!=None):
            self.arm.setNoise(self.rs.noise)

        self.dimState = self.rs.inputDim
        self.dimOutput = self.rs.outputDim

        self.posIni = np.loadtxt(pathDataFolder + self.rs.experimentFilePosIni)
        if(len(self.posIni.shape)==1):
            self.posIni=self.posIni.reshape((1,self.posIni.shape[0]))
        
        self.max_speed = 5.0
        self.steps = 0
        self.t = 0
        
        self.min_action = np.zeros(6)
        self.max_action = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])

        low_pos = self.arm.armP.lowerBounds
        high_pos = self.arm.armP.upperBounds

        self.low_state = np.array(low_pos + [-self.max_speed, -self.max_speed])
        self.high_state = np.array(high_pos + [self.max_speed, self.max_speed])

        #Viewer init
        self.viewer = None
        self.screen_width = 600
        self.screen_height = 400
        world_width = 1.4
        self.scale = self.screen_width/world_width

        self.action_space = spaces.Box(self.min_action, self.max_action)
        self.observation_space = spaces.Box(self.low_state, self.high_state)

        self._seed()
        self._configure(0,0.005)
        self.arm.set_state(self.reset())

    def test_mgd(self):
        q1, q2 = self.arm.mgi(0.45,0.2)
        print ("x y : 0.45,0.2")
        print ("q1, q2 :",q1,q2)
        coordElbow, coordHand = self.arm.mgdFull([q1, q2])
        print ("coord reset", coordElbow, coordHand)

    def _seed(self, seed=None):
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def _configure(self, point_number=0, target_size=0.005):
        self.point_number = point_number
        self.target_size = target_size

    def _reset(self):
        q1, q2 = self.arm.mgi(self.posIni[self.point_number][0],self.posIni[self.point_number][1])
        print ("xy reset",self.posIni[self.point_number][0],self.posIni[self.point_number][1])
        self.state = [0, 0, q1, q2]
        print ("state reset",self.state)
        coordElbow, coordHand = self.arm.mgdFull([q1, q2])
        print ("xy hand reset", coordHand)

        self.stateStore = np.zeros((self.delay,self.dimState))
        self.steps = 0
        self.t = 0
        return self.state
    
    def store_state(self, state):
        '''
    	Stores the current state and returns the delayed state
    
    	Input:		-state: the state to store
    	'''
        self.stateStore[1:]=self.stateStore[:-1]
        self.stateStore[0]=state
        return self.stateStore[self.delay-1]

    def _step(self, action):

        Unoisy = getNoisyCommand(action,self.arm.musclesP.knoiseU)
        Unoisy = muscleFilter(Unoisy)
#        Unoisy = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        #computation of the arm state
        dotq, q = self.arm.getDotQAndQFromStateVector(self.state)


        realNextState = self.arm.computeNextState(Unoisy, self.state)
        self.state = realNextState

        dotq, q = self.arm.getDotQAndQFromStateVector(self.state)

        coordElbow, coordHand = self.arm.mgdFull(q)
        self.xy_elbow = coordElbow
        self.xy_hand = coordHand

        output_state = self.store_state(realNextState)

        reward = 0
        cost, done = self.eval.compute_reward(self.arm, self.t, Unoisy, self.steps, coordHand, self.target_size)
        self.steps += 1
        self.t += self.rs.dt

        stepStore = []
        stepStore.append(self.state)
        stepStore.append(Unoisy)
        stepStore.append(action)
        stepStore.append(realNextState)
        stepStore.append([coordElbow[0], coordElbow[1]])
        stepStore.append([coordHand[0], coordHand[1]])
        tmpstore = np.array(stepStore).flatten()
        row = [item for sub in tmpstore for item in sub]

        if done:
            if  verbose:
                print ('goal reached!')

        return output_state, reward, done, row

    def scale_x(self,x):
        return self.screen_width/2 + x*self.scale

    def scale_y(self,y):
        return 10 + y*self.scale

    def _render(self, mode='human', close=False):
        if close:
            if self.viewer is not None:
                self.viewer.close()
                self.viewer = None
            return

        if self.viewer is None:
            self.viewer = rendering.Viewer(self.screen_width, self.screen_height)
            
        xys = []
        xys.append([self.scale_x(0),self.scale_y(0)])
        x1 = self.scale_x(self.xy_elbow[0])
        y1 = self.scale_y(self.xy_elbow[1])
        xys.append([x1,y1])
        x2 = self.scale_x(self.xy_hand[0])
        y2 = self.scale_y(self.xy_hand[1])
        xys.append([x2,y2])
        
        arm_drawing = rendering.make_polyline(xys)
        arm_drawing.set_linewidth(4)
        arm_drawing.set_color(.8, .3, .3)
        arm_drawing.add_attr(rendering.Transform())
        self.viewer.add_geom(arm_drawing)

        xmin = self.rs.XTarget - self.target_size/2
        xmax = self.rs.XTarget + self.target_size/2
        ytarg = self.rs.YTarget
        target = []
        target.append([self.scale_x(xmin),self.scale_y(ytarg)])
        target.append([self.scale_x(xmax),self.scale_y(ytarg)])
        target_drawing = rendering.make_polyline(target)
        target_drawing.set_linewidth(4)
        target_drawing.set_color(.2, .3, .8)
        target_drawing.add_attr(rendering.Transform())
        self.viewer.add_geom(target_drawing)

        start = []
        for i in range(len(self.posIni)):
            x_start = self.posIni[i][0]
            y_start = self.posIni[i][1]
            start.append([self.scale_x(x_start),self.scale_y(y_start)])
        start_drawing = rendering.make_polyline(start)
        start_drawing.set_color(.2, .8, .2)
        start_drawing.add_attr(rendering.Transform())
        self.viewer.add_geom(start_drawing)

        return self.viewer.render(return_rgb_array = mode=='rgb_array')

    def get_arm(self):
        return self.arm

    def get_target_vector(self):
        qtarget1, qtarget2 = self.arm.mgi(self.rs.XTarget, self.rs.YTarget)
        return [0.0, 0.0, qtarget1, qtarget2]

'''
a = ArmModelEnv()
a.test_mgd()
for i in range(20):
    a._step(np.array([0.5, 0.5, 0.5, 0.5, 0.5, 0.5]))
'''