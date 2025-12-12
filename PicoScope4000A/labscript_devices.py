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
                                                            "is_4000a",
                                                  "siggen_config",
                                                  "simple_trigger_config",
                                                  "trigger_conditions_config",
                                                  "trigger_directions_config",
                                                  "trigger_properties_config",
                                                  "trigger_delay_config",
                                                  "stream_config",
                                                  ],# use in BLACS_tab
                            "device_properties":[
                                "siggen_config",
                                "simple_trigger_config",
                                "trigger_conditions_config",
                                "trigger_directions_config",
                                "trigger_properties_config",
                                "trigger_delay_config",
                                "stream_config",
                            ]})

    def __init__(self, name, serial_number=None, is_4000a=True, **kwargs):
        super().__init__(name, parent_device=None, connection='None', **kwargs)
        self.BLACS_connection = serial_number # i dont know but why not
        self.serial_number = serial_number # if None, opens the first scope found

        self.siggen_config = {}
        self.simple_trigger_config =  {}
        self.trigger_conditions_config = []
        self.trigger_directions_config = []
        self.trigger_properties_config = []
        self.trigger_delay_config = {}
        self.stream_config =  {}
        self.is_4000a = is_4000a

    def add_device(self, device):
        Device.add_device(self, device)

    def set_simple_trigger(self, source:str, threshold:int, direction="rising", delay_samples:int=0, auto_trigger_s:int=0):
        """
        Simple edge trigger.
        :param source: channel
        :param threshold: in Volts
        :param direction: the direction in which the signal must move to cause a trigger.
        ['rising', 'falling', 'above', 'below', 'rising_or_falling']
        :param delay_samples: the time, in sample periods, between the trigger occurring and the first sample being taken.
        :param auto_trigger_s: the number of seconds the device will wait if no trigger occurs. If 0, wait infinitely
        """
        self.simple_trigger_config.update(dict(source=source, threshold=threshold, direction=direction, delay=delay_samples, auto_trigger=auto_trigger_s))

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

    def set_stream_sampling(self,
                            sampling_rate:float | int, #in Hz
                            no_post_trigger_samples:int,
                            downsample_ratio:int=1, # default no downsampling
                            downsample_ratio_mode:str='none', # default no downsampling
                            ):
        sample_interval_ns = int(1 / sampling_rate * 1e9)

        self.stream_config.update(dict(sample_interval=sample_interval_ns,
                                       no_post_trigger_samples=int(no_post_trigger_samples),
                                       downsample_ratio=downsample_ratio,
                                       downsample_ratio_mode=downsample_ratio_mode))

    def signal_generator_config(self,
                                offset_voltage:int, # in volts
                                pk2pk:int, # in volts
                                wave_type: str,
                                start_frequency: float=10000, # in Hz
                                stop_frequency: float=10000, # in Hz (same = no sweep)
                                increment: float=0, # Hz step in sweep
                                dwell_time: float=1, # seconds per step
                                sweep_type: int=0,
                                operation: int=0,
                                shots: int=0,
                                sweeps: int=0,
                                trigger_type: str='rising',
                                trigger_source: str='soft_trig',
                                ext_in_threshold: int=0 # ADC counts, not used?
                            ):
        """
        Configure the built-in signal generator for PicoScope 4000/4824 series.

        This method sets up a waveform, frequency sweep, and trigger options.
        Call this before starting data acquisition, even if using a trigger.

        :param offset_voltage: Voltage offset in volts to apply to the waveform.
        :param pk2pk:  Peak-to-peak voltage in volts.
        :param wave_type:  Waveform type. Allowed:
        ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down',
         'sinc', 'gaussian', 'half_sine', 'dc_voltage', 'white_noise']
        :param start_frequency:  Frequency in Hz at which the waveform starts.
        :param stop_frequency:         Frequency in Hz at which sweep reverses or resets.
        :param increment:         Frequency step in Hz for sweep mode.
        :param dwell_time:         Seconds per frequency step in sweep mode.
        :param sweep_type:         PicoScope sweep type (enum).
        :param operation:
        :param shots:         Number of waveform shots (0 = continuous).
        :param sweeps:        Number of sweeps (0 = infinite).
        :param trigger_type:        Trigger edge type. Allowed: ['rising', 'falling', 'gate_high', 'gate_low']
        :param trigger_source:        Trigger source. Allowed: ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
        :param ext_in_threshold: External input threshold in ADC counts.
        :return:
        """

        wave_types = ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down', 'sinc', 'gaussian', 'half_sine',
                      'dc_voltage', 'white_noise', 'max_wave_types']
        trig_types = ['rising', 'falling', 'gate_high', 'gate_low']
        trig_sources = ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']

        if wave_type not in wave_types:
            raise ValueError(f"Invalid wavetype: {wave_type}. Allowed values: {wave_types}")
        if trigger_type not in trig_types:
            raise ValueError(f"Invalid triggertype: {trigger_type}. Allowed values: {trig_types}")
        if trigger_source not in trig_sources:
            raise ValueError(f"Invalid triggersource: {trigger_source}. Allowed values: {trig_sources}")


        self.siggen_config.update(dict(offset_voltage=offset_voltage, pk2pk=pk2pk, wave_type=wave_type,
                                  start_frequency=start_frequency, stop_frequency=stop_frequency,
                                  increment=increment, dwell_time=dwell_time, sweep_type=sweep_type,
                                  operation=operation, shots=shots, sweeps=sweeps,trigger_type=trigger_type,
                                  trigger_source=trigger_source, ext_in_threshold=ext_in_threshold))

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
                ('source', 'S32'),
                ('threshold', np.int32),
                ('direction', 'S32'),
                ('delay', np.uint32),
                ('auto_trigger', np.uint32)
            ])
            cfg = self.simple_trigger_config
            row = (
                cfg['source'],
                cfg['threshold'],
                cfg['direction'],
                cfg['delay'],
                cfg['auto_trigger']
            )
            simple_trigger_table = np.array([row], dtype=simple_trigger_dtypes)
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
                data=str(self.trigger_delay_config.get("delay", "None"))
            )

        # ------------------------------------------- Save sampling mode -------------------------------------------

        if self.stream_config is not None:
            group.create_dataset('stream_config', data=np.bytes_(json.dumps(self.stream_config)))

        # ------------------------------------------- Save siggen configuration -------------------------------------------
        if self.siggen_config is not None:
            group.create_dataset('siggen_config', data=np.bytes_(json.dumps(self.siggen_config)))


