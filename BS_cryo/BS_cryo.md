# BS 1-10 Cryo Biasing 
Bias supply for powering cryogenic amplifiers. 
Documentation: see the official [Manual](https://www.stahl-electronics.com/devices/bs/BS-Series_Voltage_Source_v3_35.pdf)
---
## Connection interface (USB)
After connecting the device, verify that the system detects the USB–serial interface:
```bash
ls /dev/ttyUSB* 
# or
dmesg | tail -n 20
# or 
python ftdi_scanner.py
```
These commands will list all connected ftdi devices.

## Supported Device Commands
The following protocol operations are implemented:
1. get_voltage(channel) 
2. get_current(channel) (not used in labscript)
3. get_voltage_and_current(channel) (not used in labscript)
4. set_voltage(channel, voltage)
5. get_temperature()
6. get_lock_status()
7. get_info()

## Timing limitations in experiments
The Stahl BS series does not support pre-programmed timing sequences.
All voltage changes must be sent live during the experiment, via single serial commands.
Labscript does not provide timing mechanisms for devices that require live command streaming.
Because of this, strict timing with Stahl BS devices is impossible. 
The current implementation supports two working modes, 
neither of which solves precise timing, but they allow practical use depending 
on experiment requirements.

### Pre-programmed mode
Activated via `pre_programmed=True`.
```python
BS_cryo(name="BS_cryo_10CH", parent_device=clockline, ao_range=10, num_ao=10, port='/dev/pts/0', pre_programmed=True)
```

Behavior:
- Only the first timing point for each channel is used.
- Labscript will ignore all later voltage changes in the experiment script.
- The device is configured once before experiment start, and its voltages remain constant for the entire shot.

Note: define voltages to all channels in experiment script at timestamp t=0 using `constant`:
```python
t=0
BS_10_0.constant(t=t, value=10.0)
...
```


### During-shot programmed mode:
(For experiments where the bias does change, but timing does not need to be accurate.)
**Note: no timing benchmarking has been conducted.**

Behavior:
- The experiment sequence for this device starts executing already in transition_to_buffered(). 
(transition_to_buffered() happens before the shot actually starts.)
- As a result, the commands are applied earlier than intended.

To minimize this offset, force the bias supply to run its transition_to_buffered() last, 
so its commands sequence begins as close as possible to the actual experiment start:
```python
 BS_cryo(name="BS_cryo_10CH", parent_device=clockline, ao_range=10, num_ao=10, port='/dev/pts/0', start_order=10)
```
`start_order=X` controls the ordering of transition_to_buffered() execution for devices.

This mode is acceptable only when experiment timing is loose (ms-level or worse). 
It cannot be used for synchronized or deterministic voltage switching.

## Emulator
An emulator is provided to allow experimentation with Labscript without real hardware.
Run from  `user_device` directory:
```bash
python3 -m BS_cryo.testing.emulateSerPort
```
This creates a virtual serial port (e.g., /dev/pts/1).
Use this in the connection table: `port='/dev/pts/1'`
The emulator must remain running; it behaves like a real device and supports the same protocol.

## Usage
```python
from user_devices.Stahl_HV.labscript_devices import AnalogOutStahl
from user_devices.BS_cryo.labscript_devices import BS_cryo
from labscript import start, stop, add_time_marker, AnalogOut,

BS_cryo(name="BS_cryo_10CH", parent_device=clockline, ao_range=10, num_ao=10, port='/dev/pts/0', pre_programmed=True)
AnalogOutStahl(name='BS_10_0', parent_device=BS_cryo_10CH, connection='ch 0', default_value=10)
AnalogOutStahl(name='BS_10_1', parent_device=BS_cryo_10CH, connection='ch 1')
AnalogOutStahl(name='BS_10_2', parent_device=BS_cryo_10CH, connection='ch 2')
AnalogOutStahl(name='BS_10_3', parent_device=BS_cryo_10CH, connection='ch 3')
AnalogOutStahl(name='BS_10_4', parent_device=BS_cryo_10CH, connection='ch 4')
AnalogOutStahl(name='BS_10_5', parent_device=BS_cryo_10CH, connection='ch 5', ao_range=5)
AnalogOutStahl(name='BS_10_6', parent_device=BS_cryo_10CH, connection='ch 6', ao_range=5)
AnalogOutStahl(name='BS_10_7', parent_device=BS_cryo_10CH, connection='ch 7', ao_range=5)
AnalogOutStahl(name='BS_10_8', parent_device=BS_cryo_10CH, connection='ch 8', ao_range=5)
AnalogOut(name='BS_10_9', parent_device=BS_cryo_10CH, connection='ch 9')

if __name__ == '__main__':
    t = 0
    add_time_marker(t, "Start", verbose=True)
    start()
    
    BS_10_0.constant(t=t, value=1)
    BS_10_9.constant(t=t, value=5)
    BS_10_1.constant(t=t, value=1)
    BS_10_2.constant(t=t, value=1)
    BS_10_3.constant(t=t, value=1)
    BS_10_4.constant(t=t, value=1)
    BS_10_5.constant(t=t, value=1)
    BS_10_6.constant(t=t, value=1)
    BS_10_7.constant(t=t, value=1)
    BS_10_8.constant(t=t, value=1)
    
    stop(1)
```

You can define per-channel voltage ranges directly in `AnalogOutStahl`.
If no range is specified, the channel inherits the default range defined in `BS_cryo`.