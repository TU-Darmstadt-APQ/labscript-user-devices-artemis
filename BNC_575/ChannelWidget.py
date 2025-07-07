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
        self._widgets['state'] = DigitalOutput('Enable')

        self._widgets['width'] = QDoubleSpinBox()
        self._widgets['width'].setDecimals(9)
        self._widgets['width'].setRange(0.000, 999.999)
        self._widgets['width'].setSingleStep(0.001)
        self._widgets['width'].setSuffix(" s")

        self._widgets['delay'] = QDoubleSpinBox()
        self._widgets['delay'].setDecimals(9)
        self._widgets['delay'].setRange(0.000, 999.999)
        self._widgets['delay'].setSingleStep(0.001)
        self._widgets['delay'].setSuffix(" s")

        self._widgets['wait'] = QDoubleSpinBox()
        self._widgets['wait'].setDecimals(0)
        self._widgets['wait'].setRange(0, 9999999)
        self._widgets['wait'].setSingleStep(1)
        self._widgets['wait'].setSuffix(" s")

        self._widgets['mode'] = QComboBox()
        self._widgets['mode'].addItems(['NORMal', 'SINGle', 'BURSt', 'DCYCle'])
        self._widgets['mode'].currentTextChanged.connect(self.update_visibility)

        self._widgets['burst_count'] = QSpinBox()
        self._widgets['on_count'] = QSpinBox()
        self._widgets['off_count'] = QSpinBox()
        self._widgets['burst_count'].hide()
        self._widgets['on_count'].hide()
        self._widgets['off_count'].hide()

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

        form_layout.addRow("Enable:", self.gate_container)
        form_layout.addRow("Width (s):", self._widgets['width'])
        form_layout.addRow("Delay (s):", self._widgets['delay'])
        form_layout.addRow("Wait:", self._widgets['wait'])
        form_layout.addRow("Mode:", self._widgets['mode'])
        form_layout.addRow("Burst Count:", self._widgets['burst_count'])
        form_layout.addRow("On Count:", self._widgets['on_count'])
        form_layout.addRow("Off Count:", self._widgets['off_count'])
        form_layout.addRow("Sync Source:", self._widgets['sync_source'])

        # v_layout.addWidget(self.gate_container)
        # v_layout.addWidget(self._widgets['width'])
        # v_layout.addWidget(self._widgets['delay'])
        # v_layout.addWidget(self._widgets['wait'])
        # v_layout.addWidget(self._widgets['mode'])
        # v_layout.addWidget(self._widgets['burst_count'])
        # v_layout.addWidget(self._widgets['on_count'])
        # v_layout.addWidget(self._widgets['off_count'])
        # v_layout.addWidget(self._widgets['sync_source'])


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
            'mode': mode,
            'width': self._widgets['width'].value(),
            'delay': self._widgets['delay'].value(),
            'wait': self._widgets['wait'].value(),
            'sync_source': self._widgets['sync_source'].currentText(),
            'burst_count': self._widgets['burst_count'].value() if mode == 'BURST' else None,
            'on_count': self._widgets['on_count'].value() if mode == 'DCYCLE' else None,
            'off_count': self._widgets['off_count'].value() if mode == 'DCYCLE' else None,
        }

# A simple test!
if __name__ == '__main__':
    qapplication = QApplication(sys.argv)

    window = QWidget()
    layout = QVBoxLayout(window)
    button = ChannelWidget('pulse 1')

    layout.addWidget(button)

    window.show()

    sys.exit(qapplication.exec_())