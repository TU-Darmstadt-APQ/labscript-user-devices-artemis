import usb.core
import usb.util
import time

VID = 0x21e1
PID = 0x0014

def main():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    print(VID, PID)
    if dev is None:
        print(f"ERROR: Device not found (VID={hex(VID)}, PID={hex(PID)})")
        return

    if dev.is_kernel_driver_active(0):
        print(f"Detaching kernel driver from interface {0}")
        dev.detach_kernel_driver(0)

    try:
        print("Step 1: Setting configuration...")
        dev.set_configuration()
    except usb.core.USBError as e:
        print("ERROR: Could not set configuration.")
        print(e)
        return

    print("Step 2: Getting active configuration...")
    cfg = dev.get_active_configuration()

    ep_out = None
    ep_in = None
    selected_intf = None

    print("Step 3: Searching for Bulk IN and Bulk OUT endpoints in all interfaces...")

    for interface in cfg:
        for alt_setting in range(interface.bNumEndpoints):
            intf = usb.util.find_descriptor(cfg, bInterfaceNumber=interface.bInterfaceNumber, bAlternateSetting=alt_setting)
            if intf is None:
                continue

            ep_out_candidate = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: (usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT and
                                        usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
            )
            ep_in_candidate = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: (usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN and
                                        usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
            )

            if ep_in_candidate and ep_out_candidate:
                ep_in = ep_in_candidate
                ep_out = ep_out_candidate
                selected_intf = intf
                print(f"Selected interface {interface.bInterfaceNumber} alt {alt_setting}")
                break
        if ep_in and ep_out:
            break

    if ep_in is None or ep_out is None:
        print("ERROR: Could not find Bulk IN/OUT endpoints.")
        return

    print(f"Endpoint OUT: {ep_out.bEndpointAddress:#04x}")
    print(f"Endpoint IN: {ep_in.bEndpointAddress:#04x}")

    # command = "$CMD:INFO,PAR:BDNAME\r\n"
    # command = "$CMD:INFO,PAR:BDNAME\r\n"
    # command = "$CMD:INFO,PAR:ID\r\n"
    # command = "$CMD:INFO,PAR:BDSTATUS\r\n"
    command = "$CMD:MON,PAR:BDCTR\r\n"
    # command = "$CMD:MON,PAR:PARLIST\r\n"

    data = command.encode()
    try:
        ep_out.write(data)
        print(f"Step 4: Sending command... {command!r}")
        time.sleep(0.1)
    except usb.core.USBError as e:
        print("Error sending data:", e)
        return

    try:
        response = ep_in.read(ep_in.wMaxPacketSize, timeout=1000)
        response_str = bytes(response).decode('ascii', errors='ignore')
        print(f"Step 5: Reading response... {response_str!r}")
    except usb.core.USBError as e:
        print("Error reading response:", e)

    print("Cleaning up USB resources...")
    usb.util.dispose_resources(dev)
    print("Done.")


if __name__ == "__main__":
    main()
