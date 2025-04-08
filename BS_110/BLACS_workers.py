from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from user_devices.logger_config import logger
import time

"""
This class is for communication with hardware 
"""
class BS110Worker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        
        try:
            # Try to establish a serial connection
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"Connected to BS110 on {self.port} with baud rate {self.baud_rate}")
            
            # Send IDN (identify) command to identify the device
            self.send_to_BS("IDN\r")
            device_info = self.receive_from_BS().split()
            logger.debug(f"Receiving identification BS-110: {device_info}")
            print(f"Device response: {device_info}")

            # Parse the response from the device 
            if len(device_info) >= 4:
                self.device_serial = device_info[0]  # For example, 'HV023'
                self.device_voltage_range = device_info[1]  # For example, '50'
                self.device_channels = device_info[2]  # For example, '16'
                self.device_output_type = device_info[3]  # For example, 'b' (bipolar, unipolar, quadrupole, steerer supply)
                logger.info(f"Device Serial: {self.device_serial}, Voltage Range: {self.device_voltage_range}, Channels: {self.device_channels}, Output Type: {self.device_output_type}")
            else:
                raise RuntimeError("Failed to parse the device identification string.")
        
        except Exception as e:
            raise RuntimeError(f"An error occurred during initialization: {e}")
        
        
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()
        
    
    def scale_to_range(self, normalized_value, max_range):
        """Convert a normalized value (0 to 1) to the specified range (-max_range to +max_range)"""
        max_range = float(max_range)
        return  2 * max_range * normalized_value - max_range
        
    def scale_to_normalized(self, actual_value, max_range):
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        max_range = float(max_range)
        return (actual_value + max_range) / (2 * max_range)
    
    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs outside of the shot."""
        
        # print(f"List of the commands: \n"
        #   f" IDN \t\t | Identify \n"
        #   f" DDDDD CHXX Y.YYYYY \t | Set voltage \n"
        #   f" DDDDD TEMP \t | Read Temperature \n"
        #   f" DDDDD LOCK \t | Check lock status of all channels \n"
        #   f" DDDDD DIS [message] \t | Send string to LCD-display \n")
        
        print(f"front panel values: {front_panel_values}")
        for channel,value in front_panel_values.items():
            # Set voltage from front panel 
            channel_number = channel.split()[-1] # "channel X"
            channel_num = f"CH{int(channel_number):02d}"
            scaled_voltage = self.scale_to_normalized(float(value), float(self.device_voltage_range))

            sendStr = f"{self.device_serial} {channel_num} {scaled_voltage:.6f}\r"
            self.send_to_BS(sendStr)
            print(f"{sendStr}")
            
            # TODO: front panel values with actual voltage values
            denormalized_value = self.scale_to_range(float(scaled_voltage), float(self.device_voltage_range))
            print(f"denormalize: {scaled_voltage} to {denormalized_value}")
            
        # Update displayed front panel    
        return front_panel_values


    def check_remote_values(self): # reads the current settings of the device, updating the BLACS_tab widgets 
        return

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh): 
        """transitions the device to buffered shot mode, 
        reading the shot h5 file and taking the saved instructions from 
        labscript_device.generate_code and sending the appropriate commands 
        to the hardware. 
        Runs at the start of each shot."""
        return 
        

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        return  
    
    def send_to_BS(self, sendStr):
        logger.debug(f"Sending to BS110: {sendStr}")
        # print(f"Sending to BS110: {sendStr}")
        self.connection.write(sendStr.encode())
        
        
    def receive_from_BS(self):
        response = self.connection.readline().decode().strip() # assuming utf-8 encoding
        logger.debug(f"Received from device: {response}")
        # print(f"Received from device: {response}")
        return(response)
    
    def abort_transition_to_buffered(self):
        return self.transition_to_manual(True)


        