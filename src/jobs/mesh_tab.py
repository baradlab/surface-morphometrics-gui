from magicgui import widgets

class MeshGenerationWidget(widgets.Container):
    """Widget for surface mesh generation settings"""
    
    def __init__(self):
        super().__init__(layout='vertical', labels=True)
        
        # Create header container
        header = widgets.Container(widgets=[
            widgets.Label(value='<b>Surface Generation Settings</b>')
        ], layout='vertical')
        
        # Create settings container
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)
        
        # Create settings widgets
        self.angstroms = widgets.CheckBox(value=False, label='Angstrom Scaling')
        self.simplify = widgets.CheckBox(value=True, label='Simplify Surface')
        self.max_triangles = widgets.SpinBox(value=100000, min=1000, max=1000000, label='Max Triangles')
        self.extrapolation_distance = widgets.FloatSpinBox(value=1.5, min=0.1, max=10.0, step=0.1, label='Extrapolation Distance')
        self.octree_depth = widgets.SpinBox(value=9, min=1, max=15, label='Octree Depth')
        self.point_weight = widgets.FloatSpinBox(value=0.7, min=0.1, max=1.0, step=0.1, label='Point Weight')
        self.neighbor_count = widgets.SpinBox(value=300, min=10, max=1000, label='Neighbor Count')
        self.smoothing_iterations = widgets.SpinBox(value=1, min=0, max=10, label='Smoothing Iterations')

        # Add settings to container
        settings.extend([
            self.angstroms,
            self.simplify,
            self.max_triangles,
            self.extrapolation_distance,
            self.octree_depth,
            self.point_weight,
            self.neighbor_count,
            self.smoothing_iterations,
        ])

        # Create submit button
        self.submit_btn = widgets.PushButton(text='Generate Surface Mesh')
        self.submit_btn.clicked.connect(self._run_job)
        
        # Add all widgets to layout
        self.extend([
            header,
            settings,
            self.submit_btn
        ])
            
    def _run_job(self):
        """Run surface mesh generation"""
        self.submit_btn.enabled = False
        try:
            # TODO: Implement mesh generation process
            pass
        except Exception as e:
            print(f"Error starting job: {str(e)}")
        finally:
            self.submit_btn.enabled = True