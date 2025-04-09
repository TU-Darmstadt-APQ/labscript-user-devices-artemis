"""
Simulate the serial port, as I don't have access to the real device.

You will create a virtual serial port using this script. This script will act as if it’s the device. When you run the script, it will open a serial port (for example, /dev/pts/1) and allow other programs (such as your BLACS worker) to communicate with it.

The virtual serial port should stay open while the simulation is running, so other code that expects to interact with the serial device can do so just as if the actual device were connected.

In the userlib directory, run the following command:
    python3 -m user_devices.UM.emulateSerPort

"""
import os, pty, time
from logger_config import logger

def read_command(master):
    """ Reads the command until the '\r' character is encountered.
    Args:
        master: file descriptor to read from
    Returns: 
        received command in bytes format
    """
    return b"".join(iter(lambda: os.read(master, 1), b"\r"))

def test_serial():
    master, slave = pty.openpty()
    port_name = os.ttyname(slave)
    print(f"For UM use: {port_name}")
    
    while True:
        device_identity = "UM01\r"  
        command = read_command(master).decode().strip()
        if command:
            print("command {}".format(command))
            if command == "IDN":
                response = device_identity.encode() 
                os.write(master, response)
            elif command.startswith("UM01 CH"):
                device, channel, voltage = command.split()[:3]
                response = f"{channel} {voltage}\r"
                os.write(master, response.encode())
            elif command.startswith("UM01 ULTRA"):
                device, mode, sec_channel = command.split()[:3]
                response = f"{mode} {sec_channel}\r"
                os.write(master, response.encode())
            elif command.startswith("UM01 ULTRA"):
                device, mode, sec_channel = command.split()[:3]
                response = f"{mode} {sec_channel}\r"
                os.write(master, response.encode())
            else:
                response = "err\r"
                os.write(master, response.encode())
                
        time.sleep(0.1)
         
if __name__ == "__main__":
    test_serial()