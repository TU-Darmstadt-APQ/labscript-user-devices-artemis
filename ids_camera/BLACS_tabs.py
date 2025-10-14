from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL
# from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
# from qtutils.qt.QtWidgets import QGraphicsView, QGraphicsScene, QWidget
from qtutils.qt import QtWidgets, QtGui, QtCore
from qtutils.qt.QtGui import QIcon
from qtutils.qt.QtWidgets import QButtonGroup, QApplication, QStyle, QPushButton, QSlider, QComboBox
from qtutils.qt.QtCore import QPropertyAnimation, QEasingCurve, Qt, pyqtSignal

import os
import json
from time import perf_counter
import ast
from queue import Empty
import numpy as np
import h5py

from qtutils import UiLoader, inmain_decorator
import pyqtgraph as pg

import labscript_utils.properties
from labscript_utils.ls_zprocess import ZMQServer


def exp_av(av_old, data_new, dt, tau):
    """Compute the new value of an exponential moving average based on the previous
    average av_old, a new value data_new, a time interval dt and an averaging timescale
    tau. Returns data_new if dt > tau"""
    if dt > tau:
        return data_new
    k = dt / tau
    return k * data_new + (1 - k) * av_old

# class ImageReceiver(ZMQServer):
#     """ZMQServer that receives images on a zmq.REP socket, replies 'ok', and updates the
#     image widget and fps indicator"""
#
#     def __init__(self, image_view, label_fps):
#         ZMQServer.__init__(self, port=None, dtype='multipart')
#         self.image_view = image_view
#         self.label_fps = label_fps
#         self.last_frame_time = None
#         self.frame_rate = None
#         self.update_event = None
#
#     @inmain_decorator(wait_for_return=True)
#     def handler(self, data):
#         # Acknowledge immediately so that the worker process can begin acquiring the
#         # next frame. This increases the possible frame rate since we may render a frame
#         # whilst acquiring the next, but does not allow us to accumulate a backlog since
#         # only one call to this method may occur at a time.
#         self.send([b'ok'])
#         md = json.loads(data[0])
#         image = np.frombuffer(memoryview(data[1]), dtype=md['dtype'])
#         image = image.reshape(md['shape'])
#         if len(image.shape) == 3 and image.shape[0] == 1:
#             # If only one image given as a 3D array, convert to 2D array:
#             image = image.reshape(image.shape[1:])
#         this_frame_time = perf_counter()
#         if self.last_frame_time is not None:
#             dt = this_frame_time - self.last_frame_time
#             if self.frame_rate is not None:
#                 # Exponential moving average of the frame rate over 1 second:
#                 self.frame_rate = exp_av(self.frame_rate, 1 / dt, dt, 1.0)
#             else:
#                 self.frame_rate = 1 / dt
#         self.last_frame_time = this_frame_time
#         if self.image_view.image is None:
#             # First time setting an image. Do autoscaling etc:
#             self.image_view.setImage(image.swapaxes(-1, -2))
#         else:
#             # Updating image. Keep zoom/pan/levels/etc settings.
#             self.image_view.setImage(
#                 image.swapaxes(-1, -2), autoRange=False, autoLevels=False
#             )
#         # Update fps indicator:
#         # if self.frame_rate is not None:
#             # self.label_fps.setText(f"{self.frame_rate:.01f} fps")
#
#         # Tell Qt to send posted events immediately to prevent a backlog of paint events
#         # and other low-priority events. It seems that we cannot make our qtutils
#         # CallEvents (which are used to call this method in the main thread) low enough
#         # priority to ensure all other occur before our next call to self.handler()
#         # runs. This may be because the CallEvents used by qtutils.invoke_in_main have
#         # their own event handler (qtutils.invoke_in_main.Caller), perhaps posted event
#         # priorities are only meaningful within the context of a single event handler,
#         # and not for the Qt event loop as a whole. In any case, this seems to fix it.
#         # Manually calling this is usually a sign of bad coding, but I think it is the
#         # right solution to this problem. This solves issue #36.
#         QtWidgets.QApplication.instance().sendPostedEvents()
#         return self.NO_RESPONSE

