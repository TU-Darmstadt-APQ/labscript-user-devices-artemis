from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from qtutils import UiLoader
from user_devices.logger_config import logger
# from PyQt5.QtWidgets import QApplication, QWidget, QRadioButton, QVBoxLayout, QButtonGroup, QLabel
from qtutils.qt.QtWidgets import QRadioButton, QSizePolicy, QVBoxLayout, QButtonGroup, QHBoxLayout, QSpacerItem, QLabel
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
        # TODO: how it is connected to connection table, wat should be defined there?
        self.create_analog_outputs(ultra_precision_channels)
        self.create_analog_outputs(add_on_channels)
        
        # Create widgets for output objects
        _, ao_widgets, _ = self.auto_create_widgets()
        self.auto_place_widgets(("output channels", ao_widgets)) # todo: how to separate ultra high precision and add on

        # Create radio button for modes
        self.create_mode_button(self.mode_changed)
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

        # # Add centered layout to center the button
        # center_layout = QHBoxLayout()
        # center_layout.addStretch()
        # center_layout.addWidget(self.fast_button)
        # center_layout.addWidget(self.ultra_button)
        # center_layout.addWidget(self.label)
        # center_layout.addStretch()
        #
        # # Add center layout on device layout
        # self.get_tab_layout().addLayout(center_layout)

    @define_state(MODE_MANUAL, True)
    def mode_changed(self, button):
        selected_mode = button.text()
        try:
            yield (self.queue_work(self.primary_worker, 'change_mode', [selected_mode,]))
            self.label.setText(f"Selected mode: {selected_mode}")
        except Exception as e:
            logger.debug(f"[UM] Error by send work to worker(change_mode): \t {e}")
