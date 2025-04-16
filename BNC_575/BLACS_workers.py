from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import usb.core
import usb.util
import serial

from user_devices.logger_config import logger
import time


class BNC_575Worker(Worker):
    def init(self):
        """Initializes connection to BNC_575 device (USB pretending to be virtual COM port)"""
        try:
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(1)
            logger.info(f"Serial connection opened on {self.port} at {self.baud_rate}. ")

            id_cmd = "*IDN?"
            self.send_to_BNC(id_cmd)
            id_rsp = self.receive_from_BNC()
            print(f"sent: {id_cmd} \t received: {id_rsp}")
        except Exception as e:
            raise LabscriptError(f"Serial connection failed: {e}")

    def send_to_BNC(self, cmd_str):
        logger.debug(f"Sending to BNC: {cmd_str}")
        self.connection.write((cmd_str + "\r\n").encode())

    def receive_from_BNC(self):
        try:
            response = self.connection.readline().decode().strip()
            logger.debug(f"Received from Serial: {response}")
            return response
        except Exception as e:
            logger.error(f"Serial read failed: {e}")
            return 'SERIAL_ERROR'
           
    def shutdown(self):
        # Should be done when Blacs is closed
        self.connection.close()

    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot.
        setting the pulse width, delay and period --> ok\r\n


        """
        
        
        print(f"front panel values: {front_panel_values}")
        
        for channel, value in front_panel_values.items():
            
            sendStr = f"\r\n" #TODO: Setting things up
            print(f"Sent to BNC: {sendStr}")
            self.send_to_BNC(sendStr)
            response = self.receive_from_BNC()
            print(f"Received from BNC: {response}")
        
            
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
    
        