import serial
import time

PORT = "/dev/ttyACM0"
BAUDRATE = 9600
TIMEOUT = 1


def main():
    try:
        print(f"Step 1: Opening serial port {PORT}...")
        ser = serial.Serial(PORT, baudrate=BAUDRATE, timeout=TIMEOUT)

        if not ser.is_open:
            ser.open()
        print("Serial port opened.")

        ser.reset_input_buffer()
        ser.reset_output_buffer()

        print("Step 2: Sending command...")
        command = "$CMD:INFO,PAR:BDNAME\r\n"
        ser.write(command.encode('ascii'))
        ser.flush()
        print(f"Command sent: {command.strip()}")

        print("Step 3: Reading response...")
        time.sleep(0.1)
        response = ser.readline().decode('ascii', errors='ignore').strip()

        if response:
            print(f"Response: {response}")
        else:
            print("No response received or timeout.")

    except serial.SerialException as e:
        print(f"Serial port error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            print("Closing serial port...")
            ser.close()
            print("Serial port closed.")


if __name__ == "__main__":
    main()
