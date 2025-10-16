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
"""
This worker is error prone, but contains extended functionality such as 
- Signal generator
- Advanced triggering
- software triggering for signal generator
"""
class PicoScopeWorker(Worker):

    def init(self):

        self.pico = PicoScope(self.serial_number)

        self.h5_file = None
        self.device_name = None
        self.total_samples = 0

        self._stop_threads = None

    def shutdown(self):
        self._stop_threads = True
        self.pico._stop_threads = True

        self.pico.stop_unit()
        self.pico.close_unit()

        # join threads
        if getattr(self.pico, "fetcher_thread", None) is not None:
            self.fetcher_thread.join(timeout=1.0)
        if getattr(self, "writer_thread", None) is not None:
            self.writer_thread.join(timeout=1.0)

    def program_manual(self, front_panel_values):
        pass

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        """Configure the streaming, triggering, channels."""
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5_file = h5_file
        self.device_name = device_name

        # Configure channels
        for ch in self.channels_configs:
            self.pico.set_channel(ch["channel"], ch["coupling"], ch["range"], ch["enabled"], ch["analog_offset"])

        # Configure Trigger
        if self.simple_trigger:
            self.pico.set_simple_edge_trigger(
                                              self.simple_trigger["source"],
                                              self.simple_trigger["threshold"],
                                              self.simple_trigger["direction"],
                                              self.simple_trigger["delay"],
                                              self.simple_trigger["autoTrigger_ms"],
                                            # self.simple_trigger["enabled"],
            )

        if self.trigger_conditions:
            for cond in self.trigger_conditions:
                self.pico.set_trigger_conditions(cond["sources"], cond["info"])

        if self.trigger_directions:
            self.pico.set_trigger_channel_directions(self.trigger_directions)

        if self.trigger_properties:
            self.pico.set_trigger_channel_properties(self.trigger_properties)

        if self.trigger_delay:
            self.pico.set_trigger_delay(self.trigger_delay["delay"])

        print(f"[DEBUG] the pico status = {self.pico.status}")

        # Configure Sig gen
        if self.siggen_config:
            self.pico.gen_signal(
                self.siggen_config["offsetVoltage"],
                self.siggen_config["pkToPk"],
                self.siggen_config["wavetype"],
                self.siggen_config["startFrequency"],
                self.siggen_config["stopFrequency"],
                self.siggen_config["increment"],
                self.siggen_config["dwelltime"],
                self.siggen_config["sweeptype"],
                self.siggen_config["operation"],
                self.siggen_config["shots"],
                self.siggen_config["sweeps"],
                self.siggen_config["triggertype"],
                self.siggen_config["triggersource"],
                self.siggen_config["extInThreshold"],
            )

        # Configure active mode
        if self.active_mode == "stream" and self.stream_config:
            self.pico.run_stream(
                self.stream_config["sampleInterval"],
                # self.stream_config["noPreTriggerSamples"],
                self.stream_config["noPostTriggerSamples"],
                # self.stream_config["autoStop"],
                self.stream_config["downSampleRatio"],
                self.stream_config["downSampleRatioMode"],
            )

        if self.active_mode == "block" and self.block_config:
            self.pico.run_block(
                self.block_config["noPreTriggerSamples"],
                self.block_config["noPostTriggerSamples"],
                self.block_config["sampleInterval"]
            )

        # Create dataset for streaming samples:
        rows = self.pico.total_samples
        cols = sum(self.pico.enabled_channels)

        with h5py.File(self.h5_file, "r+") as f:
            group = f[f"/devices/{self.device_name}"]
            if "StreamSamples" in group:
                del(group["StreamSamples"])

            ds = group.create_dataset("StreamSamples", shape=(rows, cols), dtype=np.float32)
            ds.attrs["channel_names"] = [f"CH{ch}" for ch, enabled in enumerate(self.pico.enabled_channels) if enabled == 1]
            ds.attrs["sample_interval"] = self.pico.actual_sample_interval # todo?

        self.writer = threading.Thread(target=self.h5_writer_thread, daemon=True)
        self.writer.start()

        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return

    def transition_to_manual(self):
        rich_print(f"---------- Begin transition to Manual: ----------", color=BLUE)

        rich_print(f"---------- End transition to Manual: ----------", color=BLUE)
        return True

    def h5_writer_thread(self):
        """Get from queue 2d data block. Transform ADC counts to mV. Save new data in hdf5file."""
        with h5py.File(self.h5_file, "r+") as f:
            ds = f[f"/devices/{self.device_name}/StreamSamples"]

            while not self._stop_threads: # run till all samples collected
                try:
                    start, data2d = self.pico.h5_queue.get(timeout=0.5)

                except queue.Empty:
                    continue

                n = data2d.shape[0] # number of samples
                end = start + n # the last sample number
                if end > ds.shape[0]:
                    print(f"[WARNING] Too many samples, truncating... start={start}, requested_end={end}, ds_rows={ds.shape[0]}")
                    n = ds.shape[0] - start # number of samples to save, the rest get lost
                    if n <= 0:
                        continue
                    data2d = data2d[:n, :]
                    end = start + n

                # Save data
                data_mV = self.pico.adc2mv(data2d)
                ds[start:end, :] = data_mV.astype(ds.dtype)

                if end == self.pico.total_samples:
                    ds.attrs['trigger_at'] = int(self.pico.triggered_at)
                    break

            print(f"\n [INFO] All {self.pico.total_samples} data samples have been collected and written to the hdf5 file.")
            f.flush()

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()

    def siggen_software_trigger(self):
        self.pico.siggen_software_control(0)

