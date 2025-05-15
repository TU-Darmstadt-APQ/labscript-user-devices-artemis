import serial
import numpy as np
from labscript.labscript import LabscriptError
from user_devices.logger_config import logger

class BiasSupply:
    """ Bias Suppply BS-1-10 class to establish and maintain the communication with the connection.
    """

    def __init__(self,
                 port,
                 baud_rate,
                 verbose=False
                 ):
        logger.debug(f"<initialising Bias Supply BS-110>")
        self.verbose = verbose
        self.port = port
        self.baud_rate = baud_rate

        # connecting to connectionice
        self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
        device_info = self.identify_query()
        self.device_serial = device_info[0]  # For example, 'HV023'
        self.device_voltage_range = device_info[1]  # For example, '50'
        self.device_channels = device_info[2]  # For example, '10'
        self.device_output_type = device_info[3]  # For example, 'b' (bipolar, unipolar, quadrupole, steerer supply)

    def identify_query(self):
        """Send identification instruction through serial connection, receive response.
           Returns:
               list[str]: Parsed identity response split by whitespace.
           Raises:
               LabscriptError: If identity format is incorrect.
           """
        self.connection.write("IDN\r".encode())
        raw_response = self.connection.readline().decode()
        identity = raw_response.split()

        if len(identity) == 4:
            logger.debug(f"Device initialized with identity: {identity}")
            return identity
        else:
            raise LabscriptError(
                f"Device identification failed.\n"
                f"Raw identity: {raw_response!r}\n"
                f"Parsed identity: {identity!r}\n"
                f"Expected format: ['BSXXX', 'RRR', 'CC', 'b']\n"
                f"Device: BS-1-10 at port {self.port!r}\n"
            )

    def set_voltage(self, channel_num, value):
        """ Send set voltage command to BS-1-10.
        Args:
            channel_num (int): Channel number.
            value (float): Voltage value to set.
        Raises:
            LabscriptError: If the response from BS-1-10 is incorrect.
        """
        try:
            channel = f"CH{int(channel_num):02d}"
            scaled_voltage = self._scale_to_normalized(float(value), float(self.device_voltage_range))
            send_str = f"{self.device_serial} {channel} {scaled_voltage:.6f}\r"

            self.connection.write(send_str.encode())
            response = self.connection.readline().decode().strip() #'CHXX Y.YYYYY'

            logger.debug(f"Sent to BS-1-10: {send_str.strip()} | Received: {response!r}")

            expected_response = f"{channel} {scaled_voltage:.6f}"
            if response != expected_response:
                raise LabscriptError(
                    f"Voltage setting failed.\n"
                    f"Sent command: {send_str.strip()!r}\n"
                    f"Expected response: {expected_response!r}\n"
                    f"Actual response: {response!r}\n"
                    f"Device: BS-1-10 at port {self.port!r}"
                )
        except Exception as e:
            raise LabscriptError(f"Error in set_voltage: {e}")

    def read_temperature(self):
        """
        Query the device for temperature.
        Returns:
            float: Temperature in Celsius.
        Raises:
            LabscriptError: If the response format is invalid or parsing fails.
        """
        send_str = f"{self.device_serial} TEMP\r"
        self.connection.write(send_str.encode())

        response = self.connection.readline().decode().strip() #'XX.X°C'

        if response.endswith("°C"):
            try:
                # Remove the degree symbol and parse the number
                temperature_str = response.replace("°C", "").strip()
                temperature = float(temperature_str)
                return temperature
            except ValueError:
                raise LabscriptError(f"Failed to parse temperature from response.\n")
        else:
            raise LabscriptError(
                f"Temperature query failed.\n"
                f"Unexpected response format: {response!r}\n"
                f"Expected a value ending in '°C'."
            )

    def _scale_to_range(self, normalized_value, max_range):
        """Convert a normalized value (0 to 1) to the specified range (-max_range to +max_range)"""
        max_range = float(max_range)
        return 2 * max_range * normalized_value - max_range

    def _scale_to_normalized(self, actual_value, max_range):
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        max_range = float(max_range)
        return (actual_value + max_range) / (2 * max_range)
