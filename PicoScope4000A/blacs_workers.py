from json.decoder import FLAGS

from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from user_devices.logger_config import logger
import h5py, json, time, queue, math
import ctypes
import numpy as np
import matplotlib.pyplot as plt
import threading
from zprocess import rich_print
import labscript_utils.properties

from picosdk.ps4000a import ps4000a as psa
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
from picosdk.constants import PICO_STATUS
from labscript_utils.ls_zprocess import Context

import zmq
import datetime


BLUE = '#66D9EF'
RED = '#FF0000'
GREEN = '#008000'

class PicoScope4000A(object):
    def __init__(self, serial_number):
        self.chandle = ctypes.c_int16()
        self.status = {}

        # Data Acquisition
        self.fetching_thread = None
        self.stop_sampling_event = threading.Event() # indicates the moment the fetching stopped, and the writing can begin
        self.stop_sampling_event.clear()

        # Triggering
        self.trigger_event = threading.Event()
        self.trigger_event.clear()

        self.buffers = {} # in adc
        self.complete_buffers = {} # in adc

        # Preparing for data acquisition
        self.total_samples = None
        self.next_sample = None
        self.auto_stop_outer = None
        self.was_called_back = None
        self.triggered_at = None

        # Open Unit
        self.open_unit(serial_number)

        # Unit's constants
        self.max_adc = ctypes.c_int32()
        self.status["maximumValue"] = psa.ps4000aMaximumValue(self.chandle, ctypes.byref(self.max_adc))
        self.channel_ranges = {} # channel voltage range in serial number per channel
        self.enabled_channels = [0,0,0,0,0,0,0,0] # store channels enable status
        self.actual_sample_interval = None


    def open_unit(self, serial_number):
        serial_number = serial_number.encode()
        self.status["openUnit"] = psa.ps4000aOpenUnit(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(self.status["openUnit"])
        print("[PicoScope] PicoScope connected, chandle:", self.chandle.value)

    def stop_sampling(self):
        self.status["stopUnit"] = psa.ps4000aStop(self.chandle)
        assert_pico_ok(self.status["stopUnit"])

    def close_unit(self):
        self.status["closeUnit"] = psa.ps4000aCloseUnit(self.chandle)
        assert_pico_ok(self.status["closeUnit"])

    def run_stream(self,
                   sample_interval_ns: int,
                   max_post_trigger_samples: int,
                   downsample_ratio: int = 1,  # default no downsampling
                   downsample_ratio_mode: str = 'none',
                   ):

        # allocate and register working buffers
        self.total_samples = max_post_trigger_samples
        buffer_size = 1000
        for ch, enabled in enumerate(self.enabled_channels):
            if enabled == 1:
                self.buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16) # in adc
                self.set_data_buffer(channel=ch,
                                     buffer=self.buffers[ch],
                                     bufferLth=buffer_size,
                                     mode=downsample_ratio_mode)
        # allocate complete buffers
        for ch, enabled in enumerate(self.enabled_channels):
            if enabled == 1:
                self.complete_buffers[ch] = np.zeros(shape=self.total_samples, dtype=np.int16) # in adc

        # parameters
        max_pre_trigger_samples = 0
        stop_auto = 0 # do not stop after all samples fetched
        c_sample_interval = ctypes.c_int32(sample_interval_ns)
        time_units = psa.PS4000A_TIME_UNITS['PS4000A_NS']  # Nanoseconds
        c_downsample_ratio_mode = _get_ratio_mode(downsample_ratio_mode)
        overview_buffer_size = buffer_size

        self.status["runStreaming"] = psa.ps4000aRunStreaming(self.chandle,
                                                             ctypes.byref(c_sample_interval),
                                                             time_units,
                                                             max_pre_trigger_samples,
                                                             max_post_trigger_samples,
                                                             stop_auto,
                                                             downsample_ratio,
                                                             c_downsample_ratio_mode,
                                                             overview_buffer_size)

        assert_pico_ok(self.status["runStreaming"])

        self.actual_sample_interval = c_sample_interval.value
        print(f"[INFO] sample interval: {sample_interval_ns}ns -> {self.actual_sample_interval}ns")

        # callback
        self.next_sample = 0
        self.auto_stop_outer = False
        self.was_called_back = False

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
            self.was_called_back = True

            if triggered != 0 and not self.trigger_event.is_set():
                self.trigger_event.set()
                self.triggered_at = triggerAt
                print(f"\n [INFO] Was Triggered at {self.triggered_at}")

            if self.trigger_event.is_set():
                dest_end = self.next_sample + noOfSamples
                source_end = startIndex + noOfSamples

                if dest_end > self.total_samples:
                    complete_overflow = dest_end - self.total_samples
                    dest_end = self.total_samples
                    source_end -= complete_overflow
                    print(f"[WARNING] Truncating buffer by {complete_overflow} samples to fit total_samples={self.total_samples} \n")

                for ch_, enabled_ in enumerate(self.enabled_channels):
                    if enabled_ == 1:
                        self.complete_buffers[ch_][self.next_sample:dest_end] = self.buffers[ch_][startIndex:source_end]

                self.next_sample += noOfSamples

                if autoStop:
                    self.auto_stop_outer = True


        c_func_ptr = psa.StreamingReadyType(streaming_callback)

        def fetching():
            while self.next_sample < self.total_samples and not self.auto_stop_outer and not self.stop_sampling_event.is_set():
                self.was_called_back = False
                self.status["getStreamingLastestValues"] = psa.ps4000aGetStreamingLatestValues(self.chandle, c_func_ptr, None)
                if not self.was_called_back:
                    time.sleep(0.001)

            self.stop_sampling_event.set() # now the writing can start
            print("[WARNING] Fetching is finished ... No more data is being collected")
            self.stop_sampling()

        # start fetching data in different thread to not block buffered mode
        self.fetching_thread = threading.Thread(target=fetching)
        self.fetching_thread.start()
        print("[INFO] Waiting for trigger ...")

    def set_data_buffer(self, channel: int, buffer, bufferLth: int, segmentIndex: int=0, mode: str='none'):
        """
        You need to allocate the buffer before calling this function.
        If only one buffer needed --> downsampling mode is not 'aggregate'

        :param channel: the channel for which you want to set the buffers
        :param buffer: buffer to receive the data value. Each value is ADC count scaled to vRange.
        :param bufferLth: the size of the buffer array.
        :param segmentIndex: the number of the memory segment to be retrieved. (=0, streaming)
        :param mode: downsampling mode [0:PS4000A_RATIO_MODE_NONE, 2: PS4000A_RATIO_MODE_DECIMATE, 4: PS4000A_RATIO_MODE_AVERAGE]
        :return:
        """
        # parameters
        ptr = buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        c_mode = _get_ratio_mode(mode)
        self.status[f"setDataBuffer_{channel}"] = psa.ps4000aSetDataBuffer(self.chandle, channel, ptr, bufferLth,
                                                                          segmentIndex, c_mode)
        assert_pico_ok(self.status[f"setDataBuffer_{channel}"])


    def adc2mv_1d(self, data_adc, ch):
        channel_range = self.channel_ranges[ch]
        data_mv = adc2mV(data_adc, channel_range, self.max_adc)
        return data_mv

    def set_simple_edge_trigger(self,
                                source: str,
                                threshold: float,  # in milliVolts
                                direction: str,
                                delay: int,  # in sample periods
                                auto_trigger_ms: int = 0,
                                enable: int = 1,  # 0 = disable
                                ):
        # convert mV -> ADC
        ch_num = _get_channel_number(source)
        ch_range_v = self.channel_ranges[ch_num]
        threshold_adc = mV2adc(threshold, ch_range_v, self.max_adc)
        int_direction = _get_direction(direction)

        self.status["setSimpleTrigger"] = psa.ps4000aSetSimpleTrigger(self.chandle,
                                                                     enable,
                                                                     ch_num,
                                                                     threshold_adc,
                                                                     int_direction,
                                                                     delay,
                                                                     auto_trigger_ms)
        assert_pico_ok(self.status["setSimpleTrigger"])

        # print(f"[DEBUG] the simple level trigger is set. status: {self.status["setSimpleTrigger"]}")

    def set_channel(self, channel: str, coupling_type: str, channel_range_v: float, enabled=1, analogue_offset=0.0):
        ch_num = _get_channel_number(channel)
        int_coupling = _get_coupling(coupling_type)
        int_range = _get_range(channel_range_v)
        max_v, min_v = self._get_analogue_offset_range(int_range, int_coupling)

        if not (min_v <= analogue_offset <= max_v):
            raise LabscriptError(f"Offset {analogue_offset} out of bounds [{min_v}, {max_v}]")

        c_analogue_offset = ctypes.c_float(analogue_offset)

        self.status[f"setCh{channel}"] = psa.ps4000aSetChannel(self.chandle,
                                                              ch_num,
                                                              enabled,
                                                              int_coupling,
                                                              int_range,
                                                              c_analogue_offset)

        assert_pico_ok(self.status[f"setCh{channel}"])

        # save channel attributes: ranges, enable/disable
        self.channel_ranges[ch_num] = int_range
        if enabled == 1:
            self.enabled_channels[ch_num] = 1



    def _get_analogue_offset_range(self, ch_range: int, coupling: int):
        """ Get the maximal and minimal analogue offset (dc) for the given range on channel.
            ±250 mV (10 mV to 500 mV ranges)
            ±2.5 V (1 V to 5 V ranges)
            ±25 V (10 V to 50 V ranges)
        :param ch_range:
        :param coupling:
        :return: maximal and minimal analogue offset
        """
        max_v = ctypes.c_float()
        min_v = ctypes.c_float()
        self.status["getAnalogueOffset"] = psa.ps4000aGetAnalogueOffset(self.chandle, ch_range, coupling,
                                                                       ctypes.byref(max_v), ctypes.byref(min_v))
        assert_pico_ok(self.status["getAnalogueOffset"])
        return max_v.value, min_v.value

    #######################################################################
    ######################### Signal generator ############################
    #######################################################################
    def gen_signal(self,
                   offset_voltage: int = 1000000,  # in µV
                   pk2pk: int = 2000000,  # in µV
                   wave_type: str = 'square',
                   start_frequency: float = 10000,  # in Hz
                   stop_frequency: float = 10000,  # in Hz (same = no sweep)
                   increment: float = 0,  # Hz step in sweep
                   dwell_time: float = 1,  # seconds per step
                   sweep_type: int = 0,
                   operation: int = 0,
                   shots: int = 0,
                   sweeps: int = 0,
                   trigger_type: str = 'rising',
                   trigger_source: str = 'soft_trig',
                   ext_in_threshold: int = 0  # ADC counts
                   ):

        """
        Call this function before starting data acquisition.
         This function sets up the signal generator to produce a signal from a list of built-in waveforms.
         If different start and stop frequencies are specified, the oscilloscope will sweep either up, down or up and down.

        :param offset_voltage: in microvolts
        :param pk2pk: peak-to-peak voltage in microvolts (maxRange = +/-2V)
        :param wave_type: PS4000A_SINE, PS4000A_SQUARE, PS4000A_TRIANGLE, PS4000A_RAMP_UP, PS4000A_RAMP_DOWN, PS4000A_SINC, PS4000A_GAUSSIAN, PS4000A_HALF_SINE, PS4000A_DC_VOLTAGE
        :param start_frequency: the frequency in hertz at which the signal generator should begin
        :param stop_frequency: the frequency in hertz at which the sweep should reverse direction or return to the start frequency (no sweep: startFrequency=stopFrequency)
        :param increment:  Frequency increment per step in Hz.
        :param dwell_time: Time per frequency step in sweep mode (s).
        :param sweep_type: PS4000A_UP, PS4000A_DOWN, PS4000A_UPDOWN
        :param operation:
        :param shots: Number of waveform cycles.
        :param sweeps: Number of sweeps.
        :param trigger_type:
        :param trigger_source:
        :param ext_in_threshold: Threshold level for external trigger (in ADC counts).
        :return:
        """
        wavetype_int = _get_wave_type(wave_type)
        triggersource_int = _get_siggen_trigger_source(trigger_source)
        triggertype_int = _get_siggen_trigger_type(trigger_type)

        self.status["SetSigGenBuiltIn"] = psa.ps4000aSetSigGenBuiltIn(self.chandle, offset_voltage, pk2pk, wavetype_int,
                                                                     start_frequency, stop_frequency,
                                                                     increment, dwell_time, sweep_type, operation, shots,
                                                                     sweeps, triggertype_int,
                                                                     triggersource_int, ext_in_threshold)
        assert_pico_ok(self.status["SetSigGenBuiltIn"])

    def siggen_software_control(self, state):
        """
        To use in manual mode.
        This function causes a trigger event, or starts and stops gating. It is used when the signal generator is set to SIGGEN_SOFT_TRIG
        :param state: sets the trigger gate high or low when the trigger type is set to either SIGGEN_GATE_HIGH or SIGGEN_GATE_LOW. Ignored for other trigger types
        :return:
        """
        self.status["sigGenSoftwareControl"] = psa.ps4000aSigGenSoftwareControl(self.chandle, state)
        print("sigGenSoftwareControl executed.")

    #######################################################################
    ############################# Triggers ################################
    #######################################################################

    def set_trigger_conditions(self, sources, info: str):
        """
         conditions: list of sources (int)
         info: str
         """
        ps_conditions = []
        for source in sources:
            source_int = _get_channel_number(source)
            state = psa.PS4000A_TRIGGER_STATE["PS4000A_TRUE"]
            ps_conditions.append(psa.PS4000A_CONDITION(source_int, state))
        n_conditions = len(ps_conditions)

        # create ctypes array
        cond_array = (psa.PS4000A_CONDITION * n_conditions)(*ps_conditions)
        info_int = _get_info(info)

        self.status["setTriggerChannelConditions"] = psa.ps4000aSetTriggerChannelConditions(
            self.chandle,
            ctypes.byref(cond_array),
            n_conditions,
            info_int
        )
        assert_pico_ok(self.status["setTriggerChannelConditions"])

    def set_trigger_channel_directions(self, directions):
        ps_directions = []
        for direction in directions:
            source_int = _get_channel_number(direction["source"])
            direction_int = _get_direction(direction["direction"])
            ps_directions.append(psa.PS4000A_DIRECTION(source_int, direction_int))

        n_directions = len(ps_directions)
        dir_array = (psa.PS4000A_DIRECTION * n_directions)(*ps_directions)

        self.status["setTriggerChannelDirections"] = psa.ps4000aSetTriggerChannelDirections(
            self.chandle,
            ctypes.byref(dir_array),
            n_directions
        )
        assert_pico_ok(self.status["setTriggerChannelDirections"])

    def set_trigger_channel_properties(self, properties):
        ps_properties = []
        for prop in properties:
            ch_int = _get_channel_number(prop["source"])
            threshold_mode_int = _get_threshold_mode(prop["threshold_mode"])
            ch_range = self.channel_ranges[ch_int]
            threshold_upper_adc = mV2adc(prop["threshold_upper"], ch_range, self.max_adc)
            threshold_lower_adc = mV2adc(prop["threshold_lower"], ch_range, self.max_adc)
            upper_hysteresis_adc = mV2adc(prop["upper_hysteresis"], ch_range, self.max_adc)
            lower_hysteresis_adc = mV2adc(prop["lower_hysteresis"], ch_range, self.max_adc)

            ps_properties.append(psa.PS4000A_TRIGGER_CHANNEL_PROPERTIES(
                threshold_upper_adc,
                upper_hysteresis_adc,
                threshold_lower_adc,
                lower_hysteresis_adc,
                ch_int,
                threshold_mode_int
            ))

        n_properties = len(ps_properties)
        prop_array = (psa.PS4000A_TRIGGER_CHANNEL_PROPERTIES * n_properties)(*ps_properties)

        auto_trigger_ms = 0  # the time in milliseconds, If 0, waits indefinitely for a trigger

        self.status["setTriggerChannelProperties"] = psa.ps4000aSetTriggerChannelProperties(
            self.chandle,
            ctypes.byref(prop_array),
            n_properties,
            0,
            auto_trigger_ms
        )
        assert_pico_ok(self.status["setTriggerChannelProperties"])

    def set_trigger_delay(self, delay):
        """delay in sample periods"""
        self.status["setTriggerDelay"] = psa.ps4000aSetTriggerDelay(self.chandle, delay)
        assert_pico_ok(self.status["setTriggerDelay"])


