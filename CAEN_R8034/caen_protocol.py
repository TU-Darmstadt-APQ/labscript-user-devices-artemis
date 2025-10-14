import usb.core
import usb.util
import socket
import serial
from labscript import LabscriptError
from user_devices.logger_config import logger
import time


class Caen:
    """Protocol class to manage the communication with CAEN device.
        Communication commands format:

    $CMD:<attribute>[,CH:<chval>],PAR:<par_name>[,VAL:<par_val>]<CR><LF>
        attribute = {"MON", "SET", "INFO"}
        chval = 0..N with N = number of channels, N for group
    """
    def __init__(self, port=None, baud_rate=9600, vid=None, pid=None, verbose=True):
        self.verbose = verbose
        # Connection types
        self.using_usb = False
        self.using_serial = False
        self.using_ethernet = False

        # USB attr
        self.vid = vid
        self.pid = pid
        self.dev = None
        self.ep_in = None
        self.ep_out = None

        # Serial attr
        self.serial = None
        self.port = port
        self.baud_rate = baud_rate

        # Ethernet attr
        self.socket = None
        self.ethernet_host = '192.168.0.250'
        self.ethernet_port = 1470

        if self.vid is not None and self.pid is not None:
            print(vid)
            self.using_usb = True
            self.open_usb()
        elif port != '':
            self.using_serial = True
            self.open_serial()
        else:
            self.using_ethernet = True
            self.open_ethernet()

        for ch in range(8):
            self.enable_channel(ch, True)

        if not (self.using_usb or self.using_serial or self.using_ethernet):
            raise LabscriptError("No valid connection method (USB, Serial, Ethernet) provided.")

    def open_ethernet(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # TCP
            print(f"Connect to {self.ethernet_host}:{self.ethernet_port}")
            self.socket.connect((self.ethernet_host, self.ethernet_port))
            self.socket.settimeout(3)
            logger.info(f"[CAEN] Ethernet connection established.")
        except Exception as e:
            self.close_ethernet() # Close socket if failed
            self.socket = None
            raise LabscriptError(f"[CAEN] Ethernet connection failed: {e}")

    def close_ethernet(self):
        self.socket.close()

    def open_usb(self):
        try:
            self.dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if self.dev is None:
                raise LabscriptError(f"[CAEN] CAEN USB device not found (VID={self.vid}, PID={self.pid}).")
            # Set the device configuration
            self.dev.set_configuration()
            # get an endpoint instance
            cfg = self.dev.get_active_configuration()

            self.ep_out = None
            self.ep_in = None
            selected_intf = None
            # todo: do better
            for interface in cfg:
                for alt_setting in range(interface.bNumEndpoints):  # Можно просто перебирать альтернативы интерфейса
                    intf = usb.util.find_descriptor(cfg, bInterfaceNumber=interface.bInterfaceNumber,
                                                    bAlternateSetting=alt_setting)
                    if intf is None:
                        continue

                    # Ищем Bulk OUT
                    ep_out_candidate = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: (
                                    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT and
                                    usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
                    )

                    ep_in_candidate = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: (
                                    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN and
                                    usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
                    )

                    if ep_in_candidate and ep_out_candidate:
                        self.ep_in = ep_in_candidate
                        self.ep_out = ep_out_candidate
                        selected_intf = intf
                        print(f"Selected interface {interface.bInterfaceNumber} alt {alt_setting}")
                        break
                if self.ep_in and self.ep_out:
                    break


            logger.info(f"ep out: {self.ep_out}, ep in = {self.ep_in}")

            if self.ep_out is None or self.ep_in is None:
                raise LabscriptError("Could not find USB IN/OUT endpoints.")

            logger.info(f"[CAEN] USB connection established: VID={hex(self.vid)}, PID={hex(self.pid)}")

        except Exception as e:
            self.close_usb()
            raise LabscriptError(f"USB connection failed: {e}")

    def close_usb(self):
        if hasattr(self, 'dev') and self.dev:
            usb.util.dispose_resources(self.dev)
            self.dev = None
            logger.info("[CAEN] USB device released.")

    def open_serial(self):
        try:
            self.serial = serial.Serial(self.port, self.baud_rate, timeout=1)
            logger.info(f"[CAEN] CAEN Serial connection opened on {self.port} at {self.baud_rate} bps")
        except Exception as e:
            raise LabscriptError(f"CAEN Serial connection failed: {e}")

    def close_serial(self):
        self.serial.close()

    def close_connection(self):
        if self.using_usb:
            self.close_usb()
        elif self.using_serial:
            self.close_serial()
        elif self.using_ethernet:
            self.close_ethernet()

    ### board commands
    def set_control_mode(self, mode: str):
        mode = mode.upper()
        cmd = f"$CMD:INFO,PAR:BDCTR,VAL:{mode}"
        self.query(cmd)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set control mode to {mode}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def set_interlock_mode(self, mode: str):
        """ DRIVEN/UNDRIVEN"""
        mode = mode.upper()
        cmd = f"$CMD:SET,PAR:BDILKM,VAL:{mode}"
        self.query(cmd)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set INTERLOCK mode to {mode}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def clear_alarm_signal(self):
     cmd = f"$CMD:SET,PAR:BDCLR"
     self.query(cmd)

     # self.send_to_CAEN(cmd)
     # response = self.receive_from_CAEN()
     # self._check_response(response)
     #
     # if self.verbose:
     #     print(f"Clear alarm signal: \t {response}")
     # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    ### per channel commands
    def enable_channel(self, channel:int, enable:bool):
        if enable:
            en='on'
        else:
            en='off'
        cmd = f"$CMD:SET,CH:{channel},PAR:pw,val:{en}"
        self.query(cmd)

    def set_voltage(self, channel:int, voltage:float):
        cmd = f"$CMD:SET,CH:{channel},PAR:VSET,VAL:{voltage}"
        self.query(cmd)
        # cmd_info = f"$CMD:INFO,CH:{channel},PAR:STATUS"
        # info = self.query(cmd_info)
        # print(info)
        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set voltage on CH {channel} to {voltage}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def monitor_voltage(self, channel: int) -> float:
        cmd = f"$CMD:MON,CH:{channel},PAR:VMON"
        return self.query(cmd, expect_val=True)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Monitor voltage on CH {channel}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")
        #
        # # "#CMD:OK,VAL:<voltage>"
        # parts = response.strip().split(',')
        # if len(parts) < 2 or not parts[1].startswith("VAL:"):
        #     raise LabscriptError(f"[CAEN] Unexpected response format: {response}")
        # voltage = float(parts[1][4:])
        # return voltage

    def set_current(self, channel:int, current:float):
        cmd = f"$CMD:SET,CH:{channel},PAR:ISET,VAL:{current}"
        self.query(cmd)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set current on CH {channel} to {current}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def monitor_current(self, channel: int) -> float:
        cmd = f"$CMD:MON,CH:{channel},PAR:IMON"
        return self.query(cmd, expect_val=True)
        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Monitor current on CH {channel}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")
        #
        # # "#CMD:OK,VAL:<current>"
        # parts = response.strip().split(',')
        # if len(parts) < 2 or not parts[1].startswith("VAL:"):
        #     raise LabscriptError(f"[CAEN] Unexpected response format: {response}")
        # current = float(parts[1][4:])
        # return current

    def set_ramp_up_rate(self, channel: int, rate: float):
        """Maximum High Voltage increase rate. [V/s]"""
        cmd = f"$CMD:SET,CH:{channel},PAR:RUP,VAL:{rate}"
        self.query(cmd)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set ramp-up on CH {channel} to {rate}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def set_ramp_down_rate(self, channel: int, rate: float):
        """Maximum High Voltage descrease rate. [V/s]"""
        cmd = f"$CMD:SET,CH:{channel},PAR:RDWN,VAL:{rate}"
        self.query(cmd)

        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set ramp-down on CH {channel} to {rate}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def trip(self, channel: int, time: float):
        """Max. time an "overcurrent" can last (seconds). Overcurrent" lasting
        more than set value (1 to 9999) causes the channel to "trip".
        Output voltage will drop to zero either at the Ramp-down rate or at the fastest available rate,
        depending on Power Down setting;
        in both cases the channel is put in the off state.
        If trip= INFINITE, "overcurrent" lasts indefinitely.
        TRIP range: 0 ÷ 999.9s; 1000 s = Infinite. Step = 0.1 s. """
        cmd = f"$CMD:SET,CH:{channel},PAR:TRIP,VAL:{time}"
        self.query(cmd)
        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set trip on CH {channel} to {time}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    def set_power_down_mode(self, channel: int, mode: str):
        """RAMP/KILL"""
        mode = mode.upper()
        cmd = f"$CMD:SET,CH:{channel},PAR:PDWN,VAL:{mode}"
        self.query(cmd)
        # self.send_to_CAEN(cmd)
        # response = self.receive_from_CAEN()
        # self._check_response(response)
        #
        # if self.verbose:
        #     print(f"Set power down mode on CH {channel} to {mode}: \t {response}")
        # logger.info(f"[CAEN] Sent: {cmd} \t Received: {response}")

    ### Helpers
    def send_to_CAEN(self, cmd_str):
        data = (cmd_str + '\r\n').encode()
        try:
            if self.using_usb:
                self.ep_out.write(data)
                time.sleep(0.1)
            elif self.using_serial:
                self.serial.write(data)
            elif self.using_ethernet:
                self.socket.sendall(data)
            else:
                raise LabscriptError("[CAEN] No connection with module is established.")
        except Exception as e:
            logger.error(f"[CAEN] Write failed: {e}")
            raise LabscriptError(f"[CAEN] Failed to send command: {e}")

    def receive_from_CAEN(self):
        try:
            if self.using_usb:
                response = self.ep_in.read(64, timeout=3)
                response_str = bytes(response).decode('ascii', errors='ignore')
                return response_str
            if self.using_serial:
                response = self.serial.readline().decode().strip()
                return response
            if self.using_ethernet:
                response = self.socket.recv(512) # buffer read bytes=512
                return response.decode(errors='ignore').strip()
            return None
        except Exception as e:
            logger.error(f"[CAEN] Read from CAEN failed: {e}")
            return 'USB_ERROR' if self.using_usb else 'SERIAL_ERROR' if self.using_serial else 'Ethernet_ERROR'

    def _check_response(self, response: str):
        """Raises descriptive errors based on CAEN serial error codes.
            #<header>:<result>[,VAL:<par_val>]<CR><LF>
                header = {"CMD", "LOC", "VAL", "CH", "PAR"}
                result = {"OK", "ERR"}
        """
        error_map = {
            "#CMD:ERR": "Wrong attribute, should be 'SET'",
            "#LOC:ERR": "SET command in local mode",
            "#VAL:ERR": "Wrong 'VAL' field value in SET command",
            "#CH:ERR": "Wrong 'CH' field value",
            "#PAR:ERR": "Wrong 'PAR' field value"
        }
        for prefix, message in error_map.items():
            if response.startswith(prefix):
                raise LabscriptError(message)

    def query(self, cmd: str, expect_val: bool = False) -> str | float:
        self.send_to_CAEN(cmd)
        response = self.receive_from_CAEN()
        self._check_response(response)

        if self.verbose:
            print(f"Sent: {cmd}\tResponse: {response}")
        logger.info(f"[CAEN] Sent: {cmd}\tReceived: {response}")

        if expect_val:
            parts = response.strip().split(',')
            if len(parts) < 2 or not parts[1].startswith("VAL:"):
                raise LabscriptError(f"[CAEN] Unexpected response format: {response}")
            return float(parts[1][4:])

        return response

