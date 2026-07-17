import pandas as pd
import scipy.stats as stats

df = pd.read_csv("analysis/results.csv")
prosa = df[df['schema'] == 'PROSA']
adacor = df[df['schema'] == 'ADACOR']

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
