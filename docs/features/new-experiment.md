## New Experiment

Set up and manage experiments from the GUI. This page explains what you need, when the action button enables, what happens when creating a new experiment, and how resuming works.

### What you provide
- **Work Directory**: Parent folder where all experiments live.
- **Experiment Name**: A new name to create, or select an existing one to resume.
- **Data Directory**: Folder containing your input data.
- **Config Template File**: A YAML template (from the main repository or your own).

### When the button enables
The "New Experiment" (or "Resume Experiment") button enables only when all of the following are set:
- **Work Directory**
- **Non-empty Experiment Name**
- **Config Template File** (.yml or .yaml)
- **Data Directory**

### Create a new experiment
1. Choose a **Work Directory**.
2. Enter a unique **Experiment Name**.
3. Select your **Data Directory**.
4. Pick a **Config Template File**. The template is read and the UI (including segmentation values, if present) is populated so you can review/edit before creation.
5. Click **New Experiment**.

**What happens under the hood**:

- A folder named after your Experiment Name is created inside the Work Directory.
- Your chosen template is copied into that folder as `<experiment_name>_config.yml`.
- The copied config is personalized with:
    
    - `data_dir`: your selected Data Directory
    - `work_dir`: the new experiment folder path
    - `exp_name`: your Experiment Name
    - `cores`: value from the Cores input
    - `segmentation_values`: values from the Segmentation section in the UI
- On success, a confirmation message is shown. If any step fails (e.g., missing paths or invalid YAML), an error dialog explains what went wrong.

### Resume an existing experiment
If you select a name that already exists inside the Work Directory (its folder contains a `*_config.yml` or `config.yml`):

- The button switches to **Resume Experiment**.
- The manager loads the experiment's config, prefills the UI (including segmentation values when present), and points fields to the existing locations.
- If the stored config lacks `config_template`, the manager treats the existing config file in the experiment folder as the template reference for the UI.

### Notes
- You can use a template from the main Surface Morphometrics repository or bring your own; either way, it's copied into the experiment folder and customized.
- Segmentation label–value pairs you see in the UI are written into the created config and reloaded when resuming.


