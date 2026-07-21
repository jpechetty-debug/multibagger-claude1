import os
import glob

def fix_patch_injection(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    # Find the patch and remove it
    patch_idx = -1
    for i, line in enumerate(lines):
        if 'import modules.adapters.yf_patch' in line:
            patch_idx = i
            break
            
    if patch_idx == -1:
        return
        
    patch_line = lines.pop(patch_idx)
    
    # Find the last sys.path.insert or import sys / import os
    insert_idx = 0
    for i, line in enumerate(lines):
        if 'sys.path.insert' in line or 'sys.path.append' in line:
            insert_idx = i + 1
            
    if insert_idx == 0:
        # If no sys.path, just put it after standard imports if possible, or at index 0
        insert_idx = 0
        
    lines.insert(insert_idx, patch_line)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"Fixed: {filepath}")

entry_points = [
    "main.py",
    "sovereign_cli.py",
    "worker/celery_app.py"
]

for ep in entry_points:
    if os.path.exists(ep):
        fix_patch_injection(ep)

for script_dir in ["scripts/internal", "ops"]:
    for filepath in glob.glob(f"{script_dir}/*.py"):
        fix_patch_injection(filepath)
