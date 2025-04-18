from magicgui import widgets
from qtpy.QtWidgets import QProgressBar, QTextEdit
from qtpy.QtCore import QObject, Signal

class JobStatusWidget(widgets.Container):
    """Widget to show job status and output"""
    
    class Signals(QObject):
        status_changed = Signal(str)
        progress_changed = Signal(int)
    
    def __init__(self):
        super().__init__(layout='vertical')
        
        # Create signals object
        self.signals = self.Signals()
        
        # Create containers for Qt widgets
        progress_container = widgets.Container(layout='vertical')
        # Status display
        self.status_label = widgets.Label(value='Status: Not Started')
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_container.native.layout().addWidget(self.progress)
        self.extend([
            self.status_label,
            progress_container
        ])
        
        # Connect signals
        self.signals.status_changed.connect(self._update_status_safe)
        self.signals.progress_changed.connect(self._update_progress_safe)
        
    def _update_status_safe(self, status: str):
        """Thread-safe status update"""
        self.status_label.value = f"Status: {status}"

    def _update_progress_safe(self, value: int):
        """Thread-safe progress update"""
        self.progress.setValue(value)

    def update_status(self, status: str):
        """Update status text"""
        self.signals.status_changed.emit(status)

    def update_progress(self, value: int):
        """Update progress bar value"""
        self.signals.progress_changed.emit(value)

