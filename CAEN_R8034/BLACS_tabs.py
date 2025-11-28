from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL

class CAENTab(DeviceTab):
    def initialise_GUI(self):
        # Analog output properties dictionary
        self.base_unit = 'V'
        self.base_min = 0
        self.base_max = 6000
        self.base_step = 10
        self.base_decimals = 4

        device = self.settings['connection_table'].find_by_name(self.device_name)
        bipol = device.properties['bipol']
        analog_properties = {}

        for i in range(8):
            if bipol and i >= 4:
                ch_min, ch_max = -self.base_max, self.base_max
            else:
                ch_min, ch_max = self.base_min, self.base_max

            analog_properties['CH %d' % i] = {
                'base_unit': self.base_unit,
                'min': ch_min,
                'max': ch_max,
                'step':self.base_step,
                'decimals': self.base_decimals,
                }

        # Create and save AO objects
        self.create_analog_outputs(analog_properties)
        # Create widgets for AO objects
        dds_widgets, ao_widgets, do_widgets = self.auto_create_widgets()
        self.auto_place_widgets(("Analog outputs", ao_widgets))

        self.send_button = self._create_button("Send to device", self.reprogram_CAEN)
        self.monitor_button = self._create_button("Monitor", self.monitor_CAEN)
        self.status_button = self._create_button("Status", self.check_status)
        # Add centered layout to center the button
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(self.send_button)
        center_layout.addWidget(self.monitor_button)
        center_layout.addWidget(self.status_button)
        center_layout.addStretch()
        self.get_tab_layout().addLayout(center_layout)

        self.supports_smart_programming(False)        
        self.supports_remote_value_check(False)
    
    def initialise_workers(self):
        # Get properties from connection table
        device = self.settings['connection_table'].find_by_name(self.device_name)
        if device is None:
            raise ValueError(f"Device '{self.device_name}' not found in the connection table.")
        
        # Look up at the connection table for device properties
        vid =  device.properties["vid"]
        pid = device.properties["pid"]
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        serial_number = device.properties["serial_number"]
        
        worker_kwargs = {
            "name": self.device_name + '_main',
            "port": port,
            "vid": vid,
            "pid": pid,
            "baud_rate": baud_rate,
            "serial_number": serial_number
        }
        
        self.create_worker(
            'main_worker',
            'user_devices.CAEN_R8034.BLACS_workers.CAENWorker',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"
        
    @define_state(MODE_MANUAL, True)
    def reprogram_CAEN(self):
        """Queue a manual send-to-device operation from the GUI."""
        try:
            yield (self.queue_work(self.primary_worker, 'reprogram_CAEN', []))
        except Exception as e:
            logger.debug(f"[CAEN] Error by send work to worker(reprogram_CAEN): \t {e}")

    @define_state(MODE_MANUAL, True)
    def monitor_CAEN(self):
        """Queue a manual send-to-device operation from the GUI."""
        try:
            yield (self.queue_work(self.primary_worker, 'monitor_CAEN', []))
        except Exception as e:
            logger.debug(f"[CAEN] Error by send work to worker(monitor_CAEN): \t {e}")

    @define_state(MODE_MANUAL, True)
    def check_status(self):
        try:
            yield (self.queue_work(self.primary_worker, 'check_status', []))
        except Exception as e:
            logger.debug(f"[CAEN] Error by send work to worker(check_status): \t {e}")

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
        logger.debug(f"[CAEN] Button {text} is created")
        return button