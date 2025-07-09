import usb.core
import usb.util

self.dev = usb.core.find(idVendor=0x21e1, idProduct=0x0014)

if self.dev is None:
    raise ValueError(f"[CAEN] CAEN USB device not found (VID=, PID=.")
# if self.dev.is_kernel_driver_active(0):
#     self.dev.detach_kernel_driver(0)

self.dev.set_configuration()
logger.debug(f"ffffffffffffffffffffff")
cfg = self.dev.get_active_configuration()

logger.debug(f"cfg = {cfg}")
intf = cfg[(0, 0)]
logger.debug(f"intf = {intf}")
self.ep_out = usb.util.find_descriptor(
    intf,
    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
)
self.ep_in = usb.util.find_descriptor(
    intf,
    custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
)

if self.ep_out is None or self.ep_in is None:
    raise ValueError("Could not find USB IN/OUT endpoints.")