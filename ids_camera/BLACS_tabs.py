from blacs.tab_base_classes import Worker, define_state
from blacs.device_base_class import DeviceTab
from user_devices.logger_config import logger
from blacs.tab_base_classes import MODE_MANUAL
# from qtutils.qt.QtWidgets import QPushButton, QSizePolicy as QSP, QHBoxLayout, QSpacerItem
# from qtutils.qt.QtWidgets import QGraphicsView, QGraphicsScene, QWidget
from qtutils.qt import QtWidgets, QtGui, QtCore
from qtutils.qt.QtGui import QIcon
from qtutils.qt.QtWidgets import QButtonGroup, QApplication, QStyle, QPushButton
from qtutils.qt.QtCore import QPropertyAnimation, QEasingCurve

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

class ImageReceiver(ZMQServer):
    """ZMQServer that receives images on a zmq.REP socket, replies 'ok', and updates the
    image widget and fps indicator"""

    def __init__(self, image_view, label_fps):
        ZMQServer.__init__(self, port=None, dtype='multipart')
        self.image_view = image_view
        self.label_fps = label_fps
        self.last_frame_time = None
        self.frame_rate = None
        self.update_event = None

    @inmain_decorator(wait_for_return=True)
    def handler(self, data):
        # Acknowledge immediately so that the worker process can begin acquiring the
        # next frame. This increases the possible frame rate since we may render a frame
        # whilst acquiring the next, but does not allow us to accumulate a backlog since
        # only one call to this method may occur at a time.
        self.send([b'ok'])
        md = json.loads(data[0])
        image = np.frombuffer(memoryview(data[1]), dtype=md['dtype'])
        image = image.reshape(md['shape'])
        if len(image.shape) == 3 and image.shape[0] == 1:
            # If only one image given as a 3D array, convert to 2D array:
            image = image.reshape(image.shape[1:])
        this_frame_time = perf_counter()
        if self.last_frame_time is not None:
            dt = this_frame_time - self.last_frame_time
            if self.frame_rate is not None:
                # Exponential moving average of the frame rate over 1 second:
                self.frame_rate = exp_av(self.frame_rate, 1 / dt, dt, 1.0)
            else:
                self.frame_rate = 1 / dt
        self.last_frame_time = this_frame_time
        if self.image_view.image is None:
            # First time setting an image. Do autoscaling etc:
            self.image_view.setImage(image.swapaxes(-1, -2))
        else:
            # Updating image. Keep zoom/pan/levels/etc settings.
            self.image_view.setImage(
                image.swapaxes(-1, -2), autoRange=False, autoLevels=False
            )
        # Update fps indicator:
        # if self.frame_rate is not None:
            # self.label_fps.setText(f"{self.frame_rate:.01f} fps")

        # Tell Qt to send posted events immediately to prevent a backlog of paint events
        # and other low-priority events. It seems that we cannot make our qtutils
        # CallEvents (which are used to call this method in the main thread) low enough
        # priority to ensure all other occur before our next call to self.handler()
        # runs. This may be because the CallEvents used by qtutils.invoke_in_main have
        # their own event handler (qtutils.invoke_in_main.Caller), perhaps posted event
        # priorities are only meaningful within the context of a single event handler,
        # and not for the Qt event loop as a whole. In any case, this seems to fix it.
        # Manually calling this is usually a sign of bad coding, but I think it is the
        # right solution to this problem. This solves issue #36.
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
        self.ui.acquisition.clicked.connect(self.on_acquisition_clicked)
        self.ui.acquisition.hide()

        self.ui.settings_tool.clicked.connect(self.on_settings_clicked)

        layout.addWidget(self.ui)
        self.image = pg.ImageView()
        self.image.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.ui.verticalLayout.addWidget(self.image)

        # Set default values
        self.ui.hardware_trigger.setChecked(True)

        # Start the image receiver ZMQ server:
        self.image_receiver = ImageReceiver(self.image, None)
        self.acquiring = False

        # Initialise settings dialog GUI
        self.initialise_settings()
        self.supports_smart_programming(True)

    def initialise_settings(self):
        # todo:

        # Icons
        style = QApplication.style()
        reset_icon = style.standardIcon(QStyle.SP_DialogResetButton)
        discart_icon = style.standardIcon(QStyle.SP_DialogDiscardButton)
        media_stop_icon = style.standardIcon(QStyle.SP_MediaStop)
        media_start_icon = style.standardIcon(QStyle.SP_MediaPlay)

        dialog_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings_dialog.ui')
        self.settings_dialog = UiLoader().load(dialog_path)

        # Camera Image ROI
        self.settings_dialog.offset_y_slider
        self.settings_dialog.offset_y
        self.settings_dialog.offset_x_slider
        self.settings_dialog.offset_x
        self.settings_dialog.width_slider
        self.settings_dialog.width
        self.settings_dialog.height_slider
        self.settings_dialog.height

        # group_brightness_frame
        self.settings_dialog.slider_fps
        self.settings_dialog.spin_fps
        self.settings_dialog.slider_exp
        self.settings_dialog.spin_exp
        self.settings_dialog.slider_gain
        self.settings_dialog.spin_gain

        # Group Image Transformation
        self.settings_dialog.rotate_left_button.clicked.connect(self.on_rotate_left_clicked)
        self.settings_dialog.rotate_right_button.clicked.connect(self.on_rotate_right_clicked)
        self.settings_dialog.mirror_up_down.clicked.connect(self.on_mirror_ud_clicked)
        self.settings_dialog.mirror_left_right.clicked.connect(self.on_mirror_lr_clicked)

    def on_settings_clicked(self):
        #todo:
        return

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
        self.update_acquisition_button_state()
        yield (self.queue_work(self.primary_worker, 'hardware_trigger_conf'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_software_trigger_clicked(self, button):
        self.update_snap_button_state()
        self.update_acquisition_button_state()
        yield (self.queue_work(self.primary_worker, 'software_trigger_conf'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_freerun_clicked(self, button):
        self.update_snap_button_state()
        self.update_acquisition_button_state()
        yield (self.queue_work(self.primary_worker, 'freerun_conf'))

    def update_acquisition_button_state(self):
        enabled = self.ui.freerun.isChecked()
        self.ui.acquisition.setEnabled(enabled)
        self.ui.acquisition.setVisible(enabled)

    def update_snap_button_state(self):
        enabled = self.ui.software_trigger.isChecked()
        self.ui.pushButton_snap.setEnabled(enabled)
        self.ui.pushButton_snap.setVisible(enabled)


    def on_reset_rate_clicked(self):
        self.ui.doubleSpinBox_maxrate.setValue(0)

    def on_max_rate_changed(self, max_fps):
        if self.acquiring:
            self.stop_continuous()
            dt = 1 / max_fps if max_fps else 0
            self.start_continuous(dt)

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def start_continuous(self, dt):
        return

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def stop_continuous(self):
        return

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_acquisition_clicked(self, button):
        yield (self.queue_work(self.primary_worker, 'start_or_end_acquisition'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_rotate_left_clicked(self):
        yield (self.queue_work(self.primary_worker, 'rotate_left'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_rotate_right_clicked(self):
        yield (self.queue_work(self.primary_worker, 'rotate_right'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_mirror_ud_clicked(self):
        yield (self.queue_work(self.primary_worker, 'mirror_x'))

    @define_state(MODE_MANUAL, queue_state_indefinitely=True, delete_stale_states=True)
    def on_mirror_lr_clicked(self):
        yield (self.queue_work(self.primary_worker, 'mirror_y'))


