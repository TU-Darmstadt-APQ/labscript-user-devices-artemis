from CAEN_R8034.caen_protocol import CAENDevice
import time
from timeit import default_timer as timer
from datetime import timedelta
"""
python3 -m CAEN_R8034.testing.protocol_test
"""

STATUS_BITS = {
    0: "Channel is on",
    1: "Channel is ramping up",
    2: "Channel is ramping down",
    3: "Channel is in overcurrent",
    4: "Channel is in overvoltage",
    5: "Channel is in undervoltage",
    6: "TRIP: Ch OFF via TRIP (Imon >= Iset during TRIP)",
    7: "Channel is in max V",
    8: "Temperature Warning",
    9: "Temperature over 65°C",
    10: "Channel is in kill",
    11: "Channel is in interlock",
    12: "Channel is disabled",
    13: "Channel is failed",
    14: "Channel control switch on ON/EN",
    15: "Channel is in overvoltage HVMAX set via trimmer",
}

RAMP_UP = 500
RAMP_DOWN = 500
DELTA = 1

VOLTAGES = {
    4: 100.0,
    5: 100.0,
}

def decode_status(ch: int, st: int) -> str:
    status = f"Channel {ch}: "
    if st & 1:
        status += "ON"
    else:
        status += "OFF"

    for bit, meaning in STATUS_BITS.items():
        if bit == 0:
            continue
        if st & (1 << bit):
            status += f"\n    {meaning}"

    return status


# =====================================================================
# ACTIONS
# =====================================================================

def action_set_and_measure(caen: CAENDevice):
    """Set voltages and measure the settling time."""
    print("\n=== Setting voltages and measuring time ===")
    for ch in VOLTAGES.keys():
        caen.enable_channel(ch, True)

    settled = set()

    start = timer()

    for ch, vol in VOLTAGES.items():
        print(f"Setting CH{ch} -> {vol} V")
        caen.set_voltage(ch, vol)

    while len(settled) < len(VOLTAGES):
        for ch, target in VOLTAGES.items():
            mon = caen.monitor_voltage(ch)
            print(mon)
            if ch not in settled and abs(mon - target) < DELTA:
                settled.add(ch)
        time.sleep(0.5)

    end = timer()
    print(f"\nDONE. Settling time: {timedelta(seconds=end-start)}\n")


def action_set_negative(caen: CAENDevice):
    print("\n=== Applying voltages and showing status ===")
    for ch in VOLTAGES.keys():
        caen.enable_channel(ch, True)

    print("\n--- BEFORE ---")
    for ch in VOLTAGES.keys():
        print(decode_status(ch, int(caen.get_status(ch))))

    for ch, vol in VOLTAGES.items():
        caen.set_voltage(ch, vol)

    print("\n--- AFTER ---")
    for ch in VOLTAGES.keys():
        print(decode_status(ch, int(caen.get_status(ch))))

    print("\nMonitor voltages:")
    for ch, vol in VOLTAGES.items():
        print(f"CH{ch}: {caen.monitor_voltage(ch)} V (target {vol})")
    print()


def action_set_ramp(caen: CAENDevice):
    print("\n=== Setting ramp rates ===")
    ramp = float(input("set ramp rate").strip())
    for ch in VOLTAGES.keys():
        caen.set_ramp_up_rate(ch, ramp)
        caen.set_ramp_down_rate(ch, ramp)
        print(f"CH{ch}: UP={ramp}, DOWN={ramp}")
    print()


def action_status_all(caen: CAENDevice):
    print("\n=== Channel Status ===")
    for ch in range(8):
        st = int(caen.get_status(ch))
        print(decode_status(ch, st))
    print()


def action_monitor_all(caen: CAENDevice):
    print("\n=== Monitor Voltages ===")
    for ch in range(8):
        try:
            print(f"CH{ch}: {caen.monitor_voltage(ch)} V")
        except:
            print(f"CH{ch}: ERROR")
    print()


# =====================================================================
# MAIN LOOP
# =====================================================================

def main():
    print("Opening CAEN device...")
    caen = CAENDevice(baud_rate=9600, pid="0014", vid="21e1", serial_number="63825")
    print("Device opened.\n")

    print("Press:")
    print(" 1 – Set voltages & measure")
    print(" 2 – Set voltages & show status")
    print(" 3 – Set ramp rates")
    print(" s – Show status of all channels")
    print(" m – Monitor voltages")
    print(" q – Quit\n")

    try:
        while True:
            cmd = input("Command: ").strip()

            if cmd == "1":
                action_set_and_measure(caen)

            elif cmd == "2":
                action_set_negative(caen)

            elif cmd == "3":
                action_set_ramp(caen)

            elif cmd == "s":
                action_status_all(caen)

            elif cmd == "m":
                action_monitor_all(caen)

            elif cmd == "q":
                print("Exiting...")
                break

            else:
                print("Unknown command.\n")

    except KeyboardInterrupt:
        print("\nKeyboard interrupt -> Closing device.")

    finally:
        for ch in range(8):
            caen.set_voltage(ch, 0.0)
            caen.enable_channel(ch, False)
        caen.close()
        print("Device closed.")


if __name__ == "__main__":
    main()
