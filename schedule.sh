#!/bin/sh
#PBS -N batch_DDPG
#PBS -o batch_DDPG.out
#PBS -b batch_DDPG.err
#PBS -l walltime=05:00:00
#PBS -l ncpus=32
python schedule_calcs_DDPG.py
