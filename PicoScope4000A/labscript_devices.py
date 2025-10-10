from labscript import Device, AnalogOut, AnalogIn
from labscript import LabscriptError, set_passed_properties
from user_devices.logger_config import logger
import numpy as np
import json

class PicoAnalogIn(AnalogIn):
    @set_passed_properties({"connection_table_properties": ["channel_config"]})
    def __init__(self, name, parent_device, connection, enabled:int, coupling:str, range_v:float, analog_offset_v:float, **kwargs):
        """Instantiates an Analog Input.

        Args:
            name (str): python variable to assign this input to.
            parent_device (:obj:`IntermediateDevice`): Device input is connected to.
            enabled: 0 | 1
            coupling: 'ac' | 'dc'
            range_v: [0.01..200]
            analog_offset_v:
        """
        super().__init__(name, parent_device, connection, **kwargs)
        if enabled not in [0, 1]:
            raise ValueError(f"Invalid 'enabled' value: {enabled}. Expected 0 or 1.")

        allowed_channels = ['channel_A', 'channel_B', 'channel_C', 'channel_D', 'channel_E', 'channel_F', 'channel_G', 'channel_H']
        if connection not in allowed_channels:
            raise ValueError(f"Invalid 'connection' value: {connection}. Expected one of {allowed_channels}")
        if coupling not in ['ac', 'dc']:
            raise ValueError(f"Invalid 'coupling' value: {coupling}. Expected one of 'ac', 'dc'.")

        if 0.1 > range_v or range_v > 200:
            raise ValueError(f"Invalid 'range' value: {range_v}. Expected between 0 and 200.")

        self.channel_config = dict(channel=connection, name=name, enabled=enabled, coupling=coupling, range=range_v, analog_offset=analog_offset_v)



