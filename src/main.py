import napari
from magicgui import widgets
from qtpy.QtWidgets import QTabWidget
from qtpy import QtCore

from jobs.mesh_tab import MeshGenerationWidget
from jobs.pycurv_tab import PyCurvWidget
from jobs.distance_tab import DistanceOrientationWidget
from plugins.tomoslice_plugin import TomoslicePlugin
from plugins.custom_vedo_cutter import CustomVedoCutter
from plugins.protein import ProteinLoaderPlugin
#from plugins.camera_spline_plugin import CameraSplinePlugin
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
        
        # Create protein localization plugin
        #protein_localization = ProteinLocalizationPlugin(viewer, experiment_manager)
        
        # Create vedo cutter directly - with full functionality (no hiding)
        vedo_cutter = CustomVedoCutter(viewer)
        
        # Add a method to safely set light_dir if shading_filter exists
        def safe_set_light_dir(visual, light_dir):
            """Safely set the light_dir if shading_filter exists (prevents napari-threedee AttributeError)."""
            if hasattr(visual, 'node') and hasattr(visual.node, 'shading_filter') and visual.node.shading_filter is not None:
                visual.node.shading_filter.light_dir = light_dir
        # Usage: safe_set_light_dir(visual, light_dir)

        # Add a method to fix shading filter issues for all surface layers
        def fix_all_surface_shading():
            """Fix shading filter issues for all surface layers to prevent napari-threedee errors."""
            for layer in viewer.layers:
                if hasattr(layer, '_node') and layer._node is not None:
                    try:
                        # Force refresh to ensure proper initialization
                        layer.refresh()
                    except Exception:
                        pass
        
        # Connect layer insertion events to fix shading issues
        viewer.layers.events.inserted.connect(lambda event: fix_all_surface_shading())

        # Add CameraSplinePlugin as a dock widget (left)
        #camera_spline_plugin = CameraSplinePlugin(viewer)
        #dw_camera_spline = viewer.window.add_dock_widget(
       #     camera_spline_plugin,
       #     name='Camera Spline',
       #     area='left'
       # )

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
        protein_loader = ProteinLoaderPlugin(viewer)
        dw_protein_loader = viewer.window.add_dock_widget(
            protein_loader.container.native,
            name='Protein Loader',
            area='right'
        )
        
        # Set tab position to top
        viewer.window._qt_window.setTabPosition(QtCore.Qt.AllDockWidgetAreas, QTabWidget.North)
        
        # Tabify dock widgets
        viewer.window._qt_window.tabifyDockWidget(dw1, dw2)
        viewer.window._qt_window.tabifyDockWidget(dw2, dw3)
        viewer.window._qt_window.tabifyDockWidget(dw3, dw4)
        viewer.window._qt_window.tabifyDockWidget(dw1, dw_protein_loader)
        
        # Connect mesh generation completion signal to PyCurv file list refresh
        # (Connect after widgets are added to ensure they are fully initialized)
        mesh_widget.mesh_generation_complete.connect(pycurv_widget.on_mesh_generation_complete)
        
        napari.run()
        
    except Exception as e:
        print(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()