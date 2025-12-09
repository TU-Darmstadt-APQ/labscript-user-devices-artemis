# HV Series High Voltage Source

Labscript support for Stahl HV series high-voltage power supplies (Serial-controlled, non-buffered devices).
Commands are sent via a standard serial interface with a standard baud 
rate of 9600.

---
## Timing Strategy

The hardware provides **no internal clock, no command buffering, and no trigger
input**, so all timing is handled in software.
The difference between models is the allowed voltage range and channels number.
Per-channel voltage limits can be overridden individually.

Since the HV devices have no internal clock and no buffering, 
time-sensitive operations (e.g., updating voltages across a sequence) 
are implemented using `time.sleep(t)` in a background thread.

While this is a naive and dirty approach, it currently works to avoid 
blocking the main thread. However, we acknowledge that this is not ideal,
and we welcome proposals for a cleaner, event-driven timing model.

---
## GUI 

A "Send to Device" button that:
- Collects all values from the front panel
- Queues them to the worker
- Sends commands sequentially over serial

A "Check Remote Values" button that:
- Queries the device
- Displays the currently applied voltages

A "Temperature" button that:
- Displays the current temperature value
- Emits a warning if the device reports an overheat condition
- The warning threshold is defined by 55C

A "Check lock status" button that:
- Displays the status of each channel
- Clearly indicates which channels are locked (overloaded) and which are operational

---
## Emulator

This [emulator](testing/emulateSerPort.py) simulates the behavior of the device. 
When started, the emulator opens 
a virtual serial port that behaves like a real device. Programs can 
connect to this port and communicate with it as if it were the real device.

To launch the emulator:

```bash 
python3 -m HV_stahl_old.testing.emulateSerPort  
```

You’ll see output like: use: `/dev/pts/5`

Use that port when connecting in `connection_table.py`.

---
## Current implementation

Voltage range:
- Device-wide range (ao_range) in `Stahl_HV`
- Optional per-channel override in `AnalogOutStahl`

Serial communication only
No automatic port discovery by given pid and vid.

---
## Connection table

```python
from user_devices.HV_stahl.labscript_devices import Stahl_HV, AnalogOutStahl
from labscript_devices.DummyPseudoclock.labscript_devices import DummyPseudoclock

DummyPseudoclock('pseudoclock')
clockline = pseudoclock.clockline

Stahl_HV(name="testing_HV_200", parent_device=clockline, ao_range=200, num_ao=8, port='/dev/pts/1')
AnalogOutStahl(name='ch_1_200', parent_device=testing_HV_200, connection="ch 0", ao_range=180)
AnalogOutStahl(name='ch_4_200', parent_device=testing_HV_200, connection="ch 4", ao_range=50)
AnalogOutStahl(name='ch_5_200', parent_device=testing_HV_200, connection="ch 5") 
AnalogOutStahl(name='ch_8_200', parent_device=testing_HV_200, connection="ch 7", ao_range=200)

Stahl_HV(name="HV_250_testing", parent_device=clockline, port='/dev/pts/3', ao_range=250, num_ao=8)
AnalogOutStahl(name='ch_1_250', parent_device=HV_250_testing, connection="ch 0", ao_range=180)
AnalogOutStahl(name='ch_4_250', parent_device=HV_250_testing, connection="ch 4", ao_range=50)
AnalogOutStahl(name='ch_5_250', parent_device=HV_250_testing, connection="ch 5")
AnalogOutStahl(name='ch_8_250', parent_device=HV_250_testing, connection="ch 7", ao_range=200)

```

