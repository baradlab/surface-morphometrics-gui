from magicgui import widgets
from morphometrics_config import IntraListEditor, InterDictEditor

class DistanceOrientationWidget(widgets.Container):
    """Widget for distance and orientation measurement settings"""
    
    def __init__(self, viewer):
        super().__init__(layout='vertical', labels=True)
        self.viewer = viewer
        
        # Header container
        header = widgets.Container(widgets=[
            widgets.Label(value='<b>Distance and Orientation Measurements</b>')
        ], layout='vertical')
        
        # Settings container with reduced spacing
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(5)
        settings.native.layout().setContentsMargins(3, 3, 3, 3)
        
        # Settings widgets
        self.min_dist = widgets.SpinBox(value=3, min=0, max=1000, label='Min Distance')
        self.max_dist = widgets.SpinBox(value=400, min=0, max=1000, label='Max Distance')
        self.tolerance = widgets.FloatSpinBox(value=0.1, min=0.0, max=1.0, step=0.01, label='Tolerance')
        self.verticality = widgets.CheckBox(value=True, label='Measure Verticality')
        self.relative_orientation = widgets.CheckBox(value=True, label='Measure Relative Orientation')
        
        # Intra and Inter measurement editors
        self.intra_editor = IntraListEditor()
        self.inter_editor = InterDictEditor()
        
        # Add settings to container with spacing
        settings.extend([
            self.min_dist,
            self.max_dist,
            self.tolerance,
            self.verticality,
            self.relative_orientation,
            widgets.Label(value='<b>Intra Membrane Measurements:</b>'),
            self.intra_editor,
            widgets.Label(value='<b>Inter-membrane Measurements:</b>'),
            self.inter_editor
        ])
        
        # Submit button
        self.submit_btn = widgets.PushButton(text='Run Distance/Orientation Analysis')
        self.submit_btn.clicked.connect(self._run_job)
        
        # Add all widgets to layout
        self.extend([
            header,
            settings,
            self.submit_btn
        ])
        
            
    def _run_job(self):
        """Run distance/orientation analysis"""
        self.submit_btn.enabled = False
        try:
            # Get current values
            config = {
                'mindist': self.min_dist.value,
                'maxdist': self.max_dist.value,
                'tolerance': self.tolerance.value,
                'verticality': self.verticality.value,
                'relative_orientation': self.relative_orientation.value,
                'intra': self.intra_editor.get_values(),
                'inter': self.inter_editor.get_values()
            }
            # TODO: Implement analysis process using config
            print("Running analysis with config:", config)
        except Exception as e:
            print(f"Error starting job: {str(e)}")
        finally:
            self.submit_btn.enabled = True
