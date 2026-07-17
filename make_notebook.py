import nbformat as nbf

nb = nbf.v4.new_notebook()
text = """\
# PROSA vs. ADACOR Analysis
This notebook analyzes the results of 30 Monte Carlo replications of the Matrix Factory Twin under the `price_series_spike_test.csv` load. We compare the PROSA baseline to the ADACOR adaptive schema.
"""
nb['cells'] = [nbf.v4.new_markdown_cell(text)]

code1 = """\
import pandas as pd
import numpy as np
import scipy.stats as stats
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
df = pd.read_csv('results.csv')
display(df.head())
"""
nb['cells'].append(nbf.v4.new_code_cell(code1))

code2 = """\
# Descriptive Statistics
grouped = df.groupby('schema').agg({
    'throughput': ['mean', 'std', 'median'],
    'tardiness_mean': ['mean', 'std'],
    'wip_mean': ['mean', 'std']
})
display(grouped)
"""
nb['cells'].append(nbf.v4.new_code_cell(code2))

code3 = """\
# Normality Test (Shapiro-Wilk) on Throughput
prosa_throughput = df[df['schema'] == 'PROSA']['throughput']
adacor_throughput = df[df['schema'] == 'ADACOR']['throughput']

_, p_prosa = stats.shapiro(prosa_throughput)
_, p_adacor = stats.shapiro(adacor_throughput)

print(f"Shapiro-Wilk p-value (PROSA): {p_prosa:.4f}")
print(f"Shapiro-Wilk p-value (ADACOR): {p_adacor:.4f}")

normal = p_prosa > 0.05 and p_adacor > 0.05
print(f"Are both normally distributed (alpha=0.05)? {'Yes' if normal else 'No'}")
"""
nb['cells'].append(nbf.v4.new_code_cell(code3))

code4 = """\
# Significance Test
if normal:
    print("Using Welch's t-test")
    stat, p_val = stats.ttest_ind(prosa_throughput, adacor_throughput, equal_var=False)
else:
    print("Using Mann-Whitney U test")
    stat, p_val = stats.mannwhitneyu(prosa_throughput, adacor_throughput)

print(f"Test statistic: {stat:.4f}")
print(f"p-value: {p_val:.4e}")
if p_val < 0.05:
    print("Result: Statistically significant difference in throughput.")
else:
    print("Result: No statistically significant difference in throughput.")
"""
nb['cells'].append(nbf.v4.new_code_cell(code4))

code5 = """\
# Visualization
plt.figure(figsize=(10, 6))
sns.boxplot(x='schema', y='throughput', data=df)
plt.title('Throughput Comparison: PROSA vs ADACOR')
plt.ylabel('Throughput (Orders / SimTime)')
plt.show()
"""
nb['cells'].append(nbf.v4.new_code_cell(code5))

nbf.write(nb, 'analysis/prosa_vs_adacor.ipynb')
print("Notebook generated.")
