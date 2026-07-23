#!/usr/bin/env python3
import subprocess
import sqlite3
import pandas as pd
from pathlib import Path
import os

RUN_COUNT = int(os.environ.get("RUN_COUNT", "15"))
DB_PATH = Path("factory_history.db")
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

def compute_energy_cost(conn, run_id: int) -> float:
    """
    energy_cost = integral of (power_kw * price_eur_mwh / 1000) d(sim_time_hours)
                = Σ trapezoid(power_kw[i]*price[i]/1000, power_kw[i+1]*price[i+1]/1000) * dt_hours

    EnergyTelemetry rows are written once per telemetry frame (irregular
    cadence, same as the WS broadcast), so integration must use each row's
    own sim_time delta rather than assuming a fixed dt. Returns 0.0 if no
    rows exist for this run (e.g. runs predating this metric, or the PROSA
    arm before EnergyTelemetry was added).
    """
    try:
        e = pd.read_sql_query(
            "SELECT sim_time, energy_price_eur_mwh, compressor_power_kw "
            "FROM EnergyTelemetry WHERE run_id = ? ORDER BY sim_time",
            conn, params=(run_id,)
        )
    except Exception:
        return 0.0
    if len(e) < 2:
        return 0.0
    e["power_kw_cost_rate"] = e["compressor_power_kw"] * e["energy_price_eur_mwh"] / 1000.0  # EUR/hour
    dt_hours = e["sim_time"].diff().fillna(0.0) / 3600.0
    trapezoid = (e["power_kw_cost_rate"] + e["power_kw_cost_rate"].shift(1)) / 2.0 * dt_hours
    return float(trapezoid.fillna(0.0).sum())


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
        # Necessary Correction #5: the energy price triggers the ADACOR
        # transition but no cost metric was ever computed — only
        # throughput/tardiness were measured. This closes that gap using the
        # EnergyTelemetry table (see DatabaseArtifact.java / MainSimulator.java).
        energy_cost_eur = compute_energy_cost(conn, run_id)
        
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
                'defect_rate': defect_rate,
                'energy_cost_eur': energy_cost_eur
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
            'defect_rate': defect_rate,
            'energy_cost_eur': energy_cost_eur
        })
        
    conn.close()
    return pd.DataFrame(results)

def main():
    all_results = pd.DataFrame()

    env = os.environ.copy()
    env["RUN_COUNT"] = str(RUN_COUNT)
    env["TELEMETRY_HMAC_SECRET"] = "phase4_monte_carlo_secure_key_9912"

    original_jcm = JCM_TEMPLATE.read_text(encoding="utf-8")

    try:
        set_jcm_csv("price_series_spike_test.csv")

        print(f"=== Running PROSA Baseline ({RUN_COUNT} runs) ===")
        # ROOT CAUSE FIX (source-mutation experiment hack): previously this
        # rewrote src/agt/supervisor_agent.asl on disk and relied on a
        # `finally` block to restore it — fragile, and confounds source
        # control if the process is interrupted (this repo's checked-in copy
        # was in fact found sitting in the mutated state at review time).
        # The PROSA arm is now selected via a runtime env var that
        # RunManager.launchPhase4 reads and propagates to every simulator's
        # adacorEnabled flag; no source file is touched.
        env["ADACOR_ENABLED"] = "false"
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
        env["ADACOR_ENABLED"] = "true"
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
        JCM_TEMPLATE.write_text(original_jcm, encoding="utf-8")

if __name__ == "__main__":
    main()
