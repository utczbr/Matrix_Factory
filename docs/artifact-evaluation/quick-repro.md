# 5-Minute Quick Reproduction Guide (Artifact Evaluation)

This guide provides a single 5-minute automated reproduction procedure for peer reviewers to verify manuscript figures, tables, and empirical benchmark claims.

---

## 1-Click Automated Reproduction Script

Run the automated reproduction harness script from the repository root:

```bash
chmod +x run_manual.sh
./run_manual.sh
```

---

## Step-by-Step Manual Reproduction Commands

If you prefer executing steps individually:

### Step 1: Initialize Environment (30 seconds)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Run Station 3 & 4 Physics Calibration (Figure 4)

```bash
python3 physical_engine/scripts/calibrate_stamping_clamping.py
```
*Output:* Validates Cockcroft–Latham damage threshold $C_{\text{crit,NCL}} = 0.42$ and generates Figure 4 output plot.

### Step 3: Run PROSA vs. ADACOR Baseline Comparison (Table 2)

```bash
python3 experiments/run_prosa_vs_adacor.py
```
*Output:* Executes 10 comparative co-simulation runs under energy price spike profiles and outputs `analysis/prosa_vs_adacor_summary.csv`.

### Step 4: Run Statistical Significance Analysis (Section 5.1)

```bash
python3 experiments/analyze_results.py analysis/prosa_vs_adacor_summary.csv
```
*Output:* Evaluates Mann-Whitney U test ($p < 0.001$), Shapiro-Wilk normality, and 95% Confidence Intervals.
