from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import usb.core
import usb.util
import serial
import h5py


from user_devices.logger_config import logger
import time


class CAENWorker(Worker):
    def init(self):
        """Initializes connection to CAEN device (Serial or USB)"""
        self.using_usb = False

        if hasattr(self, 'vid') and hasattr(self, 'pid') and self.vid and self.pid:
            self.using_usb = True
            self._init_usb()
        elif self.port:
            self._init_serial()
        else:
            raise LabscriptError("No valid connection method (USB or Serial) specified.")

    def _init_usb(self):
        try:
            self.dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if self.dev is None:
                raise LabscriptError(f"CAEN USB device not found (VID={hex(self.vid)}, PID={hex(self.pid)}).")

            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)

            self.dev.set_configuration()
            cfg = self.dev.get_active_configuration()
            intf = cfg[(0, 0)]

            self.ep_out = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
            )
            self.ep_in = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
            )

            if self.ep_out is None or self.ep_in is None:
                raise LabscriptError("Could not find USB IN/OUT endpoints.")

            logger.info(f"USB connection established: VID={hex(self.vid)}, PID={hex(self.pid)}")

        except Exception as e:
            raise LabscriptError(f"USB init failed: {e}")

    def _init_serial(self):
        try:
            self.connection = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"CAEN Serial connection opened on {self.port} at {self.baud_rate} bps")
        except Exception as e:
            raise LabscriptError(f"CAEN Serial connection failed: {e}")

    def send_to_CAEN(self, cmd_str):
        logger.debug(f"Sending to CAEN: {cmd_str}")
        if self.using_usb:
            self.ep_out.write(cmd_str.encode())
        else:
            self.connection.write(cmd_str.encode())

    def receive_from_CAEN(self):
        if self.using_usb:
            try:
                response = self.ep_in.read(64, timeout=1000)
                decoded = ''.join([chr(b) for b in response]).strip()
                logger.debug(f"Received from USB: {decoded}")
                return decoded
            except Exception as e:
                logger.error(f"USB read failed: {e}")
                return 'USB_ERROR'
        else:
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
    
    def formate(self, value):
        return f"{int(value):04d}.{int(round((value % 1) * 10000)):04d}"


    def program_manual(self, front_panel_values): 
        """Allows for user control of the device via the BLACS_tab, 
        setting outputs to the values set in the BLACS_tab widgets. 
        Runs at the end of the shot."""
        
        print(f"front panel values: {front_panel_values}")
        
        for channel, value in front_panel_values.items():
            ch_num = channel[2:]  # 'CH1' -> '1'
            formated_voltage = self.formate(value)
            sendStr = f"$CMD:SET,CH:{ch_num},PAR:VSET,VAL:{formated_voltage}\r\n"
            print(f"Sent to CAEN: {sendStr}")
            self.send_to_CAEN(sendStr)
            response = self.receive_from_CAEN()
            print(f"Received from CAEN: {response}")
        
            
        return front_panel_values

    def check_remote_values(self): # reads the current settings of the device, updating the BLACS_tab widgets 
        return

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh): 
        """transitions the device to buffered shot mode, 
        reading the shot h5 file and taking the saved instructions from 
        labscript_device.generate_code and sending the appropriate commands 
        to the hardware. 
        Runs at the start of each shot."""

        print(f"[CAENWorker] Transition to buffered: {h5_file}")

        with h5py.File(h5_file, 'r') as f:
            times = f[f'devices/{device_name}/TIMES'][()]
            analog_data = f[f'devices/{device_name}/ANALOG_OUTPUTS'][()]
            channels = analog_data.dtype.names  # ('CH0', 'CH1', ...)

        self.buffer = []

        for i, t in enumerate(times):
            # Сохраняем одно состояние (время + значения всех каналов)
            entry = {ch: analog_data[ch][i] for ch in channels}
            entry['t'] = t
            self.buffer.append(entry)

        print(f"[CAENWorker] Buffered {len(self.buffer)} steps.")
        return self.buffer[0]  # для initial_state
        

    def transition_to_manual(self): 
        """transitions the device from buffered to manual mode to read/save measurements from hardware
        to the shot h5 file as results. 
        Runs at the end of the shot."""
        return

    def abort_transition_to_buffered(self):
        print("[CAENWorker] abort_transition_to_buffered() called.")
        return True

    def abort_buffered(self):
        return self.abort_transition_to_buffered()