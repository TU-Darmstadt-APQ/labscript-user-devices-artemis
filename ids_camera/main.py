from ids_peak import ids_peak

import threading
import camera

SERIAL_NUMBER = "4104380609"



def start(camera_device, ui):
    ui.start_window()
    thread = threading.Thread(target=camera_device.wait_for_signal, args=())
    thread.start()
    ui.acquisition_thread = thread
    ui.start_interface()


def main(interface):
    index = 0
    # Initialize library and device manager
    ids_peak.Library.Initialize()
    device_manager = ids_peak.DeviceManager.Instance()
    camera_device = None

    try:
        # Initialize camera device class
        camera_device = camera.Camera(device_manager, SERIAL_NUMBER, interface)
        start(camera_device, interface)

    except KeyboardInterrupt:
        print("User interrupt: Exiting...")
    except Exception as e:
        print(f"Exception (main): {str(e)}")

    finally:
        # Close camera and library after program ends
        if camera_device is not None:
            camera_device.close()
        ids_peak.Library.Close()


if __name__ == '__main__':
    from cli_interface import Interface
    main(Interface())