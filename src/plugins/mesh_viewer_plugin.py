from plugins.mesh_viewer import MeshViewer


class MeshViewerPlugin:
    def __init__(self, viewer, experiment_manager):
        self.viewer = viewer
        self.experiment_manager = experiment_manager
        self.widget = MeshViewer(viewer)

    @property
    def native(self):
        return self.widget.native if hasattr(self.widget, "native") else self.widget
