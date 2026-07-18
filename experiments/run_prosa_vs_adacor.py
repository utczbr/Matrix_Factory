#!/usr/bin/env python3
import subprocess
import sqlite3
import pandas as pd
from pathlib import Path
import os
import sys

RUN_COUNT = int(os.environ.get("RUN_COUNT", "15"))
DB_PATH = Path("factory_history.db")
SUPERVISOR_ASL = Path("src/agt/supervisor_agent.asl")
JCM_TEMPLATE = Path("factory.jcm.template")

def set_jcm_csv(csv_name: str):
    import re
    content = JCM_TEMPLATE.read_text(encoding="utf-8")
    content = re.sub(
        r'artifact\s+energy_price\s*:\s*factory\.EnergyPriceArtifact\("[^"]+"\s*,',
        f'artifact energy_price    : factory.EnergyPriceArtifact("{csv_name}",',
        content
    )
    JCM_TEMPLATE.write_text(content, encoding="utf-8")

def disable_adacor_transition():
    content = SUPERVISOR_ASL.read_text(encoding="utf-8")
    content = content.replace("+energy_price_spike(Price)", "+disabled_energy_price_spike(Price)")
    SUPERVISOR_ASL.write_text(content, encoding="utf-8")

def extract_metrics(schema_name: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    orders = pd.read_sql_query("SELECT * FROM Orders", conn)
    
    # Try reading StationQuality if it exists
    try:
        quality = pd.read_sql_query("SELECT * FROM StationQuality", conn)
    except:
        quality = pd.DataFrame(columns=['run_id', 'defect'])
    
    results = []
    
    for run_id in range(RUN_COUNT):
        run_orders = orders[orders['run_id'] == run_id]
        run_quality = quality[quality['run_id'] == run_id]
        
        submitted = run_orders[run_orders['event_type'] == 'SUBMITTED']
        completed = run_orders[run_orders['event_type'] == 'COMPLETED']
        
        submitted_count = len(submitted)
        completed_count = len(completed)
        
        defect_rate = run_quality['defect'].mean() if len(run_quality) > 0 else 0
        
        merged = pd.merge(submitted, completed, on='order_id', suffixes=('_sub', '_comp'))
        
        if len(merged) == 0:
            results.append({
                'schema': schema_name,
                'run_id': run_id,
                'throughput': 0,
                'tardiness_mean': 0,
                'tardiness_max': 0,
                'tardiness_std': 0,
                'wip_mean': 0,
                'submitted_count': submitted_count,
                'completed_count': completed_count,
                'defect_rate': defect_rate
            })
            continue
            
        merged['cycle_time'] = merged['sim_time_comp'] - merged['sim_time_sub']
        
        max_time = run_orders['sim_time'].max()
        throughput = len(merged) / max_time if max_time > 0 else 0
        tardiness_mean = merged['cycle_time'].mean()
        tardiness_max = merged['cycle_time'].max()
        tardiness_std = merged['cycle_time'].std(ddof=0)
        wip_mean = merged['cycle_time'].sum() / max_time if max_time > 0 else 0
        
        results.append({
            'schema': schema_name,
            'run_id': run_id,
            'throughput': throughput,
            'tardiness_mean': tardiness_mean,
            'tardiness_max': tardiness_max,
            'tardiness_std': tardiness_std,
            'wip_mean': wip_mean,
            'submitted_count': submitted_count,
            'completed_count': completed_count,
            'defect_rate': defect_rate
        })
        
    conn.close()
    return pd.DataFrame(results)

def main():
    if not SUPERVISOR_ASL.exists():
        print(f"Error: {SUPERVISOR_ASL} not found.")
        sys.exit(1)
        
    original_asl = SUPERVISOR_ASL.read_text(encoding="utf-8")
    original_jcm = JCM_TEMPLATE.read_text(encoding="utf-8")
    all_results = pd.DataFrame()
    
    env = os.environ.copy()
    env["RUN_COUNT"] = str(RUN_COUNT)
    env["TELEMETRY_HMAC_SECRET"] = "phase4_monte_carlo_secure_key_9912"
    
    try:
        set_jcm_csv("price_series_spike_test.csv")
        
        print(f"=== Running PROSA Baseline ({RUN_COUNT} runs) ===")
        disable_adacor_transition()
        for suffix in ["", "-wal", "-shm"]:
            f = DB_PATH.with_name(DB_PATH.name + suffix)
            if f.exists():
                f.unlink()
        
        batch_size = 5
        for start_id in range(0, RUN_COUNT, batch_size):
            env_batch = env.copy()
            env_batch["RUN_START_ID"] = str(start_id)
            env_batch["RUN_COUNT"] = str(min(batch_size, RUN_COUNT - start_id))
            print(f"  [PROSA] Batch starting at {start_id} (count: {env_batch['RUN_COUNT']})")
            subprocess.run(["bash", "scripts/launch_phase4.sh"], env=env_batch, check=True)
        
        df_prosa = extract_metrics("PROSA")
        all_results = pd.concat([all_results, df_prosa], ignore_index=True)
        
        print(f"\n=== Running ADACOR ({RUN_COUNT} runs) ===")
        SUPERVISOR_ASL.write_text(original_asl, encoding="utf-8")
        for suffix in ["", "-wal", "-shm"]:
            f = DB_PATH.with_name(DB_PATH.name + suffix)
            if f.exists():
                f.unlink()
            
        for start_id in range(0, RUN_COUNT, batch_size):
            env_batch = env.copy()
            env_batch["RUN_START_ID"] = str(start_id)
            env_batch["RUN_COUNT"] = str(min(batch_size, RUN_COUNT - start_id))
            print(f"  [ADACOR] Batch starting at {start_id} (count: {env_batch['RUN_COUNT']})")
            subprocess.run(["bash", "scripts/launch_phase4.sh"], env=env_batch, check=True)
        
        df_adacor = extract_metrics("ADACOR")
        all_results = pd.concat([all_results, df_adacor], ignore_index=True)
        
        os.makedirs("analysis", exist_ok=True)
        all_results.to_csv("analysis/results.csv", index=False)
        print("\nExperiment finished. Results saved to analysis/results.csv")
        
    finally:
        SUPERVISOR_ASL.write_text(original_asl, encoding="utf-8")
        JCM_TEMPLATE.write_text(original_jcm, encoding="utf-8")

if __name__ == "__main__":
    main()