class PicoScope4000A(Device):
    description = "PicoScope 4000A (4824) Oscilloscope"
    allowed_children = [PicoAnalogIn]

    @set_passed_properties({"connection_table_properties": ["serial_number",
                                                  "siggen_config",
                                                  "simple_trigger_config",
                                                  "trigger_conditions_config",
                                                  "trigger_directions_config",
                                                  "trigger_properties_config",
                                                  "trigger_delay_config",
                                                  "block_config",
                                                  "stream_config",
                                                  "rapid_block_config",
                                                  "run_mode_config"
                                                  ]}) # use in BLACS_tab
    def __init__(self, name, serial_number=None, **kwargs):
        super().__init__(name, parent_device=None, connection='None', **kwargs)
        self.BLACS_connection = serial_number # i dont know but why not
        self.serial_number = serial_number # if None, opens the first scope found

        self.siggen_config = {}
        self.simple_trigger_config =  {}
        self.trigger_conditions_config = []
        self.trigger_directions_config = []
        self.trigger_properties_config = []
        self.trigger_delay_config = {}
        self.block_config =  {}
        self.stream_config =  {}
        self.rapid_block_config =  {}
        self.run_mode_config = {}

    def add_device(self, device):
        Device.add_device(self, device)

    def set_simple_trigger(self, enabled:int, source:str, threshold_mV:int, direction="rising", delay_samples:int=0, autoTrigger_ms:int=0):
        """
        Simple edge trigger.

        :param enabled: [0, 1]
        :param source: channel
        :param threshold_mV: in milliVolts
        :param direction: the direction in which the signal must move to cause a trigger.
        ['rising', 'falling', 'above', 'below', 'rising_or_falling']
        :param delay_samples: the time, in sample periods, between the trigger occurring and the first sample being taken.
        :param autoTrigger_ms: the number of milliseconds the device will wait if no trigger occurs. If 0, wait infinitely
        """
        self.simple_trigger_config.update(dict(enabled=enabled, source=source, threshold=threshold_mV, direction=direction, delay=delay_samples, autoTrigger_ms=autoTrigger_ms))

    def set_trigger_conditions(self, sources, info:str):
        #fixme:  PicoSDK returned 'PICO_CONDITIONS' by 'pulse_width' source
        """
        :param sources: sources : list of trigger sources
            Allowed values:
            ['channel_A', 'channel_B', 'channel_C', 'channel_D',
             'channel_E', 'channel_F', 'channel_G', 'channel_H',
             'external', 'trigger_aux', 'pulse_width']
        :param info: determines whether the function clears previous conditions: ['clear', 'add']
        """
        self.trigger_conditions_config.append(dict(sources=sources, info=info))

    def set_trigger_direction(self, source:str, direction:str):
        """
        :param source:  ['channel_A', 'channel_B', 'channel_C', 'channel_D',
             'channel_E', 'channel_F', 'channel_G', 'channel_H']
        :param direction :
            ['above', 'above_lower', 'below', 'below_lower',
             'rising', 'rising_lower', 'falling', 'falling_lower',
             'rising_or_falling', 'inside', 'outside',
             'enter', 'exit', 'enter_or_exit',
             'positive_runt', 'negative_runt', 'none']
        """
        self.trigger_directions_config.append(dict(source=source, direction=direction))

    def set_trigger_delay(self, delay_samples:int):
        """delay_samples: in sample periods"""
        self.trigger_delay_config.update(dict(delay=delay_samples))


    def set_trigger_properties(self, source:str, thresholdMode:str, thresholdUpper_mV:float=None, thresholdLower_mV:float=None,
                               thresholdUpperHysteresis_mV:float=None, thresholdLowerHysteresis_mV:float=None,
                                ):
        """
            Per-channel trigger properties. Each dictionary must define in millivolts:
            - thresholdUpper (float)
            - thresholdUpperHysteresis (float)
            - thresholdLower (float)
            - thresholdLowerHysteresis (float)
            - channel (str, one of sources)
            - thresholdMode (str, "level" or "window")
        """
        self.trigger_properties_config.append(dict(threshold_upper=thresholdUpper_mV, threshold_lower=thresholdLower_mV,
                                                   upper_hysteresis=thresholdUpperHysteresis_mV,
                                                   lower_hysteresis=thresholdLowerHysteresis_mV,
                                                   source=source, threshold_mode=thresholdMode))
    #
    #
    # def set_block_sampling(self, noPreTriggerSamples:int, noPostTriggerSamples:int, sampleInterval_ns:float):
    #     """
    #     In block mode, the computer prompts a PicoScope to collect a block of data
    #     into its internal memory. When the oscilloscope has collected the whole block, it signals that it is ready
    #     and then transfers the whole block to the computer's memory through the USB port.
    #
    #     Timebase n in [0..2**32-1], where sampling_interval is 0.0125 * (n+1).
    #     :param noPreTriggerSamples: Number of pre trigger samples
    #     :param noPostTriggerSamples: Number of post trigger samples
    #     :param sampling_interval: in ns to define the timebase.
    #     :return:
    #     """
    #     self.block_config.update(dict(preTriggerSamples=noPreTriggerSamples,
    #                              postTriggerSamples=noPostTriggerSamples,
    #                              sampleInterval=sampleInterval_ns))

    # def set_rapid_block_sampling(self, noPreTriggerSamples:int, noPostTriggerSamples:int, sampleInterval_ns:int, noSegments:int):
    #     """Rapid block mode allows you to sample several waveforms at a time with the minimum time between waveforms.
    #     """
    #     self.rapid_block_config.update(dict(preTriggerSamples=noPreTriggerSamples,
    #                                    postTriggerSamples=noPostTriggerSamples,
    #                                    sampleInterval=sampleInterval_ns,
    #                                    noSegments=noSegments))
    #
    def set_stream_sampling(self,
                            sampleInterval_ns:int, # in ns
                            noPreTriggerSamples:int,
                            noPostTriggerSamples:int,
                            autoStop:int=1,  # default stop after all samples collected
                            downSampleRatio:int=1, # default no downsampling
                            downSampleRatioMode:str='none', # default no downsampling
                            ):

        self.stream_config.update(dict(sampleInterval=sampleInterval_ns,noPreTriggerSamples=noPreTriggerSamples,
                             noPostTriggerSamples=noPostTriggerSamples, autoStop=autoStop, downSampleRatio=downSampleRatio,
                             downSampleRatioMode=downSampleRatioMode))

    # def signal_generator_config(self,
    #                             offsetVoltage_us:int,
    #                             pkToPk_us:int,
    #                             wavetype: str,
    #                             startFrequency: float=10000, # in Hz
    #                             stopFrequency: float=10000, # in Hz (same = no sweep)
    #                             increment: float=0, # Hz step in sweep
    #                             dwelltime: float=1, # seconds per step
    #                             sweeptype: int=0,
    #                             operation: int=0,
    #                             shots: int=0,
    #                             sweeps: int=0,
    #                             triggertype: str='rising',
    #                             triggersource: str='soft_trig',
    #                             extInThreshold: int=0 # ADC counts, not used?
    #                         ):
    #     """
    #     Configure the built-in signal generator for PicoScope 4000/4824 series.
    #
    #     This method sets up a waveform, frequency sweep, and trigger options.
    #     Call this before starting data acquisition, even if using a trigger.
    #
    #     :param offsetVoltage_us: Voltage offset in microvolts to apply to the waveform.
    #     :param pkToPk_us:  Peak-to-peak voltage in microvolts.
    #     :param wavetype:  Waveform type. Allowed:
    #     ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down',
    #      'sinc', 'gaussian', 'half_sine', 'dc_voltage', 'white_noise']
    #     :param startFrequency:  Frequency in Hz at which the waveform starts.
    #     :param stopFrequency:         Frequency in Hz at which sweep reverses or resets.
    #     :param increment:         Frequency step in Hz for sweep mode.
    #     :param dwelltime:         Seconds per frequency step in sweep mode.
    #     :param sweeptype:         PicoScope sweep type (enum).
    #     :param operation:
    #     :param shots:         Number of waveform shots (0 = continuous).
    #     :param sweeps:        Number of sweeps (0 = infinite).
    #     :param triggertype:        Trigger edge type. Allowed: ['rising', 'falling', 'gate_high', 'gate_low']
    #     :param triggersource:        Trigger source. Allowed: ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
    #     :param extInThreshold: External input threshold in ADC counts.
    #     :return:
    #     """
    #
    #     wave_types = ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down', 'sinc', 'gaussian', 'half_sine',
    #                   'dc_voltage', 'white_noise', 'max_wave_types']
    #     trig_types = ['rising', 'falling', 'gate_high', 'gate_low']
    #     trig_sources = ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
    #
    #     if wavetype not in wave_types:
    #         raise ValueError(f"Invalid wavetype: {wavetype}. Allowed values: {wave_types}")
    #     if triggertype not in trig_types:
    #         raise ValueError(f"Invalid triggertype: {triggertype}. Allowed values: {trig_types}")
    #     if triggersource not in trig_sources:
    #         raise ValueError(f"Invalid triggersource: {triggersource}. Allowed values: {trig_sources}")
    #
    #
    #     self.siggen_config.update(dict(offsetVoltage=offsetVoltage_us, pkToPk=pkToPk_us, wavetype=wavetype,
    #                               startFrequency=startFrequency, stopFrequency=stopFrequency,
    #                               increment=increment, dwelltime=dwelltime, sweeptype=sweeptype,
    #                               operation=operation, shots=shots, sweeps=sweeps,triggertype=triggertype,
    #                               triggersource=triggersource, extInThreshold=extInThreshold))

    def run_mode(self, mode:str):
        self.run_mode_config.update(dict(active_mode=mode))

    def generate_code(self, hdf5_file):
        super().generate_code(hdf5_file)
        group = hdf5_file.create_group(f'/devices/{self.name}')

        #  -------------------------------------- Save channel configs -------------------------------------------------
        channels_dtypes = [
            ('channel', 'S32'),
            ('name', 'S32'),
            ('enabled', np.uint8),
            ('coupling', 'S32'),
            ('range', np.float32),
            ('offset', np.float32),
        ]
        input_configs_table = np.empty(len(self.child_devices), dtype=channels_dtypes)

        for i, device in enumerate(self.child_devices):
            if isinstance(device, PicoAnalogIn):
                cfg = device.channel_config
                input_configs_table[i]['channel'] = cfg['channel']
                input_configs_table[i]['name'] = cfg['name']
                input_configs_table[i]['enabled'] = cfg['enabled']
                input_configs_table[i]['coupling'] = cfg['coupling']
                input_configs_table[i]['range'] = cfg['range']
                input_configs_table[i]['offset'] = cfg['analog_offset']
            else:
                raise LabscriptError(f"Unsupported child device type: {type(device)}")

        group.create_dataset("channels_configs", data=input_configs_table)

        # ------------------------------------------- Save triggers -------------------------------------------
        trig_group = group.create_group('triggers')

        # Simple trigger
        if self.simple_trigger_config:
            simple_trigger_dtypes = np.dtype([
                ('enabled', np.uint8),
                ('source', 'S32'),
                ('threshold', np.uint32),
                ('direction', 'S32'),
                ('delay', np.uint32),
                ('autoTrigger_ms', np.uint32)
            ])
            cfg = self.simple_trigger_config
            row = (
                cfg['enabled'],
                cfg['source'],
                cfg['threshold'],
                cfg['direction'],
                cfg['delay'],
                cfg['autoTrigger_ms']
            )
            simple_trigger_table = np.array([row], dtype=simple_trigger_dtypes)
            # simple_trigger_table = np.array([self.simple_trigger_config], dtype=simple_trigger_dtypes)
            trig_group.create_dataset("simple_trigger", data=simple_trigger_table)

        # Advanced Trigger
        if self.trigger_conditions_config:
            trig_group.create_dataset(
                "trigger_conditions",
                data=np.bytes_(json.dumps(self.trigger_conditions_config))
            )

        if self.trigger_directions_config:
            directions_dtypes = np.dtype([('source', 'S32'),('direction', 'S32')])
            trigger_directions_table = np.empty(len(self.trigger_directions_config), dtype=directions_dtypes)
            for i, dir in enumerate(self.trigger_directions_config):
                trigger_directions_table[i] = (
                    dir['source'], dir['direction']
                )
            trig_group.create_dataset(
                "trigger_directions",
                data=trigger_directions_table
            )

        if self.trigger_properties_config:
            properties_dtypes = np.dtype([
                ('thresholdUpper', np.float32),
                ('thresholdLower', np.float32),
                ('thresholdUpperHysteresis', np.float32),
                ('thresholdLowerHysteresis', np.float32),
                ('source', 'S32'),
                ('thresholdMode', 'S32'),
            ])
            trigger_properties_table = np.empty(len(self.trigger_properties_config), dtype=properties_dtypes)
            for i, prop in enumerate(self.trigger_properties_config):
                trigger_properties_table[i] = (
                    prop['threshold_upper'],
                    prop['threshold_lower'],
                    prop['upper_hysteresis'],
                    prop['lower_hysteresis'],
                    prop['source'],
                    prop['threshold_mode']
                )
            trig_group.create_dataset("trigger_properties", data=trigger_properties_table)

        if self.trigger_delay_config:
            trig_group.create_dataset(
                "trigger_delay",
                data=str(self.trigger_delay_config.get("active_mode", "None"))
            )

        # ------------------------------------------- Save sampling modes -------------------------------------------
        if self.block_config is not None:
            group.create_dataset('block_config', data=np.bytes_(json.dumps(self.block_config)))

        if self.rapid_block_config is not None:
            group.create_dataset('rapid_block_config', data=np.bytes_(json.dumps(self.rapid_block_config)))

        if self.stream_config is not None:
            group.create_dataset('stream_config', data=np.bytes_(json.dumps(self.stream_config)))

        # ------------------------------------------- Save siggen configuration -------------------------------------------
        if self.siggen_config is not None:
            group.create_dataset('siggen_config', data=np.bytes_(json.dumps(self.siggen_config)))

        if self.run_mode_config is not None:
            group.attrs['active_mode'] = str(self.run_mode_config.get("active_mode", "None"))

