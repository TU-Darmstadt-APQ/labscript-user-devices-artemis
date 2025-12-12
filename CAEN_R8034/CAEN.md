# CAEN R8034

The CAEN R8034 is a power supply with 8 independent ±6 kV / 1 mA channels. 
Communication is possible via USB-to-serial or ETH, although only USB has been tested. 
The user device supports multiple polarity configurations: 8 positive, 8 negative, or 4 positive + 4 negative channels.

## Communication
The device can be connected in two ways:
### By PID:VID and serial number
To connect, you need the device’s PID and VID, which can be obtained using:
```lsusb```
Identify your CAEN device and note its PID and VID. 
The device’s unique serial number (PID) is on the back panel.
```python
CAEN(name='CAEN_example', parent_device=clockline, vid='21e1', pid="0014", serial_number="00000")
```
### By serial port
You can also use the serial port assigned to the device. 
Note that the port may change each PC start.
```python
CAEN(name='CAEN_example', parent_device=clockline, port='/dev/pts/0')
```

### USB Troubleshooting
If you get `errno 13: access denied`, add a udev rule:
```bash
sudo nano /etc/udev/rules.d/99-caen-device.rules
```
Set the PID and VID according to your device, then reload rules:
```bash
sudo udevadm control --reload
sudo udevadm trigger
```
Unplug and replug the device afterwards.

## Timing limitation
The CAEN HV series does not support pre-programmed timing sequences.
All voltage changes must be sent live during the experiment, via single serial commands.
Labscript does not provide timing mechanisms for devices that require live command streaming.
Because of this, strict timing with CAEN devices is impossible. 
The current implementation supports single pre-programmed voltage per channel per shot.

Behavior:
- Only the first timing point for each channel is used.
- Labscript will ignore all later voltage changes in the experiment script.
- The device is configured once before experiment start, and its voltages remain constant for the entire shot.

Note: define voltages to all channels in experiment script at timestamp t=0 using `constant`:
```python
t=0
caen_channel_1.constant(t=t, value=10.0)
...
```


## Emulator
An emulator is provided to allow experimentation with Labscript without real hardware.
Run from  `user_device` directory:
```bash
python3 -m CAEN_R8034.testing.emulateSerPort
```
This creates a virtual serial port (e.g., /dev/pts/1).
Use this in the connection table: `port='/dev/pts/1'`
The emulator must remain running; it behaves like a real device and supports the same protocol.


## Usage
```python
from user_devices.CAEN_R8034.labscript_devices import CAEN
from labscript import start, stop, add_time_marker, AnalogOut
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock

DummyPseudoclock('pseudoclock')
clockline = pseudoclock.clockline
    
CAEN(
    name='CAEN_example',
    parent_device=clockline,
    vid="21e1",
    pid="0014",
    baud_rate=9600,
    bipol=False,
    serial_number="00000",
    start_order=-1 # Configure this device first
)

if __name__ == '__main__':
    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()

    AnalogOut(name='ch_0', parent_device=CAEN_example, connection='ch 0')
    AnalogOut(name='h_1', parent_device=CAEN_example, connection='ch 1')
    AnalogOut(name='h_2', parent_device=CAEN_example, connection='ch 2')
    AnalogOut(name='h_3', parent_device=CAEN_example, connection='ch 3')
    AnalogOut(name='h_4', parent_device=CAEN_example, connection='ch 4')
    AnalogOut(name='h_5', parent_device=CAEN_example, connection='ch 5')
    AnalogOut(name='h_6', parent_device=CAEN_example, connection='ch 6')
    AnalogOut(name='h_7', parent_device=CAEN_example, connection='ch 7')
    
    stop(1)   
```
