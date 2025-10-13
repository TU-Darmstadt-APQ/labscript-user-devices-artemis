# PicoScope 4000A Series
## Installation

### 1. Install drivers
```bash
cd PicoScope4000A
./install.sh
```
### 2. Install PicoScope 7 Application
After successfully installing the drivers:
```commandline
sudo apt-get update
sudo apt-get install picoscope
```
### 3. Install picoSDK in your virtual environment
```bash
pip install picosdk
```

## General Usage
### Connecting the Picoscope
In the connection table script, define configurations for the PicoScope channels. 
It is recommended to disable unused channels explicitly.

```python
picoscope = PicoScope4000A(name='picoscope',
                   serial_number='HO248/173')
# 8 channels
# name, parent_device, connection, enabled=[0,1], coupling=['ac', 'dc'], analog_offset_v=[0.1..200], analog_offset_v=float
PicoAnalogIn(name='conn1', parent_device=picoscope, connection='channel_A', enabled=1, coupling='dc', range_v=10, analog_offset_v=0.0)
PicoAnalogIn(name='conn2', parent_device=picoscope, connection='channel_B', enabled=0, coupling='dc', range_v=10, analog_offset_v=0.0)
```
### Trigger and Streaming Mode
Set an edge trigger and run streaming sampling mode. 

Note: 
- Only streaming mode is currently supported. 
and set edge trigger and run streaming sampling mode. 
- If no trigger is set, data collection starts immediately.
- HDF5 shot file will contain up to the working buffer size (default 1000) of pre-trigger samples.

```python
picoscope.set_stream_sampling(sampleInterval_ns=250, noPostTriggerSamples=10000)
picoscope.run_mode('stream')
    
picoscope.set_simple_trigger(source="channel_A", threshold_mV=2900, direction='rising', delay_samples=0, autoTrigger_ms=0)
```

### BLACS Integration
All device settings are displayed in the BLACS device tab, divided into:
- channel settings
- trigger settings
- sampling settings
- (optional) signal generator

These settings are for display only and **should not be changed manually** in the tab.

---
Dictionary also include some modified toy examples from [PicoSDK](https://github.com/picotech/picosdk-python-wrappers/blob/master/ps4000aExamples/ps4444BlockExample.py)