class ImageReceiver(ZMQServer):
    """ZMQServer that receives images on a zmq.REP socket, replies 'ok', and updates the image widget (and fps indicator)"""

    def __init__(self, image_item, label_fps=None):
        ZMQServer.__init__(self, port=None, dtype='multipart')
        self.image_item = image_item
        self.label_fps = label_fps
        self.last_frame_time = None
        self.frame_rate = None

    @inmain_decorator(wait_for_return=True)
    def handler(self, data):
        # Acknowledge immediately so that the worker process can begin acquiring the
        # next frame. This increases the possible frame rate since we may render a frame
        # whilst acquiring the next, but does not allow us to accumulate a backlog since
        # only one call to this method may occur at a time.
        self.send([b"ok"])
        md = json.loads(data[0])
        image = np.frombuffer(memoryview(data[1]), dtype=md["dtype"])
        image = image.reshape(md["shape"])

        # delete extra axes (if [1, h, w])
        if len(image.shape) == 3 and image.shape[0] == 1:
            image = image.reshape(image.shape[1:])

        # FPS
        this_frame_time = perf_counter()
        if self.last_frame_time is not None:
            dt = this_frame_time - self.last_frame_time
            if self.frame_rate is not None:
                self.frame_rate = exp_av(self.frame_rate, 1 / dt, dt, 1.0)
            else:
                self.frame_rate = 1 / dt
        self.last_frame_time = this_frame_time

        # Update image (w/o autoLevels!)
        self.image_item.setImage(image.swapaxes(-1, -2), autoLevels=False)

        # FPS-indicator
        # if self.frame_rate is not None and self.label_fps:
        #     self.label_fps.setText(f"{self.frame_rate:.01f} fps")

        QtWidgets.QApplication.instance().sendPostedEvents()
        return self.NO_RESPONSE


