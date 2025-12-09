
import shutil
import time
from pathlib import Path
from qtpy.QtWidgets import QMessageBox

def check_and_archive_outputs(parent_widget, results_dir, config_path, targets='all', file_patterns=None, exclude_patterns=None):
    """
    Checks for existing output files and prompts the user to Overwrite, Archive, or Cancel.
    
    Args:
        parent_widget (QWidget): Parent widget for the QMessageBox.
        results_dir (Path or str): Directory to check for results.
        config_path (Path or str): Path to the config file to snapshot.
        targets (str): 'all' (legacy) or 'measurements' (legacy). Used if file_patterns is None.
        file_patterns (list): List of glob patterns to check/archive (e.g. ['*'] or ['*.csv', '*.curv']).
        exclude_patterns (list): List of glob patterns to EXCLUDE from checking/archiving (e.g. ['*AVV*']).
        
    Returns:
        bool: True if safe to proceed (Overwrite or Archived), False if Cancelled.
    """
    results_dir = Path(results_dir)
    if not results_dir.exists():
        return True
        
    # 1. Determine patterns to check
    if file_patterns is None:
        if targets == 'all':
            file_patterns = ['*']
        elif targets == 'measurements':
            file_patterns = ['*.csv', '*.curv']
        else:
            file_patterns = ['*']
            
    # 1. Identify files to check
    files_found = []
    
    # We check if the directory is effectively "populated" with what we care about
    for pattern in file_patterns:
        # iterdir() doesn't support glob directly, so we use glob() on the path
        for p in results_dir.glob(pattern):
            # Check exclusions
            if exclude_patterns:
                is_excluded = False
                for exc in exclude_patterns:
                    if p.match(exc):
                        is_excluded = True
                        break
                if is_excluded:
                    continue

            if p.is_file() and not p.name.startswith('.'):
                files_found.append(p)
            elif p.is_dir() and "archive_" not in p.name:
                 # If checking everything ('*'), directories count too unless excluded
                 if pattern == '*' and any(p.iterdir()):
                     files_found.append(p)
    
    if not files_found:
        return True
        
    # 2. Prompt User
    msg = QMessageBox(parent_widget)
    msg.setWindowTitle("Existing Results Detected")
    msg.setText("Result files were found in the output directory.")
    msg.setInformativeText(
        "Do you want to overwrite them, or archive them to a timestamped folder?\n\n"
        f"Found {len(files_found)} matching items.\n" 
        f"Patterns: {file_patterns}"
    )
    
    btn_overwrite = msg.addButton("Overwrite", QMessageBox.DestructiveRole) 
    btn_archive = msg.addButton("Archive", QMessageBox.ActionRole)
    btn_cancel = msg.addButton(QMessageBox.Cancel)
    
    msg.exec_()
    
    clicked = msg.clickedButton()
    
    if clicked == btn_cancel:
        print("User cancelled run due to existing files.")
        return False
        
    if clicked == btn_overwrite:
        print("User chose to Overwrite.")
        return True
        
    if clicked == btn_archive:
        # 3. Perform Archive
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        archive_dir = results_dir / f"archive_{timestamp}"
        archive_dir.mkdir(exist_ok=True)
        
        print(f"Archiving files to {archive_dir}...")
        
        # Move files
        count = 0
        items_to_move = []
        
        # Re-scan to catch everything safe to move matching patterns
        for pattern in file_patterns:
            for p in results_dir.glob(pattern):
                if p == archive_dir: continue 
                if p.is_dir() and "archive_" in p.name: continue
                
                # Check exclusions
                if exclude_patterns:
                    is_excluded = False
                    for exc in exclude_patterns:
                        if p.match(exc):
                            is_excluded = True
                            break
                    if is_excluded:
                        continue
                        
                # Unique items only
                if p not in items_to_move:
                    items_to_move.append(p)
        
        for p in items_to_move:
            if not p.exists(): continue
            try:
                shutil.move(str(p), str(archive_dir / p.name))
                count += 1
            except Exception as e:
                print(f"Failed to move {p.name}: {e}")
        
        # Copy Config Snapshot
        if config_path and Path(config_path).exists():
            try:
                shutil.copy2(str(config_path), str(archive_dir / "config_snapshot.yml"))
                print("Config snapshot saved.")
            except Exception as e:
                print(f"Failed to snapshot config: {e}")

        print(f"Archived {count} items.")
        return True

    return False
