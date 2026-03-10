# Surface Morphometrics GUI

A graphical interface for analyzing and quantifying membrane ultrastructure in cryo-electron tomography data. Built on the [surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by Barad et al.

![GUI Screenshot](docs/images/3.png)

## What it does

Surface Morphometrics GUI lets you run the full surface morphometrics pipeline without touching the command line. Load your cryo-ET segmentations, generate surface meshes, measure curvature and distances, and visualize results — all from one interface.

| Component | What it does |
|-----------|--------------|
| **Mesh Generation** | Converts voxel segmentations into surface meshes using screened Poisson reconstruction |
| **PyCurv** | Computes curvature measurements using a vector voting framework |
| **Distance & Orientation** | Measures distances and relative orientations between surfaces |
| **3D Visualization** | Interactive rendering of surfaces with property colormaps, ambient occlusion, and protein loading |

## Installation

### Prerequisites

- Python 3.8+
- [Conda](https://docs.conda.io/en/latest/) (Miniconda or Anaconda)
- Git

### Install the pipeline and GUI

```bash
# Install the surface morphometrics pipeline
git clone https://github.com/GrotjahnLab/surface_morphometrics.git
cd surface_morphometrics
conda env create -f environment.yml
conda activate morphometrics
cd ..

# Clone the GUI
git clone https://github.com/baradlab/surface-morphometrics-gui.git
```

### Launch

```bash
conda activate morphometrics
cd surface-morphometrics-gui/src
python main.py
```

## Quick start

1. **Create an experiment** — Set your work directory, data directory, and select a config template
2. **Generate meshes** — Run mesh generation from segmentations in the Mesh Generation tab
3. **Curvature analysis** — Compute curvature measurements in the PyCurv tab
4. **Distance & orientation** — Measure inter/intra-membrane distances in the Distance tab
5. **Visualize** — View meshes colored by properties with the built-in 3D viewer

> **Config template location matters**: Keep your config template inside the `surface_morphometrics` directory. The GUI detects analysis scripts based on the template's location.

## Documentation

Full documentation: [baradlab.github.io/surface-morphometrics-gui](https://baradlab.github.io/surface-morphometrics-gui/)

- [Installation guide](https://baradlab.github.io/surface-morphometrics-gui/getting-started/installation/)
- [Quick start walkthrough](https://baradlab.github.io/surface-morphometrics-gui/getting-started/quickstart/)
- [User guide](https://baradlab.github.io/surface-morphometrics-gui/guide/experiment-setup/)

## License

This project is licensed under the MIT License — see the LICENSE file for details.

## Acknowledgments

- [Surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by the Grotjahn Lab
- Barad et al. (2023) — Quantitative analysis of membrane ultrastructure using cryo-ET surface morphometrics
