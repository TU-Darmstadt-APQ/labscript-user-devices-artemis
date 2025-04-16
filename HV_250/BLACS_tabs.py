from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *

from qtutils import *
from PyQt5 import QtWidgets 
from labscript_utils.qtwidgets.outputbox import OutputBox
import qtutils.icons
from qtutils.qt.QtWidgets import QVBoxLayout, QGroupBox

from labscript_utils.qtwidgets.toolpalette import ToolPaletteGroup

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
        logger.info("INITIALIZE GUI FROM TAB") 

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


    def _create_overload_object(self,parent_device,BLACS_hardware_name,labscript_hardware_name,properties):
        """ """
        # Find the connection name
        device = self.get_child_from_connection_table(parent_device,labscript_hardware_name)
        connection_name = device.name if device else '-'
        
        # Get the calibration details
        calib_class = None
        calib_params = {}
        if device:
            # get the AO from the connection table, find its calibration details
            calib_class = device.unit_conversion_class if device.unit_conversion_class != "None" else None
            calib_params = device.unit_conversion_params
        
        # Instantiate the AO object
        return AO(BLACS_hardware_name, connection_name, self.device_name, self.program_device, self.settings, calib_class, calib_params,
                properties['base_unit'], properties['min'], properties['max'], properties['step'], properties['decimals'])


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
        
class CircularIndicator(QLabel):
    """ Draw a circular indicator. """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)  # Size of the circular indicator
        self.setAlignment(Qt.AlignTop)
        self.status_color = QColor("green")  # Initial color (green for normal)
        self.setStyleSheet("background-color: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw the circle
        rect = QRect(0, 0, self.width(), self.height())
        painter.setBrush(QBrush(self.status_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        
    def set_status(self, status):
        """Set the color of the circular indicator."""
        if status == "overload":
            self.status_color = QColor("red")
        else:
            self.status_color = QColor("green")
        self.update()  # Trigger a repaint to reflect the new color
