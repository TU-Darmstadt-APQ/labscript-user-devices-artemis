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

---
# USB connection
if errno 13: access denied --> add udev rule for this device.

```bash
in /etc/udev/rules.d
nano 99-caen-device.rules
```

You can change the PID, VID values according to your device. Then save the changes and reload the rules:
`sudo udevadm control --reload` and `sudo udevadm trigger`.

After all, unplug and plug the device.
