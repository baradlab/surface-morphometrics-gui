import napari
from magicgui import widgets
from qtpy.QtWidgets import QTabWidget, QSizePolicy, QApplication
from qtpy import QtCore
import logging
import warnings

# Filter out VisPy/macOS specific warnings that are harmless
warnings.filterwarnings("ignore", message="Back buffer dpr of .* doesn't match .* contents scale of .*")

logging.basicConfig(level=logging.INFO)


def _patch_status_checker_stack_size():
    # On Apple Silicon (ARM64) the default QThread stack is ~544 KB.
    # napari's StatusChecker thread calls numpy.linalg.inv(), which dispatches
    # to OpenBLAS's dgetrf_parallel.  That routine allocates a frame far larger
    # than 544 KB on ARM64, triggering ___chkstk_darwin → SIGBUS ("bus error").
    # Increasing the stack to 8 MB avoids the overflow without changing behaviour.
    from napari._qt.threads.status_checker import StatusChecker
    from qtpy.QtCore import QThread

    _orig_start = StatusChecker.start

    def _start_with_large_stack(
        self, priority: QThread.Priority = QThread.Priority.InheritPriority
    ) -> None:
        self.setStackSize(8 * 1024 * 1024)  # 8 MB; Qt default is ~544 KB on macOS ARM
        _orig_start(self, priority)

    StatusChecker.start = _start_with_large_stack


_patch_status_checker_stack_size()

from .jobs.mesh_tab import MeshGenerationWidget
from .jobs.pycurv_tab import PyCurvWidget
from .jobs.distance_tab import DistanceOrientationWidget
from .jobs.thickness_tab import ThicknessWidget
from .plugins.tomoslice_plugin import TomoslicePlugin
from .plugins.mesh_viewer import MeshViewer
from .plugins.protein import ProteinLoaderPlugin
from .experiment_manager import ExperimentManager

def setup_responsive_layout(viewer):
    """Setup responsive layout behavior for the viewer"""
    # Get the main window
    main_window = viewer.window._qt_window
    
    # Set size policies for better resizing
    main_window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    # Enable dock widget features for better resizing
    main_window.setDockNestingEnabled(True)
    main_window.setTabPosition(QtCore.Qt.AllDockWidgetAreas, QTabWidget.North)
    
    # Set minimum size for the main window
    main_window.setMinimumSize(800, 600)

def main():
    try:
        # Create the viewer
        viewer = napari.Viewer()
        
        # Setup responsive layout
        setup_responsive_layout(viewer)
        
        # Create widgets
        experiment_manager = ExperimentManager(viewer)
        mesh_widget = MeshGenerationWidget(experiment_manager)
        pycurv_widget = PyCurvWidget(experiment_manager=experiment_manager)
        distance_widget = DistanceOrientationWidget(experiment_manager)
        thickness_widget = ThicknessWidget(experiment_manager)

        # (Mesh completion connection set after dock widgets are created below)
        # Create tomoslice plugin
        tomoslice = TomoslicePlugin(viewer, experiment_manager)
        
        
        # Create mesh viewer widget
        mesh_viewer = MeshViewer(viewer)
        

        # Setup and add dock widgets with proper sizing
        dw1 = viewer.window.add_dock_widget(experiment_manager, name='Experiment Manager', area='right')
        dw2 = viewer.window.add_dock_widget(mesh_widget, name='Surface Mesh', area='right')
        dw3 = viewer.window.add_dock_widget(pycurv_widget, name='Curvature', area='right')
        dw4 = viewer.window.add_dock_widget(distance_widget.native, name='Distance', area='right')
        dw5 = viewer.window.add_dock_widget(thickness_widget, name='Thickness', area='right')

        # Add Mesh Viewer to the right side, tabified with the other widgets
        dw_mesh = viewer.window.add_dock_widget(
            mesh_viewer,
            name='Mesh Viewer',
            area='right'
        )

        protein_loader = ProteinLoaderPlugin(viewer)
        dw_protein_loader = viewer.window.add_dock_widget(protein_loader.container.native, name='Protein Loader', area='right')

        # Tabify all right-side dock widgets
        viewer.window._qt_window.tabifyDockWidget(dw1, dw2)
        viewer.window._qt_window.tabifyDockWidget(dw2, dw3)
        viewer.window._qt_window.tabifyDockWidget(dw3, dw4)
        viewer.window._qt_window.tabifyDockWidget(dw4, dw5)
        viewer.window._qt_window.tabifyDockWidget(dw5, dw_mesh)
        viewer.window._qt_window.tabifyDockWidget(dw_mesh, dw_protein_loader)
        
        # Connect mesh generation completion signal to PyCurv file list refresh
        # (Connect after widgets are added to ensure they are fully initialized)
        mesh_widget.mesh_generation_complete.connect(pycurv_widget.on_mesh_generation_complete)

        # Auto-refresh Curvature list when its dock becomes visible (tab switched to it)
        dw3.visibilityChanged.connect(lambda visible: (
            QtCore.QTimer.singleShot(0, pycurv_widget._populate_vtp_file_list) if visible else None
        ))
        
        napari.run()
        
    except Exception as e:
        print(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()