import serial
import time
import logging
from user_devices.logger_config import logger  # Assuming logger is properly configured

# -------------------- Device Communication Functions --------------------

def identify_device():
    connection.write(('*IDN?\r\n').encode())
    connection.flush()
    time.sleep(0.1)

    raw = connection.readline().decode(errors='ignore').strip()
    next_line = connection.readline().decode(errors='ignore').strip()
    logger.info(f"Identify RAW: {raw}")
    logger.info(f"Identify NEXT: {next_line}")
    return next_line


def reset_device():
    send_command('*RST')
    logger.info("Reset to default.")


def set_baud_rate(baud_rate):
    send_command(f':SYST:SER:BAUD {baud_rate}')


def send_command(cmd: str):
    connection.reset_input_buffer()
    connection.write((cmd + '\r\n').encode())
    connection.flush()
    time.sleep(0.1)
    logger.info(f"[BNC] Sent: {cmd}")

    response = receive_from_BNC()
    return response


def receive_from_BNC():
    try:
        echo = connection.readline().decode(errors='ignore').strip()
        response = connection.readline().decode(errors='ignore').strip()
        logger.info(f"\t[BNC] Echo: {echo}")
        logger.info(f"\t[BNC] Response: {response}")
        return response
    except Exception as e:
        logger.error(f"Serial read failed: {e}")
        return None


def set_width(channel, width):
    response = send_command(f':PULSE{channel}:WIDTH {width}')
    logger.info(f"Set width on channel {channel} to {width} | Device response: {response}")


# -------------------- Main Script --------------------

if __name__ == "__main__":
    port = '/dev/ttyUSB0'
    baud_rate = 38400

    try:
        connection = serial.Serial(port, baud_rate, timeout=2)
        time.sleep(0.5)
        logger.info("=" * 60)
        logger.info(f"[BNC] Serial connection opened on {port} at {baud_rate} bps")
        logger.info("=" * 60)

        for i in range(10):
            logger.info(f"\n------ Iteration {i + 1} ------")
            identity = identify_device()
            logger.info(f"Connected to: {identity}")
            set_width(1, 2)
            logger.info("-" * 50)

        connection.close()
        logger.info("[BNC] Connection closed.")

    except serial.SerialException as e:
        logger.error(f"Serial connection error: {e}")
