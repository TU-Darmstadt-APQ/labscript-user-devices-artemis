import serial
import serial.tools.list_ports

def list_ftdi_devices():
    print("Seraching for devices...")
    ports = serial.tools.list_ports.comports()
    ftdi_ports = []

    for port in ports:
        if "FTDI" in port.manufacturer or "FTDI" in port.description:
            print(f"Found: {port.device}")
            print(f"   ├─ Description: {port.description}")
            print(f"   ├─ Manufacturer: {port.manufacturer}")
            print(f"   ├─ Serial number: {port.serial_number}")
            print(f"   └─ VID:PID = {port.vid}:{port.pid}")
            ftdi_ports.append(port.device)
    
    if not ftdi_ports:
        print("FTDI devices not found.")
    return ftdi_ports

if __name__ == "__main__":
    ftdi_ports = list_ftdi_devices()