class PicoScope4000(object):
    def __init__(self, serial_number):
        self.chandle = ctypes.c_int16()
        self.status = {}

        # Data Acquisition
        self.fetching_thread = None
        self.stop_sampling_event = threading.Event() # indicates the moment the fetching stopped, and the writing can begin
        self.stop_sampling_event.clear()

        # Triggering
        self.trigger_event = threading.Event()
        self.trigger_event.clear()

        self.buffers = {} # in adc
        self.complete_buffers = {} # in adc

        # Preparing for data acquisition
        self.total_samples = None
        self.next_sample = None
        self.auto_stop_outer = None
        self.was_called_back = None
        self.triggered_at = None

        # Open Unit
        self.open_unit(serial_number)

        # Unit's constants
        self.max_adc = ctypes.c_int32()
        self.status["maximumValue"] = ps.ps4000MaximumValue(self.chandle, ctypes.byref(self.max_adc))
        self.channel_ranges = {} # channel voltage range in serial number per channel
        self.enabled_channels = [0,0,0,0,0,0,0,0] # store channels enable status
        self.actual_sample_interval = None


    def open_unit(self, serial_number):
        serial_number = serial_number.encode()
        self.status["openUnit"] = ps.ps4000OpenUnitEx(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(self.status["openUnit"])
        print("[PicoScope] PicoScope connected, chandle:", self.chandle.value)

    def stop_sampling(self):
        self.status["stopUnit"] = ps.ps4000Stop(self.chandle)
        assert_pico_ok(self.status["stopUnit"])

    def close_unit(self):
        self.status["closeUnit"] = ps.ps4000CloseUnit(self.chandle)
        assert_pico_ok(self.status["closeUnit"])

    def run_stream(self,
                   sample_interval_ns: int,
                   max_post_trigger_samples: int,
                   downsample_ratio: int = 1,  # default no downsampling
                   downsample_ratio_mode: str = 'none',
                   ):

        # allocate and register working buffers
        self.total_samples = max_post_trigger_samples
        buffer_size = 1000
        for ch, enabled in enumerate(self.enabled_channels):
            if enabled == 1:
                self.buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16) # in adc
                self.set_data_buffer(channel=ch,
                                     buffer=self.buffers[ch],
                                     bufferLth=buffer_size,
                                     mode=downsample_ratio_mode)
        # allocate complete buffers
        for ch, enabled in enumerate(self.enabled_channels):
            if enabled == 1:
                self.complete_buffers[ch] = np.zeros(shape=self.total_samples, dtype=np.int16) # in adc

        # parameters
        max_pre_trigger_samples = 0
        stop_auto = 0 # do not stop after all samples fetched
        c_sample_interval = ctypes.c_int32(sample_interval_ns)
        time_units = ps.PS4000_TIME_UNITS['PS4000_NS']  # Nanoseconds
        c_downsample_ratio_mode = _get_ratio_mode(downsample_ratio_mode)
        overview_buffer_size = buffer_size

        self.status["runStreaming"] = ps.ps4000RunStreaming(self.chandle,
                                                             ctypes.byref(c_sample_interval),
                                                             time_units,
                                                             max_pre_trigger_samples,
                                                             max_post_trigger_samples,
                                                             stop_auto,
                                                             downsample_ratio,
                                                             c_downsample_ratio_mode,
                                                             overview_buffer_size)

        assert_pico_ok(self.status["runStreaming"])

        self.actual_sample_interval = c_sample_interval.value
        print(f"[INFO] sample interval: {sample_interval_ns}ns -> {self.actual_sample_interval}ns")

        # callback
        self.next_sample = 0
        self.auto_stop_outer = False
        self.was_called_back = False
        self.was_triggered = False

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
            self.was_called_back = True

            if triggered != 0 and not self.trigger_event.is_set():
                self.trigger_event.set()
                self.triggered_at = triggerAt
                print(f"\n [INFO] Was Triggered at {self.triggered_at}")

            if self.trigger_event.is_set():
                dest_end = self.next_sample + noOfSamples
                source_end = startIndex + noOfSamples

                if dest_end > self.total_samples:
                    complete_overflow = dest_end - self.total_samples
                    dest_end = self.total_samples
                    source_end -= complete_overflow
                    print(f"[WARNING] Truncating buffer by {complete_overflow} samples to fit total_samples={self.total_samples} \n")

                for ch_, enabled_ in enumerate(self.enabled_channels):
                    if enabled_ == 1:
                        self.complete_buffers[ch_][self.next_sample:dest_end] = self.buffers[ch_][startIndex:source_end]

                self.next_sample += noOfSamples

                if autoStop:
                    self.auto_stop_outer = True


        c_func_ptr = ps.StreamingReadyType(streaming_callback)

        def fetching():
            while self.next_sample < self.total_samples and not self.auto_stop_outer and not self.stop_sampling_event.is_set():
                self.was_called_back = False
                self.status["getStreamingLastestValues"] = ps.ps4000GetStreamingLatestValues(self.chandle, c_func_ptr, None)
                if not self.was_called_back:
                    time.sleep(0.001)

            self.stop_sampling_event.set() # now the writing can start
            print("[WARNING] Fetching is finished ... No more data is being collected")
            self.stop_sampling()

        # start fetching data in different thread to not block buffered mode
        self.fetching_thread = threading.Thread(target=fetching)
        self.fetching_thread.start()
        print("[INFO] Waiting for trigger ...")

    def set_data_buffer(self, channel: int, buffer, bufferLth: int, segmentIndex: int=0, mode: str='none'):
        """
        You need to allocate the buffer before calling this function.
        If only one buffer needed --> downsampling mode is not 'aggregate'

        :param channel: the channel for which you want to set the buffers
        :param buffer: buffer to receive the data value. Each value is ADC count scaled to vRange.
        :param bufferLth: the size of the buffer array.
        :param segmentIndex: the number of the memory segment to be retrieved. (=0, streaming)
        :param mode: downsampling mode [0:PS4000A_RATIO_MODE_NONE, 2: PS4000A_RATIO_MODE_DECIMATE, 4: PS4000A_RATIO_MODE_AVERAGE]
        :return:
        """
        # parameters
        ptr = buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        c_mode = _get_ratio_mode(mode)
        self.status[f"setDataBuffer_{channel}"] = ps.ps4000SetDataBuffer(self.chandle, channel, ptr, bufferLth,
                                                                          segmentIndex, c_mode)
        assert_pico_ok(self.status[f"setDataBuffer_{channel}"])


    def adc2mv_1d(self, data_adc, ch):
        channel_range = self.channel_ranges[ch]
        data_mv = adc2mV(data_adc, channel_range, self.max_adc)
        return data_mv

    def set_simple_edge_trigger(self,
                                source: str,
                                threshold: float,  # in milliVolts
                                direction: str,
                                delay: int,  # in sample periods
                                autoTrigger_ms: int = 0,
                                enable: int = 1,  # 0 = disable
                                ):
        # convert mV -> ADC
        ch_num = _get_channel_number(source)
        ch_range_v = self.channel_ranges[ch_num]
        threshold_adc = mV2adc(threshold, ch_range_v, self.max_adc)
        int_direction = _get_direction(direction)

        self.status["setSimpleTrigger"] = ps.ps4000SetSimpleTrigger(self.chandle,
                                                                     enable,
                                                                     ch_num,
                                                                     threshold_adc,
                                                                     int_direction,
                                                                     delay,
                                                                     autoTrigger_ms)
        assert_pico_ok(self.status["setSimpleTrigger"])

        # print(f"[DEBUG] the simple level trigger is set. status: {self.status["setSimpleTrigger"]}")

    def set_channel(self, channel: str, coupling_type: str, channel_range_v: float, enabled=1, analogue_offset=0.0):
        ch_num = _get_channel_number(channel)
        int_coupling = _get_coupling(coupling_type)
        int_range = _get_range(channel_range_v)
        max_v, min_v = self._get_analogue_offset_range(int_range, int_coupling)

        if not (min_v <= analogue_offset <= max_v):
            raise LabscriptError(f"Offset {analogue_offset} out of bounds [{min_v}, {max_v}]")

        c_analogue_offset = ctypes.c_float(analogue_offset)

        self.status[f"setCh{channel}"] = ps.ps4000SetChannel(self.chandle,
                                                              ch_num,
                                                              enabled,
                                                              int_coupling,
                                                              int_range,
                                                              c_analogue_offset)

        assert_pico_ok(self.status[f"setCh{channel}"])

        # save channel attributes: ranges, enable/disable
        self.channel_ranges[ch_num] = int_range
        if enabled == 1:
            self.enabled_channels[ch_num] = 1



    def _get_analogue_offset_range(self, ch_range: int, coupling: int):
        """ Get the maximal and minimal analogue offset (dc) for the given range on channel.
            ±250 mV (10 mV to 500 mV ranges)
            ±2.5 V (1 V to 5 V ranges)
            ±25 V (10 V to 50 V ranges)
        :param ch_range:
        :param coupling:
        :return: maximal and minimal analogue offset
        """
        max_v = ctypes.c_float()
        min_v = ctypes.c_float()
        self.status["getAnalogueOffset"] = ps.ps4000GetAnalogueOffset(self.chandle, ch_range, coupling,
                                                                       ctypes.byref(max_v), ctypes.byref(min_v))
        assert_pico_ok(self.status["getAnalogueOffset"])
        return max_v.value, min_v.value

    def gen_signal(self,
                   offset_voltage: int = 1000000,  # in µV
                   pk2pk: int = 2000000,  # in µV
                   wave_type: str = 'square',
                   start_frequency: float = 10000,  # in Hz
                   stop_frequency: float = 10000,  # in Hz (same = no sweep)
                   increment: float = 0,  # Hz step in sweep
                   dwell_time: float = 1,  # seconds per step
                   sweep_type: int = 0,
                   operation: int = 0,
                   shots: int = 0,
                   sweeps: int = 0,
                   trigger_type: str = 'rising',
                   trigger_source: str = 'soft_trig',
                   ext_in_threshold: int = 0  # ADC counts
                   ):

        """
        Call this function before starting data acquisition.
         This function sets up the signal generator to produce a signal from a list of built-in waveforms.
         If different start and stop frequencies are specified, the oscilloscope will sweep either up, down or up and down.

        :param offset_voltage: in microvolts
        :param pk2pk: peak-to-peak voltage in microvolts (maxRange = +/-2V)
        :param wave_type: PS4000A_SINE, PS4000A_SQUARE, PS4000A_TRIANGLE, PS4000A_RAMP_UP, PS4000A_RAMP_DOWN, PS4000A_SINC, PS4000A_GAUSSIAN, PS4000A_HALF_SINE, PS4000A_DC_VOLTAGE
        :param start_frequency: the frequency in hertz at which the signal generator should begin
        :param stop_frequency: the frequency in hertz at which the sweep should reverse direction or return to the start frequency (no sweep: startFrequency=stopFrequency)
        :param increment:  Frequency increment per step in Hz.
        :param dwell_time: Time per frequency step in sweep mode (s).
        :param sweep_type: PS4000A_UP, PS4000A_DOWN, PS4000A_UPDOWN
        :param operation:
        :param shots: Number of waveform cycles.
        :param sweeps: Number of sweeps.
        :param trigger_type:
        :param trigger_source:
        :param ext_in_threshold: Threshold level for external trigger (in ADC counts).
        :return:
        """
        wavetype_int = _get_wave_type(wave_type)
        triggersource_int = _get_siggen_trigger_source(trigger_source)
        triggertype_int = _get_siggen_trigger_type(trigger_type)

        self.status["SetSigGenBuiltIn"] = ps.ps4000SetSigGenBuiltIn(self.chandle, offset_voltage, pk2pk, wavetype_int,
                                                                     start_frequency, stop_frequency,
                                                                     increment, dwell_time, sweep_type, operation,
                                                                     shots,
                                                                     sweeps, triggertype_int,
                                                                     triggersource_int, ext_in_threshold)
        assert_pico_ok(self.status["SetSigGenBuiltIn"])

    def siggen_software_control(self, state):
        """
        To use in manual mode.
        This function causes a trigger event, or starts and stops gating. It is used when the signal generator is set to SIGGEN_SOFT_TRIG
        :param state: sets the trigger gate high or low when the trigger type is set to either SIGGEN_GATE_HIGH or SIGGEN_GATE_LOW. Ignored for other trigger types
        :return:
        """
        self.status["sigGenSoftwareControl"] = ps.ps4000SigGenSoftwareControl(self.chandle, state)


