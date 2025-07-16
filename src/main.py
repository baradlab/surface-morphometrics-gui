import napari
from magicgui import widgets
from qtpy.QtWidgets import QTabWidget
from qtpy import QtCore

from jobs.mesh_tab import MeshGenerationWidget
from jobs.pycurv_tab import PyCurvWidget
from jobs.distance_tab import DistanceOrientationWidget
from plugins.tomoslice_plugin import TomoslicePlugin
from plugins.custom_vedo_cutter import CustomVedoCutter
from experiment_manager import ExperimentManager


def main():
    try:
        # Create the viewer
        viewer = napari.Viewer()
        

        # Create widgets
        experiment_manager = ExperimentManager(viewer)
        mesh_widget = MeshGenerationWidget(experiment_manager)
        pycurv_widget = PyCurvWidget(experiment_manager=experiment_manager)
        distance_widget = DistanceOrientationWidget(experiment_manager)

        # Connect mesh generation completion signal to PyCurv file list refresh
        mesh_widget.mesh_generation_complete.connect(pycurv_widget._populate_vtp_file_list)
        print("Mesh generation complete signal connected to PyCurv file list refresh.")
        # Create tomoslice plugin
        tomoslice = TomoslicePlugin(viewer, experiment_manager)
        
        # Create vedo cutter directly - with full functionality (no hiding)
        vedo_cutter = CustomVedoCutter(viewer)

        # Add widget as dock widget under layer controls (left)
        dw_vedo = viewer.window.add_dock_widget(
            vedo_cutter,
            name='',
            area='left'
        )
        dw1 = viewer.window.add_dock_widget(
            experiment_manager,
            name='Experiment Manager',
            area='right'
        )
        dw2 = viewer.window.add_dock_widget(
            mesh_widget,
            name='Surface Mesh',
            area='right'
        )
        dw3 = viewer.window.add_dock_widget(
            pycurv_widget.native,
            name='Curvature',
            area='right'
        )
        dw4 = viewer.window.add_dock_widget(
            distance_widget.native,
            name='Distance',
            area='right'
        )
        
        # Set tab position to top
        viewer.window._qt_window.setTabPosition(QtCore.Qt.AllDockWidgetAreas, QTabWidget.North)
        
        # Tabify dock widgets
        viewer.window._qt_window.tabifyDockWidget(dw1, dw2)
        viewer.window._qt_window.tabifyDockWidget(dw2, dw3)
        viewer.window._qt_window.tabifyDockWidget(dw3, dw4)
        
        # Connect mesh generation completion signal to PyCurv file list refresh
        # (Connect after widgets are added to ensure they are fully initialized)
        mesh_widget.mesh_generation_complete.connect(pycurv_widget.on_mesh_generation_complete)
        
        napari.run()
        
    except Exception as e:
        print(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()