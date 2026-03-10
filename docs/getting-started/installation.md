# Installation

## Prerequisites

- Python 3.8 or higher
- [Conda](https://docs.conda.io/en/latest/) (Miniconda or Anaconda)
- Git

## Install the surface morphometrics pipeline

The GUI depends on the surface morphometrics pipeline scripts. Install the pipeline first:

```bash
git clone https://github.com/GrotjahnLab/surface_morphometrics.git
cd surface_morphometrics
conda env create -f environment.yml
conda activate morphometrics
cd ..
```

## Install the GUI

```bash
git clone https://github.com/baradlab/surface-morphometrics-gui.git
```

## Launch the GUI

With the `morphometrics` conda environment active:

```bash
cd surface-morphometrics-gui/src
python main.py
```

!!! tip
    Always activate the conda environment before launching the GUI:
    ```bash
    conda activate morphometrics
    ```

## Verify the installation

When the GUI opens, you should see the experiment manager panel on the right side. If you see any import errors, make sure you installed all dependencies from both the pipeline and GUI repositories.

<!-- IMAGE NEEDED: Screenshot of the GUI right after launching, showing the empty experiment manager panel on the right with all input fields (Work Directory, Experiment Name, Data Directory, Config Template, Cores) visible and the blank visualization area on the left -->

![Starting GUI](../images/startup_page.png)