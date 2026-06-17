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

The GUI drives the **packaged** surface morphometrics pipeline through its
`morphometrics` command-line interface, so it must be installed into the same
conda environment as the pipeline.

#### Already have the pipeline installed?

If you already have the `morphometrics` conda environment (the surface
morphometrics pipeline), installing the GUI is one command:

```bash
conda activate morphometrics
pip install git+https://github.com/baradlab/surface-morphometrics-gui.git
surface-morphometrics-gui      # launches the GUI
```

The pipeline environment already provides the heavy scientific stack (vtk, numpy,
libigl, …), so pip only adds the GUI's own layer (napari, magicgui, …).

#### From scratch

```bash
# 1. Install the surface morphometrics pipeline (packaging branch = installable CLI)
git clone https://github.com/GrotjahnLab/surface_morphometrics.git
cd surface_morphometrics
git checkout packaging
conda env create -f environment.yml
conda activate morphometrics
pip install -e .            # installs the `morphometrics` CLI into this env
morphometrics --help       # verify the CLI is on PATH
cd ..

# 2. Install the GUI into the same environment
pip install git+https://github.com/baradlab/surface-morphometrics-gui.git
```

For development, clone the GUI and install it editable instead:
`git clone … && cd surface-morphometrics-gui && pip install -e .`

### Launch

```bash
conda activate morphometrics
surface-morphometrics-gui
```

## Quick start

1. **Create an experiment** — Set your work directory, data directory, and select a config template
2. **Generate meshes** — Run mesh generation from segmentations in the Mesh Generation tab
3. **Curvature analysis** — Compute curvature measurements in the PyCurv tab
4. **Distance & orientation** — Measure inter/intra-membrane distances in the Distance tab
5. **Visualize** — View meshes colored by properties with the built-in 3D viewer

> **Requires the `morphometrics` CLI**: The GUI runs each pipeline step by invoking the installed `morphometrics` command (see Installation). If you see a "morphometrics CLI not found" error, activate the conda environment where you ran `pip install -e .` for the pipeline, then launch the GUI from that same environment.

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
