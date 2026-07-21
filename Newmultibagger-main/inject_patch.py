import os
import glob

def inject_patch_into_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Avoid double patching
    if 'import modules.adapters.yf_patch' in content:
        return

    # Find the first line that is not a shebang, not a docstring, and not empty
    lines = content.splitlines()
    insert_idx = 0
    in_docstring = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i == 0 and stripped.startswith('#!'):
            continue
        
        # Super simplified docstring check (might not cover all edges but good enough for top of file)
        if stripped.startswith('"""') or stripped.startswith("'''"):
            if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                continue # single line docstring
            in_docstring = not in_docstring
            continue
            
        if in_docstring or not stripped or stripped.startswith('#'):
            continue
            
        insert_idx = i
        break
        
    patch_line = "import modules.adapters.yf_patch  # noqa: F401"
    lines.insert(insert_idx, patch_line)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"Patched: {filepath}")

entry_points = [
    "main.py",
    "sovereign_cli.py",
    "worker/celery_app.py"
]

for ep in entry_points:
    if os.path.exists(ep):
        inject_patch_into_file(ep)

# Patch all scripts in scripts/internal and ops
for script_dir in ["scripts/internal", "ops"]:
    for filepath in glob.glob(f"{script_dir}/*.py"):
        inject_patch_into_file(filepath)

