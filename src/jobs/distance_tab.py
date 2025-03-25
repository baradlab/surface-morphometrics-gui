from magicgui import widgets
from morphometrics_config import IntraListEditor, InterDictEditor

class DistanceOrientationWidget(widgets.Container):
    """Widget for distance and orientation measurement settings"""
    
    def __init__(self):
        super().__init__(layout='vertical', labels=True)
        
        # Create header container
        header = widgets.Container(widgets=[
            widgets.Label(value='Distance and Orientation Measurements')
        ], layout='vertical')
        
        # Create settings container with minimal spacing
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(2)
        settings.native.layout().setContentsMargins(2, 2, 2, 2)
        
        # Create settings widgets
        self.min_dist = widgets.SpinBox(value=3, min=0, max=1000, label='Min Distance')
        self.max_dist = widgets.SpinBox(value=400, min=0, max=1000, label='Max Distance')
        self.tolerance = widgets.FloatSpinBox(value=0.1, min=0.0, max=1.0, step=0.01, label='Tolerance')
        self.verticality = widgets.CheckBox(value=True, label='Measure Verticality')
        self.relative_orientation = widgets.CheckBox(value=True, label='Measure Relative Orientation')
        
        # Create intra and inter measurement editors
        self.intra_editor = IntraListEditor()
        self.inter_editor = InterDictEditor()
        
        # Add settings to container
        settings.extend([
            self.min_dist,
            self.max_dist,
            self.tolerance,
            self.verticality,
            self.relative_orientation,
            widgets.Label(value='Intra Membrane Measurements:'),
            self.intra_editor,
            widgets.Label(value='Inter-membrane Measurements:'),
            self.inter_editor
        ])
        
        # Create submit button
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
