"""
Emulate the serial port for the BS 34-1A.

You will create a virtual serial port using this script.
This script will act as if it’s the HV-stahl device. When you run the script, it will open a serial port
(e.g., /dev/pts/1) and allow other programs (such as your BLACS worker) to communicate with it.

The virtual serial port should stay open while the simulation is running,
so other code that expects to interact with the serial device can do so just as if the actual device were connected.

Run following command in the corresponding folder.
    python3 -m HV_stahl_old.testing.emulateSerPort
"""
import os, pty, time
from logger_config import logger
import random
import re

SET_CH_VOL = re.compile(r"^(.{5}) CH(.+) (.{8})$")
MON_CH_VOL = re.compile(r"^(.{5}) Q(.+)$")
MON_LOCK_STATUS = re.compile(r"^(.{5}) LOCK$")
MON_TEMP = re.compile(r"^(.{5}) TEMP$")
IDN = re.compile(r"^IDN$")

def read_command(master):
    """ Reads the command until the '\r' character is encountered.
    Args:
        master: file descriptor to read from
    Returns:
        received command in bytes format
    """
    buffer = b""
    while not buffer.endswith(b"\r"):
        buffer += os.read(master, 1)
    return buffer.strip()


def test_serial():
    master, slave = pty.openpty()
    port_name = os.ttyname(slave)
    print(f"For Stahl HV use: {port_name}")

    while True:
        command = read_command(master).decode()
        if command:
            if SET_CH_VOL.match(command):
                m = SET_CH_VOL.match(command)
                ch = m.group(2)
                vol = m.group(3)
                response = f"CH{ch} {vol}\r"
            elif MON_CH_VOL.match(command):
                response = "+22,000 V\r"
            elif MON_LOCK_STATUS.match(command):
                b3 = bytes([0x10])
                b2 = bytes([0x10])
                b1 = bytes([0x10])
                b0 = bytes([0x10])
                status = b3 + b2 + b1 + b0
                response = status + "\r".encode()
            elif MON_TEMP.match(command):
                response = random.choice(["TEMP 050.5ºC\r", "TEMP 076.5ºC\r",])
            elif IDN.match(command):
                response = "HV100 500 8 b\r"
            else:
                response = "err\r"

            if isinstance(response, bytes):
                os.write(master, response)
            else:
                os.write(master, response.encode())

            print(f"command {command} \t response {response}")


if __name__ == "__main__":
    test_serial()
