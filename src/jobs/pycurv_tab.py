from magicgui import widgets

class PyCurvWidget(widgets.Container):
    """Widget for pycurv curvature measurement settings"""
    
    def __init__(self):
        super().__init__(layout='vertical', labels=True)
        
        # Create header container
        header = widgets.Container(widgets=[
            widgets.Label(value='Curvature Measurement Settings')
        ], layout='vertical')
        
        # Create settings container with minimal spacing
        settings = widgets.Container(layout='vertical', labels=True)
        settings.native.layout().setSpacing(2)
        settings.native.layout().setContentsMargins(2, 2, 2, 2)
        
        # Create settings widgets
        self.radius_hit = widgets.SpinBox(value=8, min=1, max=20, label='Radius Hit')
        self.min_component = widgets.SpinBox(value=30, min=1, max=1000, label='Min Component')
        self.exclude_borders = widgets.SpinBox(value=0, min=0, max=100, label='Exclude Borders')

        # Add settings to container
        settings.extend([
            self.radius_hit,
            self.min_component,
            self.exclude_borders,
        ])

        # Create submit button
        self.submit_btn = widgets.PushButton(text='Run Curvature Analysis')
        self.submit_btn.clicked.connect(self._run_job)
        
        # Add all widgets to layout
        self.extend([
            header,
            settings,
            self.submit_btn
        ])
            
    def _run_job(self):
        """Run curvature analysis"""
        self.submit_btn.enabled = False
        try:
            # TODO: Implement curvature analysis process
            pass
        except Exception as e:
            print(f"Error starting job: {str(e)}")
        finally:
            self.submit_btn.enabled = True