class PicoScopeWorker(Worker):
    interface_class = None

    def init(self):
        self.interface_class = PicoScope4000A if self.is_4000a else PicoScope4000
        self.pico = self.interface_class(self.serial_number)

        self.h5_file = None
        self.device_name = None

        self.stop_writing_flag = False

        self.image_socket = Context().socket(zmq.REQ)
        self.image_socket.connect(
            f'tcp://{self.parent_host}:{self.image_receiver_port}'
        )


    def shutdown(self):
        # stop fetching thread
        if hasattr(self.pico, "stop_sampling_event"):
            self.pico.stop_sampling_event.set()
        if getattr(self.pico, "fetching_thread") is not None:
            self.pico.fetching_thread.join()

        # stop sampling and close unit
        self.pico.stop_sampling()
        self.pico.close_unit()

        # stop writing
        self.stop_writing_flag = True

    def program_manual(self, front_panel_values):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5_file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as f:
            # Get the attributes
            properties = labscript_utils.properties.get(
                f, self.device_name, 'device_properties'
            )

        simple_trigger = properties["simple_trigger_config"]
        trigger_conditions_config = properties["trigger_conditions_config"]
        trigger_directions_config = properties["trigger_directions_config"]
        trigger_properties_config = properties["trigger_properties_config"]
        trigger_delay_config = properties["trigger_delay_config"]
        stream_config = properties["stream_config"]

        # Configure channels
        for ch in self.channels_configs:
            self.pico.set_channel(ch["channel"], ch["coupling"], ch["range"], ch["enabled"], ch["analog_offset"])

        # Configure trigger
        if simple_trigger:
            self.pico.set_simple_edge_trigger(
                                              simple_trigger["source"],
                                              simple_trigger["threshold"] * 1e3, # in millivolts
                                              simple_trigger["direction"],
                                              simple_trigger["delay"],
                                              int(simple_trigger["auto_trigger"] * 1e3), # in milliseconds
            )

        # Configure advanced trigger if given
        if len(trigger_conditions_config) > 0:
            for cond in trigger_conditions_config:
                self.pico.set_trigger_conditions(cond["sources"], cond["info"])

        if len(trigger_directions_config) > 0:
            self.pico.set_trigger_channel_directions(trigger_directions_config)

        if len(trigger_properties_config) > 0:
            self.pico.set_trigger_channel_properties(trigger_properties_config)

        if trigger_delay_config is not None and "delay" in trigger_delay_config:
            self.pico.set_trigger_delay(trigger_delay_config["delay"])

        # Configure streaming mode and start streaming
        if stream_config:
            self.pico.run_stream(
                stream_config["sample_interval"],
                stream_config["no_post_trigger_samples"],
                stream_config["downsample_ratio"],
                stream_config["downsample_ratio_mode"],
            )

        return {}

    def transition_to_manual(self):
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        # Save the data from complete buffers into hdf5 file
        # wait until all samples are collected, blocking the shot exit

        self.pico.stop_sampling_event.wait()

        channels = sorted(self.pico.complete_buffers.keys())

        # Prepare data
        data_list = []
        for ch in channels:
            buf_adc = self.pico.complete_buffers[ch]
            buf_mv = self.pico.adc2mv_1d(buf_adc.astype(np.int32), ch)
            data_list.append(buf_mv)

        data_array = np.column_stack(data_list) # combine horizontally

        self._send_traces_to_parent(data_array)

        # Write data
        with h5py.File(self.h5_file, "r+") as f:
            properties = labscript_utils.properties.get(
                f, self.device_name, 'device_properties'
            )
            siggen_config = properties["siggen_config"]

            group = f.require_group('/data/traces')

            # Prepare a unique dataset name
            base_name = self.device_name
            dataset_name = base_name
            counter = 1
            while dataset_name in group:
                dataset_name = f"{base_name}_{counter}"
                counter += 1

            ds = group.create_dataset(dataset_name, data=data_array, dtype=np.float32)
            ds.attrs["channels"] = np.array(channels, dtype=int)
            ds.attrs["channel_names"] = np.array(self.channel_names, 'S64')
            ds.attrs["trigger_at"] = int(self.pico.triggered_at)
            ds.attrs["sample_interval"] = self.pico.actual_sample_interval
            ds.attrs["total_samples"] = self.pico.total_samples

        print(f"[INFO] Saved {data_array.shape[0]} samples × {data_array.shape[1]} channels")

        # configure the signal generator to use in manual mode
        if len(siggen_config) > 0:
            self.pico.gen_signal( int(siggen_config["offset_voltage"] * 1e6),
                    int(siggen_config["pk2pk"] * 1e6),
                    siggen_config["wave_type"],
                    siggen_config["start_frequency"],
                    siggen_config["stop_frequency"],
                    siggen_config["increment"],
                    siggen_config["dwell_time"],
                    siggen_config["sweep_type"],
                    siggen_config["operation"],
                    siggen_config["shots"],
                    siggen_config["sweeps"],
                    siggen_config["trigger_type"],
                    siggen_config["trigger_source"],
                    siggen_config["ext_in_threshold"])

        # clear all buffered events
        self.pico.trigger_event.clear()
        self.pico.stop_sampling_event.clear()

        return True

    def _send_traces_to_parent(self, traces):
        """Send the traces to the GUI to display. This will block if the parent process
        is lagging behind, in order to avoid a backlog."""
        metadata = dict(dtype=str(traces.dtype), shape=traces.shape,
                        sample_interval=self.pico.actual_sample_interval, triggered_at=self.pico.triggered_at)
        self.image_socket.send_json(metadata, zmq.SNDMORE)
        self.image_socket.send(traces, copy=False)
        response = self.image_socket.recv()
        assert response == b'ok', response

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def siggen_software_trigger(self):
        self.pico.siggen_software_control(0)

    def start_sampling(self):
        print("[Warning] Sampling in manual mode is Not supported yet.")


