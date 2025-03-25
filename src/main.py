import napari
from magicgui import magicgui, widgets
from qtpy.QtWidgets import QScrollArea, QTabWidget, QVBoxLayout, QWidget

from jobs.mesh_tab import MeshGenerationWidget
from jobs.pycurv_tab import PyCurvWidget
from jobs.distance_tab import DistanceOrientationWidget
from plugins.tomoslice_plugin import TomoslicePlugin
from experiment_manager import ExperimentManager

def main():
    try:
        # Create the viewer
        viewer = napari.Viewer()
        
        # Create main widget and layout for tabs
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # Create tab widget
        tabs = QTabWidget()
        
        # Create widgets
        experiment_manager = ExperimentManager(viewer)
        mesh_widget = MeshGenerationWidget()
        pycurv_widget = PyCurvWidget()
        distance_widget = DistanceOrientationWidget()
        
        # Create tomoslice plugin
        tomoslice = TomoslicePlugin(viewer, experiment_manager)
        
        # Create scroll areas
        experiment_scroll = QScrollArea()
        experiment_scroll.setWidget(experiment_manager)
        experiment_scroll.setWidgetResizable(True)
        
        mesh_scroll = QScrollArea()
        mesh_scroll.setWidget(mesh_widget.native)
        mesh_scroll.setWidgetResizable(True)
        
        pycurv_scroll = QScrollArea()
        pycurv_scroll.setWidget(pycurv_widget.native)
        pycurv_scroll.setWidgetResizable(True)
        
        distance_scroll = QScrollArea()
        distance_scroll.setWidget(distance_widget.native)
        distance_scroll.setWidgetResizable(True)
        
        # Add tabs
        tabs.addTab(experiment_scroll, "Experiment")
        tabs.addTab(mesh_scroll, "Surface Generation")
        tabs.addTab(pycurv_scroll, "Curvature Analysis")
        tabs.addTab(distance_scroll, "Distance/Orientation")
        
        # Add tabs to layout
        layout.addWidget(tabs)
        
        # Add main widget as dock widget
        viewer.window.add_dock_widget(
            main_widget,
            name='Surface Morphometrics',
            area='right'
        )
        
        napari.run()
        
    except Exception as e:
        print(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()