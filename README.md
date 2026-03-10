# Surface Morphometrics GUI

A graphical interface for analyzing and quantifying membrane ultrastructure in cryo-electron tomography data. Built on the [surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by Barad et al.

## Quick install

```bash
# Install the pipeline
git clone https://github.com/GrotjahnLab/surface_morphometrics.git
cd surface_morphometrics
conda env create -f environment.yml
conda activate morphometrics
pip install -r pip_requirements.txt
cd ..

# Install and launch the GUI
git clone https://github.com/baradlab/surface-morphometrics-gui.git
cd surface-morphometrics-gui/src
python main.py
```

## Documentation

Full documentation is available at the [project docs site](https://sitename.example), including:

- [Installation guide](https://sitename.example/getting-started/installation/)
- [Quick start walkthrough](https://sitename.example/getting-started/quickstart/)
- [User guide](https://sitename.example/guide/experiment-setup/)

## License

This project is licensed under the MIT License — see the LICENSE file for details.

## Acknowledgments

- [Surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by the Grotjahn Lab
