from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import serial
from user_devices.logger_config import logger
import time


class HV_250Worker(Worker):
    def init(self):
        """Initialises communication with the device. When BLACS (re)starts"""
        
        try:
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"Connected to HV_250 on {self.port} with baud rate {self.baud_rate}")
            
            # Identify the device:
            self.send_to_HV("IDN\r")
            device_info = self.receive_from_HV().split()
            logger.debug(f"Receiving identification HV-250: {device_info}")
            if len(device_info) >= 4:
                self.device_serial = device_info[0]
                self.device_voltage_range = device_info[1]
                self.device_channels_number= device_info[2]
                self.device_output_type = device_info[3]
                logger.info(f"Device Serial: {self.device_serial}, Voltage Range: {self.device_voltage_range}, Channels: {self.device_channels_number}, Output Type: {self.device_output_type}")
            else:
                raise RuntimeError("Failed to parse the device's identification string. ")
                
        except serial.SerialException as e:
            raise RuntimeError(f"Serial connection error: {e}")
        except Exception as e:
            raise RuntimeError(f"An error occurred during HV_200 worker initialization: {e}")
        
        
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
        Runs at the end of the shot."""
        
        print(f"front panel values: {front_panel_values}")
        
        for channel, value in front_panel_values.items():
            scaled_voltage = self.scale_to_normalized(float(value), float(self.device_voltage_range))
            print(f"Scaled voltage: {scaled_voltage:.6f}, \t Voltage: {value:.2f}")
            sendStr = f"{self.device_serial} {channel} {scaled_voltage:.6f}\r"
            self.send_to_HV(sendStr)
            
        return front_panel_values

    def check_remote_values(self): 
        return 

    def transition_to_buffered(self, device_name, h5_file): 
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
    
    def send_to_HV(self, sendStr):
        logger.debug(f"Sent to HV_200: {sendStr}")
        self.connection.write(sendStr.encode())
        
    def receive_from_HV(self):
        response = self.connection.readline().decode()
        logger.debug(f"Received from HV_200: {response}")
        return(response)

    def query_voltage(self):
        """Reads the current voltage values from the device and updates the blacs NEW tab widgets.
        DDDDD QXX | +/-yy,yyy V (in voltage)
        XX - channel number, yy,yyy - voltage value"""
                
        channels = ["01", "02", "03", "04", "05", "06", "07", "08"]
        print("Voltages: \n")
        for channel in channels:
            sendStr = "HV001 Q" + channel + "\r" 
            self.send_to_HV(sendStr) 
            response = self.receive_from_HV()
            logger.debug(f"Received from HV_250: {response}")

            if response.startswith("+") or response.startswith("-"):
                try:
                    voltage_str, _ = response.split().strip()  # Splitting "+/-yy,yyy V"
                    logger.debug(f"Received voltage for channel {channel}: {voltage} V")
                    voltage = float(voltage.replace(",", "."))  
                    print(f"CH{channel} = {voltage:.3f} \n") # TODO: How to update the widget?
                    
                except ValueError:
                    logger.error(f"Invalid response format: {response}")
            else:
                logger.error(f"Unexpected response: {response}")

    
    def check_lock_status(self):
        """Reads the lock status of the device and updates the blacs indicator.
        Routinely once per second the control program reads the actual status.

        DDDDD LOCK | B3B2B1B0

        With check locking status the first 4 bits (= upper nibble) of every Byte is always 0001 = 16dec
        in B3: ch16 ch15 ch14 ch13
        in B2: ch12 ch11 ch10 ch09
        in B1: ch08 ch07 ch06 ch05
        in B0: ch04 ch03 ch02 ch01

        where 0 - locked, 1 - not locked"""
        
        sendStr = "HV001 LOCK\r" 
        self.send_to_HV(sendStr) 
        response = self.receive_from_HV()
        logger.debug(f"Received from HV_250: {response}")

        if len(response.split()) == 4:  # Ensure response contains 4 bytes
            try:
                lock_status = response.strip().split()  # List of B3, B2, B1, B0 bytes
                lock_bits = []
                for byte in lock_status:
                    # Remove the first nibble "0001" and get the lock status for the 4 channels in the byte
                    byte_value = int(byte, 16)  # Convert hex to integer
                    channel_bits = format(byte_value, '08b')[4:]  # Get the lower 4 bits, ignoring the "0001" nibble
                    lock_bits.extend([int(bit) for bit in channel_bits])  # Add the bits to the lock_bits list

                # TODO: Update the Lock status indicator
                logger.debug(f"Lock status: {lock_bits}")

            except Exception as e:
                logger.error(f"Error processing lock status: {e}")
        else:
            logger.error(f"Unexpected response format: {response}")
        