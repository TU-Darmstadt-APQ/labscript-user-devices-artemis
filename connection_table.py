from labscript import *
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut
import sys, os
sys.path.append(os.path.dirname(__file__))

from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut, ClockLine
from labscript import *
from labscriptlib.example_apparatus import *
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from user_devices.UM.labscript_devices import UM
from user_devices.CAEN_R8034.labscript_devices import CAEN
from user_devices.BNC_575.labscript_devices import BNC_575, PulseChannel
from user_devices.BS_cryo.models.BS_1_10 import BS_1_10
from user_devices.BS_cryo.models.BS_1_8 import BS_1_8
from user_devices.HV_stahl.models.HV_200_8 import HV_200_8
from user_devices.HV_stahl.models.HV_250_8 import HV_250_8
from user_devices.HV_stahl.models.HV_500_8 import HV_500_8
from labscript_devices.BS_Series.models.BS_341A_spec import BS_341A_spec
from labscript_devices.BS_Series.models.BS_341A import BS_341A
from user_devices.IDS_UI_5240SE.labscript_devices import IDS_UICamera, VisibilityLevelType, TriggerEdgeType

from user_devices.PicoScope4000A.labscript_devices import PicoScope4000A, PicoAnalogIn
# from user_devices.AlliedVision.labscript_devices import AlviumCamera

from user_devices.logger_config import logger
def init_alvium():
    AlviumCamera(name='AlliedVision', serial_number="0C9X6")

def init_CAEN(clockline):
    CAEN(
        name='voltage_source_serial',
        parent_device=clockline,
        port='/dev/pts/1',
        # vid="21e1",
        # pid="0014",
        baud_rate=9600
    )
    AnalogOut(name='sikler1_north', parent_device=voltage_source_serial, connection='CH 0', default_value=0)
    AnalogOut(name='sikler1_south', parent_device=voltage_source_serial, connection='CH 1', default_value=0)
    AnalogOut(name='sikler1_east', parent_device=voltage_source_serial, connection='CH 2', default_value=0)
    AnalogOut(name='sikler1_west', parent_device=voltage_source_serial, connection='CH 3', default_value=0)
    AnalogOut(name='sikler2_north', parent_device=voltage_source_serial, connection='CH 4', default_value=0)
    AnalogOut(name='sikler2_south', parent_device=voltage_source_serial, connection='CH 5', default_value=0)
    AnalogOut(name='sikler2_east', parent_device=voltage_source_serial, connection='CH 6', default_value=0)
    AnalogOut(name='sikler2_west', parent_device=voltage_source_serial, connection='CH 7', default_value=0)

def init_picoscope_178():
    picoscope = PicoScope4000A(name='picoscope',
                   serial_number='HO248/178',
                   )
    # 8 channels
    # name, parent_device, connection, enabled=[0,1], coupling=['ac', 'dc'], analog_offset_v=[0.1..200], analog_offset_v=float
    PicoAnalogIn(name='pico_0', parent_device=picoscope, connection='channel_A', enabled=1, coupling='dc', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_1', parent_device=picoscope, connection='channel_B', enabled=1, coupling='dc', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_2', parent_device=picoscope, connection='channel_C', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_3', parent_device=picoscope, connection='channel_D', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_4', parent_device=picoscope, connection='channel_E', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)

