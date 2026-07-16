import subprocess
import os
import shutil
import sqlite3
import pandas as pd
import scipy.stats as stats

def modify_template(remove_org):
    with open("factory.jcm.template", "r") as f:
        content = f.read()
    
    # Strip the target organisation out
    import re
    # We find the organisation block and remove it. The block starts with "organisation {remove_org} :" and ends with "    }"
    pattern = r"\s*organisation\s+" + remove_org + r"\s*:.*?\}\s*\n    \}"
    new_content = re.sub(pattern, "", content, flags=re.DOTALL)
    
    with open("factory.jcm.template.tmp", "w") as f:
        f.write(new_content)
    return "factory.jcm.template.tmp"

def run_experiment(schema):
    print(f"Running Monte Carlo for {schema}...")
    if os.path.exists("factory_history.db"):
        os.remove("factory_history.db")
    
    remove_org = "factory_adacor_org" if schema == "PROSA" else "factory_prosa_org"
    tmp_template = modify_template(remove_org)
    
    env = os.environ.copy()
    env["RUN_COUNT"] = "30"
    
    # In generate_factory_jcm.py, it reads args.template which defaults to factory.jcm.template.
    # We must modify generate_factory_jcm.py to accept template from env or pass it, but since it's hardcoded in launch_phase4.sh, 
    # let's just temporarily replace factory.jcm.template
    
    shutil.copy("factory.jcm.template", "factory.jcm.template.bak")
    shutil.move("factory.jcm.template.tmp", "factory.jcm.template")
    
    try:
        subprocess.run(["bash", "scripts/launch_phase4.sh"], env=env, check=True)
    finally:
        shutil.move("factory.jcm.template.bak", "factory.jcm.template")
    
    shutil.copy("factory_history.db", f"factory_history_{schema.lower()}.db")

if __name__ == "__main__":
    run_experiment("PROSA")
    run_experiment("ADACOR")
    print("Done! Data collected in factory_history_prosa.db and factory_history_adacor.db")
