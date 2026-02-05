from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from user_devices.logger_config import logger
import h5py, json, time, queue, math
import ctypes
import numpy as np
import threading
from enum import Enum
from zprocess import rich_print
import labscript_utils.properties

from picosdk.ps4000a import ps4000a as psa
from picosdk.ps4000 import ps4000 as ps
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc, mV2adcpl1000
from picosdk.constants import PICO_STATUS
from labscript_utils.ls_zprocess import Context

import zmq
import datetime

RATIO_MODES = {"none": 0, "aggregate": 1, "decimate": 2, "average": 4}
THRESHOLD_MODES = {"level": 0, "window": 1}
WAVE_TYPES = {
    'sine': 0,
    'square': 1,
    'triangle': 2,
    'ramp_up': 3,
    'ramp_down': 4,
    'sinc': 5,
    'gaussian': 6,
    'half_sine': 7,
    'dc_voltage': 8,
    'white_noise': 9,
    'max_wave_types': 10,
}
RANGES = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200] # RANGES.index(range)
INFO = {"clear": 1, "add": 2}
TRIGGER_TYPES = {'rising':0, 'falling':1, 'gate_high':2, 'gate_low':3}
SIGGEN_TRIGGER_SOURCES =  {'none': 0, 'scope_trig': 1, 'aus_in': 2, 'ext_in': 3, 'soft_trig': 4}
DIRECTIONS = {
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

COUPLING = {"ac": 0, "dc": 1}
ENABLED = {True: 1, False: 0}

CONNECTIONS = {
    "channel_A": 0,
    "channel_B": 1,
    "channel_C": 2,
    "channel_D": 3,
    "channel_E": 4,
    "channel_F": 5,
    "channel_G": 6,
    "channel_H": 7,
}

BUFFER_SIZE = 250
SEGMENT_INDEX = 0

BLUE = '#66D9EF'
RED = '#FF0000'
GREEN = '#008000'
YELLOW = '#FFFF00'

class AcqMode(Enum):
    STREAM = "stream"
    BLOCK = "block"


def _channel_overflowed(overflow_mask: int, ch_idx: int) -> bool:
    return bool(overflow_mask & (1 << ch_idx))


class PicoScope4000A(object):
    def __init__(self, serial_number):
        self.chandle = ctypes.c_int16()

        # Triggering
        self.trigger_event = threading.Event()
        self.auto_stop_outer = threading.Event()

        # Buffers
        self.buffers = {} # in adc
        self.complete_buffers = {} # in adc

        # Open Unit
        self.open_unit(serial_number)

        # Unit's constants
        self.max_adc = ctypes.c_int32()
        status = psa.ps4000aMaximumValue(self.chandle, ctypes.byref(self.max_adc))
        assert_pico_ok(status)

        self.actual_sample_interval = None
        self.actual_number_of_samples = None
        self.overvoltage = ctypes.c_int16(0)
        self.total_samples = None
        self.next_sample_idx = 0
        self.triggered_at = None
        self.was_called_back = False
        self.channel_ranges = {} # ch_idx<int>: range_idx<int>
        self.enabled_channels = {} # ch_idx<int>: enabled<bool>

        self.fetching_thread = threading.Thread()
        self.data_ready_event = threading.Event()


    def open_unit(self, serial_number):
        serial_number = serial_number.encode()
        status = psa.ps4000aOpenUnit(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(status)
        if status == PICO_STATUS['PICO_OK']:
            print("PicoScope connected ! HANDLE = {}".format(self.chandle))

    def close_unit(self):
        status = psa.ps4000aCloseUnit(self.chandle)
        assert_pico_ok(status)

    def stop_sampling(self):
        """Call even if autoStop = 1"""
        status = psa.ps4000aStop(self.chandle)
        assert_pico_ok(status)
        print("[DEBUG] STOP SAMPLING !!!")

    def register_buffer(self, ch_idx:int, buffer, down_sampling_mode:str, buffer_lth):
        ptr = buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        c_mode = RATIO_MODES[down_sampling_mode.lower()]

        status = psa.ps4000aSetDataBuffer(self.chandle, ch_idx, ptr, buffer_lth, SEGMENT_INDEX, c_mode)
        assert_pico_ok(status)

    def setup_buffers(self, total_samples:int, down_sampling_mode:str, acq_mode:AcqMode, working_buffer_size:int=None):
        """Depending on sampling mode (stream | block) we register different buffers.
        For streaming there are two types of fix-sized buffers: working and complete.
        Working buffers are registered and picoscope will fill them and callback, in which we copy data from
        working buffers to complete and release working buffers to picoscope back to be filled with new data until complete buffers are full.

        For blocking there is only complete buffers, which will be registered. The whole chunk of required data will be stored
        directly in complete buffers without copying them. The buffer size is boundared by picoscope specification, up to 256 MS shared between active channels.
        Teh actual internal buffer size upper limit can be lower, since the scope allocates a certain amount of memory for internal
        overheads and this may vary depending on the number of segments,  number of channels enabled, and the timebase chosen.
        """
        if acq_mode == "stream":
            for ch_idx, en in self.enabled_channels.items():
                if en:
                    self.buffers[ch_idx] = np.zeros(shape=working_buffer_size, dtype=np.int16)  # in adc
                    self.register_buffer(ch_idx=ch_idx, buffer=self.buffers[ch_idx], down_sampling_mode=down_sampling_mode, buffer_lth=working_buffer_size)
                    # Allocate complete buffers
                    self.complete_buffers[ch_idx] = np.zeros(shape=total_samples, dtype=np.int16)  # in adc
            print("[DEBUG] Streaming buffers are set.")

        if acq_mode == "block":
            for ch_idx, en in self.enabled_channels.items():
                if en:
                    self.complete_buffers[ch_idx] = np.zeros(shape=total_samples, dtype=np.int16) # in adc
                    self.register_buffer(ch_idx=ch_idx, buffer=self.complete_buffers[ch_idx], down_sampling_mode=down_sampling_mode, buffer_lth=total_samples)
            print("[DEBUG] Block buffers are set.")

    def set_simple_edge_trigger(self,
                                source: str,  # e.g. "channel_A"
                                threshold: float,  # in milliVolts
                                direction: str,
                                delay: int,  # in sample periods
                                auto_trigger_ms: int = 0,
                                enable: int = 1,  # 0 = disable
                                ):
        # convert mV -> ADC
        ch_idx = CONNECTIONS[source]  # "channel_A" -> 0
        range_idx = self.channel_ranges[ch_idx]
        threshold_adc = mV2adc(threshold, range_idx, self.max_adc)
        range_mv = RANGES[range_idx]
        print(
            f"[DEBUG] Trigger sanity: "
            f"range_idx={range_idx}, "
            f"range_mv={range_mv}, "
            f"threshold_mv={threshold}, "
            f"threshold_adc={threshold_adc}, "
            f"max_adc={self.max_adc.value}"
        )

        int_direction = DIRECTIONS[direction]  # "falling" -> 1

        status = psa.ps4000aSetSimpleTrigger(self.chandle,
                                             enable,
                                             ch_idx,
                                             threshold_adc,
                                             int_direction,
                                             delay,
                                             auto_trigger_ms)
        assert_pico_ok(status)
        print("[DEBUG] TRIGGER SET SUCCESS")

    def set_channel(self, channel: str, coupling_type: str, channel_range_v: float, enabled: bool, analogue_offset=0.0,
                    fresh: bool = True):
        """Set channel and if reconfigured from GUI -- update fields (enabled_channels, channel_ranges, channels_properties)"""
        ch_idx = CONNECTIONS[channel]
        coupling = COUPLING[coupling_type]
        channel_range = RANGES.index(channel_range_v)
        max_v, min_v = self._get_analogue_offset_range(channel_range, coupling)
        enabled_digit = ENABLED[enabled]

        if not (min_v <= analogue_offset <= max_v):
            raise LabscriptError(f"Offset {analogue_offset} out of bounds [{min_v}, {max_v}]")

        c_analogue_offset = ctypes.c_float(analogue_offset)

        status = psa.ps4000aSetChannel(self.chandle, ch_idx, enabled_digit, coupling, channel_range, c_analogue_offset)
        assert_pico_ok(status)

        # save channel_ranges in indexes
        self.channel_ranges[ch_idx] = channel_range
        self.enabled_channels[ch_idx] = enabled

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
        status = psa.ps4000aGetAnalogueOffset(self.chandle, ch_range, coupling, ctypes.byref(max_v),
                                              ctypes.byref(min_v))
        assert_pico_ok(status)
        return max_v.value, min_v.value

    def run_stream(self,
                   sample_interval_ns: int,
                   max_pre_trigger_samples: int,
                   max_post_trigger_samples: int,
                   buffer_size,
                   downsample_ratio: int = 1,  # no downsampling
                   downsample_ratio_mode: str = 'none',
                   ):

        # parameters
        stop_auto = 1 # stop after all samples fetched
        c_sample_interval = ctypes.c_int32(sample_interval_ns)
        time_units = psa.PS4000A_TIME_UNITS['PS4000A_NS']  # Nanoseconds
        c_downsample_ratio_mode = RATIO_MODES[downsample_ratio_mode]
        overview_buffer_size = buffer_size

        status = psa.ps4000aRunStreaming(self.chandle,
                                         ctypes.byref(c_sample_interval),
                                         time_units,
                                         max_pre_trigger_samples,
                                         max_post_trigger_samples,
                                         stop_auto,
                                         downsample_ratio,
                                         c_downsample_ratio_mode,
                                         overview_buffer_size)

        assert_pico_ok(status)
        print("[DEBUG] STREAM STARTED")

        self.actual_sample_interval = c_sample_interval.value
        print(f"[INFO] sample interval: {sample_interval_ns}ns --> {self.actual_sample_interval}ns")

        self.total_samples = max_pre_trigger_samples + max_post_trigger_samples

        # Prepare global flags
        self.next_sample_idx = 0
        self.was_called_back = False
        self.auto_stop_outer.clear()

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
            # 1. Process trigger
            # 2. Write data from buffers

            self.was_called_back = True

            if triggered != 0 and not self.trigger_event.is_set():
                print("TRIGGERED")
                self.trigger_event.set()
                self.triggered_at = self.next_sample_idx + triggerAt

            if not self.trigger_event.is_set():
                return

            samples_left = self.total_samples - self.next_sample_idx
            if samples_left <= 0:
                self.auto_stop_outer.set()
                return

            n_copy = min(noOfSamples, samples_left)

            src_start = startIndex
            src_end = startIndex + n_copy
            dst_start = self.next_sample_idx
            dst_end = self.next_sample_idx + n_copy

            for ch_idx, en in self.enabled_channels.items():
                if en:
                    self.complete_buffers[ch_idx][dst_start:dst_end] = self.buffers[ch_idx][src_start:src_end]

            self.next_sample_idx += n_copy

            if autoStop == 1 or self.next_sample_idx >= self.total_samples:
                self.auto_stop_outer.set()

            self.overvoltage = overflow # fixme?

        c_func_ptr = psa.StreamingReadyType(streaming_callback)

        def fetching():
            while not self.auto_stop_outer.is_set() and self.next_sample_idx < self.total_samples:
                self.was_called_back = False
                streaming_status = psa.ps4000aGetStreamingLatestValues(self.chandle, c_func_ptr, None)
                if streaming_status == PICO_STATUS['PICO_BUSY']:
                    time.sleep(0.0001)
                    continue
                assert_pico_ok(streaming_status)
                if not self.was_called_back:
                    time.sleep(0.0001)

            print("[WARNING] Fetching is finished ... No more data is being collected. Stop streaming ...")
            self.stop_sampling()
            self.data_ready_event.set()


        # start fetching data in different thread to not block buffered mode
        self.fetching_thread = threading.Thread(target=fetching)
        self.fetching_thread.start()
        print("[INFO] Waiting for trigger ...")

    def adc2mv_1d(self, data_adc, ch):
        channel_range = self.channel_ranges[ch]
        data_mv = adc2mV(data_adc, channel_range, self.max_adc)
        return data_mv

    def run_block(self, no_pre_trigger_samples:int, no_post_trigger_samples:int, sample_interval:int|float, down_sample_mode:str, down_sample_ratio:int):
        # Get the timebase
        timebase = int(round(sample_interval / 12.5) - 1) # from specification
        c_sample_interval_ns = ctypes.c_int32()
        c_max_samples = ctypes.c_int32()
        self.get_timebase(timebase=timebase,
                         no_samples=no_pre_trigger_samples+no_post_trigger_samples,
                         sample_interval=ctypes.byref(c_sample_interval_ns),
                         max_samples=ctypes.byref(c_max_samples))

        #  sanity check
        if c_max_samples is None or c_max_samples == 0:
            raise LabscriptError("Block mode: Nothing will be written here -- maxSamples is null.")

        self.actual_sample_interval = c_sample_interval_ns.value
        print(f"[INFO] Sample interval: {sample_interval}ns --> {self.actual_sample_interval}ns. ")
        print("[DEBUG] Timebase = {}".format(timebase))
        print("[INFO] Maximum samples number = {}".format(c_max_samples.value))


        # Run block
        c_time_indisposed_ms = ctypes.c_int32()
        lpReady = None # polling in fetching thread

        status_block = psa.ps4000aRunBlock(self.chandle, no_pre_trigger_samples, no_post_trigger_samples, timebase,
                                           ctypes.byref(c_time_indisposed_ms), SEGMENT_INDEX, lpReady, None)
        assert_pico_ok(status_block)

        def fetching():
            ready = ctypes.c_int16(0)
            check = ctypes.c_int16(0)
            while ready.value == check.value: # polling
                ready_status = psa.ps4000aIsReady(self.chandle, ctypes.byref(ready))
                assert_pico_ok(ready_status)

            print("[WARNING] Fetching is finished ... No more data is being collected. Stop sampling ...")
            self.stop_sampling()
            self.data_ready_event.set() # --> retrieve data NOW

            start_index = 0
            c_no_of_sample = ctypes.c_int32(no_pre_trigger_samples + no_post_trigger_samples)
            downsample_ratio_mode = RATIO_MODES[down_sample_mode]
            c_overflow = ctypes.c_int16()
            status = psa.ps4000aGetValues(self.chandle,
                                          start_index, # start point for data collection ( in sample intervals from the start of the buffer)
                                          ctypes.byref(c_no_of_sample), # on entry number of samples requested, on exit number of samples actually retrieved
                                          down_sample_ratio,
                                          downsample_ratio_mode,
                                          SEGMENT_INDEX,
                                          ctypes.byref(c_overflow)) # a set of flags that indicate whether an overvoltage has occurred on any of the channels. It is a bit pattern, with bit 0 corresponding to Channel A.
            assert_pico_ok(status)
            self.overvoltage = c_overflow

        self.fetching_thread = threading.Thread(target=fetching)
        self.fetching_thread.start()

    def get_timebase(self, timebase, no_samples, sample_interval, max_samples):
        status = psa.ps4000aGetTimebase(self.chandle, timebase, no_samples, sample_interval, max_samples, SEGMENT_INDEX)
        assert_pico_ok(status)


class PicoScopeWorker(Worker):
    interface_class = None

    def init(self):
        self.interface_class = PicoScope4000A
        self.pico = self.interface_class(self.serial_number)

        self.h5_file = None
        self.device_name = None

        self.image_socket = Context().socket(zmq.REQ)
        self.image_socket.connect(
            f'tcp://{self.parent_host}:{self.image_receiver_port}'
        )

        # Initial configure device and channels
        # Configure channels
        for ch_conn, ch in self.channels_properties.items():
            self.pico.set_channel(channel=ch_conn, coupling_type=ch["coupling"], channel_range_v=ch["range"], enabled=ch["enabled"], analogue_offset=ch["analog_offset"], fresh=True)
        print("[DEBUG] CHANNELS ENABLED: {}".format(self.pico.enabled_channels))

        # Configure trigger
        print("[DEBUG] Simple trigger config: {}".format(self.simple_trigger))
        if self.simple_trigger:
            self.pico.set_simple_edge_trigger(
                source=self.simple_trigger["source"],
                threshold=self.simple_trigger["threshold"] * 1e3,  # in millivolts
                direction=self.simple_trigger["direction"],
                delay=self.simple_trigger["delay"],
                auto_trigger_ms=int(self.simple_trigger["auto_trigger"] * 1e3),  # in milliseconds
            )

        # Create the structure of all channels identificators
        self.channels = [] # [{index=0, conn="channel_A", name="fc"}, {..}, ..]
        for conn, props in self.channels_properties.items():
            self.channels.append(dict(index=CONNECTIONS[conn], conn=conn, name=props["name"]))
        self.by_index = {ch["index"]: ch for ch in self.channels}
        self.by_conn  = {ch["conn"]: ch for ch in self.channels}
        self.by_name = {ch["name"]: ch for ch in self.channels}

    def shutdown(self):
        # stop fetching thread
        self.pico.auto_stop_outer.set()

        # wait till finish
        if self.pico.fetching_thread is not None and self.pico.fetching_thread.is_alive():
            self.fetching_thread.join(timeout=1)

        print("[INFO] Fetching thread stopped")

        # stop sampling and close unit
        self.pico.stop_sampling()
        self.pico.close_unit()

        print('[INFO] Shutdown complete.')

    def program_manual(self, front_panel_values):
        pass

    def _get_acquisition_config(self, properties):
        stream_cfg = properties.get("stream_config")
        block_cfg = properties.get("block_config")

        if stream_cfg and block_cfg:
            raise LabscriptError(
                "Both stream_config and block_config are set. Only one acquisition mode is allowed per shot.")

        if stream_cfg:
            cfg = stream_cfg
            mode = AcqMode.STREAM
        elif block_cfg:
            cfg = block_cfg
            mode = AcqMode.BLOCK
        else:
            raise LabscriptError("No sampling mode configured. Call either:\n"
                                 f"  {self.name}.set_stream_sampling(...)\n"
                                 f"  {self.name}.set_block_sampling(...)")

        return mode, cfg


    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5_file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, 'r') as hdf5_file:
            properties = labscript_utils.properties.get(
                hdf5_file, self.device_name, 'device_properties'
            )

        # 1. Re-Configure channels again specifically for this shot (from h5 file)
        for ch_conn, props in properties['channels_properties'].items():
            self.pico.set_channel(channel=props["channel"],
                                  coupling_type=props["coupling"],
                                  channel_range_v=props["range"],
                                  enabled=props["enabled"],
                                  analogue_offset=props["analog_offset"],
                                  fresh=False)

        # 2. Get mode
        acq_mode, config = self._get_acquisition_config(properties)
        max_pre_trigger_samples = config["no_pre_trigger_samples"]
        max_post_trigger_samples = config["no_post_trigger_samples"]
        total_samples = max_pre_trigger_samples + max_post_trigger_samples
        down_sampling_mode = config["downsampling_mode"]
        down_sample_ratio = config["downsample_ratio"]
        sample_interval = config["sample_interval"]

        # 3. Allocate and register buffers according to sampling mode
        self.pico.setup_buffers(total_samples=total_samples, down_sampling_mode=down_sampling_mode, acq_mode=acq_mode, working_buffer_size=BUFFER_SIZE)

        # 4. Configure Trigger
        simple_trigger_config = properties['simple_trigger_config']
        self.pico.set_simple_edge_trigger(
            source=simple_trigger_config["source"],
            threshold=simple_trigger_config["threshold"] * 1e3,  # in millivolts
            direction=simple_trigger_config["direction"],
            delay=simple_trigger_config["delay"],
            auto_trigger_ms=int(simple_trigger_config["auto_trigger"] * 1e3),  # in milliseconds
        )

        # 5. Run sampling mode
        if acq_mode == AcqMode.STREAM:
            self.pico.run_stream(
                sample_interval_ns=sample_interval,
                max_pre_trigger_samples=max_pre_trigger_samples,
                max_post_trigger_samples=max_post_trigger_samples,
                buffer_size=BUFFER_SIZE,
                downsample_ratio=down_sample_ratio,
                downsample_ratio_mode=down_sampling_mode,
            )

        if acq_mode == "block":
            self.pico.run_block(no_pre_trigger_samples=max_pre_trigger_samples,
                                no_post_trigger_samples=max_post_trigger_samples,
                                sample_interval=sample_interval,
                                down_sample_ratio=down_sample_ratio,
                                down_sample_mode=down_sampling_mode)


        rich_print(f"---------- END transition to Buffered: ----------", color=BLUE)

        return {}

    def transition_to_manual(self):
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)
        # Save the data from complete buffers into hdf5 file
        # wait until all samples are collected
        self.pico.data_ready_event.wait()
        # or ????
        if self.pico.fetching_thread is not None and self.pico.fetching_thread.is_alive():
            rich_print("[INFO] Waiting for fetching thread to finish...", color=YELLOW)
            self.pico.fetching_thread.join()  # block until finish
            rich_print("[INFO] Fetching thread finished.", color=GREEN)


        buffered_channels = self.pico.complete_buffers.keys() # already sorted by idx?

        # Prepare data
        data_list = []
        for ch in buffered_channels:
            buf_adc = self.pico.complete_buffers[ch]
            buf_mv = self.pico.adc2mv_1d(buf_adc.astype(np.int32), ch)
            data_list.append(buf_mv)

        data_array = np.column_stack(data_list)  # combine horizontally
        self._send_traces_to_parent(data_array)

        # Write data
        with h5py.File(self.h5_file, "r+") as f:
            group = f.require_group('/data/traces')
            picoscope_group = group.require_group(self.device_name)

            ds = picoscope_group.create_dataset(
                "data",
                data=data_array,
                dtype=np.float32,
                compression="gzip",
                shuffle=True,
                chunks=True,
            )

            ds.attrs["sample_interval"] = self.pico.actual_sample_interval  # uint
            ds.attrs["triggered_at"] = self.pico.triggered_at               # uint
            ds.attrs["units"] = "mV"
            ds.attrs["axis_0"] = "time"
            ds.attrs["axis_1"] = "channel"
            enabled_indices = sorted([idx for idx, en in self.pico.enabled_channels.items() if en])
            ds.attrs["enabled_indices"] = np.array(enabled_indices, dtype=np.uint8)

            # channels metadata
            dtype = np.dtype([
                ("index", np.uint8), # [0..7]
                ("conn", h5py.string_dtype("utf-8")),
                ("name", h5py.string_dtype("utf-8")),
            ])
            ch_ds = picoscope_group.create_dataset("channels", shape=(len(self.buffered_channels),), dtype=dtype)
            for i, ch_idx in enumerate(buffered_channels):
                ch_ds[i] = (
                    ch_idx,
                    self.by_index[ch_idx]["conn"],  # "channel_A"
                    self.by_index[ch_idx]["name"]  # "mot_from_fc"
                )

        print(f"[INFO] Saved {data_array.shape[0]} samples × {data_array.shape[1]} channels")

        # clear all buffered events
        # Set all fields default
        self.pico.trigger_event.clear()
        self.pico.next_sample_idx = 0
        self.pico.auto_stop_outer = None
        self.pico.fetching_thread = None
        self.pico.data_ready_event.clear()
        self.pico.triggered_at = None
        self.h5_file = None
        self.device_name = None
        self.enabled_channels = None
        self.total_samples = None

        return True

    def _send_traces_to_parent(self, traces):
        """Send the traces to the GUI to display. This will block if the parent process
        is lagging behind, in order to avoid a backlog."""
        channel_names = {}  # trace_idx<int>: ch_name<str>
        # from currently enabled channel get the mapping of trace index in stack with the channel name
        trace_idx = 0
        for ch_idx, en in self.pico.enabled_channels.items():
            if en:
                channel_names[trace_idx] = self.by_index[ch_idx]["name"]
                trace_idx += 1

        # sanity check
        assert trace_idx == traces.shape[1], (
            f"Mismatch: {trace_idx=} vs {traces.shape[1]=}"
        )

        print("[DEBUG] channel names: {} ".format(channel_names))

        metadata = dict(dtype=str(traces.dtype), shape=traces.shape,
                        sample_interval=self.pico.actual_sample_interval, triggered_at=self.pico.triggered_at,
                        channel_names=channel_names)
        self.image_socket.send_json(metadata, zmq.SNDMORE)
        self.image_socket.send(traces, copy=False)
        response = self.image_socket.recv()
        assert response == b'ok', response

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def siggen_software_trigger(self):
        rich_print("NOT IMPLEMENTED YET", color=RED)
        # self.pico.siggen_software_control(0)

    def start_streaming(self):
        rich_print("NOT IMPLEMENTED YET", color=RED)
