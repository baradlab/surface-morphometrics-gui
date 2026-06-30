# Installation

## Prerequisites

- Python 3.8 or higher
- [Conda](https://docs.conda.io/en/latest/) (Miniconda or Anaconda)
- Git

## If you already have morphometrics installed, but not the gui:

If you already have the `morphometrics` conda environment (the surface
morphometrics pipeline), installing the GUI is a single command into that
environment:

```bash
conda activate morphometrics
pip install git+https://github.com/baradlab/surface-morphometrics-gui.git
morphometrics gui
```

The pipeline environment already provides the heavy scientific stack (vtk, numpy,
libigl, …), so pip only adds the GUI's own dependencies (napari, magicgui, …).

## From scratch

Install the surface morphometrics pipeline with the `[gui]` extra, which pulls in
the GUI alongside the `morphometrics` CLI in one step:

```bash
git clone https://github.com/GrotjahnLab/surface_morphometrics.git
cd surface_morphometrics
conda env create -f environment.yml
conda activate morphometrics
pip install -e .[gui]            # installs the `morphometrics` CLI and the gui
```

For development, clone the GUI and install it editable: `pip install -e .` from
the GUI repo root.

## Launch the GUI

With the `morphometrics` conda environment active:

```bash
conda activate morphometrics
morphometrics gui
```

`surface-morphometrics-gui` is also available as a secondary, development-only
launcher (the GUI's own console script).

!!! tip
    Always activate the conda environment before launching the GUI:
    ```bash
    conda activate morphometrics
    ```

## Verify the installation

When the GUI opens, you should see the experiment manager panel on the right side. If you see any import errors, make sure you installed all dependencies from both the pipeline and GUI repositories.

<!-- IMAGE NEEDED: Screenshot of the GUI right after launching, showing the empty experiment manager panel on the right with all input fields (Work Directory, Experiment Name, Data Directory, Config Template, Cores) visible and the blank visualization area on the left -->

![Starting GUI](../images/startup_page.png)