#######################################################################
####################### Helpers #######################################
#######################################################################
# Map the readable values into PicoScope constants
def _get_channel_number(channel_name) -> int:
    channel_name = _decode_if_bytes(channel_name)

    if channel_name.endswith('external'):
        return 8
    if channel_name.endswith('aux'):
        return 9
    if channel_name.lower().endswith('pulse_width'):
        return 0x10000000

    last_ch = channel_name[-1].upper()
    if last_ch.isdigit() and int(last_ch) in range(8):
        return int(last_ch)

    letter_map = {c: i for i, c in enumerate("ABCDEFGH")}
    if last_ch in letter_map:
        return letter_map[last_ch]

    raise ValueError(
        f"Invalid channel name: {channel_name}. "
        f"Expected suffix A..H or 0..7 or 'external', 'aux', or 'width_source'."
    )

def _get_coupling(coupling: str) -> int:
    mapping = {"ac": 0, "dc": 1}
    if coupling not in mapping:
        raise ValueError(...)
    return mapping[coupling]


def _get_direction(direction: str) -> int:
    direction = _decode_if_bytes(direction).lower()
    direction_map = {
        "above": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_ABOVE"],
        "below": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_BELOW"],
        "rising": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING"],
        "falling": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_FALLING"],
        "rising_or_falling": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING_OR_FALLING"],
        "above_lower": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_ABOVE_LOWER"],
        "below_lower": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_BELOW_LOWER"],
        "rising_lower": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING_LOWER"],
        "falling_lower": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_FALLING_LOWER"],
        "inside": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_INSIDE"],
        "outside": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_OUTSIDE"],
        "enter": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_ENTER"],
        "exit": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_EXIT"],
        "enter_or_exit": psa.PS4000A_THRESHOLD_DIRECTION["PS4000A_ENTER_OR_EXIT"],
    }

    key = direction.lower()
    if key not in direction_map:
        raise ValueError(
            f"Invalid trigger direction: {direction}. "
            f"Expected one of {list(direction_map.keys())}"
        )
    return direction_map[key]