BLUE = '#66D9EF'

class PicoScope:

    def __init__(self, serial_number):
        self.status = {}
        self.chandle = ctypes.c_int16()

        self.enabled_channels = [0,0,0,0,0,0,0,0] # store channels status
        self.channel_ranges = {} # store each channel [0..7] vRange [0..13]

        self.buffers = {}
        self.max_buffers = {} # if downsample mode is 'aggregate'
        self.complete_buffers = {}
        self.complete_max_buffers = {}
        self.total_samples = 0

        self.auto_stop_outer = None
        self.was_called_back = None
        self.stop_h5_writer = False

        self.fetch_ready = False
        self._stop_threads = False

        # Open device
        self.open_unit(serial_number)

        self.maxADC = ctypes.c_int32()
        self.status["maximumValue"] = ps.ps4000aMaximumValue(self.chandle, ctypes.byref(self.maxADC))
        self.actual_sample_interval = None
        self.next_sample = 0
        self.auto_stop = False

        self.h5_queue = queue.Queue()
        self.triggered_at = None

    #######################################################################
    ################# Device Management ###################################
    #######################################################################

    def open_unit(self, serial_number):
        serial_number = serial_number.encode()
        self.status["openUnit"] = ps.ps4000aOpenUnit(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(self.status["openUnit"])
        print("[PicoScope] PicoScope connected, chandle:", self.chandle.value)

    def close_unit(self):
        print(f"[PicoScope] {self.status}")
        self._stop_threads = True
        self.status["close"] = ps.ps4000aCloseUnit(self.chandle)

    def stop_unit(self):
        self._stop_threads = True
        print('[DEBUG] STOP STREAMING')
        self.status["stop"] = ps.ps4000aStop(self.chandle)

    #######################################################################
    ########################### Queries ###################################
    #######################################################################
    def _get_device_resolution(self):
        resolution = ctypes.c_int32()
        self.status["GetDeviceResolution"] = ps.ps4000aGetDeviceResolution(self.chandle, ctypes.byref(resolution))
        assert_pico_ok(self.status["GetDeviceResolution"])
        return resolution.value

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

    def _find_best_timebase(self, desired_no_samples, desired_interval_ns, segment_index=0):
        """
        Automatically find the best timebase.

        :param desired_no_samples (int): Number of samples you want to capture.
        :param desired_interval_ns (float): Desired time interval between samples in milliseconds.
        :param segment_index (int): Memory segment to use (default 0).

        :return best_timebase (int):  Timebase code to use.
        :return actual_interval_ns (float): Actual achievable time interval per sample.
        :return max_samples(int): Maximum number of samples available for this timebase.
        """
        best_timebase = None
        actual_interval_ns = None
        max_samples_available = None

        # PicoScope 4000A supports 0..2**32-1 timebases theoretically
        tb_guess = int(round(desired_interval_ns / 12.5 - 1))
        max_tb = tb_guess + 100
        for tb in range(tb_guess, max_tb):
            t_ns = ctypes.c_float()
            max_s = ctypes.c_int32()
            status = ps.ps4000aGetTimebase2(
                self.chandle,
                ctypes.c_uint32(tb),
                ctypes.c_int32(desired_no_samples),
                ctypes.byref(t_ns),
                ctypes.byref(max_s),
                ctypes.c_uint32(segment_index)
            )
            if status != PICO_STATUS['PICO_OK']:
                continue

            if t_ns.value >= desired_interval_ns and max_s.value >= desired_no_samples:
                best_timebase = tb
                actual_interval_ns = t_ns.value
                max_samples_available = max_s.value
                break

            logger.debug(f"Finding best timebase for {tb} samples... Status: {status}.")

        if best_timebase is None:
            raise RuntimeError(f"Compatible Timebase not found for "
                               f"[numberOfSamples={desired_no_samples}, intervalSamplesNs={desired_interval_ns}]. ")

        return best_timebase, actual_interval_ns, max_samples_available

    #######################################################################
    ########################### Channel setup #############################
    #######################################################################

    def set_channel(self, channel: str, coupling_type: str, channel_range: float, enabled=1, analogue_offset=0.0):
        """ Set the channel up and create the buffer for each enabled channel.
        :param channel:
        :param coupling_type: 'ac' | 'dc'
        :param channel_range: Measuring ranges 0 to 13, specifies the measuring range.
        This is defined differently depending on the oscilloscope.
        :param enabled: 0 | 1
        :param analogue_offset: in Volts
        :return:
        """
        # check if offset is allowed
        channel_int = _get_channel_number(channel)
        coupling_type_int = _get_coupling(coupling_type)
        range_int = _get_range(channel_range)
        max_v, min_v = self._get_analogue_offset_range(range_int, coupling_type_int)

        if not (min_v <= analogue_offset <= max_v):
            raise LabscriptError(f"Offset {analogue_offset} out of bounds [{min_v}, {max_v}]")

        c_analogue_offset = ctypes.c_float(analogue_offset)

        self.status[f"setCh{channel}"] = ps.ps4000aSetChannel(self.chandle,
                                                              channel_int,
                                                              enabled,
                                                              coupling_type_int,
                                                              range_int,
                                                              c_analogue_offset)
        assert_pico_ok(self.status[f"setCh{channel}"])

        self.channel_ranges[channel_int] = range_int

        if enabled == 1: # save enabled channels to create buffers
            self.enabled_channels[channel_int] = 1

    #######################################################################
    ######################### Data Acquisition ############################
    #######################################################################

    def set_data_buffer(self, channel: int, buffer, bufferLth: int, segmentIndex: int, mode: int):
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
        ptr = buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        self.status[f"setDataBuffer_{channel}"] = ps.ps4000aSetDataBuffer(self.chandle, channel, ptr, bufferLth,
                                                               segmentIndex, mode)
        assert_pico_ok(self.status[f"setDataBuffer_{channel}"])

    def set_max_min_data_buffers(self, channel:int, bufferMax, bufferMin, bufferLth:int, segmentIndex:int, mode: int):
        """
        This function registers data buffers, for receiving aggregated data (downsampling type = aggregate)
        :param channel:
        :param bufferMax:
        :param bufferMin:
        :param bufferLth: specifies the size of the bufferMax and bufferMin arrays
        :param segmentIndex:
        :param mode: default PS4000A_RATIO_MODE_AGGREGATE
        :return:
        """
        pmax = bufferMax.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        pmin = bufferMin.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        self.status[f"setMaxMinDataBuffer_{channel}"] = ps.ps4000aSetDataBuffer(self.chandle, channel,
                                                                                pmax, pmin, bufferLth, segmentIndex, mode)
        assert_pico_ok(self.status[f"setMaxMinDataBuffer_{channel}"])

    def run_stream(self,
                   sampleInterval_ns: int,
                   # maxPreTriggerSamples: int,
                   maxPostTriggerSamples: int,
                   # autoStop: int = 0,  # dont stop after all samples collected
                   downSampleRatio: int = 1,  # default no downsampling
                   downSampleRatioMode: str='none',
                   ):
        """
        In this mode, data is passed directly to the PC without being stored in the scope's
        internal buffer memory. This enables long periods of slow data collection for chart recorder
        and datalogging applications. Streaming mode provides fast streaming at up to 160 MS/s with a USB 3.0
        connection. Downsampling and triggering are supported in this mode.

        First, we allocate buffers for each enabled channel to store data.
        Seconds, we run the streaming mode.

        :param sampleInterval_ns: requested sample interval in Nanoseconds, on exit the actual interval
        :param maxPreTriggerSamples: the maximum number of raw samples before a trigger event for each enabled channel
        :param maxPostTriggerSamples:
        :param autoStop: flag whether to stop after maxPreTriggerSamples+maxPostTriggerSamples have been taken [0, 1]
        :param downSampleRatio: the number of raw values to each downsampled value.
        :param downSampleRatioMode:
        :return:
        """
        # prepare arguments
        autoStop = 0 # dont stop after all samples collected
        c_sampleInterval = ctypes.c_int32(sampleInterval_ns)
        timeUnits = ps.PS4000A_TIME_UNITS['PS4000A_NS']  # Nanoseconds
        downSampleRatioMode_int = _get_ratio_mode(downSampleRatioMode)

        # Define buffers
        maxPreTriggerSamples = 0
        self.total_samples = maxPreTriggerSamples + maxPostTriggerSamples
        buffer_size = 1000
        overviewBufferSize = buffer_size

        # Allocate and register working buffers for enabled channels
        for ch, enabled in enumerate(self.enabled_channels):
            if enabled == 1:
                self.buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16)
                if downSampleRatioMode == 'aggregate':
                    self.max_buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16)
                    self.set_max_min_data_buffers(
                        channel=ch,
                        bufferMax=self.max_buffers[ch],
                        bufferMin=self.buffers[ch],
                        bufferLth=buffer_size,
                        segmentIndex=0,
                        mode=downSampleRatioMode_int
                    )
                else:
                    self.set_data_buffer(
                        channel=ch,
                        buffer=self.buffers[ch],
                        bufferLth=buffer_size,
                        segmentIndex=0,
                        mode=downSampleRatioMode_int
                    )

        # Configure and run streaming sampling mode
        self.status["runStreaming"] = ps.ps4000aRunStreaming(
            self.chandle, ctypes.byref(c_sampleInterval), timeUnits, maxPreTriggerSamples,
            maxPostTriggerSamples, autoStop, downSampleRatio, downSampleRatioMode_int, overviewBufferSize)
        assert_pico_ok(self.status["runStreaming"])

        self.actual_sample_interval = c_sampleInterval.value
        print(f"[INFO] Sample Interval {sampleInterval_ns} -> {self.actual_sample_interval}")

        # Prepare callback
        self.next_sample = 0
        self.auto_stop_outer = False
        self.was_called_back = False
        self.was_triggered = False

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
            """
            This callback function receives a notification when streaming-mode data is ready.
            We put the colleted after trigger data into queue, to save it into hdf5file in another thread to not block the data streaming.

            :param handle:
            :param noOfSamples: The number of samples to collect.
            :param startIndex: an index to the first valid sample in the working buffer
            :param overflow: returns a set of flags that indicate whether an overvoltage has occurred on any of the channels.
            :param triggerAt: trigger index relative to the start index in the buffer.
                This parameter is valid only when triggered is non-zero.
            :param triggered: a flag indicating whether a trigger occurred. If non-zero, a trigger occurred at the location indicated by triggerAt
            :param autoStop:  the flag that was set in the call to ps4000aRunStreaming()
            :param param: a void pointer passed from ps4000aGetStreamingLatestValues(). The callback function can write to this
                location to send any data, such as a status flag, back to the application.
            :return:
            """
            print("CALLBACK CALLED")
            if triggered != 0:
                self.was_triggered = True
                self.triggered_at = self.next_sample + triggerAt
                print(f"[DEBUG] Was triggered at {self.triggered_at}. ")

            if self.was_triggered:
                start_sample = self.next_sample
                self.was_called_back = True
                blocks = [
                    self.buffers[ch][startIndex:startIndex + noOfSamples].astype(np.int16).copy()
                    for ch, enabled in enumerate(self.enabled_channels)
                    if enabled == 1
                ]
                data2d = np.stack(blocks, axis=1)  # shape (noOfSamples, n_enabled_channels)

                try:
                    self.h5_queue.put_nowait((start_sample, data2d))
                    self.next_sample += noOfSamples

                except queue.Full:
                    self.next_sample += noOfSamples
                    print(f"[DEBUG] Queue full! Dropping data: start_sample={start_sample}, end_sample={start_sample + noOfSamples}")
                    pass

                if autoStop != 0:
                    self.auto_stop_outer = True

        self.c_lpReady = ps.StreamingReadyType(streaming_callback)


        def fetching_thread():
            print(f"[INFO] Start Fetcher. ")
            while self.next_sample < self.total_samples and not self.auto_stop_outer and not self._stop_threads:
                try:
                    self.was_called_back = False
                    self.status["getStreamingValues"] = ps.ps4000aGetStreamingLatestValues(self.chandle, self.c_lpReady, None)
                except ps.PicoSDKCtypesError as e:
                    if "PICO_BUSY" in str(e):
                        time.sleep(0.01)
                    else:
                        raise

                if not self.was_called_back:
                    time.sleep(0.01)

            print(f"[WARNING] Fetcher thread is finished... No more data is being collected.")
            self.stop_h5_writer = True

        # Start a thread to register callback and fetch data
        self.fetcher = threading.Thread(target=fetching_thread, daemon=True)
        self.fetcher.start()

    def run_block(self, preTriggerSamples, postTriggerSamples, desiredInterval):
        # todo: not supported yet (not used)
        """
        In this mode, the scope stores data in internal buffer memory and then transfers it to the
        PC. When the data has been collected it is possible to examine the data, with an optional
        downsampling factor. The data is lost when a new run is started in the same segment, the settings are
        changed, or the scope is powered down.
        :param preTriggerSamples:
        :param postTriggerSamples:
        :param desiredInterval:
        :return:
        """
        self.max_samples = preTriggerSamples + postTriggerSamples

        timebase, actual_interval_ns, max_samples = self._find_best_timebase(preTriggerSamples + postTriggerSamples,
                                                                             desiredInterval)
        logger.debug(f"Best Timebase: {timebase} with corresponding interval: {actual_interval_ns}, "
                     f"and max #samples: {max_samples}")

        # ctypes wrappers
        c_timeIndisposedMs = ctypes.c_uint32()
        segmentIndex = 0
        c_pParameter = ctypes.c_void_p(None)  # a void pointer that is passed to the ps4000aBlockReady() callback function. To return data to the application

        # convert the python function into a C function pointer
        c_lpReady = None # polling
        self.status["runBlock"] = ps.ps4000aRunBlock(
            self.chandle,
            preTriggerSamples,
            postTriggerSamples,
            timebase,
            ctypes.byref(c_timeIndisposedMs),  # or None
            segmentIndex,
            c_lpReady,
            c_pParameter,
        )
        assert_pico_ok(self.status["runBlock"])

        return c_timeIndisposedMs.value

    def run_rapid(self):
        # todo:
        print("Rapid block sampling mode is NOT implemented yet")

    def adc2mv(self, data2d_adc):
        """Convert raw ADC counts from enabled PicoScope channels to mV.

        Each column of `data2d_adc` corresponds to one enabled channel.
        First, maps those columns to their actual channel numbers (0–7),
        applies the appropriate voltage range for each, and converts.

        :param data2d_adc (np.ndarray 2D)
        :return data2d_mV (np.ndarray 2D)
        """
        enabled_channels = [i for i, enabled in enumerate(self.enabled_channels) if enabled == 1]

        blocks_mV = []
        for i, ch in enumerate(enabled_channels):
            buffer_adc = data2d_adc[:, i].astype(np.int32)  # get the column of channel
            mv = adc2mV(buffer_adc, self.channel_ranges[ch], self.maxADC)
            blocks_mV.append(mv)

        data2d_mV = np.stack(blocks_mV, axis=1)
        return data2d_mV

    #######################################################################
    ############################# Triggers ################################
    #######################################################################

    def set_trigger_conditions(self, sources, info:str):
        """
         conditions: list of sources (int)
         info: str
         """
        ps_conditions = []
        for source in sources:
            source_int = _get_channel_number(source)
            state = ps.PS4000A_TRIGGER_STATE["PS4000A_TRUE"]
            ps_conditions.append(ps.PS4000A_CONDITION(source_int, state))
        nConditions = len(ps_conditions)

        # create ctypes array
        cond_array = (ps.PS4000A_CONDITION * nConditions)(*ps_conditions)
        info_int = _get_info(info)

        self.status["setTriggerChannelConditions"] = ps.ps4000aSetTriggerChannelConditions(
            self.chandle,
            ctypes.byref(cond_array),
            nConditions,
            info_int
        )
        assert_pico_ok(self.status["setTriggerChannelConditions"])

    def set_trigger_channel_directions(self, directions):
        ps_directions = []
        for direction in directions:
            source_int = _get_channel_number(direction["source"])
            direction_int = _get_direction(direction["direction"])
            ps_directions.append(ps.PS4000A_DIRECTION(source_int, direction_int))

        nDirections = len(ps_directions)
        dir_array = (ps.PS4000A_DIRECTION * nDirections)(*ps_directions)

        self.status["setTriggerChannelDirections"] = ps.ps4000aSetTriggerChannelDirections(
            self.chandle,
            ctypes.byref(dir_array),
            nDirections
        )
        assert_pico_ok(self.status["setTriggerChannelDirections"])


    def set_trigger_channel_properties(self, properties):
        ps_properties = []
        for prop in properties:
            ch_int = _get_channel_number(prop["source"])
            threshold_mode_int = _get_threshold_mode(prop["threshold_mode"])
            ch_range = self.channel_ranges[ch_int]
            threshold_upper_adc = mV2adc(prop["threshold_upper"], ch_range, self.maxADC)
            threshold_lower_adc = mV2adc(prop["threshold_lower"], ch_range, self.maxADC)
            upper_hysteresis_adc = mV2adc(prop["upper_hysteresis"], ch_range, self.maxADC)
            lower_hysteresis_adc = mV2adc(prop["lower_hysteresis"], ch_range, self.maxADC)

            ps_properties.append(ps.PS4000A_TRIGGER_CHANNEL_PROPERTIES(
                threshold_upper_adc,
                upper_hysteresis_adc,
                threshold_lower_adc,
                lower_hysteresis_adc,
                ch_int,
                threshold_mode_int
            ))

        nProperties = len(ps_properties)
        prop_array = (ps.PS4000A_TRIGGER_CHANNEL_PROPERTIES * nProperties)(*ps_properties)

        autoTrigger_ms = 0 # the time in milliseconds
        # for which the scope will wait before collecting data
        # if no trigger event occurs. If 0, waits indefinitely for a trigger

        self.status["setTriggerChannelProperties"] = ps.ps4000aSetTriggerChannelProperties(
            self.chandle,
            ctypes.byref(prop_array),
            nProperties,
            0,
            autoTrigger_ms
        )
        assert_pico_ok(self.status["setTriggerChannelProperties"])

    def set_trigger_delay(self, delay):
        """delay in sample periods"""
        self.status["setTriggerDelay"] = ps.ps4000aSetTriggerDelay(self.chandle, delay)
        assert_pico_ok(self.status["setTriggerDelay"])


    def set_simple_edge_trigger(self,
                                source: str,
                                threshold: float,  # in milliVolts
                                direction: str,
                                delay: int, # in sample periods
                                autoTrigger_ms: int = 0,
                                enable: int = 1,  # 0 = disable
                                ):
        """
        Arms the trigger. Trigger type = LEVEL. Only one channel. Starts acquisition.
        :param enable: 0 = disable
        :param source:
        :param threshold: in millivolts, (later converted into ADC count)
        :param direction: direction of signal, [ABOVE, BELOW, RISING, FALLING, RISING_OR_FALLING]
        :param delay: in sample periods
        :param autoTrigger_ms: trigger timeout in ms, 0 = infinite
        :return:
        """
        print(f"[DEBUG] source, direction, delay, autotrigger, enable", source, threshold, direction, delay, autoTrigger_ms, enable)

        print(f"[DEBUG] trigger threshold = {threshold}. ")
        # Convert millivolts into ADC count (threshold)
        source_int = _get_channel_number(source)
        direction_int = _get_direction(direction)
        v_range = self.channel_ranges[source_int]
        threshold_adc = mV2adc(threshold, v_range, self.maxADC)

        self.status["setSimpleTrigger"] = ps.ps4000aSetSimpleTrigger(self.chandle, enable, source_int, threshold_adc,
                                                                     direction_int, delay, autoTrigger_ms)
        assert_pico_ok(self.status["setSimpleTrigger"])

    #######################################################################
    ######################### Signal Generator ############################
    #######################################################################

    def gen_signal(self,
                   offsetVoltage: int = 1000000,  # in µV
                   pkToPk:int=2000000,  # in µV
                   wavetype: str='square',
                   startFrequency: float = 10000,  # in Hz
                   stopFrequency: float = 10000,  # in Hz (same = no sweep)
                   increment: float = 0,  # Hz step in sweep
                   dwelltime: float = 1,  # seconds per step
                   sweeptype: int = 0,
                   operation: int = 0,
                   shots: int = 0,
                   sweeps: int = 0,
                   triggertype: str = 'rising',
                   triggersource: str = 'soft_trig',
                   extInThreshold: int = 0  # ADC counts
                   ):

        """
        Call this function before starting data acquisition.
         This function sets up the signal generator to produce a signal from a list of built-in waveforms.
         If different start and stop frequencies are specified, the oscilloscope will sweep either up, down or up and down.

        :param offsetVoltage: in microvolts
        :param pkToPk: peak-to-peak voltage in microvolts (maxRange = +/-2V)
        :param wavetype: PS4000A_SINE, PS4000A_SQUARE, PS4000A_TRIANGLE, PS4000A_RAMP_UP, PS4000A_RAMP_DOWN, PS4000A_SINC, PS4000A_GAUSSIAN, PS4000A_HALF_SINE, PS4000A_DC_VOLTAGE
        :param startFrequency: the frequency in hertz at which the signal generator should begin
        :param stopFrequency: the frequency in hertz at which the sweep should reverse direction or return to the start frequency (no sweep: startFrequency=stopFrequency)
        :param increment:  Frequency increment per step in Hz.
        :param dwelltime: Time per frequency step in sweep mode (s).
        :param sweeptype: PS4000A_UP, PS4000A_DOWN, PS4000A_UPDOWN
        :param operation:
        :param shots: Number of waveform cycles.
        :param sweeps: Number of sweeps.
        :param triggertype:
        :param triggersource:
        :param extInThreshold: Threshold level for external trigger (in ADC counts).
        :return:
        """
        wavetype_int = _get_wave_type(wavetype)
        triggersource_int = _get_siggen_trigger_source(triggersource)
        triggertype_int = _get_siggen_trigger_type(triggertype)

        self.status["SetSigGenBuiltIn"] = ps.ps4000aSetSigGenBuiltIn(self.chandle, offsetVoltage, pkToPk, wavetype_int,
                                                                     startFrequency, stopFrequency,
                                                                     increment, dwelltime, sweeptype, operation, shots,
                                                                     sweeps, triggertype_int,
                                                                     triggersource_int, extInThreshold)
        assert_pico_ok(self.status["SetSigGenBuiltIn"])

    def siggen_software_control(self, state):
        """
        To use in manual mode.
        This function causes a trigger event, or starts and stops gating. It is used when the signal generator is set to SIGGEN_SOFT_TRIG
        :param state: sets the trigger gate high or low when the trigger type is set to either SIGGEN_GATE_HIGH or SIGGEN_GATE_LOW. Ignored for other trigger types
        :return:
        """
        self.status["sigGenSoftwareControl"] = ps.ps4000aSigGenSoftwareControl(self.chandle, state)


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