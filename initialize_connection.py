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
from user_devices.UM.labscript_devices import UM
from user_devices.CAEN_R8034.labscript_devices import CAEN
from user_devices.BNC_575.labscript_devices import BNC_575, PulseChannel
from user_devices.BS_cryo.models.BS_1_10 import BS_1_10
from user_devices.BS_cryo.models.BS_1_8 import BS_1_8
from user_devices.HV_stahl.models.HV_200_8 import HV_200_8
from user_devices.HV_stahl.models.HV_250_8 import HV_250_8
from user_devices.HV_stahl.models.HV_500_8 import HV_500_8
# from labscript_devices.BS_Series.models.BS_341A_spec import BS_341A_spec
# from labscript_devices.BS_Series.models.BS_341A import BS_341A

from user_devices.logger_config import logger



def init_UM(clockline):
    # '/dev/ttyUSB0'
    UM(name='UM_ST', parent_device=clockline, port='/dev/ttyUSB0', baud_rate=9600)
    AnalogOut(name="CRES_1", parent_device=UM_ST, connection='CH A')
    AnalogOut(name="CRES_2", parent_device=UM_ST, connection='CH B')
    AnalogOut(name="CRES_3", parent_device=UM_ST, connection='CH C')
    AnalogOut(name="CRES_4", parent_device=UM_ST, connection='CH 1')
    AnalogOut(name="CRES_5", parent_device=UM_ST, connection='CH 2')

def init_BNC_575():
    # sudo dmesg | grep tty
    BNC_575(name='pulse_generator', port='/dev/ttyUSB0', trigger_mode='DISabled')
    PulseChannel(name='pulse_1_for_CAEN', connection='pulse 1', parent_device=pulse_generator, delay=4, width=1, mode='SINGle')
    PulseChannel(name='pulse_2_for_CC', connection='pulse 2', parent_device=pulse_generator, delay=1+2e-3, width=1, mode='SINGle')
    PulseChannel(name='pulse_3_for_MCT', connection='pulse 3', parent_device=pulse_generator, delay=2+2e-3, width=1, mode='SINGle')
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

def init_CAEN(clockline):
    logger.debug("INIT  VOLTAGE SOURCE")
    CAEN(
        name='voltage_source_serial',
        parent_device=clockline,
        port='',
        vid=0x21e1,
        pid=0x0014,
        baud_rate=9600
    )
    AnalogOut(name='caen_ch_0', parent_device=voltage_source_serial, connection='CH 0', default_value=0)
    AnalogOut(name='caen_ch_1', parent_device=voltage_source_serial, connection='CH 1', default_value=0)
    AnalogOut(name='caen_ch_3', parent_device=voltage_source_serial, connection='CH 3', default_value=0)

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