def init_picoscope_173():
    picoscope = PicoScope4000A(name='picoscope_173', serial_number='HO248/173')
    # 8 channels
    # name, parent_device, connection, enabled=[0,1], coupling=['ac', 'dc'], analog_offset_v=[0.1..200], analog_offset_v=float
    PicoAnalogIn(name='pico_0', parent_device=picoscope, connection='channel_A', enabled=1, coupling='dc', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_1', parent_device=picoscope, connection='channel_B', enabled=1, coupling='dc', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_2', parent_device=picoscope, connection='channel_C', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_3', parent_device=picoscope, connection='channel_D', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)
    PicoAnalogIn(name='pico_4', parent_device=picoscope, connection='channel_E', enabled=1, coupling='ac', range_v=50, analog_offset_v=0.0)

def init_IDS(trigger_device):
    IDSCamera(name='CameraIds',
        parent_device=trigger_device,
        connection='trigger',
        serial_number="4104380609",
        camera_setting="Default")

def init_IDS_UI():
    IDS_UICamera(name='IDSCameraUI5240SE', serial_number="4104380609", visibility_level=VisibilityLevelType.ADVANCED,
                 gain=3.5, exposure_time=0.0090, roi=(0,0,1280,1024), frame_rate_fps=13,
                 acquisition_timeout=6)

def init_UM(clockline):
    # '/dev/ttyUSB0'
    UM(name='UM_ST', parent_device=clockline, port='/dev/ttyUSB0', baud_rate=9600)
    # Possible connections: "CH A'", "CH B'", "CH C'", "CH [1..10]"
    AnalogOut(name="UM_1", parent_device=UM_ST, connection="CH A'")
    AnalogOut(name="UM_2", parent_device=UM_ST, connection="CH B'")
    AnalogOut(name="UM_3", parent_device=UM_ST, connection="CH C'")

def init_BNC_575():
    # sudo dmesg | grep tty , '/dev/ttyUSB0'
    BNC_575(name='pulse_generator', port='/dev/pts/6', trigger_mode='DISabled')
    # Possible connections: "pulse [1..]"
    PulseChannel(name='pulse_1', connection='pulse 1', parent_device=pulse_generator, delay=1e-3, width=1, mode='SINGle')
    PulseChannel(name='pulse_2', connection='pulse 2', parent_device=pulse_generator, delay=1+2e-3, width=1, mode='SINGle')
    PulseChannel(name='pulse_3', connection='pulse 3', parent_device=pulse_generator, delay=2+2e-3, width=1, mode='SINGle')
    PulseChannel(name='pulse_4', connection='pulse 4', parent_device=pulse_generator, delay=2e-3, width=1)

def init_BS_10(clockline):
    BS_1_10(name='bias_supply_10', parent_device=clockline, port='/dev/pts/1', baud_rate=115200)
    AnalogOut(name='BS_110_analog_output_1', parent_device=bias_supply_10, connection='CH 1', default_value=2.22)
    AnalogOut(name='BS_110_analog_output_2', parent_device=bias_supply_10, connection='CH 4')
    AnalogOut(name='BS_110_analog_output_3', parent_device=bias_supply_10, connection='CH 3')
    AnalogOut(name='BS_110_analog_output_4', parent_device=bias_supply_10, connection='CH 2', default_value=3.33)

def init_BS_8(clockline):
    BS_1_8(name='bias_supply_8', parent_device=clockline, port='/dev/pts/4', baud_rate=115200)
    AnalogOut(name='BS_18_analog_output_1', parent_device=bias_supply_8, connection='CH 1', default_value=4.44)
    AnalogOut(name='BS_18_analog_output_2', parent_device=bias_supply_8, connection='CH 4')
    AnalogOut(name='BS_18_analog_output_3', parent_device=bias_supply_8, connection='CH 3')
    AnalogOut(name='BS_18_analog_output_4', parent_device=bias_supply_8, connection='CH 2', default_value=5.55)

def init_BS_341A_spec():
    BS_341A_spec(name='precision_voltage_source_for_ST', parent_device=clockline, port='/dev/pts/3', baud_rate=9600)
    AnalogOut(name='ao0_bs', parent_device=precision_voltage_source_for_ST, connection='CH 1', default_value=1.23)
    AnalogOut(name='ao1_bs', parent_device=precision_voltage_source_for_ST, connection='CH 2')

def init_BS_341A(clockline):
    BS_341A_spec(name='source_for_ST', parent_device=clockline, port='/dev/pts/3', baud_rate=9600)
    AnalogOut(name='ao0_bs_norm', parent_device=source_for_ST, connection='CH01', default_value=1.23)
    AnalogOut(name='ao1_bs_norm', parent_device=source_for_ST, connection='CH02')

def init_HV_200_8(clockline):
    HV_200_8(name="power_supply_for_ST", parent_device=clockline, port='/dev/pts/4')
    AnalogOut(name='AO_ST_1', parent_device=power_supply_for_ST, connection='CH 1', default_value=0)
    AnalogOut(name='AO_ST_2', parent_device=power_supply_for_ST, connection='CH 2', default_value=0)
    AnalogOut(name='AO_ST_3', parent_device=power_supply_for_ST, connection='CH 3', default_value=0)
    AnalogOut(name='AO_ST_4', parent_device=power_supply_for_ST, connection='CH 4', default_value=0)

def init_HV_250_8(clockline):
    HV_200_8(name="power_supply_for_CT", parent_device=clockline, port='/dev/pts/6')
    AnalogOut(name='AO_ST_1', parent_device=power_supply_for_CT, connection='CH 1', default_value=0)
    AnalogOut(name='AO_ST_2', parent_device=power_supply_for_CT, connection='CH 2', default_value=0)
    AnalogOut(name='AO_ST_3', parent_device=power_supply_for_CT, connection='CH 3', default_value=0)
    AnalogOut(name='AO_ST_4', parent_device=power_supply_for_CT, connection='CH 4', default_value=0)

def init_HV_500_8(clockline):
    HV_200_8(name="power_supply_for_E14", parent_device=clockline, port='/dev/pts/4')
    AnalogOut(name='AO_E14_1', parent_device=power_supply_for_E14, connection='CH 1', default_value=0)
    AnalogOut(name='AO_E14_2', parent_device=power_supply_for_E14, connection='CH 2', default_value=0)
    AnalogOut(name='AO_E14_3', parent_device=power_supply_for_E14, connection='CH 3', default_value=0)
    AnalogOut(name='AO_E14_4', parent_device=power_supply_for_E14, connection='CH 4', default_value=0)

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
    # init_CAEN(clockline)
    # init_HV_200_8(clockline)
    # init_BNC_575()
    # init_IDS(camera_trigger)
    # init_IDS_UI()
    init_picoscope_173()
    # init_alvium()

if __name__ == '__main__':
    build_connectiontable()
    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()
    picoscope_173.set_stream_sampling(sampling_rate=4e6, no_post_trigger_samples=10000)
    picoscope_173.set_simple_trigger(source="channel_A", threshold=2.9, direction='rising', delay_samples=0, auto_trigger_s=0)
    picoscope_173.signal_generator_config(offset_voltage=0, pk2pk=2, wave_type='square')

    stop(1)
    # picoscope_178.set_stream_sampling(sampleInterval_ns=250, noPostTriggerSamples=10000)
    # picoscope.run_mode('stream')
    # picoscope.set_simple_trigger(source="channel_A", threshold_mV=2900, direction='rising', delay_samples=0, autoTrigger_ms=0)
    # picoscope.set_trigger_conditions(sources=["Channel_A"], info="add")
    # picoscope.set_trigger_direction(source="Channel_A", direction="rising")
    # picoscope.set_trigger_properties(source="Channel_A", thresholdMode="level", thresholdUpper_mV=5000, thresholdUpperHysteresis_mV=0.1, thresholdLower_mV=0, thresholdLowerHysteresis_mV=0.1)
    # picoscope.set_trigger_delay(delay_samples=20)
    # picoscope.signal_generator_config(0,200000,'sine')

    # CAEN
    # caen_ch_0.constant(t=t, value=2000)
    # caen_ch_1.constant(t=t, value=2000)
    # caen_ch_3.constant(t=t, value=2000)

    # BS 1-8:
    # BS_18_analog_output_1.constant(t=t, value=2.000)
    # BS_18_analog_output_2.constant(t=t, value=3.000)

    # BS=34-1a SPEC:
    # t += 1
    # ao_BS_1.constant(t=t, value=12)
    # ao_BS_2.constant(t=t, value=16)
    # ao_BS_3.constant(t=t, value=15)

    # UM:
    # t += 1
    # CRES_1.constant(t=t, value=-2)
    # CRES_2.constant(t=t, value=-15)
    # CRES_5.constant(t=t, value=-22)

    # BS=34-1a:
    # t += 1
    # ao0_bs_norm.constant(t=t, value=12)
    # t += 2
    # ao1_bs_norm.constant(t=t, value=16)
    # t += 1
    # ao0_bs_norm.constant(t=t, value=15)


