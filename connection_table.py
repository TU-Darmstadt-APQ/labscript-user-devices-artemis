from labscript import start, stop, add_time_marker, AnalogOut, DigitalOut
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock
from labscript_devices.DummyIntermediateDevice import DummyIntermediateDevice
from user_devices.initialize_connection import *


def build_connectiontable():
    dummy_pseudoclock = DummyPseudoclock(name='dummy_pseudoclock')
    clockline = dummy_pseudoclock.clockline

    # init_BS_10(clockline)
    # init_BS_8(clockline)
    # init_HV_250_8(clockline)
    # init_BS_341A(clockline)
    # init_UM(clockline)
    init_CAEN(clockline)
    init_BNC_575()

if __name__ == '__main__':

    build_connectiontable()

    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()

    # BNC

    # CAEN
    t += 1
    # caen_ch_0.constant(t=t, value=2000)
    # t += 1
    # caen_ch_1.constant(t=t, value=2000)
    # t += 1
    # caen_ch_3.constant(t=t, value=2000)

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

    stop(t)
