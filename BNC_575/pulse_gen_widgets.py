import sys

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from labscript_utils.qtwidgets.analogoutput import AnalogOutput
from labscript_utils.qtwidgets.digitaloutput import DigitalOutput

class ChannelWidget(QWidget):
    def __init__(self, hardware_name, connection_name='-', parent=None):
        QWidget.__init__(self, parent)

        self._connection_name = connection_name
        self._hardware_name = hardware_name

        label_text = (self._hardware_name + '\n' + self._connection_name)
        self._label = QLabel(label_text)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)

        # Create widgets
        self._widgets = {}
        self._widgets['state'] = DigitalOutput('On/Off')

        self._widgets['width'] = AnalogOutput('', display_name='<i>width</i>', horizontal_alignment=True)
        self._widgets['width'].set_num_decimals(9)
        self._widgets['width'].set_limits(0.000, 999.999)
        self._widgets['width'].set_step_size(0.001)
        self._widgets['width']._combobox.setModel(QStringListModel(['s']))
        self._widgets['width'].set_selected_unit('s')

        self._widgets['delay'] = AnalogOutput('', display_name='<i>delay</i>', horizontal_alignment=True)
        self._widgets['delay'].set_num_decimals(9)
        self._widgets['delay'].set_limits(0.000, 999.999)
        self._widgets['delay'].set_step_size(0.001)
        self._widgets['delay']._combobox.setModel(QStringListModel(['s']))
        self._widgets['delay'].set_selected_unit('s')

        self._widgets['wait'] = AnalogOutput('', display_name=u'<i>wait</i>', horizontal_alignment=True)
        self._widgets['wait'].set_num_decimals(0)
        self._widgets['wait'].set_limits(0, 9999999)
        self._widgets['wait'].set_step_size(1)
        self._widgets['wait']._combobox.setModel(QStringListModel(['pulses']))
        self._widgets['wait'].set_selected_unit('pulses')

        self._widgets['mode'] = QComboBox()
        self._widgets['mode'].addItems(['NORMal', 'SINGle', 'BURSt', 'DCYCle'])
        self._widgets['mode'].currentTextChanged.connect(self.update_visibility)

        for name in ['burst_count', 'on_count', 'off_count']:
            self._widgets[name] = self.make_pulse_spinbox(name)

        self._widgets['sync_source'] = QComboBox()
        self._widgets['sync_source'].addItems(['T0', 'CHA', 'CHB', 'CHC', 'CHD', 'CHE', 'CHF', 'CHG', 'CHH'])

        # Extra layout at the top level with horizontal stretches so that our
        # widgets do not grow to take up all available horizontal space:
        self._outer_layout = QHBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._frame = QFrame(self)
        self._outer_layout.addStretch()
        self._outer_layout.addWidget(self._frame)
        self._outer_layout.addStretch()

        # Create grid layout that keeps widgets from expanding and keeps label centred above the widgets
        self._layout = QGridLayout(self._frame)
        self._layout.setVerticalSpacing(3)
        self._layout.setHorizontalSpacing(0)
        self._layout.setContentsMargins(0, 0, 0, 0)

        v_widget = QFrame()
        v_widget.setFrameStyle(QFrame.StyledPanel)
        # v_layout = QVBoxLayout(v_widget)
        # v_layout.setContentsMargins(6, 6, 6, 6)
        form_layout = QFormLayout(v_widget)
        form_layout.setContentsMargins(6, 6, 6, 6)

        # Extra widget with stretches around the enabled button so it doesn't
        # stretch out to fill all horizontal space:
        self.gate_container = QWidget()
        gate_layout = QHBoxLayout(self.gate_container)
        gate_layout.setContentsMargins(0, 0, 0, 0)
        gate_layout.setSpacing(0)
        gate_layout.addStretch()
        gate_layout.addWidget(self._widgets['state'])
        gate_layout.addStretch()

        form_layout.addRow("State:", self.gate_container)
        form_layout.addRow(self._widgets['width'])
        form_layout.addRow(self._widgets['delay'])
        form_layout.addRow(self._widgets['wait'])

        form_layout.addRow("Mode:", self._widgets['mode'])
        form_layout.addRow(self._widgets['burst_count'])
        form_layout.addRow(self._widgets['on_count'])
        form_layout.addRow(self._widgets['off_count'])

        form_layout.addRow("Sync Source:", self._widgets['sync_source'])


        self._layout.addWidget(self._label, 0, 0)
        # self._layout.addItem(QSpacerItem(0,0,QSizePolicy.MinimumExpanding,QSizePolicy.Minimum),0,1)
        self._layout.addWidget(v_widget, 1, 0)
        # self._layout.addItem(QSpacerItem(0,0,QSizePolicy.MinimumExpanding,QSizePolicy.Minimum),1,1)
        self._layout.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.MinimumExpanding), 2, 0)

    def update_visibility(self):
        mode = self._widgets['mode'].currentText().upper()
        self._widgets['burst_count'].setVisible(mode == 'BURST')
        self._widgets['on_count'].setVisible(mode == 'DCYCLE')
        self._widgets['off_count'].setVisible(mode == 'DCYCLE')

    def get_config(self):
        mode = self._widgets['mode'].currentText().upper()
        return {
            'mode': self._widgets['mode'].currentText(),
            'width': round(self._widgets['width']._spin_widget.value(), 5),
            'delay': round(self._widgets['delay']._spin_widget.value(), 5),
            'wait_counter': self._widgets['wait']._spin_widget.value(),
            'sync_source': self._widgets['sync_source'].currentText(),
            'burst_count': self._widgets['burst_count']._spin_widget.value() if mode == 'BURST' else None,
            'on_count': self._widgets['on_count']._spin_widget.value() if mode == 'DCYCLE' else None,
            'off_count': self._widgets['off_count']._spin_widget.value() if mode == 'DCYCLE' else None,
        }

    def make_pulse_spinbox(self, name):
        widget = AnalogOutput('', display_name=f'<i>{name}</i>', horizontal_alignment=True)
        widget.set_num_decimals(0)
        widget.set_limits(0, 9999999)
        widget.set_step_size(1)
        widget._combobox.setModel(QStringListModel(['pulses']))
        widget.set_selected_unit('pulses')
        widget.hide()
        return widget

