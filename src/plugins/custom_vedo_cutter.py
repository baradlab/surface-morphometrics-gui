from napari_vedo_bridge._cutter_widget import VedoCutter
import threading

class CustomVedoCutter(VedoCutter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("CustomVedoCutter initialized!")
        
        self.setMinimumSize(420, 430)
        self.setMaximumSize(420, 430)

        self._hide_unwanted_tools()

    def _hide_unwanted_tools(self):
        
        def hide_buttons():
            for btn_name in [
                "pushButton_box_cutter",
                "pushButton_sphere_cutter",
                "pushButton_plane_cutter",
            ]:
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    btn.hide()
        hide_buttons()
        
        threading.Timer(0.5, hide_buttons).start()
        

