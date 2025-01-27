# Surface Morphometrics GUI
A graphical user interface for analyzing and quantifying membrane ultrastructure in cryo-electron tomography data. This tool provides and accessible interface to the surface morphometrics pipeline developed by Barad et al. (2023).

## Overview
The Surface Morphometrics GUI enables researchers to: 

- Load and visualize 3D membrane segmentations from cryo-ET data
- Generate high-quality surface mesh reconstructions using screened Poisson reconstruction
- Analyze membrane features including:
  - Inter and Intra membrane spacing
  - Membrane curvature
  - Relative orientation between membrane surfaces
  - Statistical analysis of membrane features across multiple samples

## Prerequisites
- [ ] Install the surface morphometrics pipeline [here](https://github.com/GrotjahnLab/surface_morphometrics)
- Python 3.8 or higher

## Dependencies
- [ ] napari
- [ ] napari-tomoslice

## Installation Steps
1. Clone the repository
```bash
git clone https://github.com/baradlab/surface_morphometrics.git
cd surface-morphometrics-gui
```
2. Activate the conda environment that was created during the installation of the surface morphometrics pipeline
```bash
conda activate morphometrics
```
3. Install dependencies
```bash
pip install -r requirements.txt
```
4. Run the GUI
1. Make sure you are in the root directory of the repository and virtual environment is activated
2. Run the main script
```bash
python main.py
```

## Features (Planned)
- [ ] Interactive visualization of membrane segmentations
- [ ] Configuration file editor
- [ ] Tabs for running each step of the surface morphometrics pipeline
- [ ] Interactive Color coding for segmentation classes

## License
This project is licensed under the MIT licence - see the LICESNSE file for details

## Acknowledgments
- OG [surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by Barad et al
