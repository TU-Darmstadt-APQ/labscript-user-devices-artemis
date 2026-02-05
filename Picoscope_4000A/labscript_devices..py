from labscript import Device, AnalogOut, AnalogIn
from labscript import LabscriptError, set_passed_properties
from user_devices.logger_config import logger
import numpy as np
import json

class PicoAnalogIn(AnalogIn):
    @set_passed_properties({"connection_table_properties": ["channel_connection"]})
    def __init__(self, name, parent_device, connection, enabled:bool, coupling:str, range_v:float, analog_offset_v:float, **kwargs):
        """ Represents a single analog input channel on a PicoScope device.

        Args:
            name (str): The Labscript variable name for this input channel.
            parent_device (str): The parent PicoScope device instance. (name of the PicoScope)
            enabled (bool):
            coupling (str): 'ac' | 'dc'
            range_v (float): Full-scale input voltage range in volts [0.01..200]
            analog_offset_v (float): Analog offset value for the input channel, in volts.
        """
        super().__init__(name, parent_device, connection, **kwargs)
        allowed_channels = ['channel_A', 'channel_B', 'channel_C', 'channel_D', 'channel_E', 'channel_F', 'channel_G', 'channel_H']
        if connection not in allowed_channels:
            raise ValueError(f"Invalid 'connection' value: {connection}. Expected one of {allowed_channels}")
        if coupling not in ['ac', 'dc']:
            raise ValueError(f"Invalid 'coupling' value: {coupling}. Expected one of 'ac', 'dc'.")

        allowed_ranges = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
        if range_v not in allowed_ranges:
            raise ValueError(f"Invalid 'range' value: {range_v}. Expected between 0 and 200.")

        self.enabled = enabled
        self.range_v = range_v
        self.channel_config = dict(channel=connection, name=name, enabled=enabled, coupling=coupling, range=range_v, analog_offset=analog_offset_v)
        self.channel_connection = dict(channel=connection, name=name)