def _get_ratio_mode(ratio_mode: str) -> int:
    ratio_mode = _decode_if_bytes(ratio_mode).lower()
    mapping = {"none": 0, "aggregate": 1, "decimate": 2, "average": 4}
    if ratio_mode not in mapping:
        raise ValueError( f"Invalid ratio_mode: {ratio_mode}. Allowed values: 'none', 'aggregate', 'decimate', 'average'")
    return mapping[ratio_mode]

def _get_threshold_mode(threshold_mode: str) -> int:
    threshold_mode = _decode_if_bytes(threshold_mode).lower()
    mapping = {"level": 0, "window": 1}
    if threshold_mode not in mapping:
        raise ValueError(f"Invalid threshold mode: {threshold_mode}. Allowed: 'level', 'window'")
    return mapping[threshold_mode]

def _get_wave_type(wave_type: str) -> int:
    wave_type = _decode_if_bytes(wave_type).upper()
    wave_types = [
        'SINE',
        'SQUARE',
        'TRIANGLE',
        'RAMP_UP',
        'RAMP_DOWN',
        'SINC',
        'GAUSSIAN',
        'HALF_SINE',
        'DC_VOLTAGE',
        'WHITE_NOISE',
        'MAX_WAVE_TYPES',
    ]

    if wave_type not in wave_types:
        raise ValueError(f"Invalid wave_type: {wave_type}")
    return wave_types.index(wave_type)

