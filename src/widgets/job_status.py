from magicgui import magicgui, widgets
from qtpy.QtWidgets import QProgressBar, QTextEdit
from qtpy.QtCore import Qt, QObject, Signal

class JobStatusWidget(widgets.Container):
    """Widget to show job status and output"""
    
    class Signals(QObject):
        status_changed = Signal(str)
        progress_changed = Signal(int)
        output_appended = Signal(str)
        output_cleared = Signal()
    
    def __init__(self):
        super().__init__(layout='vertical')
        
        # Create signals object
        self.signals = self.Signals()
        
        # Create containers for Qt widgets
        progress_container = widgets.Container(layout='vertical')
        output_container = widgets.Container(layout='vertical')
        
        # Status display
        self.status_label = widgets.Label(value='Status: Not Started')
        
        # Progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_container.native.layout().addWidget(self.progress)
        
        # Output display
        self.output_display = QTextEdit()
        self.output_display.setReadOnly(True)
        self.output_display.setMinimumHeight(200)
        output_container.native.layout().addWidget(self.output_display)
        
        # Add widgets to main container
        self.extend([
            self.status_label,
            progress_container,
            output_container
        ])
        
        # Connect signals
        self.signals.status_changed.connect(self._update_status_safe)
        self.signals.progress_changed.connect(self._update_progress_safe)
        self.signals.output_appended.connect(self._append_output_safe)
        self.signals.output_cleared.connect(self._clear_safe)
        
    def _update_status_safe(self, status: str):
        """Thread-safe status update"""
        self.status_label.value = f"Status: {status}"
        
    def _update_progress_safe(self, value: int):
        """Thread-safe progress update"""
        self.progress.setValue(value)
        
    def _append_output_safe(self, text: str):
        """Thread-safe output append"""
        self.output_display.append(text)
        scrollbar = self.output_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def _clear_safe(self):
        """Thread-safe clear"""
        self.output_display.clear()
        self.progress.setValue(0)
        self.status_label.value = 'Status: Not Started'
        
    def update_status(self, status: str):
        """Update status text"""
        self.signals.status_changed.emit(status)
        
    def update_progress(self, value: int):
        """Update progress bar value"""
        self.signals.progress_changed.emit(value)
        
    def append_output(self, text: str):
        """Append text to output display"""
        self.signals.output_appended.emit(text)
        
    def clear(self):
        """Clear all displays"""
        self.signals.output_cleared.emit()
