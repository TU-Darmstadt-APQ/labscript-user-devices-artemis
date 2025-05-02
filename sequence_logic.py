'''
    This is a simple file that shows you the minimal elements you need
    to write your own experimental sequence.
'''
import numpy as np
from labscript import (
    AnalogIn,
    AnalogOut,
    ClockLine,
    DDS,
    DigitalOut,
    MHz,
    Shutter,
    StaticDDS,
    WaitMonitor,
    start,
    stop,
    wait,
)

from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, ClockLine
from labscript import *
from labscriptlib.example_apparatus import *
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
# from user_devices.BS_110.labscript_devices import BS_110
# from user_devices.BS_341A.labscript_devices import BS_341A
# from user_devices.HV_250.labscript_devices import HV_250
# from user_devices.HV_200.labscript_devices import HV_200
# from user_devices.UM.labscript_devices import UM
# from user_devices.CAEN_R8034.labscript_devices import CAEN
# from user_devices.BNC_575.labscript_devices import BNC_575

# def ConnectionTable():
#     dummy_pseudoclock = DummyPseudoclock(name='dummy_pseudoclock')
#     clockline = dummy_pseudoclock.clockline
#     CAEN(
#         name='voltage_source_serial',
#         parent_device=clockline,
#         port='/dev/pts/2',
#         baud_rate=9600
#     )
#     AnalogOut(name='AO_1', parent_device=voltage_source_serial, connection='CH0', default_value=3333)
#     AnalogOut(name='AO_2', parent_device=voltage_source_serial, connection='CH1', default_value=0.134)
#     AnalogOut(name='AO_3', parent_device=voltage_source_serial, connection='CH3', default_value=5555.55)
#
#     BNC_575(name='impulse_generator', port='/dev/pts/1', baud_rate=38400)



if __name__ == '__main__':

    # ConnectionTable()
    build_connectiontable()

    # Begin issuing labscript primitives.
    # Start() elicits the commencement of the shot.
    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()
    # t += AO_1.ramp(t=t, initial=0.0, final=888.0, duration=0.15, samplerate=1e3)
    t += 0.001
    # Set voltage on ao0
    # BS_110_analog_output_1.constant(t, 0.050213)
    stop(t)