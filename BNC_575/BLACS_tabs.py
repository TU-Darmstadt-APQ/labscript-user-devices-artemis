from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
from blacs.tab_base_classes import MODE_MANUAL
from user_devices.BNC_575.ChannelWidget import ChannelWidget


class BNC_575Tab(DeviceTab):
    def initialise_GUI(self):
        layout = QVBoxLayout()
        self.get_tab_layout().addLayout(layout)

        # System config
        self.system_box = QGroupBox("System Configuration")
        sys_layout = QVBoxLayout()

        self.t0_mode = QComboBox();
        self.t0_mode.addItems(['NORMal', 'SINGle', 'BURSt', 'DCYCle'])
        self.t0_mode.currentTextChanged.connect(self.update_system_visibility)

        self.period = QDoubleSpinBox();
        self.period.setSuffix(" s")
        self.trigger = QCheckBox("Trigger Enabled")
        self.burst_count = QSpinBox()
        self.on_count = QSpinBox()
        self.off_count = QSpinBox()

        sys_layout.addWidget(QLabel("Mode:"));
        sys_layout.addWidget(self.t0_mode)
        sys_layout.addWidget(QLabel("Period:"));
        sys_layout.addWidget(self.period)
        sys_layout.addWidget(self.trigger)
        sys_layout.addWidget(QLabel("Burst Count:"));
        sys_layout.addWidget(self.burst_count)
        sys_layout.addWidget(QLabel("On Count:"));
        sys_layout.addWidget(self.on_count)
        sys_layout.addWidget(QLabel("Off Count:"));
        sys_layout.addWidget(self.off_count)
        self.system_box.setLayout(sys_layout)
        layout.addWidget(self.system_box)

        self.update_system_visibility()

        # Channel config
        self.channels_box = QGroupBox("Channels")
        ch_layout = QVBoxLayout()
        self.channel_widgets = []
        for i in range(8):
            ch = ChannelWidget(f"pulse {i}")
            ch_layout.addWidget(ch)
            self.channel_widgets.append(ch)
        self.channels_box.setLayout(ch_layout)
        layout.addWidget(self.channels_box)

        # Buttons
        self.btn_configure = QPushButton("Configure")
        self.btn_trigger = QPushButton("Trigger")
        self.btn_reset = QPushButton("Reset")

        layout.addWidget(self.btn_configure)
        layout.addWidget(self.btn_trigger)
        layout.addWidget(self.btn_reset)

        self.btn_configure.clicked.connect(self.configure_device)
        self.btn_trigger.clicked.connect(self.trigger_device)
        self.btn_reset.clicked.connect(self.reset_device)

        self.create_trigger_button(self.trigger_device)
        self.supports_remote_value_check(False)
        self.supports_smart_programming(False)

    def update_system_visibility(self):
        mode = self.t0_mode.currentText().lower()
        self.burst_count.setVisible(mode == 'burst')
        self.on_count.setVisible(mode == 'dcycle')
        self.off_count.setVisible(mode == 'dcycle')

    def configure_device(self):
        system_config = {
            'mode': self.t0_mode.currentText(),
            'period': self.period.value(),
            'trigger': self.trigger.isChecked(),
            'burst_count': self.burst_count.value() if self.burst_count.isVisible() else None,
            'on_count': self.on_count.value() if self.on_count.isVisible() else None,
            'off_count': self.off_count.value() if self.off_count.isVisible() else None
        }
        channel_configs = [ch.get_config() for ch in self.channel_widgets]
        self.primary_worker.send_async("program_device", {
            'system': system_config,
            'channels': channel_configs
        })


    def reset_device(self):
        # self.primary_worker.send_async("reset", {})
        logger.info("Now we wnat to reset devie from GUI ")

    def initialise_workers(self):
        connection_table = self.settings['connection_table']
        device_properties = connection_table.find_by_name(self.device_name).properties # dict
        channels_properties = self.get_children_properties()

        worker_kwargs = {
            "name": self.device_name + '_main',
            "device_properties": device_properties,
            "channels_properties": channels_properties
        }

        self.create_worker(
            'main_worker',
            'user_devices.BNC_575.BLACS_workers.BNC_575Worker',
            worker_kwargs,
        )

        self.primary_worker = "main_worker"

    def get_children_properties(self):
        children_properties = []
        connection_table = self.settings['connection_table']
        device = connection_table.find_by_name(self.device_name)

        for i in range(len(device.child_list)):
            child = self.get_child_from_connection_table(self.device_name, 'pulse {:01d}'.format(i + 1))
            children_properties.append(child.properties)
            # logger.info(f" child with {children_properties[i]['connection']}: {children_properties[i]}")
        return children_properties

    def create_trigger_button(self, on_click_callback):
        """Creates a styled QPushButton with consistent appearance and connects it to the given callback."""
        text = 'Software Trigger'
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
        logger.debug(f"[BNC] Button {text} is created")

        # Add centered layout to center the button
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(button)
        center_layout.addStretch()
        self.get_tab_layout().addLayout(center_layout)

    @define_state(MODE_MANUAL, True)
    def trigger_device(self):
        try:
            yield (self.queue_work(self.primary_worker, 'trigger', []))
        except Exception as e:
            logger.debug(f"[BNC] Error by send work to worker(trigger): \t {e}")

