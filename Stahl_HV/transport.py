import serial
import serial.tools.list_ports
from typing import Optional

class TransportError(Exception):
    pass

class Transport:
    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read_line(self, timeout: float | None = None) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self):
        try:
            self.close()
        except Exception:
            pass

class SerialTransport(Transport):
    """Serial transport wrapper around pyserial.Serial.    """
    def __init__(self, baud: int,
                 port: Optional[str] = None,
                 vid: Optional[str] = None,
                 pid: Optional[str] = None,
                 serial_number: Optional[str] = None,
                 timeout: float = 1.0):

        self.ser: Optional[serial.Serial] = None
        self.timeout = timeout
        self.baud = baud
        self.serial_number = None

        try:
            if port:
                self.ser = serial.Serial(port, baud, timeout=timeout)
                self.serial_number = self._query_device_serial(self.ser)
            elif not port and (vid and pid and serial_number):
                self.serial_number = serial_number
                self._find_port_by_hwid(vid=vid, pid=pid, serial_number=serial_number)
            elif not port and not vid and not pid and serial_number:
                self.serial_number = serial_number
                self._find_port_by_serial(serial_number=self.serial_number)
            else:
                raise ValueError("Connection failed. Required port or (pid, vid, serial_number).")
        except Exception:
            if self.ser is not None and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            raise

    def _find_port_by_hwid(self, vid, pid, serial_number):
        for port in serial.tools.list_ports.comports():
            if (port.vid and port.vid == vid) and (port.pid and port.pid == pid):
                temp_ser = serial.Serial(port.device, self.baud)
                recv_serial = self._query_device_serial(temp_ser)
                if recv_serial == serial_number:
                    self.ser = temp_ser

    def _find_port_by_serial(self, serial_number):
        for port in serial.tools.list_ports.comports():
            temp_ser = serial.Serial(port.device, self.baud)
            recv_serial = self._query_device_serial(temp_ser)
            if recv_serial == serial_number:
                self.ser = temp_ser
            else:
                temp_ser.close()

    def _query_device_serial(self, ser) -> str:
        cmd = "IDN\r"
        ser.write(cmd.encode())
        resp = ser.readline()
        serial_num = resp.decode().split()[0] # get the serial number
        return serial_num

    def write(self, data: bytes) -> None:
        if not self.ser or not self.ser.is_open:
            raise TransportError("Serial port not open")
        try:
            self.ser.write(data)
        except Exception as e:
            raise TransportError(f"Serial write failed: {e}") from e

    def read_line(self, timeout: float | None = None) -> bytes:
        if not self.ser or not self.ser.is_open:
            raise TransportError("Serial port not open")
        try:
            b = self.ser.read_until(b'\r')
            if b is None:
                raise TransportError("Serial read returned None")
            return b
        except Exception as e:
            raise TransportError(f"Serial read failed: {e}") from e

    def close(self) -> None:
        if self.ser:
            try:
                if self.ser.is_open:
                    self.ser.close()
                self.ser = None
            except Exception:
                pass
