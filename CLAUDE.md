# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SurveySimDev is a development area for SurveySimulation modules intended for eventual
use with EXOSIMS (Exoplanet Observation Simulation). 

## Context

Some of the modules and classes here
may implement methods analogous to those in either: 
`EXOSIMS.Prototypes.SurveySimulation` 
or
`EXOSIMS.SurveySimulation.coroOnlyScheduler`

(See here under the `ref/EXOSIMS` subdirectory.)

We are adopting a finite-state-machine (FSM) or state-transition, or StateCharts
approach for maintaining scheduler state. To do this, we have been using the 
`transitions` (also known as `pytransitions`)
Python package (`https://github.com/pytransitions/transitions`).


## TODO

Fill in this are with more guidance.