# class BNC_575Tab(DeviceTab):
#     def __init__(self, notebook, settings, restart=False):
#         self._Pulse = {}
#         super().__init__(notebook, settings, restart)
#
#     def initialise_GUI(self):
#         self.base_units = {'width': 's', 'delay': 's', 'wait': 'pulses'}
#         self.base_min = {'width': 0, 'delay': 0, 'wait': 0}
#         self.base_max = {'width': 999, 'delay': 999, 'wait': 9999999}
#         self.base_step = {'width': 1e-3, 'delay': 1e-3, 'wait': 1}
#         self.base_decimals = {'width': 4, 'delay': 4, 'wait': 0}
#
#         self.num_pulse = 8 # fixme
#
#         pulse_prop = {}
#         for i in range(1, self.num_pulse + 1):
#             key = f'pulse {i:01d}'
#             pulse_prop[key] = {}
#             # Add pulse properties for width, delay, wait
#             for subchnl in ['width', 'delay', 'wait']:
#                 pulse_prop[key][subchnl] = {
#                     'base_unit': self.base_units[subchnl],
#                     'min': self.base_min[subchnl],
#                     'max': self.base_max[subchnl],
#                     'step': self.base_step[subchnl],
#                     'decimals': self.base_decimals[subchnl]
#                 }
#             # Add placeholder for state (digital output) and mode (combo box)
#             pulse_prop[key]['state'] = {'base_unit': None, 'min': 0, 'max': 1, 'step': 1, 'decimals': 0}
#             pulse_prop[key]['mode'] = {
#                 'options': ['NORMal', 'SINGle', 'BURSt', 'DCYCle']}  # custom property for ComboBox options
#
#         self.create_pulse_outputs(pulse_prop)
#         pulse_widgets = self.create_pulse_widgets(pulse_prop)
#         self.auto_place_widgets(('Digital Outputs/Flags', pulse_widgets))
#         self.supports_remote_value_check(False)
#         self.supports_smart_programming(False)
#
#     def initialise_workers(self):
#         connection_table = self.settings['connection_table']
#         properties = connection_table.find_by_name(self.device_name).properties
#
#         worker_property_keys = [
#             "port", "baud_rate", "pulse_width", "trigger_mode",
#             "t0_mode", "t0_period", "t0_burst_count",
#             "t0_on_count", "t0_off_count", "trigger_logic", "trigger_level"
#         ]
#
#         worker_kwargs = {
#             "name": self.device_name + '_main',
#             **{k: properties[k] for k in worker_property_keys if k in properties}
#         }
#
#         self.create_worker(
#             'main_worker',
#             'user_devices.BNC_575.BLACS_workers.BNC_575Worker',
#             worker_kwargs,
#             )
#
#         self.primary_worker = "main_worker"
#
#     def create_pulse_outputs(self, pulse_properties):
#         for hardware_name, properties in pulse_properties.items():
#             device = self.get_child_from_connection_table(self.device_name, hardware_name)
#             connection_name = device.name if device else '-'
#
#             subchnl_name_list = ['width', 'delay', 'wait', 'state', 'mode']
#             sub_chnls = {}
#
#             for subchnl in subchnl_name_list:
#                 if subchnl not in properties:
#                     continue
#
#                 if subchnl in ['width', 'delay', 'wait']:
#                     sub_chnls[subchnl] = self._create_AO_object(
#                         connection_name, hardware_name + '_' + subchnl, subchnl, properties[subchnl])
#                 elif subchnl == 'state':
#                     sub_chnls['state'] = self._create_DO_object(
#                         connection_name, hardware_name + '_state', 'state', properties[subchnl])
#                 elif subchnl == 'mode':
#
#                     sub_chnls['mode'] = self._create_select_object(connection_name, hardware_name + '_mode', 'mode', properties[subchnl])
#
#             self._Pulse[hardware_name] = PULSE(hardware_name, connection_name, sub_chnls)
#
#     def _create_select_object(self,parent_device,BLACS_hardware_name,labscript_hardware_name,properties):
#         # Find the connection name
#         device = self.get_child_from_connection_table(parent_device,labscript_hardware_name)
#         connection_name = device.name if device else '-'
#
#         # Instantiate the DO object
#         return SELECT(BLACS_hardware_name, connection_name, self.device_name, self.program_device, self.settings)
#
#     def create_pulse_widgets(self, channel_properties):
#         widgets = {}
#         for hardware_name, properties in channel_properties.items():
#             properties.setdefault('args', [])
#             properties.setdefault('kwargs', {})
#             if hardware_name in self._Pulse:
#                 widgets[hardware_name] = self._Pulse[hardware_name].create_widget(*properties['args'],
#                                                                                 **properties['kwargs'])
#
#         return widgets
#
#
# class PULSE(object):
#     def __init__(self, hardware_name, connection_name, output_list):
#         self._hardware_name = hardware_name
#         self._connection_name = connection_name
#         self._sub_channel_list = ['width', 'delay', 'wait', 'state', 'mode']
#         self._widget_list = []
#         for subchnl in self._sub_channel_list:
#             value = None
#             if subchnl in output_list:
#                 value = output_list[subchnl]
#
#                 setattr(self, subchnl, value)
#
#     def create_widget(self, *args, **kwargs):
#         widget = PulseOutput(self._hardware_name, self._connection_name, *args, **kwargs)
#         self.add_widget(widget)
#         return widget
#
#     def add_widget(self, widget):
#         if widget in self._widget_list:
#             return False
#
#         # Check that the widget has a method for getting/showin/hiding subwidgets
#         for subchnl in self._sub_channel_list:
#             widget.get_sub_widget(subchnl)
#             widget.hide_sub_widget(subchnl)
#             widget.show_sub_widget(subchnl)
#
#         self._widget_list.append(widget)
#
#         for subchnl in self._sub_channel_list:
#             if hasattr(self, subchnl):
#                 getattr(self, subchnl).add_widget(widget.get_sub_widget(subchnl))
#                 widget.show_sub_widget(subchnl)
#             else:
#                 widget.hide_sub_widget(subchnl)
#
#         return True
#
#     def remove_widget(self, widget):
#         if widget not in self._widget_list:
#             # TODO: Make this error better!
#             raise RuntimeError('The widget specified was not part of the DDS object')
#
#         for subchnl in self._sub_channel_list:
#             if hasattr(self, subchnl):
#                 getattr(self, subchnl).remove_widget(widget.get_sub_widget(subchnl))
#
#         self._widget_list.remove(widget)
#
#     def get_subchnl_list(self):
#         subchnls = []
#         for subchnl in self._sub_channel_list:
#             if hasattr(self, subchnl):
#                 subchnls.append(subchnl)
#
#         return subchnls
#
#     def get_unused_subchnl_list(self):
#         return list(set(self._sub_channel_list).difference(set(self.get_subchnl_list())))
#
#     @property
#     def value(self):
#         value = {}
#         for subchnl in self._sub_channel_list:
#             if hasattr(self, subchnl):
#                 value[subchnl] = getattr(self, subchnl).value
#         return value
#
#     def set_value(self, value, program=True):
#         for subchnl in self._sub_channel_list:
#             if subchnl in value:
#                 if hasattr(self, subchnl):
#                     getattr(self, subchnl).set_value(value[subchnl], program=program)
#
#     @property
#     def name(self):
#         return self._hardware_name + ' - ' + self._connection_name
#
#
# class SELECT(object):
#     def __init__(self, hardware_name, connection_name, device_name, program_function, settings, options=None):
#         self._hardware_name = hardware_name
#         self._connection_name = connection_name
#         self._device_name = device_name
#         self._program_device = program_function
#         self._widget_list = []
#         self._options = options or ['NORMal', 'SINGle', 'BURSt', 'DCYCle']
#         self._current_selection = self._options[0]  # Default selection
#
#         self._update_from_settings(settings)
#
#     def _update_from_settings(self, settings):
#         if not isinstance(settings, dict):
#             settings = {}
#         if 'front_panel_settings' not in settings or not isinstance(settings['front_panel_settings'], dict):
#             settings['front_panel_settings'] = {}
#         if self._hardware_name not in settings['front_panel_settings'] or not isinstance(
#                 settings['front_panel_settings'][self._hardware_name], dict):
#             settings['front_panel_settings'][self._hardware_name] = {}
#
#         if 'base_value' not in settings['front_panel_settings'][self._hardware_name]:
#             settings['front_panel_settings'][self._hardware_name]['base_value'] = self._options[0]
#
#         if 'name' not in settings['front_panel_settings'][self._hardware_name]:
#             settings['front_panel_settings'][self._hardware_name]['name'] = self._connection_name
#
#         self._settings = settings['front_panel_settings'][self._hardware_name]
#
#         # self.set_value(self._settings['selected_option'], program=False)
#         self.set_value(self._settings['base_value'], program=False)
#         self._update_lock(self._settings['locked'])
#
#     def create_widget(self, *args, **kwargs):
#         widget = ModeBox(self._hardware_name, self._connection_name, self._options, *args, **kwargs)
#         self.add_widget(widget)
#         return widget
#
#     def add_widget(self, widget):
#         if widget not in self._widget_list:
#             widget.setCurrentText(self._current_selection)
#             widget._combobox.currentTextChanged.connect(self.set_value)
#             self._widget_list.append(widget)
#             self._update_lock(self._locked)
#             return True
#         return False
#
#     def remove_widget(self, widget):
#         if widget not in self._widget_list:
#             raise RuntimeError("The widget specified was not part of the SELECT object.")
#         widget._combobox.currentTextChanged.disconnect(self.set_value)
#         self._widget_list.remove(widget)
#
#     def lock(self):
#         self._update_lock(True)
#
#     def unlock(self):
#         self._update_lock(False)
#
#     def _update_lock(self, locked):
#         self._locked = locked
#         for widget in self._widget_list:
#             widget._combobox.setEnabled(not locked)
#         self._settings['locked'] = locked
#
#     def set_value(self, selection, program=True):
#         if selection not in self._options:
#             raise ValueError(f"Invalid selection: {selection}. Must be one of {self._options}")
#
#         self._current_selection = selection
#         # self._settings['selected_option'] = selection
#         self._settings['base_value'] = selection
#
#         if program:
#             self._program_device()
#
#         for widget in self._widget_list:
#             if widget.currentText() != selection:
#                 widget._combobox.blockSignals(True)
#                 widget.setCurrentText(selection)
#                 widget._combobox.blockSignals(False)
#
#
#     @property
#     def value(self):
#         return self._current_selection
#
#     @property
#     def name(self):
#         return f"{self._hardware_name} - {self._connection_name}"
#
#
