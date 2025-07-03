import labscript_utils.h5_lock
import h5py
import numpy as np
from blacs.tab_base_classes import Worker
from labscript import LabscriptError
from labscript_utils import properties
from user_devices.logger_config import logger


class BNC_575Worker(Worker):
    def init(self):
        """Initializes connection to BNC_575 device (USB pretending to be virtual COM port)"""

        try:
            from .pulse_generator import PulseGenerator
            self.generator = PulseGenerator(self.port, self.baud_rate, verbose=True)
        except Exception as e:
            raise LabscriptError(f"Serial connection failed: {e}")

           
    def shutdown(self):
        self.connection.close()

    def program_manual(self, front_panel_values):
        print(f"front panel values: {front_panel_values}")

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        print(f"---------- Begin transition to Buffered: ----------")

        self.h5file = h5_file
        with h5py.File(h5_file, 'r') as hdf5_file:
            group = hdf5_file['devices'][device_name]
            system_data = group['system_timer'][0]
            channels_data = group['channel_timer'][:]

        # Configure internal system
        self.generator.set_t0_period(system_data['period'])
        self.generator.set_t0_mode(system_data['mode'])

        mode = system_data['mode'].upper().decode('utf-8')
        if mode == 'BURST' and system_data['burst_count'] != -1:
            self.generator.set_burst_counter(0, system_data['burst_count'])
            logger.info(f"[BNC]T0 timer mode is BURST with burst_count = {system_data['burst_count']}")
        elif mode == 'DCYCLE' and system_data['on_count'] != -1 and system_data['off_count'] != -1:
            self.generator.set_on_counter(0, system_data['on_count'])
            self.generator.set_off_counter(0, system_data['off_count'])
            logger.info(f"[BNC]T0 timer mode is DCYCLE with (on_count, off_count) = ({system_data['on_count']}, {system_data['off_count']})")
        elif mode in ('NORMAL', 'SINGLE'):
            logger.info(f"[BNC]T0 timer mode is {mode}")
        else:
            raise ValueError(f"Invalid T0 timer mode: {mode}. Select from: [NORMAL / SINGLE / BURST / DCYCLE]")

        self.generator.set_trigger_mode(system_data['trigger_mode'])
        if system_data['trigger_mode'].upper() == 'TRIGGERED':
            self.generator.set_trigger_logic(system_data['trigger_logic'])
            self.generator.set_trigger_level(system_data['trigger_level'])


        # Configure separate channels
        for channel in channels_data:
            ch = channel['channel']  # channel number starting from 1
            self.generator.enable_output(ch)
            self.generator.set_mode(ch, channel['mode'])

            output_mode = channel['mode'].upper().decode('utf-8')
            if output_mode == 'BURST' and channel['burst_count'] != -1:
                self.generator.set_burst_counter(ch, channel['burst_count'])
                logger.info(f"[BNC]Channel {ch} timer mode is BURST with burst_count = {channel['burst_count']}")
            elif output_mode == 'DCYCLE' and channel['on_count'] != -1 and channel['off_count'] != -1:
                self.generator.set_on_counter(0, channel['on_count'])
                self.generator.set_off_counter(0, channel['off_count'])
                logger.info(f"[BNC]Channel {ch} timer mode is DCYCLE with (on_count, off_count) = ({channel['on_count']}, {channel['off_count']})")
            elif output_mode in ('NORMAL', 'SINGLE'):
                logger.info(f"[BNC]Channel {ch} timer mode is {mode}")
            else:
                raise ValueError(f"Invalid T0 timer mode: {mode}. Select from: [NORMAL / SINGLE / BURST / DCYCLE]")

            self.generator.set_delay(ch, channel['delay'])
            self.generator.set_width(ch, channel['width'])
            self.generator.set_output_mode(ch, channel['output_mode'])
            if channel['output_mode'].upper() == 'ADJUSTABLE':
                self.generator.set_output_amplitude(ch, channel['amplitude'])
            self.generator.select_sync_source(ch, channel['sync_source'])
            self.generator.set_polarity(ch, channel['polarity'])

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
            return

    def trigger(self, kwargs):
        self.generator.generate_trigger()

    
        