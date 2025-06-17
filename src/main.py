import napari
from magicgui import widgets
from qtpy.QtWidgets import QTabWidget
from qtpy import QtCore

from jobs.mesh_tab import MeshGenerationWidget
from jobs.pycurv_tab import PyCurvWidget
from jobs.distance_tab import DistanceOrientationWidget
from plugins.tomoslice_plugin import TomoslicePlugin
from experiment_manager import ExperimentManager

def main():
    try:
        # Create the viewer
        viewer = napari.Viewer()
        
        # Create widgets
        experiment_manager = ExperimentManager(viewer)
        mesh_widget = MeshGenerationWidget(experiment_manager)
        pycurv_widget = PyCurvWidget(experiment_manager=experiment_manager)
        distance_widget = DistanceOrientationWidget(viewer)
        # Create tomoslice plugin
        tomoslice = TomoslicePlugin(viewer, experiment_manager)
        
        # Add widgets as separate dock widgets
        dw1 = viewer.window.add_dock_widget(
            experiment_manager,
            name='Experiment',
            area='right'
        )
        dw2 = viewer.window.add_dock_widget(
            mesh_widget.native,
            name='Mesh',
            area='right'
        )
        dw3 = viewer.window.add_dock_widget(
            pycurv_widget.native,
            name='PyCurv',
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
        
        napari.run()
        
    except Exception as e:
        print(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()