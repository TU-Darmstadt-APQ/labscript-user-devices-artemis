# BS 1-10 Cryo Biasing 
The bias supply for amplifiers. 
Biasing is for delivery of an accurate and stable voltage for operation of transistors that require a stable supply to ensure minimal noise and optimal performance.
In order for a transistor to amplify a signal, it needs to be sepplied with bias voltage, which sets it to an operating point where it can amplify weak singnals. 

---
##Connection interface (USB)
USB drivers are required, can be found [here](https://ftdichip.com/drivers/)


---
## Remote Commands
IDN | Identify
DDDDD CHXX Y.YYYYY | Set voltage
DDDDD TEMP | Read Temperature
DDDDD LOCK | Check lock status of all channels
DDDDD DIS [message] | Send string to LCD-display