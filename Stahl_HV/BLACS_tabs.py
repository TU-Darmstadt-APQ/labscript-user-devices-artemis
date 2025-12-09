from logging.config import valid_ident

from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL
from labscript import LabscriptError
import time


class HV_Tab(DeviceTab):
    def initialise_GUI(self):
        # Analog output properties dictionary
        connection_table = self.settings['connection_table']
        properties = connection_table.find_by_name(self.device_name).properties

        self.num_ao = properties['num_ao']
        self.ao_range = properties['ao_range']
        self.port = properties['port']
        self.baud_rate = properties['baud_rate']
        self.pid = properties['pid']
        self.vid = properties['vid']
        self.serial_number = properties['serial_number']
        self.ao_ranges = self.get_channel_ranges()

        # logger.debug(f"[DEBUG] {self.device_name} Properties from connection table: {properties}")

        base_unit = 'V'
        base_step = 10
        base_decimals = 3

        analog_properties = {}
        for conn in range(self.num_ao):
            ao_range = self.ao_ranges[conn]
            base_min, base_max = -ao_range, ao_range
            analog_properties["ch %d" %conn] = {
                'base_unit': base_unit,
                'min': base_min,
                'max': base_max,
                'step': base_step,
                'decimals': base_decimals,
            }

        self.create_analog_outputs(analog_properties)
        _, ao_widgets, _ = self.auto_create_widgets()
        self.auto_place_widgets(("Analog outputs", ao_widgets))

        # Create buttons to send-to-device and check-remote-values
        self.send_button = self._create_button('Send to device', self.reprogram)
        self.check_button = self._create_button('Check remote values', self.monitor_voltage)
        self.temp_button = self._create_button('Temperature', self.monitor_temperature)
        self.status_button = self._create_button('Check lock status', self.monitor_lock_status)

        # Add centered layout to center the button
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(self.send_button)
        center_layout.addWidget(self.check_button)
        center_layout.addWidget(self.temp_button)
        center_layout.addWidget(self.status_button)
        center_layout.addStretch()

        # Add center layout on device layout
        self.get_tab_layout().addLayout(center_layout)

        self.supports_smart_programming(False)
        self.supports_remote_value_check(False)

    def initialise_workers(self):

        # Look up at the connection table for device properties
        worker_kwargs = {"name": self.device_name + '_main',
                         "port": self.port,
                         "baud_rate": self.baud_rate,
                         "pid": self.pid,
                         "vid": self.vid,
                         "num_ao": self.num_ao,
                         "ao_ranges": self.ao_ranges,
                         "serial_number": self.serial_number,
                         }

        self.create_worker(
            'main_worker',
            'user_devices.HV_stahl_old.BLACS_workers.HV_Worker',
            worker_kwargs,
        )

        self.primary_worker = "main_worker"

    @define_state(MODE_MANUAL, True)
    def reprogram(self):
        """Queue a manual send-to-device operation from the GUI.

            This function is triggered from the BLACS tab (by pressing a button)
            and runs in the main thread. It queues the `send_to_HV()` function to be
            executed by the worker.

            Used to reprogram the device based on current front panel values.
            """
        try:
            yield self.queue_work(self.primary_worker, 'reprogram', [])
        except Exception as e:
            raise e

    @define_state(MODE_MANUAL, True)
    def monitor_voltage(self):
        yield self.queue_work(self.primary_worker, 'monitor_voltage', [])

    @define_state(MODE_MANUAL, True)
    def monitor_temperature(self):
        yield self.queue_work(self.primary_worker, 'monitor_temperature')

    @define_state(MODE_MANUAL, True)
    def monitor_lock_status(self):
        yield self.queue_work(self.primary_worker, 'check_lock_status')

    def _create_button(self, text, on_click_callback):
        """Creates a styled QPushButton with consistent appearance and connects it to the given callback."""
        button = QPushButton(text)
        button.setSizePolicy(QSP.Fixed, QSP.Fixed)
        button.adjustSize()
        button.setStyleSheet("""
                QPushButton {
                    border: 1px solid #B8B8B8;
                    border-radius: 3px;
                    background-color: #F0F0F0;
                    padding: 4px 10px;
                    font-weight: light;
                }
                QPushButton:hover {
                    background-color: #E0E0E0;
                }
                QPushButton:pressed {
                    background-color: #D0D0D0;
                }
            """)
        button.clicked.connect(lambda: on_click_callback())
        return button

    def get_channel_ranges(self):
        """Return channel-specific range or fallback to default."""
        ao_ranges = {}
        for i in range(self.num_ao):
            ch = self.get_child_from_connection_table(self.device_name, "ch %d" % i)
            if ch:
                ao_range = ch.properties.get("ao_range")
                if ao_range is None:
                    ao_range = self.ao_range
            else:
                ao_range = self.ao_range
            ao_ranges[i] = ao_range

        return ao_ranges
