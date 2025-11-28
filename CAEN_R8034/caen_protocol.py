import socket
import serial
from labscript import LabscriptError
from user_devices.logger_config import logger
import serial.tools.list_ports
import re
from typing import Optional

class TransportError(Exception):
    pass


class ProtocolError(Exception):
    pass


class CAENError(Exception):
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

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except Exception:
            pass

class SerialTransport(Transport):
    """Serial transport wrapper around pyserial.Serial.    """
    def __init__(self, baud: int,
                 port: Optional[str] = None,
                 pid: Optional[str] = None,
                 vid: Optional[str] = None,
                 serial_number: Optional[str] = None,
                 timeout: float = 1.0):

        self.ser: Optional[serial.Serial] = None
        self.timeout = timeout
        self.baud = baud

        if port and (pid or vid):
            raise ValueError("Specify either port OR (pid,vid), not both")

        try:
            if port:
                self.ser = serial.Serial(port, baud, timeout=timeout)
            elif pid and vid:
                found = self._find_and_open_by_vid_pid(vid, pid, serial_number, baud, timeout)
                if not found:
                    raise TransportError(f"No serial device found with VID={vid} PID={pid} SN={serial_number}")
            else:
                raise ValueError("Either port or (pid and vid) must be provided")
        except Exception:
            if self.ser is not None and self.ser.is_open:
                try:
                    self.ser.close()
                except Exception:
                    pass
            raise

    def _find_and_open_by_vid_pid(self, vid: str, pid: str, serial_number: Optional[str], baudrate: int,
                                  timeout: float) -> bool:
        vid = vid.upper()
        pid = pid.upper()
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            try:
                hwid = (p.hwid or "").upper()
                if vid in hwid and pid in hwid:
                    logger.debug("Candidate port %s (hwid=%s)", p.device, p.hwid)
                    tmp = serial.Serial(p.device, baudrate, timeout=timeout)
                    if serial_number:
                        try:
                            tmp.write(("$CMD:MON,PAR:BDSNUM\r\n").encode())
                            response = tmp.readline().decode(errors="ignore").strip()
                            m = re.match(r"#CMD:OK,VAL:(.+)$", response)
                            if m:
                                found_sn = m.group(1)
                                if found_sn == serial_number:
                                    self.ser = tmp
                                    logger.info("Opened serial %s for serial_number=%s", p.device, serial_number)
                                    return True
                                else:
                                    tmp.close()
                                    continue
                            else:
                                # no valid probe
                                tmp.close()
                                continue
                        except Exception:
                            try:
                                tmp.close()
                            except Exception:
                                pass
                            continue
                    else:
                        # no serial_number check requested -> accept first match
                        self.ser = tmp
                        logger.info("Opened serial %s by VID/PID match", p.device)
                        return True
            except Exception as e:
                logger.debug("Error probing port %s: %s", getattr(p, "device", "<?>"), e)
                continue
        return False

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
            b = self.ser.readline()
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

class EthTransport(Transport):
    def __init__(self, host: str, port: int, timeout: float = 3.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)


    def write(self, data: bytes) -> None:
        try:
            self.sock.sendall(data)
        except Exception as e:
            raise TransportError(f"Socket write failed: {e}") from e


    def read_line(self, timeout: float | None = None) -> bytes:
        # read until CRLF
        prev_timeout = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            buf = bytearray()
            while True:
                chunk = self.sock.recv(1)
                if not chunk:
                    # connection closed
                    raise TransportError("Socket closed")
                buf += chunk
                if buf.endswith(b"\r\n"):
                    return bytes(buf)
        except socket.timeout as e:
            raise TransportError("Socket read timeout") from e
        except Exception as e:
            raise TransportError(f"Socket read failed: {e}") from e
        finally:
            if timeout is not None:
                self.sock.settimeout(prev_timeout)


    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class CAENProtocol:
    """Formats commands, sends via Transport, parses responses."""
    RE_OK_VAL = re.compile(r"^#CMD:OK,VAL:(.+)$")
    RE_OK = re.compile(r"^#CMD:OK$")
    RE_ERR = re.compile(r"^#CMD:ERR(?:,(.*))?$")
    RE_LOC_ERR = re.compile(r"^#LOC:ERR(?:,(.*))?$")
    RE_VAL_ERR = re.compile(r"^#VAL:ERR(?:,(.*))?$")
    RE_CH_ERR = re.compile(r"^#CH:ERR(?:,(.*))?$")
    RE_PAR_ERR = re.compile(r"^#PAR:ERR(?:,(.*))?$")

    RE_GENERIC = re.compile(r"^#(.*)$")

    def __init__(self, transport: Transport, write_timeout: float = 1.0, read_timeout: float = 2.0):
        self.transport = transport
        self.write_timeout = write_timeout
        self.read_timeout = read_timeout

    def close(self):
        if self.transport:
            self.transport.close()
            self.transport = None

    def _format_cmd(self, attribute: str, par: Optional[str] = None, val: Optional[str] = None, ch: Optional[int] = None) -> str:
        """ attribute is one of INFO/SET/MON."""
        parts = [f"$CMD:{attribute}"]
        if ch is not None:
            parts.append(f"CH:{int(ch)}")
        if par is not None:
            parts.append(f"PAR:{par}")
        if val is not None:
            parts.append(f"VAL:{val}")
        return ",".join(parts)

    def send_raw(self, cmdstr: str) -> None:
        data = (cmdstr + "\r\n").encode()
        self.transport.write(data)

    def read_raw(self) -> str:
        raw = self.transport.read_line(timeout=self.read_timeout)
        try:
            return raw.decode(errors="ignore").strip()
        except Exception as e:
            raise ProtocolError(f"Failed to decode raw response: {e}") from e

    def query(self, cmdstr: str, expect_val: bool = False) -> Optional[str]:
        try:
            self.send_raw(cmdstr)
            resp = self.read_raw()
            # print(f"\t {cmdstr} \t {resp}")
            return self._parse_response(resp, expect_val)
        except (TransportError, ProtocolError) as e:
           raise e

    def _parse_response(self, response: str, expect_val: bool) -> Optional[str]:
        if response is None:
            raise ProtocolError("Empty response")
        m_val = self.RE_OK_VAL.match(response)
        if m_val:
            val = m_val.group(1)
            if expect_val:
                return val
            return None
        if self.RE_OK.match(response):
            if expect_val:
                return None  # OK with no value
            return None

        # Error handling
        m_err = self.RE_ERR.match(response)
        if m_err:
            extra = m_err.group(1)
            raise CAENError(f"CAEN reported error (Wrong attribute, should be 'SET'): {extra}")
        m_loc_err = self.RE_LOC_ERR.match(response)
        if m_loc_err:
            raise CAENError("SET command in local mode")
        m_val_err = self.RE_VAL_ERR.match(response)
        if m_val_err:
            raise CAENError("Wrong 'VAL' field value in SET command")
        m_par_err = self.RE_PAR_ERR.match(response)
        if m_par_err:
            raise CAENError("Wrong 'PAR' field value")
        m_ch_err = self.RE_CH_ERR.match(response)
        if m_ch_err:
            raise CAENError("Wrong 'CH' field value")

        if expect_val:
            return response # error??
        return None

    # High-level helpers
    def make_set(self, par: str, val: str, ch: Optional[int] = None) -> str:
        return self._format_cmd("SET", par=par, val=val, ch=ch)

    def make_mon(self, par: str, ch: Optional[int] = None) -> str:
        return self._format_cmd("MON", par=par, ch=ch)

    def make_info(self, par: str, ch: Optional[int] = None) -> str:
        return self._format_cmd("INFO", par=par, ch=ch)


