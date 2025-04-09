from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *

from qtutils import *
from PyQt5 import QtWidgets 
from labscript_utils.qtwidgets.outputbox import OutputBox
import qtutils.icons

from user_devices.logger_config import logger


class HV_250Tab(DeviceTab):
    def initialise_GUI(self):
        # Analog output properties dictionary
        self.base_unit = 'V'
        self.base_min = -250 # TODO: What is the range?
        self.base_max = 250
        self.base_step = 10
        self.base_decimals = 3
        self.num_AO = 8 # Assuming 8 channels
        
        # DEBUG
        print("HOW IS IT") # soes not show up
        logger.info("INITIALIZE GUI FROM TAB") # not working, Why?

        analog_properties = {}
        for i in range(self.num_AO):
            analog_properties['CH%02d' % i] = {
                'base_unit': self.base_unit,
                'min': self.base_min,
                'max': self.base_max,
                'step':self.base_step,
                'decimals': self.base_decimals,
                }
        # Create and save AO objects
        self.create_analog_outputs(analog_properties)

        # Create widgets for AO objects
        _, ao_widgets,_ = self.auto_create_widgets()
        self.auto_place_widgets(("Analog outputs", ao_widgets))
        self.supports_smart_programming(False)        
        self.supports_remote_value_check(False)

        ### Create indicator UI elements. But i don't see any new widgets in BLACS
        self.status_indicators = {}  # Dictionary to store indicators for each channel
        self.check_buttons = {}

        status_widgets = []
        for i in range(self.num_AO):
            channel_name = f"CH{i:02d}"
            
            # Create QLabel for the indicator
            indicator = QtWidgets.QLabel()
            indicator.setFixedSize(20, 20)
            indicator.setStyleSheet("background-color: green; border-radius: 10px;")
            
            # Store the indicator in the status_indicators dictionary
            self.status_indicators[channel_name] = indicator

            # Create Check button
            check_button = QtWidgets.QPushButton("Check")
            check_button.setFixedWidth(60)
            check_button.clicked.connect(lambda _, ch=channel_name: self.check_overload_status(ch))
            self.check_buttons[channel_name] = check_button

            # Create layout for the status display
            layout = QtWidgets.QHBoxLayout()
            layout.addWidget(QtWidgets.QLabel(channel_name))
            layout.addWidget(indicator)
            layout.addWidget(check_button)
            
            # Create a QWidget to hold the layout
            widget = QtWidgets.QWidget()
            widget.setLayout(layout)

            # Add the widget to the list
            status_widgets.append(widget)

        # Place the status widgets in the GUI
        self.auto_place_widgets(("Overload Status", status_widgets))

    
    def initialise_workers(self):
        # Get properties from connection table
        device = self.settings['connection_table'].find_by_name(self.device_name)
        if device is None:
            raise ValueError(f"Device '{self.device_name}' not found in the connection table.")
        
        # Look up a the connection table for device properties
        port = device.properties["port"]
        baud_rate = device.properties["baud_rate"]
        worker_kwargs = {
            "name": self.device_name + '_main',
            "port": port,
            "baud_rate": baud_rate,
            }
        
        self.create_worker(
            'main_worker',
            'user_devices.HV_250.BLACS_workers.HV_250Worker',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"
        