def _get_range(ch_range: float) -> int:
    allowed_ranges = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]

    if ch_range < allowed_ranges[0] or ch_range > allowed_ranges[-1]:
        raise ValueError(
            f"Invalid 'range' value: {ch_range}. Expected {allowed_ranges[0]} <= range <= {allowed_ranges[-1]}.")

    for idx, r in enumerate(allowed_ranges):
        if r >= ch_range:
            return idx

    raise RuntimeError("Unexpected error: range value not matched.")

def _get_info(info: str) -> int:
    info = _decode_if_bytes(info).lower()
    mapping = {"clear": 1, "add": 2}
    if info not in mapping:
        raise ValueError(f"Invalid info: {info}")
    return mapping[info]

def _get_siggen_trigger_type(trig_type: str) -> int:
    trig_type = _decode_if_bytes(trig_type).lower()
    trig_types = ['rising', 'falling', 'gate_high', 'gate_low']
    for index, entry in enumerate(trig_types):
        if trig_type == entry:
            return index
    raise ValueError(f"Invalid trigger type: {trig_type}. Allowed values: {trig_types}")

def _get_siggen_trigger_source(source: str) -> int:
    source = _decode_if_bytes(source).lower()
    mapping = {'none': 0, 'scope_trig': 1, 'aus_in': 2, 'ext_in': 3, 'soft_trig': 4}
    if source not in mapping:
        raise ValueError(f"Invalid siggen trigger source: {source}")
    return mapping[source]

def _choose_buffer_size(max_samples: int, target_buffer_size: int = 500):
    """
    Choose optimal buffer size for total number of samples...

    :param max_samples: (pre + post trigger)
    :param target_buffer_size: desired buffer size
    :return: (buffer_size, no_buffers)
    """
    if max_samples <= target_buffer_size:
        return max_samples, 1

    buffer_size = target_buffer_size

    while max_samples % buffer_size != 0:
        buffer_size += 1

    no_buffers = max_samples // buffer_size
    return buffer_size, no_buffers

def _decode_if_bytes(arg):
    if isinstance(arg, (bytes, np.bytes_)):
        return arg.decode()
    return arg