"""
Simulate the serial port, as I don't have access to the real device.

You will create a virtual serial port using this script. This script will act as if it’s the device. When you run the script, it will open a serial port (for example, /dev/pts/1) and allow other programs (such as your BLACS worker) to communicate with it.

The virtual serial port should stay open while the simulation is running, so other code that expects to interact with the serial device can do so just as if the actual device were connected.

In the user_devices directory, run the following command:
    python3 -m CAEN_R8034.emulateSerPort

"""
import os, pty, time
from logger_config import logger
import random
import re

SET_CH_VOL = re.compile(r"^\$CMD:SET,CH:(.+),PAR:VSET(?:,VAL:.+)?$")
MON_CH_VOL = re.compile(r"^\$CMD:MON,CH:(.+),PAR:VMON$")
MON_CH_STATUS = re.compile(r"^\$CMD:MON,CH:(.+),PAR:STATUS$")
SET_CH_EN = re.compile(r"^\$CMD:SET,CH:(.+),PAR:PW(?:,VAL:.+)?$")

MON_BD_SNUM = re.compile(r"^\$CMD:MON,PAR:BDSNUM$")
MON_BD_BDCTR =  re.compile(r"^\$CMD:MON,PAR:BDCTR$")



def read_command(master):
    """ Reads the command until the '\r' character is encountered.
    Args:
        master: file descriptor to read from
    Returns: 
        received command in bytes format
    """
    buffer = b""
    while not buffer.endswith(b"\r\n"):
        buffer += os.read(master, 1)
    return buffer.strip()

def test_serial():
    master, slave = pty.openpty()
    port_name = os.ttyname(slave)
    print(f"For CAEN use: {port_name}")
    
    while True:
        command = read_command(master).decode()
        if command:
            print(f"command {command}")
            # logger.debug(f"[CAEN] command from remote: {command} ")
            if SET_CH_VOL.match(command) or SET_CH_EN.match(command):
                response = "#CMD:OK\r\n"
            elif MON_CH_VOL.match(command):
                response = "#CMD:OK,VAL:2000.0\r\n"
            elif MON_CH_STATUS.match(command):
                statuses = ["04096", "04112", "00001", "04096"]
                status = random.choice(statuses)
                response = f"#CMD:OK,VAL:{status}\r\n"
            elif MON_BD_SNUM.match(command):
                response = random.choice(["#CMD:OK,VAL:12000\r\n", "#CMD:OK,VAL:24200\r\n"])
            elif MON_BD_BDCTR.match(command):
                response = "#CMD:OK,VAL:REM\r\n"
            else:
                response = "err\r\n"
            os.write(master, response.encode())
         
if __name__ == "__main__":
    test_serial()