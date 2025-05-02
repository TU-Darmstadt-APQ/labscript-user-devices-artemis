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
        logger.debug(f"<initialising Pulse Generator>")
        self.verbose = verbose
        self.port = port
        self.baud_rate = baud_rate

        # connecting to connectionice
        self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
        print(f'Initialized: {self.connection.write(("*IDN?\r\n)").encode())}') # manufacturer,modelNo,serialNo,versionNo

        # initialize connection
        self.reset_device()

    ### Basic intern system commands

    def start_pulses(self):
        self.connection.write((':PULSE0:STATE ON\r\n').encode())

    def end_pulses(self):
        self.connection.write((':PULSE0:STATE OFF\r\n').encode())

    def reset_device(self): # Resets to default state
        self.connection.write(('*RST\r\n').encode())

    def set_mode(self, mode):
        """ Set the mode of the pulse generator.
        Args:
            mode (str): The mode to set. Options are 'NORMAL', 'SINGLE', 'BURST'.
        """
        if mode not in ['NORMAL', 'SINGLE', 'BURST']:
            raise ValueError("Invalid mode. Choose from 'NORMAL', 'SINGLE', 'BURST'.")
        self.connection.write((f':PULSE0:MODE {mode}\r\n').encode())

    def set_period(self, period):
        """ Set the period of the pulse generator.
        Args:
            period (float): The period in seconds. Range: 100ns-5000s
        """
        self.connection.write((f':PULSE0:PERIOD {period}\r\n').encode())

    def disable_trigger(self):
        self.connection.write((f":PULSE0:TRIGger:MODe DISabled \r\n").encode())

    ### Basic channel commands

    def enable_output(self, channel):
        """ Enable the output of the specified channel.
        Args:
            channel (int): The channel number (1-7).
        """
        self.connection.write((f':PULSE{channel}:STATE ON\r\n').encode())

    def disable_output(self, channel):
        """ Enable the output of the specified channel.
        Args:
            channel (int): The channel number (1-7).
        """
        self.connection.write((f':PULSE{channel}:STATE OFF\r\n').encode())

    def set_delay(self, channel, delay):
        """ Set the delay to the specified channel.
        Args:
            channel (int): The channel number (1-7).
            delay (float): The delay in seconds.
        """
        self.connection.write((f':PULSE{channel}:DELAY {delay}\r\n').encode())

    def set_width(self, channel, width):
        """ Set the width to the specified channel.
        Args:
            channel (int): The channel number (1-7).
            width (float): The width in seconds.
        """
        self.connection.write((f':PULSE{channel}:WIDTH {width}\r\n').encode())

    ### Basic queries

    def receive_from_BNC(self):
        try:
            response = self.connection.readline().decode().strip()
            logger.debug(f"Received from Serial: {response}")
            return response
        except Exception as e:
            logger.error(f"Serial read failed: {e}")
            return 'SERIAL_ERROR'