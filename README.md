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

## Installation Steps
1. Clone the repositories
```bash
git clone https://github.com/baradlab/surface_morphometrics.git
git clone https://github.com/baradlab/surface-morphometrics-gui.git
```
2. Go to the surface morphometrics directory
```
cd surface_morphometrics
```
3. Install conda environment
```
conda env create -f environment.yml
```
4. Activate the conda environment
```
conda activate morphometrics
```
5. Install additional dependencies
```
pip install -r pip_requirements.txt
```
6. exit the surface morphometrics directory and open the gui directory
```
cd surface-morphometrics-gui/src
```
7. Run the GUI
```
python main.py
```


## Features (Planned)
- [x] Interactive visualization of membrane segmentations
- [x] Configuration file editor
- [x] Tabs for running each step of the surface morphometrics pipeline
- [x] Interactive Color coding for segmentation classes

## License
This project is licensed under the MIT licence - see the LICESNSE file for details

## Acknowledgments
- OG [surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics) by Barad et al
