# ~/labscript-suite/userlib/analysislib/example_apparatus/single_shot_lyse_scan.py
import numpy as np

import pyqtgraph as pg
from qtutils.qt import QtWidgets, QtGui, QtCore
from pylab import *
from lyse import *
import h5py

parent = QtWidgets.QApplication.activeWindow()

run = Run(path)

############# Globals ###############
globals_dict = run.get_globals()
print("Globals:", globals_dict)


def get_images(shot):
    images_list = []
    titles = []
    try:
        image_labels_dict = shot.get_all_image_labels()
    except KeyError:
        print("No images in this shot...")
        return [], []

    for orientation, labels in image_labels_dict.items():
        for label in labels:
            group = shot.h5_file[f'images/{orientation}/{label}']
            for image_name in group.keys():
                img = shot.get_image(orientation, label, image_name)
                images_list.append(img)
                titles.append(f"{orientation}/{label}/{image_name}")
    return images_list, titles

def plot_traces(shot):
    win = pg.GraphicsLayoutWidget(show=True, title="Picoscope traces")
    win.resize(1200, 800)
    plot_row = 0
    picoscopes = shot.trace_names()  # gets the dataset names per picoscope
    for picoscope in picoscopes:
        print(picoscope)
        traces_ds = shot.h5_file['data']['traces'][picoscope]
        traces_names = traces_ds.attrs["channel_names"]
        dt = traces_ds.attrs["sample_interval"]
        triggered_at = traces_ds.attrs["triggered_at"]
        data = traces_ds[()]
        N, C = data.shape
        t = np.linspace(0, (N-1) * dt, N)
        traces = {name: data[:, i] for i, name in enumerate(traces_names)}

        p = win.addPlot(row=plot_row, col=0, title=picoscope)
        p.addLegend(offset=(1, 1))
        p.showGrid(x=True, y=True)

        for i, (name, y) in enumerate(traces.items()):
            p.plot(t, y, pen=pg.intColor(i), name=name)
            if i == 0: # plot the trigger dot on the first channel
                p.plot([t[triggered_at]], [y[triggered_at]], pen=None, symbol='o', symbolBrush='r')
        plot_row += 1

    return win

with run.open('r+') as shot:
    # get images
    images_list, titles = get_images(shot)
    # get traces
    trace_window = plot_traces(shot)
    trace_window.setWindowFlags(QtCore.Qt.Tool)
    trace_window.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    trace_window.show()



if images_list:
    image_views = []

    for i, image in enumerate(images_list):
        print(f"image: {titles[i]}, {i}")
        image_view = pg.ImageView(parent=parent)
        image_view.setWindowFlags(QtCore.Qt.Tool) # To not block the Qt event loop by manual view-window closing.
        image_view.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        image_view.setImage(image.swapaxes(-1, -2), autoRange=False, autoLevels=False)
        image_view.setWindowTitle(titles[i])
        image_view.show()

        image_views.append(image_view)

print("DONE")


