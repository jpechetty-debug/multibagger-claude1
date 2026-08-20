import subprocess

scripts = [
    "research/holdout_validation.py",
    "research/regime_validation.py",
    "research/explainability_audit.py",
    "research/feature_stability.py",
    "research/ablation_engine.py",
    "research/compounder_validation.py",
    "research/trust_score.py"
]

import os
env = os.environ.copy()
env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
for s in scripts:
    print(f"Running {s}...")
    subprocess.run(["python", s], env=env, check=True)
print("All validations completed.")
