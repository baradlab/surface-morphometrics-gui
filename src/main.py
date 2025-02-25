import napari
from magicgui import magicgui, widgets
from qtpy.QtWidgets import QScrollArea, QTabWidget, QVBoxLayout, QWidget

from morphometrics_config import ConfigEditor
from jobs.seg_to_mesh import SegToMeshSubmissionWidget
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
        config_editor = ConfigEditor()
        job_widget = SegToMeshSubmissionWidget(config_editor)
        
        # Create tomoslice plugin
        tomoslice = TomoslicePlugin(viewer, config_editor)
        
        # Create scroll areas
        experiment_scroll = QScrollArea()
        experiment_scroll.setWidget(experiment_manager)
        experiment_scroll.setWidgetResizable(True)
        
        config_scroll = QScrollArea()
        config_scroll.setWidget(config_editor.native)
        config_scroll.setWidgetResizable(True)
        
        job_scroll = QScrollArea()
        job_scroll.setWidget(job_widget.native)
        job_scroll.setWidgetResizable(True)
        
        # Add tabs
        tabs.addTab(experiment_scroll, "Experiment")
        tabs.addTab(config_scroll, "Configuration")
        tabs.addTab(job_scroll, "Segmentation to Mesh")
        
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