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


class PicoScopeWorker(Worker):

    def init(self):

        # convert serial number to bytes, or None if using first device
        if hasattr(self, "serial_number") and self.serial_number:
            self.serial = self.serial_number.encode()
        else:
            self.serial = None  # will open the first picoscope found

        self.pico = PicoScope(self.serial, self.no_inputs)

        self.active_mode = None
        self.block_config = None
        self.rapid_config = None
        self.stream_config = None

        self.h5_file = None
        self.device_name = None

    def shutdown(self):
        self._stop_threads = True
        self.pico.stop_unit()
        self.pico.close_unit()

    def program_manual(self, front_panel_values):
        pass

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        """Configure the streaming, triggering, channels."""
        rich_print(f"---------- Begin transition to Buffered: ----------", color=BLUE)
        self.h5_file = h5_file
        self.device_name = device_name

        with h5py.File(h5_file, "r") as f:
            group = f[f"/devices/{device_name}"]

            # 0. Configure channels
            channel_configs = group["channel_configs"][:]
            for ch in channel_configs:
                self.pico.set_channel(ch["channel"], ch["coupling"], ch["range"], ch["enabled"], ch["offset"])

            # 1. Configure Trigger (if defined)
            trig_group = group["triggers"]

            if "simple_trigger" in trig_group:
                simple_trigger = trig_group["simple_trigger"][:]
                self.pico.set_simple_edge_trigger(simple_trigger["enabled"],
                                                  simple_trigger["source"],
                                                  simple_trigger["threshold"],
                                                  simple_trigger["direction"],
                                                  simple_trigger["delay"],
                                                  simple_trigger["autoTrigger_ms"])

            if "trigger_conditions" in trig_group:
                trigger_conditions = json.loads(trig_group["trigger_conditions"][()].decode())
                for cond in trigger_conditions:# todo: if pulse width, add PulseWidthQualifierConditions/Properties
                    self.pico.set_trigger_conditions(cond["sources"], cond["info"])

            if "trigger_directions" in trig_group:
                trigger_directions = trig_group["trigger_directions"][:]
                self.pico.set_trigger_channel_directions(trigger_directions)

            if "trigger_properties" in trig_group:
                trigger_properties = trig_group["trigger_properties"][:]
                self.pico.set_trigger_channel_properties(trigger_properties)

            if "trigger_delay" in trig_group:
                trigger_delay = trig_group["trigger_delay"][:][0]
                self.pico.set_trigger_delay(trigger_delay)

            # 2. Configure active mode
            self.active_mode = group.attrs["active_mode"]

            # Save other modes configuration for future use in manual mode
            if "block_config" in group:
                self.block_config = json.loads(group["block_config"][()].decode())
            if "rapid_block_config" in group:
                self.rapid_config = json.loads(group["rapid_block_config"][()].decode())
            if "stream_config" in group:
                self.stream_config = json.loads(group["stream_config"][()].decode())


            if self.active_mode == "stream" and self.stream_config:
                self.pico.run_stream(
                    self.stream_config["sampleInterval_ns"],
                    self.stream_config["noPreTriggerSamples"],
                    self.stream_config["noPostTriggerSamples"],
                    self.stream_config["autoStop"],
                    self.stream_config["downSampleRatio"],
                    self.stream_config["downSampleRatioMode"],
                )
            if self.active_mode == "block" and self.block_config:
                self.pico.run_block(
                    self.block_config["noPreTriggerSamples"],
                    self.block_config["noPostTriggerSamples"],
                    self.block_config["sampleInterval_ns"]
                )
            if self.active_mode == "rapid" and self.rapid_config:
                self.pico.run_rapid()

            # 2. Configure Sig gen
            if "siggen_config" in group:
                siggen_config = json.loads(group["siggen_config"][()].decode())
                self.pico.gen_signal(
                    siggen_config["offsetVoltage"],
                    siggen_config["pkToPk"],
                    siggen_config["wavetype"],
                    siggen_config["startFrequency"],
                    siggen_config["stopFrequency"],
                    siggen_config["increment"],
                    siggen_config["dwelltime"],
                    siggen_config["sweeptype"],
                    siggen_config["operation"],
                    siggen_config["shots"],
                    siggen_config["sweeps"],
                    siggen_config["triggertype"],
                    siggen_config["triggersource"],
                    siggen_config["extInThreshold"],
                )

        rich_print(f"---------- End transition to Buffered: ----------", color=BLUE)
        return

    def transition_to_manual(self):
        def writing_thread():
            while not self.pico.fetch_ready and not self._stop_threads:
                time.sleep(1)

            # Save fetched data to hdf5 file
            with h5py.File(self.h5_file, "r+") as f:
                group = f[f"/devices/{self.device_name}"]

                # Collect buffers into matrix, columns=channels, rows=samples
                channel_names = list(self.pico.complete_buffers.keys())
                data = np.vstack([self.pico.adc2mv(ch, self.pico.complete_buffers[ch]) for ch in channel_names])

                group.create_dataset(
                    name="stream_sampling",
                    data=data,
                    dtype=np.float32,
                    compression="gzip"
                )
                group["stream_sampling"].attrs["channels"] = json.dumps(channel_names)

                times = np.linspace(0, (self.pico.total_samples - 1) * self.pico.actual_sample_interval, self.pico.total_samples)
                for buff in self.self.pico.complete_buffers.values():
                    plt.plot(times, buff)
                plt.show()

                if self.pico.complete_max_buffers != {}:
                    # Collect buffers into matrix, columns=channels, rows=samples
                    channel_names = list(self.pico.complete_max_buffers.keys())
                    data = np.vstack([self.pico.complete_max_buffers[ch] for ch in channel_names])

                    group.create_dataset(
                        name="stream_sampling_max",
                        data=data,
                        dtype=np.float32,
                        compression="gzip"
                    )
                    group["stream_sampling_max"].attrs["channels"] = json.dumps(channel_names)

        writer = threading.Thread(target=writing_thread, daemon=True)
        writer.start()
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()


