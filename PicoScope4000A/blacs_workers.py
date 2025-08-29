from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from user_devices.logger_config import logger
import h5py
import ctypes

from picosdk.ps4000a import ps4000a as ps
import matplotlib.pyplot as plt
from picosdk.functions import adc2mV, assert_pico_ok


class PicoScopeWorker(Worker):
    def init(self):
        # open picoScope
        self.chandle = ctypes.c_int16()
        # convert serial number to bytes, or None if using first device
        if hasattr(self, "serial_number") and self.serial_number:
            self.serial = self.serial_number.encode()
        else:
            self.serial = None
        status = {}

        openunit_status = ps._OpenUnit(ctypes.byref(self.chandle), self.serial)
        status["openunit"] = openunit_status
        if openunit_status != 0:
            raise LabscriptError(f"PicoScope open failed with status {openunit_status}")

        print("PicoScope connected, handle:", self.chandle.value)

    def program_manual(self, front_panel_values):
        return


class PicoScope4000A:
    PS4000A_CHANNEL = {
        "PS4000A_CHANNEL_A": 0,
        "PS4000A_CHANNEL_B": 1,
        "PS4000A_CHANNEL_C": 2,
        "PS4000A_CHANNEL_D": 3,
        ("PS4000A_CHANNEL_E", "PS4000A_MAX_4_CHANNELS"): 4,
        "PS4000A_CHANNEL_F": 5,
        "PS4000A_CHANNEL_G": 6,
        "PS4000A_CHANNEL_H": 7,
        ("PS4000A_MAX_CHANNELS", "PS4000A_EXTERNAL"): 8,
        "PS4000A_TRIGGER_AUX": 9,
        "PS4000A_MAX_TRIGGER_SOURCES": 10,
        "PS4000A_PULSE_WIDTH_SOURCE": 0x10000000
    }

    PS4000A_COUPLING = make_enum([
        'PS4000A_AC',
        'PS4000A_DC',
    ])

    def __init__(self):
        return

    def stream(self):
        """collects streamed data (1 buffer). Plot oscillograph in GUI (mV/ns)"""
        return

    def set_channel(self, chandle, channel:str, coupling_type:str, channel_range:int, enabled=1, analogue_offset=0.0, ):
        enabled = 1
        disabled = 0
        analogue_offset = 0.0
        coupling_type = 1 # PS4000A_DC
        channel_range = 7 # PS4000A_2V

        status["setChA"] = ps.ps4000aSetChannel(chandle,
                                                ps.PS4000A_CHANNEL[channel],
                                                enabled,
                                                ps.PS4000A_COUPLING['PS4000A_DC'],
                                                channel_range,
                                                analogue_offset)
        assert_pico_ok(status["setChA"])

    def set_data_buffer(self, handle, source, pointer_max, pointer_min, buffer_length):
        return

    def set_trigger(self, handle, enable, source, threshold, direction, delay):
        return

    def gen_signal(self):
        return
