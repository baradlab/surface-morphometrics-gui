## Resume Experiment

Pick up where you left off. This page explains how resume is detected, what state is loaded, and how tabs reflect progress.

### How resume is triggered
- Select a Work Directory that contains your experiment folder.
- Choose an existing Experiment Name (folder with `*_config.yml` or `config.yml`).
- The action button switches to **Resume Experiment**; click it to load the config.

### What gets loaded
- Loads `<exp_dir>/*_config.yml`, or falls back to `<exp_dir>/config.yml`.
- Applies to the UI when present: `data_dir`, `config_template` (or uses the loaded config path), `cores`, `segmentation_values`.
- Emits a global `config_loaded` event so job tabs refresh.

### How tabs update on resume
- **Mesh Generation**
    - Reads mesh settings from `surface_generation` if present.
    - Infers completion by checking `<exp_dir>/results` for `*.ply`, `*.surface.vtp`, or `*.xyz`.
    - Status: Completed (files found) or Not Started (none).
- **PyCurv (Curvature)**
    - Status set to Ready; progress 0.
    - Re-populates VTP list by searching `<exp_dir>`, then `meshes`, then `results` for `*.surface.vtp`/`*.SURFACE.VTP`.
- **Distance/Orientation**
    - Status set to Ready; progress 0.
    - Loads `distance_and_orientation_measurements` settings if present.


