import serial
import numpy as np
from labscript.labscript import LabscriptError
from user_devices.logger_config import logger

class PulseGenerator:
    """ Pulse generator class to establish and maintain the communication with the connectionice. Using SCPI.
    """

    def __init__(self,
                 port,
                 baud_rate,
                 verbose=False
                 ):
        logger.info(f"[BNC] <initialising Pulse Generator>")
        self.verbose = verbose
        self.port = port
        self.baud_rate = baud_rate

        # connecting to connectionice
        self.connection = serial.Serial(self.port, self.baud_rate, timeout=1) # what is the exact response time
        logger.info(f"[BNC] Pulse Generator Serial connection opened on {self.port} at {self.baud_rate} bps")
        identity = self.identify_device()
        print(f"Connected to {identity}")
        logger.debug(f"[BNC] Received from BNC Serial: {identity}")

        # initialize connection
        self.reset_device()
        self.set_baud_rate(baud_rate)

    ### Common commands

    def identify_device(self):  # Returns identification
        self.connection.write(('*IDN?\r\n').encode())
        response = self.connection.readline().decode().strip()
        return response

    def reset_device(self): # Resets to default state
        self.send_command('*RST')
        if self.verbose:
            print("Reset to default.")

    def set_baud_rate(self, baud_rate):
        self.send_command(f':SYST:SER:BAUD {baud_rate}')

    def generate_trigger(self):
        self.send_command('*TRG')
        if self.verbose:
            print("Generate software trigger.")

    ### Basic intern system commands

    def enable_output_for_all(self):
        """Enable output on all channels."""
        self.send_command(':PULSE0:STATE ON')
        if self.verbose:
            print("Enable output for all channels.")

    def disable_output_for_all(self):
        self.send_command(':PULSE0:STATE OFF')
        if self.verbose:
            print("Disable output for all channels.")

    def set_t0_mode(self, mode):
        """ Set the mode of the pulse generator.
        Args:
            mode (str): The mode to set. Options are 'NORMAL', 'SINGLE', 'BURST'.
        """
        mode = self._normalize(mode)
        if mode not in ['NORMAL', 'SINGLE', 'BURST', 'DCYCLE']:
            raise ValueError(f"Invalid t0 mode={mode}. Choose from 'NORMal', 'SINGLe', 'BURSt', 'DCYCLe'.")
        self.send_command(f':PULSE0:MODE {mode}')
        if self.verbose:
            print(f"Set system mode to {mode}.")

    def set_t0_period(self, period):
        """ Set the period of the pulse generator.
        Args:
            period (float): The period in seconds. Range: 100ns-5000s
        """
        self.send_command(f':PULSE0:PER {period}')
        if self.verbose:
            print(f"Set system period to {period}")

    def set_trigger_mode(self, mode):
        self.send_command(f":PULSE0:TRIG:MOD {self._normalize(mode)}")
        if self.verbose:
            print(f"Set trigger mode to {mode}")

    def set_trigger_logic(self, trigger_logic):
        self.send_command(f":PULSE0:TRIG:LOG {trigger_logic}")

    def set_trigger_level(self, trigger_level):
        self.send_command(f":PULSE0:TRIG:LEV {trigger_level}")

    ### Channel/system combined commands

    def set_burst_counter(self, channel, burst_count):
        """Set burst count for a given channel. Or for all channels if channel=0"""
        self.send_command(f":PULSE{channel}:BCO {burst_count}")

    def set_on_counter(self, channel, on_count):
        """Set ON count for DCYCLe mode."""
        self.send_command(f":PULSE{channel}:PCO {on_count}")

    def set_off_counter(self, channel, off_count):
        """Set OFF count for DCYCLe mode."""
        self.send_command(f":PULSE{channel}:OCO {off_count}")

    ### Channel specific commands

    def enable_output(self, channel):
        """Enable output on a specific channel."""
        self.send_command(f':PULSE{channel}:STATE ON')

    def disable_output(self, channel):
        """Disable output on a specific channel."""
        self.send_command(f':PULSE{channel}:STATE OFF')

    def set_delay(self, channel, delay):
        """ Set the delay to the specified channel.
        Args:
            channel (int): The channel number [1:8].
            delay (float): The delay in seconds.
        """
        self.send_command(f':PULSE{channel}:DELAY {delay}')
        if self.verbose:
            print(f"Set delay on channel {channel} to {delay}")

    def set_width(self, channel, width):
        """ Set the width to the specified channel.
        Args:
            channel (int): The channel number [1:8].
            width (float): The width in seconds.
        """
        self.send_command(f':PULSE{channel}:WIDTH {width}')
        if self.verbose:
            print(f"Set width on channel {channel} to {width}")

    def select_sync_source(self, channel, sync_source):
        self.send_command(f':PULSE{channel}:SYNC {self._normalize(sync_source)}')

    def set_mode(self, channel, mode):
        """ Set the mode of the pulse generator.
        Args:
            channel (int): Channel number [1:8]
            mode (str): The mode to set. Options are 'NORMAL', 'SINGLE', 'BURST'.
        """
        mode = self._normalize(mode)
        if mode not in ['NORMAL', 'SINGLE', 'BURST', 'DCYCLE']:
            raise ValueError(f"Invalid mode={mode}. Choose from 'NORMAL', 'SINGLE', 'BURST', 'DCYCLE'.")
        self.send_command(f':PULSE{channel}:CMODe {mode}')
        if self.verbose:
            print(f"Set mode on channel {channel} to {mode}")

    def set_wait_counter(self, channel, wait_counter):
        """Sets the number of T0 pulses to delay until enabling output."""
        self.send_command(f':PULSE{channel}:WCOunter {wait_counter}')

    def set_output_mode(self, channel, output_mode):
        if isinstance(output_mode, bytes):
            output_mode = output_mode.decode('utf-8')
        if output_mode.upper() not in ['TTL', 'ADJUSTABLE']:
            raise ValueError(f"Invalid mode={output_mode}. Choose from 'TTL', 'ADJustable'")
        self.send_command(f':PULSE{channel}:OUTPut:MODe {output_mode}')

    def set_output_amplitude(self, channel, amplitude):
        if not (2.0 <= amplitude <= 20.0):
            raise ValueError("Amplitude must be between 2.0V and 20.0V.")
        self.send_command(f':PULSE{channel}:OUTPut:AMP {amplitude}')

    def set_polarity(self, channel, polarity):
        polarity = self._normalize(polarity)
        if polarity not in ['NORMAL', 'COMPLEMENT', 'INVERTED']:
            raise ValueError(f"Invalid polarity={polarity}. Choose from [NORMal / COMPlement / INVerted]")
        self.send_command(f':PULSE{channel}:POL {polarity}')


    ### helpers
    def send_command(self, cmd: str):
        self.connection.write((cmd + '\r\n').encode())
        response = self.receive_from_BNC()
        logger.debug(f"[BNC] Sent: {cmd} \t Received: {response}")

    def receive_from_BNC(self):
        try:
            response = self.connection.readline().decode().strip()
            # logger.debug(f"[BNC] Received from BNC Serial: {response}")
            if not response or response.lower() != 'ok':
                raise LabscriptError(f'Device responded with error:  {response}')
            return True
        except Exception as e:
            logger.error(f"Serial read failed: {e}")
            return 'SERIAL_ERROR'

    def _normalize(self, value):
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return str(value).strip().upper()