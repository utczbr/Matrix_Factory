import sqlite3
import pandas as pd
import scipy.stats as stats

def get_metrics(db_path):
    conn = sqlite3.connect(db_path)
    
    # Throughput: completed orders per run_id
    query = """
    SELECT run_id, count(order_id) as throughput 
    FROM Orders 
    WHERE event_type = 'COMPLETED' 
    GROUP BY run_id
    """
    throughput_df = pd.read_sql_query(query, conn)
    
    # If a run completed 0 orders, it might not be in the result.
    # Assuming run_ids 0 to 29
    all_runs = pd.DataFrame({'run_id': range(30)})
    throughput_df = pd.merge(all_runs, throughput_df, on='run_id', how='left').fillna(0)
    
    conn.close()
    return throughput_df

prosa = get_metrics("factory_history_prosa.db")
adacor = get_metrics("factory_history_adacor.db")

prosa['schema'] = 'PROSA'
adacor['schema'] = 'ADACOR'

df = pd.concat([prosa, adacor])
df.to_csv("results.csv", index=False)

# Test for normality
prosa_tp = prosa['throughput'].values
adacor_tp = adacor['throughput'].values

stat_p, p_p = stats.shapiro(prosa_tp)
stat_a, p_a = stats.shapiro(adacor_tp)

print(f"Shapiro-Wilk PROSA: p-value = {p_p:.4f}")
print(f"Shapiro-Wilk ADACOR: p-value = {p_a:.4f}")

if p_p > 0.05 and p_a > 0.05:
    print("Normal distribution assumed. Using Welch's t-test.")
    stat, p = stats.ttest_ind(prosa_tp, adacor_tp, equal_var=False)
else:
    print("Non-normal distribution. Using Mann-Whitney U test.")
    stat, p = stats.mannwhitneyu(prosa_tp, adacor_tp)

print(f"Test statistic: {stat:.4f}, p-value: {p:.4e}")
print(f"Mean Throughput - PROSA: {prosa_tp.mean():.2f}, ADACOR: {adacor_tp.mean():.2f}")
