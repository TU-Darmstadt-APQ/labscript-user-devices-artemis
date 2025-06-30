from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils import UiLoader
from user_devices.logger_config import logger
from qtutils.qt.QtWidgets import QRadioButton, QSizePolicy, QVBoxLayout, QButtonGroup, QHBoxLayout, QSpacerItem, QLabel, QPushButton, QSizePolicy as QSP
from qtutils.qt.QtCore import Qt
from blacs.tab_base_classes import MODE_MANUAL


class UMTab(DeviceTab):
    """to define device capabilities and generate the GUI for manual control of the device through the front panel"""
    def initialise_GUI(self):

        # Define capabilities 
        self.base_unit = 'V'
        self.base_min = -28
        self.base_max = 0
        self.base_step = 1
        self.base_decimals_ultra = 7
        self.base_decimals_add_on = 4
        self.num_add_ons = 10

        ultra_precision_channels = {
            "CH A'": {
                'base_unit': self.base_unit,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals_ultra,
            },
            "CH B'": {
                'base_unit': self.base_unit,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals_ultra,
            },
            "CH C'": {
                'base_unit': self.base_unit,
                'min': self.base_min,
                'max': self.base_max,
                'step': self.base_step,
                'decimals': self.base_decimals_ultra,
            },
        }
        add_on_channels = {}
        for i in range(1, self.num_add_ons + 1):
            add_on_channels['CH %d' % i] = {
                'base_unit': self.base_unit,
                'min': self.base_min,
                'max': self.base_max,
                'step':self.base_step,
                'decimals': self.base_decimals_add_on,
                }
        
        # Create the output objects
        # It will have automatically looked up relevant entries in the BLACS connection table to get their name and unit conversion.
        self.create_analog_outputs(ultra_precision_channels)
        self.create_analog_outputs(add_on_channels)
        
        # Create widgets for output objects
        ultra_widgets = self.create_analog_widgets(ultra_precision_channels)
        add_on_widgets = self.create_analog_widgets(add_on_channels)
        self.auto_place_widgets(("ultra high precision channels", ultra_widgets))
        self.auto_place_widgets(("add on channels", add_on_widgets))

        # Create radio button for modes
        self.create_mode_button(self.mode_changed)
        self.create_send_button(self.send_to_device)
        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False) # see at 3.3.19, 5.3 (docs) 

    def initialise_workers(self):
        """ Tells the device Tab to launch one or more worker processes to communicate with the device."""
        # Get properties from connection table.
        device = self.settings['connection_table'].find_by_name(self.device_name)
        
        # look up the port and baud in the connection table
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        
        # Start a worker process 
        self.create_worker(
            'main_worker',
            'user_devices.UM.BLACS_workers.UMWorker',
            {"port": port, "baud_rate": baud_rate} # All connection table properties should be added 
            )
        self.primary_worker = "main_worker"

    def create_mode_button(self, on_click_callback):
        self.fast_button = QRadioButton("FAST")
        self.ultra_button = QRadioButton("ULTRA")

        # Group them to make them exclusive
        self.button_group = QButtonGroup()
        self.button_group.addButton(self.fast_button)
        self.button_group.addButton(self.ultra_button)

        # Create a label to show current mode
        self.label = QLabel("Select a mode")

        self.button_group.setExclusive(True)

        # Connect signal to function
        self.button_group.buttonClicked.connect(on_click_callback)

        # Vertical layout for buttons and label (stacked vertically)
        vbox = QVBoxLayout()
        vbox.addWidget(self.label, alignment=Qt.AlignHCenter)
        vbox.addWidget(self.fast_button, alignment=Qt.AlignHCenter)
        vbox.addWidget(self.ultra_button, alignment=Qt.AlignHCenter)

        # Horizontal layout to center the vertical layout
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addLayout(vbox)
        hbox.addStretch()

        # Add the centered layout to the main device tab layout
        self.get_tab_layout().addLayout(hbox)

    def create_send_button(self, on_click_callback):
        """Creates a styled QPushButton with consistent appearance and connects it to the given callback."""
        text = 'Send to Device'
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

        # Add centered layout to center the button
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(button)
        center_layout.addStretch()
        self.get_tab_layout().addLayout(center_layout)

    @define_state(MODE_MANUAL, True)
    def mode_changed(self, button):
        selected_mode = button.text()
        try:
            yield (self.queue_work(self.primary_worker, 'change_mode', [selected_mode,]))
            self.label.setText(f"Selected mode: {selected_mode}")
        except Exception as e:
            logger.debug(f"[UM] Error by send work to worker(change_mode): \t {e}")

    @define_state(MODE_MANUAL, True)
    def send_to_device(self):
        try:
            yield (self.queue_work(self.primary_worker, 'reprogram_UM', []))
        except Exception as e:
            logger.debug(f"[UM] Error by send work to worker(reprogram_UM): \t {e}")