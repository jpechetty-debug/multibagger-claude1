import subprocess
import json

ux = ""
seo = ""

try:
    ux = subprocess.check_output(['python', '.agent/skills/frontend-design/scripts/ux_audit.py', 'Newmultibagger-main/web-ui', '--json'], text=True)
except subprocess.CalledProcessError as e:
    ux = e.output

try:
    seo = subprocess.check_output(['python', '.agent/skills/seo-fundamentals/scripts/seo_checker.py', 'Newmultibagger-main/web-ui'], text=True)
except subprocess.CalledProcessError as e:
    seo = e.output

with open('audit_results.txt', 'w', encoding='utf-8') as f:
    f.write("UX:\n" + ux + "\nSEO:\n" + seo)
