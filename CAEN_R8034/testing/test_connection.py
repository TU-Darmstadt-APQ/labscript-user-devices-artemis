import usb.core
import usb.util
import errno
import sys
import time

VID = 0x21e1
PID = 0x0014

"""
    1. lsusb
    2. Create a new .rules file in /etc/udev/rules.d/
sudo nano /etc/udev/rules.d/99-caen.rules
    3. Paste the following
SUBSYSTEM=="usb", ATTR{idVendor}=="21e1", ATTR{idProduct}=="0014", MODE="0666"
    4. Save file, reload udev
sudo udevadm control --reload-rules
sudo udevadm trigger
    5. Replug
    6. Verify repmission
ls -l /dev/bus/usb/*/*
    7. Run test (optionally restart udev: sudo service udev restart)
"""

def main():
    try:
        dev = usb.core.find(idVendor=VID, idProduct=PID)
        if dev is None:
            print(f"ERROR: Device not found (VID={hex(VID)}, PID={hex(PID)})")
            return

        print("Step 1: Setting configuration...")
        try:
            dev.set_configuration()
        except usb.core.USBError as e:
            print("ERROR: Could not set configuration.")
            print(e)
            if hasattr(e, 'errno'):
                print("Errno:", e.errno)
            return

        print("Step 2: Getting active configuration...")
        try:
            cfg = dev.get_active_configuration()
            intf = cfg[(0, 0)]
        except usb.core.USBError as e:
            print("ERROR: Could not get configuration/interface.")
            print(e)
            return

        print("Step 3: Looking for OUT endpoint...")
        ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        print("Step 4: Looking for IN endpoint...")
        ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
        )

        print(f"Endpoint OUT: {ep_out}")
        print(f"Endpoint IN: {ep_in}")

        if ep_out is None or ep_in is None:
            print("ERROR: Could not find IN/OUT endpoints.")
            return

        print("Success: USB device initialized.")

        print("STEP 5: Lets try to send command...")
        command = "$CMD:INFO,PAR:BDNAME\r\n"
        data = command.encode() #mb 'ascii'
        print(f"Sending command: {command.strip()}")
        ep_out.write(data)
        time.sleep(0.1)

        print("Reading response...")
        try:
            response = ep_in.read(64).decode()  # Reads up to 64 bytes
            print(f"Response: {response}")
        except usb.core.USBError as e:
            print("No response or read error:", e)

    except usb.core.USBError as e:
        print("USBError occurred.")
        print(e)
        if hasattr(e, 'errno'):
            print("Errno:", e.errno)
    except Exception as e:
        print("General Exception occurred.")
        print(e)
        if hasattr(e, 'errno'):
            print("Errno:", e.errno)

    finally:
        if 'dev' in locals():
            print("Cleaning up USB resources...")
            usb.util.dispose_resources(dev)
            print("Done.")


if __name__ == '__main__':
    main()