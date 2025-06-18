from plugins.custom_vedo_cutter import CustomVedoCutter

from plugins.custom_vedo_cutter import CustomVedoCutter

class VedoBridgePlugin:
    def __init__(self, viewer, experiment_manager):
        self.viewer = viewer
        self.experiment_manager = experiment_manager
        self.widget = CustomVedoCutter(viewer)

    @property
    def native(self):
        return self.widget.native if hasattr(self.widget, "native") else self.widget