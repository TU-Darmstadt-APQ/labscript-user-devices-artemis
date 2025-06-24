# CAEN R8034
Power supply for sickler lens
USB/Ethernet
8 or 16 independent 6kV / 1mA channels 

---
## Communication protocol 
 Set voltage command:
    command = "$CMD:SET,CH:X,PAR:VSET,VAL:YYYY.YYYY\r\n"
 Response:
    response = "#CMD:OK\r\n"
    response = "#VAL:ERR\r\n"
    response = "#CH:ERR\r\n"
    response = "#PAR:ERR\r\n"

---
The unit is automatically recognised by Linux; 
unit name is assigned to serial port with name /dev/ttyACM[x], 
where x is the device number. 

