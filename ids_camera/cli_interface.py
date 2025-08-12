# \file    cli_interface.py
# \author  IDS Imaging Development Systems GmbH
# \date    2024-02-20
#
# \brief   This sample shows how to start and stop acquisition as well as
#          how to capture images using a software trigger
#
# \version 1.0
#
# Copyright (C) 2024, IDS Imaging Development Systems GmbH.
#
# The information in this document is subject to change without notice
# and should not be construed as a commitment by IDS Imaging Development Systems GmbH.
# IDS Imaging Development Systems GmbH does not assume any responsibility for any errors
# that may appear in this document.
#
# This document, or source code, is provided solely as an example of how to utilize
# IDS Imaging Development Systems GmbH software libraries in a sample application.
# IDS Imaging Development Systems GmbH does not assume any responsibility
# for the use or reliability of any portion of this document.
#
# General permission to copy or modify is hereby granted.

from ids_peak import ids_peak

from camera import Camera


class Interface:
    def __init__(self, cam_module: Camera = None):
        self.__camera = cam_module
        self.acquisition_thread = None

    def is_gui(self):
        return False

    def set_camera(self, cam_module: Camera):
        self.__camera = cam_module

    def acquisition_check_and_set(self):
        if not self.__camera.acquisition_running:
            print("The image acquisition must be running to get an image.")
            choice = input("Start acquisition now?: [Y|n]")
            if choice == "" or choice == "y" or choice == "Y":
                self.__camera.start_acquisition()
                return True
            return False
        return True

    def acquisition_check_and_disable(self):
        if self.__camera.acquisition_running:
            print("Acquisition must NOT be running to set a new pixelformat")
            choice = input("Stop acquisition now?: [Y|n]")
            if choice == "" or choice == "y" or choice == "Y":
                self.__camera.stop_acquisition()
                return True
            if choice == "n" or choice == "N":
                return False
        return True

    def change_pixelformat(self):
        formats = self.__camera.node_map.FindNode("PixelFormat").Entries()
        available_options = []
        for idx in formats:
            if (idx.AccessStatus() != ids_peak.NodeAccessStatus_NotAvailable
                    and idx.AccessStatus() != ids_peak.NodeAccessStatus_NotImplemented):
                available_options.append(idx.SymbolicValue())
        print("Select available option by index:\n")
        counter = 0
        for entry in available_options:
            print(f"[{counter}]: {entry}")
            counter += 1
        selected = -1
        while selected == -1:
            try:
                selected = int(input(" >> "))
            except ValueError:
                selected = -1
            if selected < 0 or selected >= len(available_options):
                print(
                    f"Please enter a number between 0 and {len(available_options) - 1}")
                selected = -1
        self.__camera.change_pixel_format(available_options[selected])

    def configure_mock_trigger(self):
        def is_aqcuisition_running():
            # Before accessing AcquisitionStatus, make sure AcquisitionStatusSelector is set correctly
             # Set AcquisitionStatusSelector to "AcquisitionActive" (str)
            self.__camera.node_map.FindNode("AcquisitionStatusSelector").SetCurrentEntry("FrameTriggerWait")
             # Determine the current status of AcquisitionStatus (bool)
            value = self.__camera.node_map.FindNode("AcquisitionStatus").Value()
            return value

        # Place ExposureStart trigger on Line2
        self.__camera.init_hardware_trigger(trigger_source="Line0")

        # Configure Line0
        self.__camera.node_map.FindNode("LineSelector").SetCurrentEntry("Line0")

        # Determine the current entry of LineMode (str)
        value = self.__camera.node_map.FindNode("LineMode").CurrentEntry().SymbolicValue()
        # Get a list of all available entries of LineMode
        allEntries = self.__camera.node_map.FindNode("LineMode").Entries()
        availableEntries = []
        for entry in allEntries:
            if (entry.AccessStatus() != ids_peak.NodeAccessStatus_NotAvailable
                    and entry.AccessStatus() != ids_peak.NodeAccessStatus_NotImplemented):
                availableEntries.append(entry.SymbolicValue())

        print(f"Acquisition is ")
        print(f"Line Mode available entries: {availableEntries} and current entry={value}")

        node_line_mode = self.__camera.node_map.FindNode("LineMode")
        access_mode = node_line_mode.GetAccessMode()
        print(f"LineMode access mode: {access_mode}")

        self.__camera.node_map.FindNode("LineMode").SetCurrentEntry("Output")
        self.__camera.node_map.FindNode("LineSource").SetCurrentEntry("UserOutput0")

        value = self.__camera.node_map.FindNode("LineMode").CurrentEntry().SymbolicValue()
        print(f"Line mode is set on : \t {value}")

    def start_interface(self):
        """Now, we will try simulate external trigger.
        place a UserOutput on a Line (hardware input) and configure this as the output.
        You can now use the UserOutput to activate and deactivate the Line, as though a hardware signal were present there."""
        try:
            while True:
                var = input("> ")
                var = var.split()
                if not var:
                    continue
                if var[0] == "t":
                    # start simulation
                    if not self.acquisition_check_and_set():
                        print("Acquisition not started... Skipping trigger command!")
                        continue
                    self.__camera.make_image = True
                    # wait until image has been made
                    while self.__camera.make_image:
                        pass



            # while True:
            #     var = input("> ")
            #
            #     var = var.split()
            #     if not var:
            #         continue
            #
                # if var[0] == "trigger":
                #     # trigger an image
                #     if not self.acquisition_check_and_set():
                #         print("Acquisition not started... Skipping trigger command!")
                #         continue
                #     self.__camera.make_image = True
                #     # wait until image has been made
                #     while self.__camera.make_image:
                #         pass
            #
            #     elif var[0] == "save":
            #         # enable/disable saving to drive
            #         if len(var) < 2:
            #             print("Missing argument! Usage: save True|False")
            #             continue
            #         if var[1] == "True":
            #             self.__camera.keep_image = True
            #             print("Saving images: Enabled")
            #         elif var[1] == "False":
            #             self.__camera.keep_image = False
            #             print("Saving images: Disabled")
            #
            #     elif var[0] == "start":
            #         self.__camera.start_acquisition()
            #         # trigger an image
            #         if not self.acquisition_check_and_set():
            #             print("Acquisition not started... Skipping trigger command!")
            #             continue
            #         self.__camera.make_image = True
            #         # wait until image has been made
            #         while self.__camera.make_image:
            #             pass
            #
            #     elif var[0] == "stop":
            #         self.__camera.stop_acquisition()
            #
            #     elif var[0] == "help":
            #         self.print_help()
            #
            #     elif var[0] == "pixelformat":
            #         if not self.acquisition_check_and_disable():
            #             continue
            #         self.change_pixelformat()
            #
            #     elif var[0] == "exit":
            #         break
            #     else:
            #         print(f"Unrecognized command: `{var[0]}`")
            #         self.print_help()
        finally:
            # make sure to always stop the acquisition_thread, otherwise
            # we'd hang, e.g. on KeyboardInterrupt
            self.__camera.killed = True
            self.acquisition_thread.join()

    def start_window(self):
        pass

    def on_image_received(self, image):
        pass

    def warning(self, message: str):
        print(f"Warning: {message}")

    def information(self, message: str):
        print(f"Info: {message}")
