from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from user_devices.logger_config import logger
import time

class UMWorker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        try: 
            # Try to establish a serial connection
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"Connected to UM on {self.port} with baud rate {self.baud_rate}")
            
            # Identify the device
            self.send_to_UM("IDN\r")
            self.device_serial  = self.receive_from_UM()
            print(f"Device response to IDN: {self.device_serial}")
            self.device_voltage_range = 28 # TODO: Check it later
            
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
        # TODO: How to set voltages one by one and not all at once?
        # TODO: self.attributes are same across the py fiels?
        
        # current_mode = self.mode_dropdown.currentText() # Firstly i need to create the UI input for modes.
        # print(f"Current Mode: {current_mode}") 

        # if current_mode == "FAST": 
        #     self.send_to_HV("UM01 FAST LV\r")
        # elif current_mode == "ULTRA": 
        #     self.send_to_HV("UM01 ULTRA LV\r")
        
        
        for channel, value in front_panel_values.items():
            # channel = 'CH. X'
            # sendStr = 'UM01 CHXX Y.YYYYYYY'
            channel_letter = channel.split()[-1] # 'X'
            channel_number = self.channels2numbers("ULTRA", channel_letter)
            formatted_channel = f"CH{channel_number:02d}"
            scaled_voltage = self.scale_to_normalized(float(value), float(self.device_voltage_range))
            sendStr = f"{self.device_serial} {formatted_channel} {scaled_voltage:.7f}\r"
            self.send_to_UM(sendStr)
            print(f"{sendStr}")

        return front_panel_values

    def channels2numbers(self, mode, channel):
        """
            CHXX:
                01 - A', fast mode      19 - A', precision mode
                03 - B'                 20 - B'
                05 - C'                 21 - C'
        """
        channel_name = channel.split()[-1] # channel = "CH. X", where X can be A, B or C
        channel_mapping = {
            "ULTRA": {"A": "19", "B": "20", "C": "21"},
            "FAST": {"A": "01", "B": "03", "C": "05"}
        }

        if mode not in channel_mapping:
            raise ValueError(f"Invalid mode: {mode}")

        if channel_name not in channel_mapping[mode]:
            raise ValueError(f"Invalid channel name: {channel_name}")

        return channel_mapping[mode][channel_name]

    def numbers2channels(self, mode, number): 
        channel_mapping = {
            "ULTRA": {"19": "A", "20": "B", "21": "C"},
            "FAST": {"01": "A", "03": "B", "05": "C"}
        }

        if mode not in channel_mapping:
            raise ValueError(f"Invalid mode: {mode}")

        if channel_name not in channel_mapping[mode]:
            raise ValueError(f"Invalid channel number: {number}")

        return channel_mapping[mode][number]


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
    
    def send_to_UM(self, sendStr):
        logger.debug(f"Sending to UM: {sendStr}")
        self.connection.write(sendStr.encode())
        
    def receive_from_UM(self):
        response = self.connection.readline().decode('utf-8').strip() 
        logger.debug(f"Received from UM: {response}")
        return(response)
    
    def abort_transition_to_buffered(self):
        return self.transition_to_manual(True)
    
    def scale_to_range(self, normalized_value, range_max):
        """Convert a normalized value (0 to 1) to the specified range (-range_max to +range_max)"""
        return  2 * range_max * normalized_value - range_max

    def scale_to_normalized(self, actual_value, range_max):
        """Convert an actual value (within -max_range to +max_range) to a normalized value (0 to 1)"""
        return (actual_value + range_max) / (2 * range_max)
        