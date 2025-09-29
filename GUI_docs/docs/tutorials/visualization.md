# Visualization Guide

This guide covers how to visualize results from your Surface Morphometrics analysis.

## Dataset Preview

When setting up a new experiment as described in the [Pipeline Guide](pipeline.md), one of the segmentations from your selected data directory is automatically displayed. This preview allows you to verify that you're working with the correct dataset before proceeding with the analysis.

![Segmentation Preview]()

## Editing Segmentation Values

On the right-hand side tab, you'll find a section to add or edit segmentation values. This is where you can input associated segmentation values with descriptive labels.

**Important Note:**
Once you select a config template, the GUI automatically populates the segmentation values based on the template's default settings. **Make sure to review and edit these values** to match your specific data requirements before proceeding with the analysis.

![Segmentation Values]()

## Visualizing Meshes

After running Step 4 (Surface Reconstruction) from the [Pipeline Guide](pipeline.md), you can visualize the generated meshes in 3D.

**Loading Meshes:**
- On the left-hand side, you'll see a highlighted section with an option to load meshes
- Pick the specific mesh you want to visualize from the available options

**3D Rendering Mode:**
- Once a mesh is loaded, locate the **"n display"** button highlighted in the lower left corner
- Click this button to enter 3D rendering mode
- The volume will be displayed in full 3D view
- Click and drag to rotate the 3D view around the mesh

## Visualizing 3D Mapping of Quantification

After the quantification step in the pipeline, you can visualize the 3D mapping of your analysis results.

**Loading Quantified Meshes:**
- Follow the same steps as above to load the appropriate surface meshes file
- The file will contain the quantification results from your analysis
- Once loaded, the mesh will be rendered in 3D view

**Property Visualization:**
- Use the **dropdown menu** to select which property values you want to visualize
- Different morphometric measures (curvature, distance, etc.) can be displayed as color maps on the 3D surface
- Use the **slider** in the same section to adjust contrast values

## Loading Structures onto Meshes

The **Protein Loader** tab (highlighted on the right) provides tools to load and position structural data onto your ribosome meshes.

**Loading Files:**
- **Load MRC File**: Load the structure file itself (the protein structure)
- **Load STAR File**: Load the file containing location coordinates and orientation information for the structures

**Coordinate Extraction:**
- Select the specific tomogram layer on the left side panel
- Press **"Extract Coordinates"** to get information about the number of structures associated with the selected tomogram

**Visualizing Structures:**
- Use the **"Show Structure"** button to display copies of the structure
- Structures will be positioned with the correct orientation based on the coordinate data
- This allows you to see how proteins are positioned relative to your surfaces








