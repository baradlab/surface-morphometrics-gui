## Resume Experiment

Pick up where you left off. This page explains how resume is detected, what state is loaded, and how tabs reflect progress.

### How resume is triggered
- Select a Work Directory that contains your experiment folder.
- Choose an existing Experiment Name (folder with `*_config.yml` or `config.yml`).
- The action button switches to **Resume Experiment**; click it to load the config.

### What gets loaded
- Loads `<exp_dir>/*_config.yml`, or falls back to `<exp_dir>/config.yml`.
- Applies to the UI when present: `data_dir`, `config_template` (or uses the loaded config path), `cores`, `segmentation_values`, `script_location`.
- Emits a global `config_loaded` event so job tabs refresh.

### Rerunning Jobs
When you run a job (Mesh Generation, PyCurv, Distance) on an experiment that already has results:
1. The system detects existing files (e.g., `*.ply`, `*.csv` in the results folder).
2. A popup asks: **"Result files were found... Overwrite or Archive?"**
    - **Overwrite**: Deletes old files matching the job's key extensions and runs the new job.
    - **Archive**: Moves old files to a timestamped folder (e.g., `results/archive_20241208_120000/`) and saves a snapshot of the current config there. Then runs the new job.
    - **Cancel**: Aborts the run.
- This ensures you never accidentally lose data when re-trying parameters.

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


