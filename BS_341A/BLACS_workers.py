from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from user_devices.logger_config import logger
import time


class BS_341AWorker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        
        try:
            # Try to establish a serial connection
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"Connected to BS34-1A on {self.port} with baud rate {self.baud_rate}")
            
            # Identify the device
            self.send_to_BS("IDN\r")
            device_info = self.receive_from_BS().split()
            print(f"Device response to IDN: {device_info}")
            
            # Parsing
            self.device_serial = device_info[0]
            self.device_voltage_range = device_info[1] # e.g. 5 from emulateSerPort
            self.device_channels_number= device_info[2]
            self.device_output_type = device_info[3]
            
        except Exception as e:
            raise RuntimeError(f"An error occurred during worker initialization: {e}")
        
        
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()
        
    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot."""
        
        print(f"front panel values: {front_panel_values}")
        
        for channel, value in front_panel_values.items():
            scaled_voltage = self.scale_to_normalized(float(value), float(self.device_voltage_range))
            sendStr = f"{self.device_serial} {channel} {scaled_voltage:.6f}\r"
            self.send_to_BS(sendStr)
            print(f"{sendStr}")
            
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
        logger.debug(f"Sending to BS34-1A: {sendStr}")
        self.connection.write(sendStr.encode())
        # print(f"Sending to BS110: {sendStr}")
        
    def receive_from_BS(self):
        response = self.connection.readline().decode('utf-8').strip() # assuming utf-8 encoding
        logger.debug(f"Received from BS34-1A: {response}")
        # print(f"Received from device: {response}")
        return(response)
    
    def abort_transition_to_buffered(self):
        return self.transition_to_manual(True)
    
    def scale_to_range(self, normalized_value, range_max):
        """Convert a normalized value (0 to 1) to the specified range (-range_max to +range_max)"""
        return  2 * range_max * normalized_value - range_max

    def scale_to_normalized(self, actual_value, range_max):
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        return (actual_value + range_max) / (2 * range_max)