BLUE = '#66D9EF'

class PicoScope:

    def __init__(self, serial_number, no_inputs):
        self.status = {}
        self.chandle = ctypes.c_int16()

        self.enabled_channels = []
        self.channel_ranges = {} # store each channel [0..7] vRange [0..13]

        self.buffers = {}
        self.max_buffers = {} # if downsample mode is 'aggregate'
        self.complete_buffers = {}
        self.complete_max_buffers = {}
        self.max_samples = None
        self.total_samples = None
        self.no_buffers = None

        self.auto_stop_outer = None
        self.was_called_back = None

        self.fetch_ready = False
        self._stop_threads = False

        # Open device
        self.open_unit(serial_number)
        self.device_info = self._get_unit_info()
        print(f"[PicoScope] INFO: {self.device_info}")

        self.resolution = self._get_device_resolution()
        self.maxADC = (2 ** (self.resolution - 1)) - 1  # symmetric
        self.actual_sample_interval = None
        self.next_sample = 0
        self.auto_stop = False


    #######################################################################
    ################# Device Management ###################################
    #######################################################################

    def open_unit(self, serial_number):
        no_scopes, serials, _ = self._enumerate_units_connected()
        print(f"All connected Picoscopes: {no_scopes} with serial numbers: {serials}")

        self.status["openUnit"] = ps.OpenUnit(ctypes.byref(self.chandle), serial_number)
        assert_pico_ok(self.status["openUnit"])
        print("[PicoScope] PicoScope connected, chandle:", self.chandle.value)

    def close_unit(self):
        print(f"[PicoScope] {self.status}")
        self.status["close"] = ps.ps4000aCloseUnit(self.chandle)

    def stop_unit(self):
        self._stop_threads = True
        self.status["stop"] = ps.ps4000aStop(self.chandle)

    #######################################################################
    ########################### Queries ###################################
    #######################################################################
    def _get_device_resolution(self):
        resolution = ctypes.c_int32()
        self.status["GetDeviceResolution"] = ps.ps4000aGetDeviceResolution(self.chandle, ctypes.byref(resolution))
        assert_pico_ok(self.status["GetDeviceResolution"])
        return resolution.value

    def _enumerate_units_connected(self):
        count = ctypes.c_int16()
        serials = ctypes.c_int8()
        serialLth = ctypes.c_int16()

        self.status["enumerateUnits"] = ps.ps4000aEnumerateUnits(ctypes.byref(count), ctypes.byref(serials),
                                                                 ctypes.byref(serialLth))
        assert_pico_ok(self.status["enumerateUnits"])

        return count.value, serials.value, serialLth.value

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

    def _get_unit_info(self):
        """Fetch device info (batch + serial, variant, etc.)."""
        string_buffer_len = 64
        string_buffer = ctypes.create_string_buffer(string_buffer_len)
        required = ctypes.c_int16()

        self.status["getUnitInfo"] = ps.ps4000aGetUnitInfo(
            self.chandle,
            string_buffer,
            string_buffer_len,
            ctypes.byref(required),
            ps.PICO_INFO["PICO_BATCH_AND_SERIAL"]
        )
        assert_pico_ok(self.status["getUnitInfo"])
        return string_buffer.value.decode("utf-8")

    def _find_best_timebase(self, desired_no_samples, desired_interval_ns, segment_index=0):
        """
        Automatically find the best timebase.

        Parameters
        ----------
        desired_no_samples (int): Number of samples you want to capture.
        desired_interval_ns (float): Desired time interval between samples in milliseconds.
        segment_index (int): Memory segment to use (default 0).

        Returns
        -------
        best_timebase (int):  Timebase code to use.
        actual_interval_ns (float): Actual achievable time interval per sample.
        max_samples(int): Maximum number of samples available for this timebase.
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
            self.enabled_channels.append(channel_int)

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
        self.status[f"setDataBuffer_{channel}"] = ps.ps4000aSetDataBuffer(self.chandle, channel, ctypes.byref(buffer), bufferLth,
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

        self.status[f"setMaxMinDataBuffer_{channel}"] = ps.ps4000aSetDataBuffer(self.chandle, channel, ctypes.byref(bufferMax),
                                                                     ctypes.byref(bufferMin),
                                                                     bufferLth, segmentIndex, mode)
        assert_pico_ok(self.status[f"setMaxMinDataBuffer_{channel}"])

    def run_stream(self,
                   sampleInterval_ns: int,
                   maxPreTriggerSamples: int,
                   maxPostTriggerSamples: int,
                   autoStop: int = 1,  # stop after all samples collected
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

        self.fetch_ready = False

        # prepare arguments
        c_sampleInterval = ctypes.c_int(sampleInterval_ns)
        timeUnits = ps.PS4000A_TIME_UNITS['PS4000A_NS']  # Nanoseconds
        downSampleRatioMode_int = _get_ratio_mode(downSampleRatioMode)

        # Define buffers
        self.max_samples = maxPreTriggerSamples + maxPostTriggerSamples
        buffer_size, no_buffers = _choose_buffer_size(self.max_samples)
        overviewBufferSize =  ctypes.c_int(buffer_size)

        # Allocate and register working buffers and allocate complete buffers
        for ch in self.enabled_channels:
            self.buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16)
            self.complete_buffers[ch] = np.zeros(shape=self.total_samples, dtype=np.int16)

            if downSampleRatioMode == 'aggregate':
                self.max_buffers[ch] = np.zeros(shape=buffer_size, dtype=np.int16)
                self.complete_max_buffers[ch] = np.zeros(shape=self.total_samples, dtype=np.int16)

                self.set_max_min_data_buffers(
                    channel=ch,
                    bufferMax=self.max_buffers[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    bufferMin=self.buffers[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    bufferLth=buffer_size,
                    segmentIndex=0,
                    mode=downSampleRatioMode_int
                )
            else:
                self.set_data_buffer(
                    channel=ch,
                    buffer=self.buffers[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    bufferLth=buffer_size,
                    segmentIndex=0,
                    mode=downSampleRatioMode_int
                )

        # Configure streaming sampling mode
        self.status["runStreaming"] = ps.ps4000aRunStreaming(
            self.chandle, ctypes.byref(c_sampleInterval), timeUnits, maxPreTriggerSamples,
            maxPostTriggerSamples, autoStop, downSampleRatio, downSampleRatioMode_int, overviewBufferSize)
        assert_pico_ok(self.status["runStreaming"])

        self.actual_sample_interval = c_sampleInterval.value

        # Prepare callback
        self.next_sample = 0
        self.auto_stop_outer = False
        self.was_called_back = False

        def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
            """
            This callback function receives a notification when streaming-mode data is ready.
            Your callback function should do nothing more than copy the data to another buffer within your
            application. To maintain the best application performance, the function should return as quickly as
            possible without attempting to process or display the data
            :param handle:
            :param noOfSamples: The number of samples to collect.
            :param startIndex: an index to the first valid sample in the working buffer
            :param overflow: returns a set of flags that indicate whether an overvoltage has occurred on any of the channels.
            :param triggerAt: an index to the buffer indicating the location of the trigger point relative to startIndex.
                This parameter is valid only when triggered is non-zero.
            :param triggered: a flag indicating whether a trigger occurred. If non-zero, a trigger occurred at the location indicated by triggerAt
            :param autoStop:  the flag that was set in the call to ps4000aRunStreaming()
            :param param: a void pointer passed from ps4000aGetStreamingLatestValues(). The callback function can write to this
                location to send any data, such as a status flag, back to the application.
            :return:
            """
            self.was_called_back = True

            # Copy data from working buffers to the complete buffers with corresponding channel serial number.
            dest_end = self.next_sample + noOfSamples
            source_end = startIndex + noOfSamples

            for chan, buff in self.buffers.items():
                self.complete_buffers[chan][self.next_sample:dest_end] = buff[startIndex:source_end]

            self.next_sample += noOfSamples
            if autoStop:
                self.auto_stop_outer = True


        c_lpReady = ps.StreamingReadyType(streaming_callback)

        # Start a thread to fetch data from the driver in a loop, copying it out from registered buffers into complete ones.
        def fetching_thread():
            while self.next_sample < self.total_samples and not self.auto_stop_outer and not self._stop_threads:
                self.was_called_back = False
                self.status["getStreamingValues"] = ps.ps4000aGetStreamingLatestValues(self.chandle, c_lpReady, None)
                if not self.was_called_back:
                    time.sleep(0.01)

            self.fetch_ready = True

        fetcher = threading.Thread(target=fetching_thread, daemon=True)
        fetcher.start()

    def run_block(self, preTriggerSamples, postTriggerSamples, desiredInterval):
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
        logger.info("Rapid block sampling mode is NOT implemented yet")

    def adc2mv(self, ch, buffer_adc):
        return adc2mV(buffer_adc, self.channel_ranges[ch], self.maxADC)

    #######################################################################
    ############################# Triggers ################################
    #######################################################################

    def set_trigger_conditions(self, sources, info:str):
        """
         conditions: list of sources:int
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

    def set_trigger_channel_properties(self, properties):
        ps_properties = []
        for prop in properties:
            ch_int = _get_channel_number(prop["channel"])
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

    def set_trigger_delay(self, delay):
        """delay in sample periods"""
        self.status["setTriggerDelay"] = ps.ps4000aSetTriggerDelay(self.chandle, delay)

    def set_simple_edge_trigger(self,
                                enable: int,  # 0 = disable
                                source: str,
                                threshold: float,  # in milliVolts
                                direction: str,
                                delay: int, # in sample periods
                                autoTrigger_ms: int = 0
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
                   wavetype: int = 1,
                   startFrequency: float = 10000,  # in Hz
                   stopFrequency: float = 10000,  # in Hz (same = no sweep)
                   increment: float = 0,  # Hz step in sweep
                   dwelltime: float = 1,  # seconds per step
                   sweeptype: int = 0,
                   operation: int = 0,
                   shots: int = 0,
                   sweeps: int = 0,
                   triggertype: int = 0,
                   triggersource: int = 1,
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

        self.status["SetSigGenBuiltIn"] = ps.ps4000aSetSigGenBuiltIn(self.chandle, offsetVoltage, pkToPk, wavetype,
                                                                     startFrequency, stopFrequency,
                                                                     increment, dwelltime, sweeptype, operation, shots,
                                                                     sweeps, triggertype,
                                                                     triggersource, extInThreshold)
        assert_pico_ok(self.status["SetSigGenBuiltIn"])

    def siggen_software_control(self, state):
        """
        This function causes a trigger event, or starts and stops gating. It is used when the signal generator is set to SIGGEN_SOFT_TRIG
        :param state: sets the trigger gate high or low when the trigger type is set to either SIGGEN_GATE_HIGH or SIGGEN_GATE_LOW. Ignored for other trigger types
        :return:
        """
        self.status["sigGenSoftwareControl"] = ps.ps4000aSigGenSoftwareControl(self.chandle, state)


#######################################################################
####################### Helpers #######################################
#######################################################################
# Map the readable values into PicoScope contants
def _get_channel_number(channel_name: str) -> int:
    if channel_name.endswith('external'): return 8
    if channel_name.endswith('aux'): return 9
    if channel_name.lower().endswith('pulse_width'): return 0x10000000

    last_ch = channel_name[-1].upper()
    if last_ch.isdigit():
        ch_num = int(last_ch)
        if ch_num in range(8):
            return int(last_ch)

    letter_map = {c: i for i, c in enumerate("ABCDEFGH")}
    if last_ch in letter_map:
        return letter_map[last_ch]

    raise ValueError(
        f"Invalid channel name: {channel_name}. "
        f"Expected suffix A..H or 0..7 or 'external', 'aux', or 'width_source'."
    )


def _get_direction(direction: str) -> int:
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
    match ratio_mode.lower():
        case 'none':
            return 0
        case 'aggregate':
            return 1
        case 'decimate':
            return 2
        case 'average':
            return 4
        case _:
            raise ValueError(
                f"Invalid ratio_mode: {ratio_mode}. Allowed values: 'none', 'aggregate', 'decimate', 'average'")


def _get_threshold_mode(threshold_mode: str) -> int:
    if threshold_mode.lower() == 'level':
        return 0
    elif threshold_mode.lower() == 'window':
        return 1
    else:
        raise ValueError(f"Invalid threshold mode: {threshold_mode}. Allowed: 'level', 'window'")


def _get_wave_type(wave_type: str) -> int:
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

    wave_type_upper = wave_type.upper()

    for index, entry in enumerate(wave_types):
        if wave_type_upper == entry:
            return index

    raise ValueError(f"Invalid Wave type: {wave_type}")


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
    if info == 'clear':
        return 1
    elif info == 'add':
        return 2
    else:
        raise ValueError(f"Invalid info: {info}. Allowed values: 'clear', 'add'")


def _get_siggen_trigger_type(trig_type: str) -> int:
    trig_types = ['rising', 'falling', 'gate_high', 'gate_low']
    for index, entry in enumerate(trig_types):
        if type == entry:
            return index

    raise ValueError(f"Invalid trigger type: {trig_type}. Allowed values: {trig_types}")


def _get_siggen_trigger_source(source: str) -> int:
    trig_sources = ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
    for index, entry in enumerate(trig_sources):
        if source == entry:
            return index

    raise ValueError(f"Invalid trigger source: {source}. Allowed values: {trig_sources}")


def _get_coupling(coupling: str) -> int:
    if coupling.lower() == 'ac':
        return 0
    elif coupling.lower() == 'dc':
        return 1
    else:
        raise ValueError(f"Invalid coupling: {coupling}. Allowed values: 'ac', 'dc'")

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