class CameraTab(DeviceTab):
    def initialise_GUI(self):
        layout = self.get_tab_layout()
        ui_filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'blacs_tab_new.ui')
        self.ui = UiLoader().load(ui_filepath)

        # Freerun/Trigger
        self.ui.hardware_trigger.clicked.connect(self.on_hardware_trigger_clicked)
        self.ui.software_trigger.clicked.connect(self.on_software_trigger_clicked)
        self.ui.pushButton_snap.clicked.connect(self.on_snap_clicked)
        self.ui.pushButton_snap.hide()  # default hardware trigger

        self.ui.freerun.clicked.connect(self.on_freerun_clicked)
        self.ui.frame_rate_spin.valueChanged.connect(self.on_freerun_framerate_clicked)
        self.ui.frame_rate_spin.hide()
        self.ui.start_acquisition_button.clicked.connect(self.on_start_acquisition_clicked)
        self.ui.stop_acquisition_button.clicked.connect(self.on_stop_acquisition_clicked)
        self.ui.start_acquisition_button.hide()
        self.ui.stop_acquisition_button.hide()

        self.ui.settings_tool.clicked.connect(self.on_settings_clicked)

        layout.addWidget(self.ui)
        # ---- ImageItem (instead of ImageView) ----
        self.img_item = pg.ImageItem()
        self.img_item.setLevels((0, 255))  # fixed levels

        view = pg.GraphicsLayoutWidget()
        vb = view.addViewBox()
        vb.addItem(self.img_item)
        vb.setAspectLocked(True)

        self.ui.verticalLayout.addWidget(view)

        # Start the image receiver ZMQ server:
        self.image_receiver = ImageReceiver(self.img_item)
        self.acquiring = False

        # self.image = pg.ImageView()
        # self.image.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        # self.image.ui.histogram.setLevels(0, 255)
        # self.image.ui.histogram.setHistogramRange(0, 255)

        # self.ui.verticalLayout.addWidget(self.image)

        # Start the image receiver ZMQ server:
        # self.image_receiver = ImageReceiver(self.image, None)
        # self.acquiring = False

        # Set default values
        self.ui.hardware_trigger.setChecked(True)

        # Initialise settings dialog GUI
        self.initialise_settings()
        self.supports_smart_programming(True)

    def initialise_settings(self):
        # Icons
        style = QApplication.style()
        reset_icon = style.standardIcon(QStyle.SP_DialogResetButton)
        discart_icon = style.standardIcon(QStyle.SP_DialogDiscardButton)
        media_stop_icon = style.standardIcon(QStyle.SP_MediaStop)
        media_start_icon = style.standardIcon(QStyle.SP_MediaPlay)

        dialog_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings_dialog.ui')
        self.settings_dialog = UiLoader().load(dialog_path)

        # # Remove QSliders, replace with DoubleSliders
        # self.slider_fps = DoubleSlider(0.5, 17.29)
        # self.slider_exp = DoubleSlider(8.982/1000, 114912.8/1000)
        # self.slider_gain = DoubleSlider(1.0, 4.0)

        layout = self.settings_dialog.gridLayout_brightness

        # row, col, rowSpan, colSpan = layout.getItemPosition(layout.indexOf(self.settings_dialog.slider_fps))
        # layout.addWidget(self.slider_fps, row, col, rowSpan, colSpan)
        # layout.removeWidget(self.settings_dialog.slider_fps)
        # self.settings_dialog.slider_fps.deleteLater()
        #
        # row, col, rowSpan, colSpan = layout.getItemPosition(layout.indexOf(self.settings_dialog.slider_exp))
        # layout.addWidget(self.slider_exp, row, col, rowSpan, colSpan)
        # layout.removeWidget(self.settings_dialog.slider_exp)
        # self.settings_dialog.slider_exp.deleteLater()
        #
        # row, col, rowSpan, colSpan = layout.getItemPosition(layout.indexOf(self.settings_dialog.slider_gain))
        # layout.addWidget(self.slider_gain, row, col, rowSpan, colSpan)
        # layout.removeWidget(self.settings_dialog.slider_gain)
        # self.settings_dialog.slider_gain.deleteLater()

        # # Update links
        # self.settings_dialog.slider_fps = self.slider_fps
        # self.settings_dialog.slider_exp = self.slider_exp
        # self.settings_dialog.slider_gain = self.slider_gain

        # Group Image Transformation
        self.settings_dialog.rotate_left_button.clicked.connect(self.on_rotate_left_clicked)
        self.settings_dialog.rotate_right_button.clicked.connect(self.on_rotate_right_clicked)
        self.settings_dialog.mirror_up_down.clicked.connect(self.on_mirror_ud_clicked)
        self.settings_dialog.mirror_left_right.clicked.connect(self.on_mirror_lr_clicked)

        # Sync sliders and spinboxs
        self.settings_dialog.spin_fps.valueChanged.connect(self.on_fps_changed)
        self.settings_dialog.spin_exp.valueChanged.connect(self.on_exposure_changed)
        self.settings_dialog.spin_gain.valueChanged.connect(self.on_gain_changed)

        # self.sync_slider_spin(self.settings_dialog.slider_fps, self.settings_dialog.spin_fps, self.on_fps_changed)
        # self.sync_slider_spin(self.settings_dialog.slider_exp, self.settings_dialog.spin_exp, self.on_exposure_changed)
        # self.sync_slider_spin(self.settings_dialog.slider_gain, self.settings_dialog.spin_gain, self.on_gain_changed)

        self.sync_slider_spin(self.settings_dialog.offset_x_slider, self.settings_dialog.offset_x, self.on_roi_changed)
        self.sync_slider_spin(self.settings_dialog.offset_y_slider, self.settings_dialog.offset_y, self.on_roi_changed)
        self.sync_slider_spin(self.settings_dialog.width_slider, self.settings_dialog.width, self.on_roi_changed)
        self.sync_slider_spin(self.settings_dialog.height_slider, self.settings_dialog.height, self.on_roi_changed)

        # ROI
        self.settings_dialog.offset_x_slider.setRange(0, 1280)
        self.settings_dialog.offset_x_slider.setSingleStep(1)
        self.settings_dialog.offset_x.setRange(0, 1280)

        self.settings_dialog.offset_y_slider.setRange(0, 1024)
        self.settings_dialog.offset_y_slider.setSingleStep(1)
        self.settings_dialog.offset_y.setRange(0, 1024)

        self.settings_dialog.width_slider.setRange(16, 1280)
        self.settings_dialog.width_slider.setSingleStep(1)
        self.settings_dialog.width.setRange(16, 1280)

        self.settings_dialog.height_slider.setRange(4, 1024)
        self.settings_dialog.height_slider.setSingleStep(1)
        self.settings_dialog.height.setRange(4, 1024)

        # Default values
        self.settings_dialog.width.setValue(1280)
        self.settings_dialog.height.setValue(1024)

        self.settings_dialog.spin_fps.setValue(10.0)
        self.settings_dialog.spin_exp.setValue(5000.0)
        self.settings_dialog.spin_gain.setValue(2.0)
        # self.slider_fps.setValue(self.settings_dialog.spin_fps.value())
        # self.slider_exp.setValue(self.settings_dialog.spin_exp.value())
        # self.slider_gain.setValue(self.settings_dialog.spin_gain.value())

    def sync_slider_spin(self, slider, spinbox, callback, ):
        """Sync QSlider and QSpinBox in both directions.
        Scaling to DoubleSpinBox[float] <-> Slider[float]"""
        if hasattr(slider, 'doubleValueChanged'):
            # DoubleSlider
            slider.doubleValueChanged.connect(spinbox.setValue)
            spinbox.valueChanged.connect(slider.setValue)
            slider.doubleValueChanged.connect(callback)
            spinbox.valueChanged.connect(callback)
        else:
            # regular QSlider
            slider.valueChanged.connect(spinbox.setValue)
            spinbox.valueChanged.connect(slider.setValue)
            slider.valueChanged.connect(callback)
            spinbox.valueChanged.connect(callback)

    def on_settings_clicked(self):
        self.settings_dialog.setParent(self.ui.parent())
        self.settings_dialog.setWindowFlags(QtCore.Qt.Tool)
        self.settings_dialog.setWindowTitle("{} settings".format(self.device_name))
        self.settings_dialog.show()

    def initialise_workers(self):
        table = self.settings['connection_table']
        connection_table_properties = table.find_by_name(self.device_name).properties
        with h5py.File(table.filepath, 'r') as f:
            device_properties = labscript_utils.properties.get(
                f, self.device_name, "device_properties"
            )
        if table.find_by_name(self.device_name) is None:
            raise ValueError(f"Camera '{self.device_name}' not found in the connection table.")

        worker_kwargs = {
            "name": self.device_name + '_main',
            "serial_number": connection_table_properties["serial_number"],
            "exposure_time":  device_properties["exposure_time"],
            "frame_rate": device_properties["frame_rate"],
            "gain": device_properties["gain"],
            "roi": device_properties["roi"],
            "camera_setting": device_properties["camera_setting"],
            'image_receiver_port': self.image_receiver.port,
        }
        self.create_worker(
            'main_worker',
            'user_devices.ids_camera.BLACS_workers.CameraWorker',
            worker_kwargs,
            )
        
        self.primary_worker = "main_worker"

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_snap_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'software_trigger_snap'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_hardware_trigger_clicked(self, button):
        self.update_snap_button_state()
        self.update_freerun_settings_visibility()
        yield (self.queue_work(self.primary_worker, 'hardware_trigger_conf'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_software_trigger_clicked(self, button):
        self.update_snap_button_state()
        self.update_freerun_settings_visibility()
        yield (self.queue_work(self.primary_worker, 'software_trigger_conf'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_freerun_framerate_clicked(self, button):
        frame_rate =  self.ui.frame_rate_spin.value()
        yield (self.queue_work(self.primary_worker, 'freerun_conf', [frame_rate]))

    def on_freerun_clicked(self, button):
        self.update_snap_button_state()
        self.update_freerun_settings_visibility()
        self.ui.start_acquisition_button.setEnabled(True)
        self.ui.stop_acquisition_button.setEnabled(False)

    def update_freerun_settings_visibility(self):
        enabled = self.ui.freerun.isChecked()
        self.ui.start_acquisition_button.setVisible(enabled)
        self.ui.stop_acquisition_button.setVisible(enabled)
        self.ui.frame_rate_spin.setVisible(enabled)

    def update_snap_button_state(self):
        enabled = self.ui.software_trigger.isChecked()
        self.ui.pushButton_snap.setEnabled(enabled)
        self.ui.pushButton_snap.setVisible(enabled)

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_start_acquisition_clicked(self, button):
        # Disable start, enable stop
        self.ui.start_acquisition_button.setEnabled(False)
        self.ui.stop_acquisition_button.setEnabled(True)
        yield (self.queue_work(self.primary_worker, 'start_freerun_acquisition'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_stop_acquisition_clicked(self, button):
        # Enable start, disable stop
        self.ui.start_acquisition_button.setEnabled(True)
        self.ui.stop_acquisition_button.setEnabled(False)
        yield (self.queue_work(self.primary_worker, 'stop_acquisition'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_rotate_left_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'rotate_left'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_rotate_right_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'rotate_right'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_mirror_ud_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'mirror_x'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_mirror_lr_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'mirror_y'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_fps_changed(self, value):
        yield (self.queue_work(self.primary_worker, 'set_fps', [value]))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_exposure_changed(self, value):
        yield (self.queue_work(self.primary_worker, 'set_exposure', [value]))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_gain_changed(self, value):
        yield (self.queue_work(self.primary_worker, 'set_gain', [value]))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_roi_changed(self, *args):
        """ Acquisition should be stopped first """
        x = self.settings_dialog.offset_x.value()
        y = self.settings_dialog.offset_y.value()
        w = self.settings_dialog.width.value()
        h = self.settings_dialog.height.value()
        yield (self.queue_work(self.primary_worker, 'set_roi', [x, y, w, h]))



class DoubleSlider(QSlider):
    doubleValueChanged = pyqtSignal(float)

    def __init__(self, minimum: float, maximum: float, step: float = 0.1, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._min_value = minimum
        self._max_value = maximum
        self._step = step

        # Number of descrete steps for QSlider
        self._steps = int(round((self._max_value - self._min_value) / self._step))

        super().setOrientation(Qt.Horizontal)
        super().setMinimum(0)
        super().setMaximum(self._steps)

        # Connect change signal
        self.valueChanged.connect(self._emit_double_value)

        self.is_double_slider = True

    def _emit_double_value(self, int_val):
        self.doubleValueChanged.emit(round(self.value(), 1))

    @property
    def value_range(self):
        return self._max_value - self._min_value

    def value(self) -> float:
        """Getting float value"""
        return round(self._min_value + super().value() * self._step, 1)

    def setValue(self, val: float):
        """Setting float value"""
        int_val = int(round((val - self._min_value) / self._step, 1))
        int_val = max(0, min(int_val, self._steps))
        super().setValue(int_val)

    def setMinimum(self, value: float):
        self._min_value = value
        self._steps = int(round((self._max_value - self._min_value) / self._step))
        super().setMaximum(self._steps)
        self.setValue(self.value())

    def setMaximum(self, value: float):
        self._max_value = value
        self._steps = int(round((self._max_value - self._min_value) / self._step))
        super().setMaximum(self._steps)
        self.setValue(self.value())

    def minimum(self):
        return self._min_value

    def maximum(self):
        return self._max_value