class PicoScope4000A(Device):
    description = "PicoScope 4000A (4824) Oscilloscope"
    allowed_children = [PicoAnalogIn]

    @set_passed_properties({"connection_table_properties": ["serial_number",
                                                            "is_4000a"],
                            "device_properties":[
                                "siggen_config",
                                "simple_trigger_config",
                                "trigger_conditions_config",
                                "trigger_directions_config",
                                "trigger_properties_config",
                                "trigger_delay_config",
                                "stream_config",
                                "block_config"
                            ]})

    def __init__(self, name, serial_number=None, is_4000a=True, **kwargs):
        """
        The Picoscope 4000(A) object.
        :param name (str): User defined name
        :param serial_number (str): Serial number of the device e.g. "HO248/173"
        :param is_4000a (boolean): True, if the Picoscope from 4000A series, False if of 4000 Series
        :param kwargs:
        """
        super().__init__(name, parent_device=None, connection='None', **kwargs)
        self.BLACS_connection = serial_number
        self.serial_number = serial_number # if None, opens the first scope found
        self.is_4000a = is_4000a

        self.siggen_config = {}
        self.trigger_conditions_config = []
        self.trigger_directions_config = []
        self.trigger_properties_config = []

        self.simple_trigger_config =  {}
        self.trigger_delay_config = {}
        self.stream_config =  {}
        self.block_config = {}

    def add_device(self, device):
        Device.add_device(self, device)

    def set_simple_trigger(self, source:str, threshold:float, direction="rising", delay_samples:int=0, auto_trigger_s:float=0):
        """
        Defines parameters of simple edge/level trigger.
        :param source (str): channel e.g. "channel_A", "channel_H"
        :param threshold (float): in Volts
        :param direction (str): the direction in which the signal must move to cause a trigger.
        ['rising', 'falling', 'above', 'below', 'rising_or_falling']
        :param delay_samples (int): the time, in sample periods, between the trigger occurring and the first sample being taken.
        :param auto_trigger_s (int): the number of seconds the device will wait if no trigger occurs. If 0, wait infinitely
        """
        self.simple_trigger_config.update(dict(source=source, threshold=threshold, direction=direction, delay=delay_samples, auto_trigger=auto_trigger_s))

    def set_stream_sampling(self,
                            sampling_rate:float | int, #in Hz
                            no_pre_trigger_samples:int,
                            no_post_trigger_samples:int,
                            downsample_ratio:int=1, # default no downsampling
                            downsample_ratio_mode:str='none', # default no downsampling
                            ):
        """ Obligatory setting of stream parameters.
        :param sampling_rate (float|int): sampling rate in Hz
        :param no_post_trigger_samples (int): number of samples to collect. NOTE: it can also contain the pre-trigger samples (less than 1000).
        :param downsample_ratio (int): downsample ratio. Default=1 , meaning no downsampling.
        :param downsample_ratio_mode (str): 'none' means no downsampling. Allowed values: 'none', 'aggregate', 'decimate', 'average'. NOTE: only 'none' is supported now.
        Since the current implementation is based on stream sampling, the downsample can only be extended to 'aggregate' mode, which requires two buffers per channel.
        """
        sample_interval_ns = int(round(1e9 * 1 / sampling_rate)) # int

        self.stream_config.update(dict(sample_interval=sample_interval_ns,
                                       no_pre_trigger_samples=no_pre_trigger_samples,
                                       no_post_trigger_samples=no_post_trigger_samples,
                                       downsample_ratio=downsample_ratio,
                                       downsample_ratio_mode=downsample_ratio_mode))

    def set_block_sampling(self,
                           sampling_rate:float | int,
                           no_pre_trigger_samples:int,
                           no_post_trigger_samples:int,
                           downsample_ratio:int=1,
                           downsample_ratio_mode:str='none'):
        sample_interval_ns = int(round(1e9 * 1 / sampling_rate))  # int

        self.block_config.update(dict(sample_interval=sample_interval_ns,
                                      no_pre_trigger_samples=no_pre_trigger_samples,
                                      no_post_trigger_samples=no_post_trigger_samples,
                                      downsample_ratio=downsample_ratio,
                                      downsample_ratio_mode=downsample_ratio_mode))

    # def set_trigger_conditions(self, sources, info: str):
    #     # fixme:  PicoSDK returned 'PICO_CONDITIONS' by 'pulse_width' source
    #     """
    #     To set parameters for advanced triggering. Also requires setting direction, delay, properties.
    #     :param sources (list of str): sources : list of trigger sources
    #         Allowed values:
    #         ['channel_A', 'channel_B', 'channel_C', 'channel_D',
    #          'channel_E', 'channel_F', 'channel_G', 'channel_H',
    #          'external', 'trigger_aux', 'pulse_width']
    #     :param info: determines whether the function clears previous conditions: ['clear', 'add']
    #     """
    #     self.trigger_conditions_config.append(dict(sources=sources, info=info))
    #
    # def set_trigger_direction(self, source: str, direction: str):
    #     """
    #     To set advanced trigger direction for a single source.
    #     Once you defined multiple trigger sources in condition, you also need to define their direction each.
    #      Also requires setting direction, delay, properties.
    #     :param source (str):  ['channel_A', 'channel_B', 'channel_C', 'channel_D',
    #          'channel_E', 'channel_F', 'channel_G', 'channel_H']
    #     :param direction (str):
    #         ['above', 'above_lower', 'below', 'below_lower',
    #          'rising', 'rising_lower', 'falling', 'falling_lower',
    #          'rising_or_falling', 'inside', 'outside',
    #          'enter', 'exit', 'enter_or_exit',
    #          'positive_runt', 'negative_runt', 'none']
    #     """
    #     self.trigger_directions_config.append(dict(source=source, direction=direction))
    #
    # def set_trigger_delay(self, delay_samples: int):
    #     """
    #     Defines the trigger delay in sample periods. The time between the trigger occurring and the first sample,
    #     in sample periods. For example, if delay = 100 then the scope would wait 100
    #     sample periods before sampling. Example: with the PicoScope 4224, at a
    #     timebase of 80 MS/s, or 12.5 ns per sample (timebase = 0) the total delay
    #     would then be 100 x 12.5 ns = 1.25 Âµs
    #     :param delay_samples (int): sample periods
    #     """
    #     self.trigger_delay_config.update(dict(delay=delay_samples))
    #
    # def set_trigger_properties(self, source: str, thresholdMode: str, thresholdUpper_mV: float = None,
    #                            thresholdLower_mV: float = None,
    #                            thresholdUpperHysteresis_mV: float = None, thresholdLowerHysteresis_mV: float = None,
    #                            ):
    #     """
    #     Trigger per-channel properties for advanced triggering.
    #     :param source (str): channel e.g. "channel_A", "channel_H" or
    #     :param thresholdMode (str): mode "level" | "window"
    #     :param thresholdUpper_mV (float): the upper threshold at which the trigger must fire
    #     :param thresholdLower_mV (float): the lower threshold at which the trigger must fire.
    #     :param thresholdUpperHysteresis_mV (float): the hysteresis by which the trigger must exceed the upper threshold before it will fire
    #     :param thresholdLowerHysteresis_mV (float): the hysteresis by which the trigger must exceed the lower threshold before it will fire
    #     :return:
    #     """
    #     self.trigger_properties_config.append(dict(threshold_upper=thresholdUpper_mV, threshold_lower=thresholdLower_mV,
    #                                                upper_hysteresis=thresholdUpperHysteresis_mV,
    #                                                lower_hysteresis=thresholdLowerHysteresis_mV,
    #                                                source=source, threshold_mode=thresholdMode))
    #
    # def signal_generator_config(self,
    #                             offset_voltage:int, # in volts
    #                             pk2pk:int, # in volts
    #                             wave_type: str,
    #                             start_frequency: float=10000, # in Hz
    #                             stop_frequency: float=10000, # in Hz (same = no sweep)
    #                             increment: float=0, # Hz step in sweep
    #                             dwell_time: float=1, # seconds per step
    #                             sweep_type: int=0,
    #                             operation: int=0,
    #                             shots: int=0,
    #                             sweeps: int=0,
    #                             trigger_type: str='rising',
    #                             trigger_source: str='soft_trig',
    #                             ext_in_threshold: int=0 # ADC counts, not used?
    #                         ):
    #     """
    #     Configure the built-in signal generator for PicoScope 4000(A) series.
    #
    #     This method sets up a waveform, frequency sweep, and trigger options.
    #     Call this before starting data acquisition, even if using a trigger.
    #
    #     :param offset_voltage (int): Voltage offset in volts to apply to the waveform.
    #     :param pk2pk (int):  Peak-to-peak voltage in volts.
    #     :param wave_type (int):  Waveform type. Allowed:
    #     ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down',
    #      'sinc', 'gaussian', 'half_sine', 'dc_voltage', 'white_noise']
    #     :param start_frequency (float):  Frequency in Hz at which the waveform starts.
    #     :param stop_frequency (float):  Frequency in Hz at which sweep reverses or resets.
    #     :param increment:         Frequency step in Hz for sweep mode.
    #     :param dwell_time:         Seconds per frequency step in sweep mode.
    #     :param sweep_type:         PicoScope sweep type (enum).
    #     :param operation:
    #     :param shots:         Number of waveform shots (0 = continuous).
    #     :param sweeps:        Number of sweeps (0 = infinite).
    #     :param trigger_type:        Trigger edge type. Allowed: ['rising', 'falling', 'gate_high', 'gate_low']
    #     :param trigger_source:        Trigger source. Allowed: ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
    #     :param ext_in_threshold: External input threshold in ADC counts.
    #     :return:
    #     """
    #
    #     wave_types = ['sine', 'square', 'triangle', 'ramp_up', 'ramp_down', 'sinc', 'gaussian', 'half_sine',
    #                   'dc_voltage', 'white_noise', 'max_wave_types']
    #     trig_types = ['rising', 'falling', 'gate_high', 'gate_low']
    #     trig_sources = ['none', 'scope_trig', 'aus_in', 'ext_in', 'soft_trig']
    #
    #     if wave_type not in wave_types:
    #         raise ValueError(f"Invalid wavetype: {wave_type}. Allowed values: {wave_types}")
    #     if trigger_type not in trig_types:
    #         raise ValueError(f"Invalid triggertype: {trigger_type}. Allowed values: {trig_types}")
    #     if trigger_source not in trig_sources:
    #         raise ValueError(f"Invalid triggersource: {trigger_source}. Allowed values: {trig_sources}")
    #
    #
    #     self.siggen_config.update(dict(offset_voltage=offset_voltage, pk2pk=pk2pk, wave_type=wave_type,
    #                               start_frequency=start_frequency, stop_frequency=stop_frequency,
    #                               increment=increment, dwell_time=dwell_time, sweep_type=sweep_type,
    #                               operation=operation, shots=shots, sweeps=sweeps,trigger_type=trigger_type,
    #                               trigger_source=trigger_source, ext_in_threshold=ext_in_threshold))

    def generate_code(self, hdf5_file):
        super().generate_code(hdf5_file)

        # save channels properties to device properties
        # enabled_channels = {} # ch_idx<str>: enabled<bool>
        # channel_ranges = {} # ch_idx<str>: range_v<float>
        # channel_names = {} # ch_conn<str>: ch_name<str>
        channels_properties = {} # ch_conn<str>: ch_prop<dict>

        for device in self.child_devices:
            if isinstance(device, PicoAnalogIn):
                channels_properties[device.connection] = device.channel_config
            else:
                raise LabscriptError(f"Unsupported child device type: {type(device)}")

        self.set_property(name='channels_properties', value=channels_properties, location="device_properties")


CHANNEL_MAPPING = {
    "channel_A": 0,
    "channel_B": 1,
    "channel_C": 2,
    "channel_D": 3,
    "channel_E": 4,
    "channel_F": 5,
    "channel_G": 6,
    "channel_H": 7,
}


