import ctypes
import threading

import numpy as np
from picosdk.ps4000a import ps4000a as ps
import matplotlib.pyplot as plt
from picosdk.functions import adc2mV, assert_pico_ok, mV2adc
import time

chandle = ctypes.c_int16()
status = {}
serial_number = 'H0248/178'
serial_number = serial_number.encode()
status["openunit"] = ps.ps4000aOpenUnit(ctypes.byref(chandle), serial_number)

enabled = 1
disabled = 0
analogue_offset = 0.0
channel_range = 9

maxADC = ctypes.c_int16()
status["maximumValue"] = ps.ps4000aMaximumValue(chandle, ctypes.byref(maxADC))
assert_pico_ok(status["maximumValue"])

buffers = {}
complete_buffers = {}
# Size of capture
sizeOfOneBuffer = 500
numBuffersToCapture = 20
totalSamples = sizeOfOneBuffer * numBuffersToCapture
totalSamples_stream = totalSamples
memory_segment = 0

threshold_mv = 1200

for ch in range(8):
    status[f"setCh{ch}"] = ps.ps4000aSetChannel(chandle,
                                        ch,
                                        enabled,
                                        1,
                                        channel_range,
                                        analogue_offset)

    assert_pico_ok(status[f"setCh{ch}"])
    buffers[ch] = np.zeros(shape=sizeOfOneBuffer, dtype=np.int16)
    complete_buffers[ch] = np.zeros(shape=totalSamples, dtype=np.int16)

    status[f"setDataBuffers{ch}"] = ps.ps4000aSetDataBuffers(chandle,
                                                         ch,
                                                         buffers[ch].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                                                         None,
                                                         sizeOfOneBuffer,
                                                         memory_segment,
                                                         ps.PS4000A_RATIO_MODE['PS4000A_RATIO_MODE_NONE'])
    assert_pico_ok(status[f"setDataBuffers{ch}"])

threshold = mV2adc(threshold_mv, channel_range, maxADC)
status["SimpleTrigger"] = ps.ps4000aSetSimpleTrigger(chandle,
                                                     1,
                                                     0, # ps.PS4000A_CHANNEL['PS4000A_CHANNEL_A'],
                                                     threshold,
                                                     ps.PS4000A_THRESHOLD_DIRECTION['PS4000A_FALLING'],
                                                     0,
                                                     0)
assert_pico_ok(status["SimpleTrigger"])

# Begin streaming mode:
sampleInterval = ctypes.c_int32(250)
sampleUnits = ps.PS4000A_TIME_UNITS['PS4000A_US']
maxPreTriggerSamples = 0
autoStopOn = 0
# No downsampling:
downsampleRatio = 1
status["runStreaming"] = ps.ps4000aRunStreaming(chandle,
                                                ctypes.byref(sampleInterval),
                                                sampleUnits,
                                                maxPreTriggerSamples,
                                                totalSamples_stream,
                                                autoStopOn,
                                                downsampleRatio,
                                                ps.PS4000A_RATIO_MODE['PS4000A_RATIO_MODE_NONE'],
                                                sizeOfOneBuffer)
assert_pico_ok(status["runStreaming"])

actualSampleInterval = sampleInterval.value
actualSampleIntervalNs = actualSampleInterval * 1000

nextSample = 0
autoStopOuter = False
wasCalledBack = False

was_triggered = 0
def streaming_callback(handle, noOfSamples, startIndex, overflow, triggerAt, triggered, autoStop, param):
    global nextSample, autoStopOuter, wasCalledBack, was_triggered
    wasCalledBack = True
    if triggered != 0:
        print(f"trigger occurred: {triggered} ->  TriggeredAT : {triggerAt}")
        was_triggered = 1
    if was_triggered == 1:
        destEnd = nextSample + noOfSamples
        sourceEnd = startIndex + noOfSamples
        print(f"complete = {destEnd-nextSample}, working = {sourceEnd-startIndex}")
        for ch in range(8):
            complete_buffers[ch][nextSample:destEnd] = buffers[ch][startIndex:sourceEnd]
            complete_buffers[ch][nextSample:destEnd] = buffers[ch][startIndex:sourceEnd]
        nextSample += noOfSamples
        if autoStop:
            autoStopOuter = True

# Convert the python function into a C function pointer.
cFuncPtr = ps.StreamingReadyType(streaming_callback)

fetching_thread = threading.Thread(target=fetching)
fetching_thread.start()

def fetching():
    # Fetch data from the driver in a loop, copying it out of the registered buffers and into our complete one.
    while nextSample < totalSamples and not autoStopOuter:
        wasCalledBack = False
        status["getStreamingLastestValues"] = ps.ps4000aGetStreamingLatestValues(chandle, cFuncPtr, None)
        if not wasCalledBack:
            # If we weren't called back by the driver, this means no data is ready. Sleep for a short while before trying
            # again.
            time.sleep(0.01)

    print(f"Stop grabbing")


# Convert ADC counts data to mV
mv_buffers = {}
for ch in range(8):
    mv_buffers[ch] =  adc2mV(buffers[ch].astype(np.int32) , channel_range, maxADC)

# Create time data
time = np.linspace(0, (totalSamples - 1) * actualSampleIntervalNs, totalSamples)

# Plot data from channel A and B
for ch in range(8):
    plt.plot(time, mv_buffers[ch][:])
# plt.plot(time, adc2mVChBMax[:])
plt.xlabel('Time (ns)')
plt.ylabel('Voltage (mV)')
plt.show()


# Stop the scope
# handle = chandle
status["stop"] = ps.ps4000aStop(chandle)
assert_pico_ok(status["stop"])

# Disconnect the scope
# handle = chandle
status["close"] = ps.ps4000aCloseUnit(chandle)
assert_pico_ok(status["close"])

# Display status returns
print(status)
