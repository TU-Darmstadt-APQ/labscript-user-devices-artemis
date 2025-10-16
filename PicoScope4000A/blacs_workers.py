from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from user_devices.logger_config import logger
import h5py, json, time, queue, math
import ctypes
import numpy as np
import matplotlib.pyplot as plt
import threading
from zprocess import rich_print
from labscript_utils import properties

from picosdk.ps4000a import ps4000a as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
from picosdk.constants import PICO_STATUS

BLUE = '#66D9EF'

class PicoScopeWorker(Worker):
    def init(self):
        self.pico = PicoScope(self.serial_number)

        self.h5_file = None
        self.device_name = None

        self.stop_writing_flag = False

    def shutdown(self):
        # stop fetching thread
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

        # Configure channels
        for ch in self.channels_configs:
            self.pico.set_channel(ch["channel"], ch["coupling"], ch["range"], ch["enabled"], ch["analog_offset"])

        # Configure trigger
        if self.simple_trigger:
            self.pico.set_simple_edge_trigger(
                                              self.simple_trigger["source"],
                                              self.simple_trigger["threshold"],
                                              self.simple_trigger["direction"],
                                              self.simple_trigger["delay"],
                                              self.simple_trigger["autoTrigger_ms"],
            )

        # Configure streaming mode
        if self.active_mode == "stream" and self.stream_config:
            self.pico.run_stream(
                self.stream_config["sampleInterval"],
                self.stream_config["noPostTriggerSamples"],
                self.stream_config["downSampleRatio"],
                self.stream_config["downSampleRatioMode"],
            )
        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return

    def transition_to_manual(self):
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        # Save the data from complete buffers into hdf5 file
        # wait until all samples are collected, blocking the shot exit
        while not self.pico.stop_sampling_event.is_set() and not self.stop_writing_flag:
            time.sleep(0.01)

        channels = sorted(self.pico.complete_buffers.keys())

        # dimensions
        rows = self.pico.total_samples
        cols = sum(self.pico.enabled_channels)

        # Prepare data
        data_list = []
        for ch in channels:
            buf_adc = self.pico.complete_buffers[ch]
            buf_mv = self.pico.adc2mv_1d(buf_adc.astype(np.int32), ch)
            data_list.append(buf_mv)

        print(f"[DEBUG] final shape {len(data_list)}")
        data_array = np.column_stack(data_list) # combine horizontally

        # Write data
        with h5py.File(self.h5_file, "r+") as f:
            group = f[f"/devices/{self.device_name}"]
            if "StreamSamples" in group:
                del group["StreamSamples"]

            ds = group.create_dataset("StreamSamples", data=data_array, dtype=np.float32)
            ds.attrs["channels"] = np.array(channels, dtype=int)
            ds.attrs["trigger_at"] = int(self.pico.triggered_at)

        print(f"[INFO] Saved {data_array.shape[0]} samples × {data_array.shape[1]} channels")

        # # DEBUG
        # with h5py.File(self.h5_file, "r") as f:
        #     ds = f[f"/devices/{self.device_name}/StreamSamples"]
        #     # print("[DEBUG] Shape, Channels: ", ds.shape, ds.attrs["channels"])

        rich_print(f"---------- End transition to Manual: ----------", color=BLUE)
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def siggen_software_trigger(self):
        print("[Warning] SigGen is Not supported in the simplified version.")

class PicoScope(object):
    def __init__(self, serial_number):
        self.chandle = ctypes.c_int16()
        self.status = {}

        # Data Acquisition
        self.fetching_thread = None
        self.stop_sampling_event = threading.Event() # indicates the moment the fetching stoped, and the writing can begin
        self.stop_sampling_event.clear()

        self.buffers = {} # in adc
        self.complete_buffers = {} # in adc

        # Preparing for data acquisition
        self.total_samples = None
        self.next_sample = None
        self.auto_stop_outer = None
        self.was_called_back = None
        self.was_triggered = None
        self.triggered_at = None

        # Open Unit
        self.open_unit(serial_number)

        # Unit's constants
        self.max_adc = ctypes.c_int32()
        self.status["maximumValue"] = ps.ps4000aMaximumValue(self.chandle, ctypes.byref(self.max_adc))
        self.channel_ranges = {} # channel voltage range in serial number per channel
        self.enabled_channels = [0,0,0,0,0,0,0,0] # store channels enable status
        self.actual_sample_interval = None


    def open_unit(self, serial_number):
        serial_number = serial_number.encode()
        self.status["openUnit"] = ps.ps4000aOpenUnit(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(self.status["openUnit"])
        print("[PicoScope] PicoScope connected, chandle:", self.chandle.value)

    def stop_sampling(self):
        self.status["stopUnit"] = ps.ps4000aStop(self.chandle)
        assert_pico_ok(self.status["openUnit"])

    def close_unit(self):
        self.status["closeUnit"] = ps.ps4000aCloseUnit(self.chandle)
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
        time_units = ps.PS4000A_TIME_UNITS['PS4000A_NS']  # Nanoseconds
        c_downsample_ratio_mode = _get_ratio_mode(downsample_ratio_mode)
        overview_buffer_size = buffer_size

        self.status["runStreaming"] = ps.ps4000aRunStreaming(self.chandle,
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
            trigger_now = False
            if triggered != 0 and not self.was_triggered:
                self.was_triggered = True
                trigger_now = True
                self.triggered_at = triggerAt
                print(f"\n [INFO] Was Triggered at {self.triggered_at}")

            if self.was_triggered or trigger_now:
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
            while self.next_sample < self.total_samples and not self.auto_stop_outer:
                self.was_called_back = False
                self.status["getStreamingLastestValues"] = ps.ps4000aGetStreamingLatestValues(self.chandle, c_func_ptr, None)
                if not self.was_called_back:
                    time.sleep(0.01)

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
        self.status[f"setDataBuffer_{channel}"] = ps.ps4000aSetDataBuffer(self.chandle, channel, ptr, bufferLth,
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

        self.status["setSimpleTrigger"] = ps.ps4000aSetSimpleTrigger(self.chandle,
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

        self.status[f"setCh{channel}"] = ps.ps4000aSetChannel(self.chandle,
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
        self.status["getAnalogueOffset"] = ps.ps4000aGetAnalogueOffset(self.chandle, ch_range, coupling,
                                                                       ctypes.byref(max_v), ctypes.byref(min_v))
        assert_pico_ok(self.status["getAnalogueOffset"])
        return max_v.value, min_v.value


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
        "above": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_ABOVE"],
        "below": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_BELOW"],
        "rising": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING"],
        "falling": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_FALLING"],
        "rising_or_falling": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING_OR_FALLING"],
        "above_lower": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_ABOVE_LOWER"],
        "below_lower": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_BELOW_LOWER"],
        "rising_lower": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_RISING_LOWER"],
        "falling_lower": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_FALLING_LOWER"],
        "inside": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_INSIDE"],
        "outside": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_OUTSIDE"],
        "enter": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_ENTER"],
        "exit": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_EXIT"],
        "enter_or_exit": ps.PS4000A_THRESHOLD_DIRECTION["PS4000A_ENTER_OR_EXIT"],
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