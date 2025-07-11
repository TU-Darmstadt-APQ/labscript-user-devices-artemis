import labscript_utils.h5_lock
import h5py
import numpy as np
from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from labscript_utils import properties
from user_devices.logger_config import logger
from zprocess import rich_print


class BNC_575Worker(Worker):
    def init(self):
        """Initializes connection to BNC_575 device (USB pretending to be virtual COM port)"""
        try:
            from .pulse_generator import PulseGenerator
            self.generator = PulseGenerator(self.port, self.baud_rate, verbose=True)
        except Exception as e:
            raise LabscriptError(f"Serial connection failed: {e}")

        worker_property_keys = [
            "port", "baud_rate", "trigger_mode",
            "t0_mode", "t0_period", "t0_burst_count",
            "t0_on_count", "t0_off_count", "trigger_logic", "trigger_level"
        ]
        worker_property_channel_keys = ["name", "connection", "state",
                                        "delay", "width", "mode", "burst_count",
                                        "on_count", "off_count", "polarity",
                                        "output_mode", "amplitude", "sync_source", "wait_counter"]

        # Configure internal system
        system_config = {
            't0_period': getattr(self, 't0_period', 0),
            'trigger_mode': getattr(self, 'trigger_mode', 'DISabled'),
            'trigger_logic': getattr(self, 'trigger_logic', 'RISing'),
            'trigger_level': getattr(self, 'trigger_level', 0),
            't0_mode': getattr(self, 't0_mode', 'NORMal'),
            't0_burst_count': getattr(self, 't0_burst_count', -1),
            't0_on_count': getattr(self, 't0_on_count', -1),
            't0_off_count': getattr(self, 't0_off_count', -1),
        }
        self.configure_system(system_config)

        # configure separate channels
        channels_config = []
        for ch in self.channels_properties:
            channel_config = {
                'state': ch.get('state', 'ON'),
                'mode': ch.get('mode', 'NORMal'),
                'burst_count': ch.get('burst_count', -1),
                'on_count': ch.get('on_count', -1),
                'off_count': ch.get('off_count', -1),
                'delay': ch.get('delay', 0),
                'width': ch.get('width', 0),
                'output_mode': ch.get('output_mode', 'NORMal'),
                'amplitude': ch.get('amplitude', 0),
                'sync_source': ch.get('sync_source', 'T0'),
                'polarity': ch.get('polarity', 'NORMal'),
                'wait_counter': ch.get('wait_counter', 0)
            }
            channels_config.append(channel_config)
        self.configure_channels(channels_config)

        # todo: pass values to GUI


    def configure_system(self, system_config):
        rich_print("System configuration: ", color=GREEN)
        self.generator.set_t0_period(system_config['t0_period'])
        self.generator.set_trigger_mode(system_config['trigger_mode'])
        if system_config['trigger_mode'].upper() == 'TRIGGERED':
            self.generator.set_trigger_logic(system_config['trigger_logic'])
            self.generator.set_trigger_level(system_config['trigger_level'])

        self.generator.set_t0_mode(system_config['t0_mode'])
        mode = system_config['t0_mode'].upper()
        if mode == 'BURST' and system_config['t0_burst_count'] != -1:
            self.generator.set_burst_counter(0, system_config['t0_burst_count'])
            logger.info(f"[BNC] T0 timer mode is BURST with burst_count = {system_config['t0_burst_count']}")
        elif mode == 'DCYCLE' and system_config['t0_on_count'] != -1 and system_config['t0_off_count'] != -1:
            self.generator.set_on_counter(0, system_config['t0_on_count'])
            self.generator.set_off_counter(0, system_config['t0_off_count'])
            logger.info(f"[BNC]T0 timer mode is DCYCLE with (on_count, off_count) = ({system_config['t0_on_count']}, {system_config['t0_off_count']})")
        elif mode in ('NORMAL', 'SINGLE'):
            logger.info(f"[BNC] T0 timer mode is {system_config['t0_mode']}")
        else:
            raise ValueError(f"Invalid T0 timer mode: {system_config['t0_mode']}. Select from: [NORMAL / SINGLE / BURST / DCYCLE]")

    def configure_channels(self, channels_config):
        rich_print("Channels configuration: ", color=GREEN)
        for i, channel in enumerate(channels_config):
            ch = i + 1  # BNC_575 channels are 1-indexed

            self.generator.set_mode(ch, channel['mode'])
            (self.generator.enable_output if channel['state'].upper() == 'ON' else self.generator.disable_output)(ch)

            output_mode = channel['mode'].upper()
            if output_mode == 'BURST' and channel['burst_count'] not in (None, -1):
                self.generator.set_burst_counter(ch, channel['burst_count'])
                logger.info(f"[BNC] Channel {ch} timer mode is BURST with burst_count = {channel['burst_count']}")
            elif output_mode == 'DCYCLE' and channel['on_count'] not in (None, -1) and channel['off_count'] not in (None, -1):
                self.generator.set_on_counter(ch, channel['on_count'])
                self.generator.set_off_counter(ch, channel['off_count'])
                logger.info(
                    f"[BNC] Channel {ch} timer mode is DCYCLE with (on_count, off_count) = ({channel['on_count']}, {channel['off_count']})")
            elif output_mode in ('NORMAL', 'SINGLE'):
                logger.info(f"[BNC] Channel {ch} timer mode is {output_mode}")
            else:
                raise ValueError(
                    f"Invalid timer mode for channel {ch}: {output_mode}. Choose from: [NORMAL / SINGLE / BURST / DCYCLE]")

            self.generator.set_delay(ch, channel['delay'])
            self.generator.set_width(ch, channel['width'])
            self.generator.set_output_mode(ch, channel['output_mode'])

            if channel['output_mode'].upper() == 'ADJUSTABLE':
                self.generator.set_output_amplitude(ch, channel['amplitude'])

            self.generator.select_sync_source(ch, channel['sync_source'])
            self.generator.set_polarity(ch, channel['polarity'])

            self.generator.set_wait_counter(ch, channel['wait_counter'])

    def shutdown(self):
        self.connection.close()

    def program_manual(self, front_panel_values):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        print(f"---------- Begin transition to Buffered: ----------")
        print(f"---------- END transition to Buffered: ----------")
        return

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. Transition to manual mode after buffered execution completion.

        Returns:
            bool: `True` if transition to manual is successful.
        """
        print(f"---------- Begin transition to Manual: ----------")
        print(f"---------- END transition to Manual: ----------")
        return True

    def abort_transition_to_buffered(self):
        try:
            return self.transition_to_manual()
        except Exception as e:
            print(f"Failed to abort properly: {e}")
            return None

    def trigger(self, kwargs):
        self.generator.generate_trigger()

    def configure(self, config_list):
        rich_print("Configure device from front panel ! ", color=GREEN)
        system, channels = config_list

        # extend incomplete system configuration from GUI with attributes
        system_config = {
            't0_period': system['t0_period'],
            'trigger_mode': system['trigger_mode'],
            'trigger_logic': getattr(self, 'trigger_logic', 'RISing'),
            'trigger_level': getattr(self, 'trigger_level', 0),
            't0_mode':  system['t0_mode'],
            't0_burst_count': system['t0_burst_count'],
            't0_on_count': system['t0_on_count'],
            't0_off_count': system['t0_off_count'],
        }

        # configure channels
        channel_keys = ["state", "delay", "width", "mode", "burst_count",
                        "on_count", "off_count", "polarity",
                        "output_mode", "amplitude", "sync_source", "wait_counter"]

        channels_config = []
        for idx, ch in enumerate(channels):
            if idx + 1 > len(self.channels_properties):
                break
            ch_config = {}
            for key in channel_keys:
                ch_config[key] = ch[key] if key in ch else self.channels_properties[idx].get(key)
            channels_config.append(ch_config)

        self.configure_system(system_config)
        self.configure_channels(channels_config)

    def reset(self):
        self.generator.reset_device()



# --------------------contants
BLUE = '#66D9EF'
GREEN = '#097969'
        