class SystemWidget(QWidget):
    def __init__(self, hardware_name, connection_name='', parent=None):
        QWidget.__init__(self, parent)

        self._connection_name = connection_name
        self._hardware_name = hardware_name

        label_text = (self._hardware_name + '\n' + self._connection_name)
        self._label = QLabel(label_text)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Minimum)

        # Create widgets
        self._widgets = {}
        self._widgets['period'] = AnalogOutput('', display_name='<i>period</i>', horizontal_alignment=True)
        self._widgets['period'].set_num_decimals(9)
        self._widgets['period'].set_limits(0.0000001, 5000.0)
        self._widgets['period'].set_step_size(0.001)
        self._widgets['period']._combobox.setModel(QStringListModel(['s']))
        self._widgets['period'].set_selected_unit('s')

        self._widgets['mode'] = QComboBox()
        self._widgets['mode'].addItems(['NORMal', 'SINGle', 'BURSt', 'DCYCle'])
        self._widgets['mode'].currentTextChanged.connect(self.update_visibility)

        self._widgets['trigger mode'] = QCheckBox("Trigger Enabled")

        for name in ['burst_count', 'on_count', 'off_count']:
            self._widgets[name] = self.make_pulse_spinbox(name)

        # Create the form layout
        v_widget = QFrame()
        v_widget.setFrameStyle(QFrame.StyledPanel)
        form_layout = QFormLayout(v_widget)
        form_layout.setContentsMargins(6, 6, 6, 6)

        form_layout.addRow(self._label)
        form_layout.addRow(self._widgets['period'])
        form_layout.addRow("Mode:", self._widgets['mode'])
        form_layout.addRow("Trigger mode:", self._widgets['trigger mode'])
        form_layout.addRow(self._widgets['burst_count'])
        form_layout.addRow(self._widgets['on_count'])
        form_layout.addRow(self._widgets['off_count'])

        #Add a layout to the widget and include the form
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(v_widget)

    def update_visibility(self):
        mode = self._widgets['mode'].currentText().upper()
        self._widgets['burst_count'].setVisible(mode == 'BURST')
        self._widgets['on_count'].setVisible(mode == 'DCYCLE')
        self._widgets['off_count'].setVisible(mode == 'DCYCLE')

    def make_pulse_spinbox(self, name):
        widget = AnalogOutput('', display_name=f'<i>{name}</i>', horizontal_alignment=True)
        widget.set_num_decimals(0)
        widget.set_limits(0, 9999999)
        widget.set_step_size(1)
        widget._combobox.setModel(QStringListModel(['pulses']))
        widget.set_selected_unit('pulses')
        widget.hide()
        return widget

    def get_config(self):
        mode = self._widgets['mode'].currentText().upper()
        return {
            't0_mode': self._widgets['mode'].currentText(),
            'trigger_mode': 'TRIGgered' if self._widgets['trigger mode'].isChecked() else 'DISabled',
            't0_period': round(self._widgets['period']._spin_widget.value(), 7),
            't0_burst_count': self._widgets['burst_count']._spin_widget.value() if mode == 'BURST' else None,
            't0_on_count': self._widgets['on_count']._spin_widget.value() if mode == 'DCYCLE' else None,
            't0_off_count': self._widgets['off_count']._spin_widget.value() if mode == 'DCYCLE' else None,
        }



# A simple test!
if __name__ == '__main__':
    qapplication = QApplication(sys.argv)

    window = QWidget()
    layout = QVBoxLayout(window)
    button = ChannelWidget('pulse 1')
    system_wid = SystemWidget('system')

    layout.addWidget(button)
    layout.addWidget(system_wid)

    window.show()

    sys.exit(qapplication.exec_())