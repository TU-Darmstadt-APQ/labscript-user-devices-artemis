# BS 1-10 Cryo Biasing 
The bias supply for amplifiers. 
Biasing is for delivery of an accurate and stable voltage for operation of transistors that require a stable supply to ensure minimal noise and optimal performance.
In order for a transistor to amplify a signal, it needs to be sepplied with bias voltage, which sets it to an operating point where it can amplify weak singnals. 

---
## Connection interface (USB)
To enable communication over USB, appropriate drivers are required.
You can download them from the official FTDI website: [here](https://ftdichip.com/drivers/)

On Linux systems, the Virtual COM Port (VCP) driver (ftdi_sio) is already included in the kernel and is usually loaded automatically.
If it's not active, you can manually load it using: `sudo modprobe ftdi_sio`

If your FTDI-based device is programmed with a custom Product ID (PID) and is not automatically recognized by the system, you need to manually inform the driver about the device.

Use the following commands:
``` bash
sudo modprobe ftdi_sio
echo VVVV PPPP | sudo tee /sys/bus/usb-serial/drivers/ftdi_sio/new_id
```
- VID: VVVV
- PID: PPPP (custom)

Refer to the [FTDI FAQ on custom PIDs](https://ftdichip.com/faq/how-do-i-add-a-custom-pid-to-the-ftdi_sio-linux-com-port-driver/) for more details.


Once the device is plugged in via USB, verify that it's recognized using: `ls /dev/ttyUSB*` or `dmesg | tail -n 20`. (Or run `python ftdi_scanner.py` to list all connected ftdi devices). If the device appears (e.g., /dev/ttyUSB0), you can communicate with it using pyserial.

---
## Remote Commands
IDN | Identify
DDDDD CHXX Y.YYYYY | Set voltage
DDDDD TEMP | Read Temperature
DDDDD LOCK | Check lock status of all channels
DDDDD DIS [message] | Send string to LCD-display