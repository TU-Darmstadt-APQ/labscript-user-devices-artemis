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
            if command.startswith("$CMD:SET"):
                response = "#CMD:OK\r\n"
            elif command.startswith("$CMD:MON"):
                response = "#CMD:OK,VAL:2000.0\r\n"
            elif command.startswith("$CMD:INFO"):
                response = random.choice(["#CMD:OK,VAL:DT2000\r\n", "#CMD:OK,VAL:OK200\r\n"])
            else:
                response = "err\r\n"
            os.write(master, response.encode())
         
if __name__ == "__main__":
    test_serial()