# CAEN R8034

The CAEN R8034 is a power supply with 8 independent ±6 kV / 1 mA channels. 
Communication is possible via USB-to-serial or ETH, although only USB has been tested. 
The user device supports multiple polarity configurations: 8 positive, 8 negative, or 4 positive + 4 negative channels.
---
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

---

## Emulator
An emulator is provided to allow experimentation with Labscript without real hardware.
Run from  `user_device` directory:
```bash
python3 -m CAEN_R8034.testing.emulateSerPort
```
This creates a virtual serial port (e.g., /dev/pts/1).
Use this in the connection table: `port='/dev/pts/1'`
The emulator must remain running; it behaves like a real device and supports the same protocol.


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
t=0 # Important: set voltages at timepoint t=0
caen_channel_1.constant(t=t, value=10.0)
caen_channel_2.constant(t=t, value=global_variable_for_channel_2) # defined in RunManager
...
```

---
### Voltage settling and experiment start
The experiment can be configured to start only after all channel voltages have stabilized.
To achieve this, the CAEN device should be initialized first by setting `start_order = -1` and validating that the voltages have settled.

Two settling strategies are supported: deterministic and non-deterministic.

### Deterministic strategy
The device waits for a fixed settling time calculated in [_calculate_settling_time](BLACS_workers.py).
The calculation depends on:
- ramp rate,
- decay time,
- ramp step size,
- ramp direction (downward ramps are usually slower).

To use this strategy:
- `decay_time` must be defined,
- `timeout` must be set to `None`.

The `decay_time` should be measured beforehand.
After waiting, the settled voltages are validated by comparing the target values with the monitored voltages.
If the difference exceeds the allowed threshold, a LabscriptError is raised and the shot sequence execution is stopped.

### Non-Deterministic strategy
In this mode, the device is polled in a loop until either:
- all enabled channels are settled, or
- the timeout is exceeded.

To use this strategy:
- `timeout` must be defined,
- `decay_time` must be set to None.

If the timeout is exceeded while some channels are still unsettled, a LabscriptError is raised and the shot sequence execution is stopped.

---

## Usage
Hardware checklist:
- Caen is powered on.
- Channels are physically turned on.
- Caen is in remote mode.

```python
from user_devices.CAEN_R8034.labscript_devices import CAEN, CaenAnalogOut
from labscript import start, stop, add_time_marker, AnalogOut
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock

DummyPseudoclock('pseudoclock')
clockline = pseudoclock.clockline
    
CAEN(
    name='CAEN_example',
    parent_device=clockline,
    # port='/dev/pts/1',
    vid="21e1",
    pid="0014",
    baud_rate=9600,
    bipol=False,
    ramp_up=10,             # in V/s
    ramp_down=10,           # in V/s
    timeout=None,
    threshold=2,            # in Volts
    decay_time=0.05,        # in seconds
    ch_num=8,
    output_voltage=6000,
    serial_number="12345",
    start_order=-1
)
CaenAnalogOut(name='ch_0', parent_device=CAEN_example, connection='ch 0', enable=True)
CaenAnalogOut(name='ch_1', parent_device=CAEN_example, connection='ch 1', enable=True)
CaenAnalogOut(name='ch_2', parent_device=CAEN_example, connection='ch 2', enable=True)
CaenAnalogOut(name='ch_3', parent_device=CAEN_example, connection='ch 3', enable=True)
CaenAnalogOut(name='ch_4', parent_device=CAEN_example, connection='ch 4', enable=False) # channel is disabled to achieve 0V
CaenAnalogOut(name='ch_5', parent_device=CAEN_example, connection='ch 5', enable=False)
CaenAnalogOut(name='ch_6', parent_device=CAEN_example, connection='ch 6', enable=False)
CaenAnalogOut(name='ch_7', parent_device=CAEN_example, connection='ch 7', enable=False)

if __name__ == '__main__':
    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()
    ch_0.constant(t=t, value=100)
    ch_1.constant(t=t, value=200)
    ch_2.constant(t=t, value=250)
    ch_3.constant(t=t, value=global_variable_ch_3) 
    
    stop(1)   
```

### [Managing global variables](https://docs.labscriptsuite.org/projects/runmanager/en/latest/usage/#managing-global-variables)
Global variables are defined and edited in RunManager.