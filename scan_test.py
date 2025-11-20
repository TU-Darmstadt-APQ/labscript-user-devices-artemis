# ~/labscript-suite/userlib/labscriptlib/example_apparatus/scan_test.py

from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript import *

from labscriptlib.example_apparatus.connection_table import *

def build_connectiontable():
    DummyPseudoclock('pseudoclock')
    DummyIntermediateDevice('intermediatedevice', parent_device=pseudoclock.clockline)
    clockline = pseudoclock.clockline
    Trigger('camera_trigger', parent_device=intermediatedevice, connection='do0')

    # init_BNC_575()
    # init_BS_10(clockline)
    # init_BS_8(clockline)
    # init_HV_250_8(clockline)
    # init_BS_341A(clockline)
    # init_UM(pseudoclock.clockline)
    # init_CAEN_bipol(clockline)
    init_CAEN_monopol(clockline)
    # init_HV_200_8(clockline)
    # init_BNC_575()
    # init_IDS(camera_trigger)
    init_IDS_UI()
    init_picoscope_173()
    # init_alvium()


build_connectiontable()

t = 0

add_time_marker(t, "start_initialization_test", verbose=True)
start()

picoscope_173.set_stream_sampling(sampling_rate=4e6, no_post_trigger_samples=10000)
picoscope_173.set_simple_trigger(source="channel_A", threshold=2.9, direction='falling', delay_samples=0,
                                 auto_trigger_s=0)
picoscope_173.signal_generator_config(offset_voltage=0, pk2pk=2, wave_type='square')

IDSCameraUI5240SE.expose("image_111", "frametype_111")
IDSCameraUI5240SE.expose("image_222", "frametype_111")

# IDSCameraUI5240SE.expose("image_111", "frametype_222")
# IDSCameraUI5240SE.expose("image_222", "frametype_333")
# picoscope_173.set_stream_sampling(sampling_rate=4e6, noPostTriggerSamples=10000)
# picoscope_173.run_mode('stream')
# picoscope_173.set_simple_trigger(source="channel_A", threshold_mV=2900, direction='rising', delay_samples=0, autoTrigger_ms=0)
# picoscope.set_trigger_conditions(sources=["Channel_A"], info="add")
# picoscope.set_trigger_direction(source="Channel_A", direction="rising")
# picoscope.set_trigger_properties(source="Channel_A", thresholdMode="level", thresholdUpper_mV=5000, thresholdUpperHysteresis_mV=0.1, thresholdLower_mV=0, thresholdLowerHysteresis_mV=0.1)
# picoscope.set_trigger_delay(delay_samples=20)
# picoscope.signal_generator_config(0,200000,'sine')

# BNC

# CAEN
# t += 1
sikler1_north.constant(t=t, value=sikler1_north_v)
sikler1_south.constant(t=t, value=sikler1_south_v)
sikler1_east.constant(t=t, value=100)
# aaa.constant(t=t, value=aaa_v)
# bbb.constant(t=t, value=bbb_v)
# ccc.constant(t=t, value=-555)


# t += 1

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

stop(t+0.0001)
