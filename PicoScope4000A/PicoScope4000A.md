# PicoScope 4000(A) Series
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
- HDF5 shot file will contain up to the working buffer size (default 1000) of pre-trigger samples.
- In an HDF5 file, the traces are stored under `data/traces`. Each group contains a single dataset with a column for each channel, and the groups are named by picoscope.

```python
picoscope_173.set_stream_sampling(sampling_rate=4e6, no_post_trigger_samples=10000)
picoscope_173.set_simple_trigger(source="channel_A", threshold=2.9, direction='falling', delay_samples=0, auto_trigger_s=0)
picoscope_173.signal_generator_config(offset_voltage=0, pk2pk=2, wave_type='square')
```

Make sure that the stream, trigger, and signal generator settings in your experiment script match those defined in the connection table. 
### BLACS Integration
All device settings are displayed in the BLACS device tab under `Attributes`, divided into:
- channel settings
- trigger settings
- sampling settings
- (optional) signal generator

The plot will be displayed in the BLACS tab after the shot has run.

### Lyse
```python
with run.open('r+') as shot:
    picoscopes = shot.trace_names() # gets the group=picoscope names
    for picoscope in picoscopes:
        traces_ds = shot.h5_file['data']['traces'][picoscope] # get the dataset with traces
        traces_names = traces_ds.attrs["channel_names"] # get the chanel names
        # the t-values are not stored in the dataset, but they can be computed as follows:
        dt = traces_ds.attrs["sample_interval"] 
        triggered_at = traces_ds.attrs["triggered_at"]
        data = traces_ds[()]
        N, C = data.shape
        t = np.linspace(0, (N-1) * dt, N)
        traces = {name: data[:, i] for i, name in enumerate(traces_names)}

        ### todo: visualization/analysis
```
---
Dictionary also include some modified toy examples from [PicoSDK](https://github.com/picotech/picosdk-python-wrappers/blob/master/ps4000aExamples/ps4444BlockExample.py)

