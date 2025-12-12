from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript import *
import sys
from labscriptlib.example_apparatus.connection_table import *


build_connectiontable()

t = 0

add_time_marker(t, "start_initialization_test", verbose=True)
start()

# IDSCameraUI5240SE.expose("ion_detect", "ions")

# CAEN
sikler1_north.constant(t=t, value=sikler1_north_v)
sikler1_south.constant(t=t, value=sikler1_south_v)
sikler1_east.constant(t=t, value=sikler1_east_v)
sikler1_west.constant(t=t, value=sikler1_west_v)
sikler2_north.constant(t=t, value=sikler2_north_v)
sikler2_south.constant(t=t, value=sikler2_south_v)
sikler2_east.constant(t=t, value=sikler2_east_v)
sikler2_west.constant(t=t, value=sikler2_west_v)

caen_2.constant(t=t, value=caen_2_v)
caen_3.constant(t=t, value=caen_3_v)
caen_4.constant(t=t, value=caen_4_v)
caen_5.constant(t=t, value=caen_5_v)
caen_6.constant(t=t, value=caen_6_v)
caen_7.constant(t=t, value=caen_7_v)



# ch_1_200.constant(t=t, value=11)
# ch_4_200.ramp(t=t, duration=2, initial=20, final=60, samplerate=1)
# ch_5_250.ramp(t=t, duration=2, initial=200, final=222, samplerate=1)

# BS_10_0.constant(t=t, value=10)
# BS_10_1.constant(t=t, value=10)
# BS_10_2.constant(t=t, value=10)
# BS_10_3.constant(t=t, value=10)
# BS_10_4.constant(t=t, value=10)
# BS_10_5.constant(t=t, value=10)
# BS_10_6.constant(t=t, value=10)
# BS_10_7.constant(t=t, value=10)
# BS_10_8.constant(t=t, value=10)
# BS_10_9.constant(t=t, value=10)

# ch_1_250.constant(t=t, value=250)
# ch_4_250.ramp(t=t, duration=5, initial=4, final=10, samplerate=1)


# BS_10_0.constant(t=t, value=1)
# BS_10_1.constant(t=t, value=1)
# BS_10_2.constant(t=t, value=1)
# BS_10_3.constant(t=t, value=1)
# BS_10_4.constant(t=t, value=1)
# BS_10_5.constant(t=t, value=1)
# BS_10_6.constant(t=t, value=1)
# BS_10_7.constant(t=t, value=1)
# BS_10_8.constant(t=t, value=1)
# BS_10_9.constant(t=t, value=5)

# BS 1-8
# BS_18_analog_output_1.constant(t=t, value=6.000)
# BS_18_analog_output_2.constant(t=t, value=6.000)

# BS=34-1a SPEC:
# t += 1
# ao_BS_1.constant(t=t, value=12)
# t += 2
# ao_BS_2.constant(t=t, value=16)
# t += 1
# ao_BS_3.constant(t=t, value=15)

# UM:
# t += 1
# CRES_1.constant(t=t, value=-2)
# t += 2
# CRES_2.constant(t=t, value=-15)
# t += 1
# CRES_5.constant(t=t, value=-22)

# BS=34-1a:
# t += 1
# ao0_bs_norm.constant(t=t, value=12)
# t += 2
# ao1_bs_norm.constant(t=t, value=16)
# t += 1
# ao0_bs_norm.constant(t=t, value=15)

t = t + 0.0001
stop(t)