class CAENDevice:
    """High-level device API. Channels indexed 0..N-1."""
    def __init__(self, port=None, baud_rate=9600, vid=None, pid=None, serial_number=None):
        if port or (pid and vid):
            transport = SerialTransport(port=port, baud=baud_rate, pid=pid, vid=vid, serial_number=serial_number)
        else:
            transport = EthTransport(host='192.168.0.250', port=1470)

        self.protocol = CAENProtocol(transport=transport)

    def close(self):
        # set VSET to 0 and disable
        for ch in range(8):
            self.set_voltage(ch, 0)
            self.enable_channel(ch, False)
        self.protocol.close()

    # Board-level
    def read_board_serial(self) -> str:
        return self.protocol.query(self.protocol.make_mon("BDSNUM"), expect_val=True)

    def set_control_mode(self, mode: str):
        self.protocol.query(self.protocol.make_set("BDCTR", val=mode), expect_val=False)

    def monitor_control_mode(self) -> str:
        return self.protocol.query(self.protocol.make_mon("BDCTR"), expect_val=True)

    def set_interlock_mode(self, mode: str):
        mode = str(mode).upper()
        cmd = self.protocol.make_set("BDILKM", val=mode)
        return self.protocol.query(cmd, expect_val=False)

    def clear_alarm_signal(self):
        cmd = self.protocol.make_set("BDCLR")
        return self.protocol.query(cmd, expect_val=False)

    # Channel-level
    def enable_channel(self, channel: int, enable: bool = True):
        val = "ON" if enable else "OFF"
        cmd = self.protocol.make_set("PW", val=val, ch=channel)
        self.protocol.query(cmd, expect_val=False)

    def set_voltage(self, channel: int, voltage: float):
        cmd = self.protocol.make_set("VSET", val=str(float(voltage)), ch=channel)
        self.protocol.query(cmd, expect_val=False)

    def monitor_voltage(self, channel: int) -> float:
        val = self.protocol.query(self.protocol.make_mon("VMON", ch=channel), expect_val=True)
        try:
            return float(val)
        except Exception as e:
            raise ProtocolError(f"Failed to parse VMON response '{val}': {e}")

    def set_current(self, channel: int, current: float):
        cmd = self.protocol.make_set("ISET", val=str(float(current)), ch=channel)
        self.protocol.query(cmd, expect_val=False)

    def monitor_current(self, channel: int) -> float:
        val = self.protocol.query(self.protocol.make_mon("IMON", ch=channel), expect_val=True)
        try:
            return float(val)
        except Exception as e:
            raise ProtocolError(f"Failed to parse IMON response '{val}': {e}")

    def set_ramp_up_rate(self, channel: int, rate: float):
        cmd = self.protocol.make_set("RUP", val=str(float(rate)), ch=channel)
        return self.protocol.query(cmd, expect_val=False)

    def set_ramp_down_rate(self, channel: int, rate: float):
        cmd = self.protocol.make_set("RDWN", val=str(float(rate)), ch=channel)
        return self.protocol.query(cmd, expect_val=False)

    def trip(self, channel: int, time_s: float):
        cmd = self.protocol.make_set("TRIP", val=str(float(time_s)), ch=channel)
        return self.protocol.query(cmd, expect_val=False)

    def set_power_down_mode(self, channel: int, mode: str):
        cmd = self.protocol.make_set("PDWN", val=str(mode).upper(), ch=channel)
        return self.protocol.query(cmd, expect_val=False)

    def get_status(self, channel:int) -> str:
        cmd = self.protocol.make_mon("STATUS", ch=channel)
        return self.protocol.query(cmd, expect_val=True)





