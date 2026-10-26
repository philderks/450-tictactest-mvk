# Renders branch-coverage history (CSV with Datum,Commit,Coverage) as a PNG line chart.
# Usage: coverage-chart.py <history.csv> <chart.png>
import csv
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

GATE = 90

history_csv, chart_png = sys.argv[1], sys.argv[2]

with open(history_csv, newline="") as f:
    rows = list(csv.DictReader(f))

coverage = [float(row["Coverage"]) for row in rows]
labels = [f"{row['Datum']}\n{row['Commit']}" for row in rows]
x = list(range(len(rows)))
step = max(1, len(rows) // 10)

fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(x, coverage, marker="o", color="#2a78d6")
ax.axhline(GATE, color="#d03b3b", linestyle="--", linewidth=1, label=f"Branch-Gate ({GATE} %)")
ax.annotate(f"{coverage[-1]:.1f} %", (x[-1], coverage[-1]), textcoords="offset points", xytext=(0, 8), ha="center")

ax.set_title("Branch-Coverage-Verlauf auf main")
ax.set_ylabel("Branch Coverage (%)")
ax.set_ylim(max(0, min(min(coverage), GATE) // 5 * 5 - 5), 101)
ax.set_xticks(x[::step], labels[::step], fontsize=8)
ax.grid(alpha=0.3)
ax.legend(loc="lower left")

fig.tight_layout()
fig.savefig(chart_png, dpi=100)
