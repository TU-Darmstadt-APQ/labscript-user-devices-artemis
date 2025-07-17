from blacs.tab_base_classes import Worker
from labscript import LabscriptError
import h5py
from zprocess import rich_print
from user_devices.logger_config import logger


class CAENWorker(Worker):
    def init(self):
        pass
        
    def shutdown(self):
        pass

    def program_manual(self, front_panel_values): 
        return front_panel_values

    def check_remote_values(self):
        pass

    def transition_to_buffered(self, device_name, h5_file, initial_values, fresh):
        return

    def transition_to_manual(self):
        return True

    def abort_transition_to_buffered(self):
        return self.transition_to_manual()

    def abort_buffered(self):
        return self.abort_transition_to_buffered()
