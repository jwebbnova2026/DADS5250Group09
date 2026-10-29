"""Run the whole pipeline end to end and write every output to outputs/.

Usage (repository root, virtual environment active):

    python scripts/run_all.py              # offline: replays recorded model answers (no key, no network)
    python scripts/run_all.py --mode live  # fresh model calls for every input; appends the answers

Steps: forecast -> workloads -> frozen plan -> score plan and baseline on all
four scenarios (with full reconciliation checks) -> intake evaluation ->
neighborhood equity -> figures -> run manifest. The notebook demo.ipynb runs
the same steps with commentary.
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")  # draw figures to files; no window needed
import matplotlib.pyplot as plt
import pandas as pd

from boston311 import config, equity, evaluate, forecast, manifest, staffing, workload
from boston311.agent import IntakeAssistant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=config.MODES, default="offline")
    args = parser.parse_args()
    out = config.OUTPUTS_DIR
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    written = []

    def save(df: pd.DataFrame, name: str) -> None:
        path = out / name
        df.to_csv(path, index=False, lineterminator="\n")
        written.append(path)

    # 1. Forecast.
    fc = forecast.forecast_2025()
    save(fc.pivot(index="month", columns="department", values="forecast")[list(config.DEPT_CODES)].reset_index(), "forecast_2025.csv")
    save(forecast.backtest(), "forecast_backtest.csv")

    # 2-3. Workloads, frozen plan, scoring.
    wl = workload.build_all_workloads(fc)
    plan = staffing.make_plan(wl["planning"])
    base = staffing.baseline_plan()
    save(plan.to_frame(), "staffing_plan.csv")
    (out / "staffing_plan_log.txt").write_text(
        "\n".join(f"{d}: {line}" for d, dp in plan.departments.items() for line in dp.log) + "\n", encoding="utf-8", newline="\n"
    )
    written.append(out / "staffing_plan_log.txt")
    all_rows, summaries = [], []
    for p in (plan, base):
        for scenario in config.SCENARIOS:
            rows, year_ends = staffing.score_plan(p, wl[scenario], scenario)
            failures = staffing.reconciliation_failures(rows, p, wl[scenario])
            if failures:
                raise SystemExit(f"Reconciliation failed for {p.name}/{scenario}: {failures[:5]}")
            all_rows.append(rows)
            summaries.append(staffing.summarize(rows, year_ends))
    rows = pd.concat(all_rows, ignore_index=True)
    summary = pd.concat(summaries, ignore_index=True)
    save(rows, "staffing_rows.csv")
    save(summary, "scenario_summary.csv")
    # Evidence for the Parks seasonal target (re-plans once per target; ~20 s).
    save(staffing.seasonal_frontier(wl), "parks_seasonal_frontier.csv")

    # 4. Intake evaluation.
    assistant = IntakeAssistant(mode=args.mode)
    metric_tables = []
    for name in ("dev", "test"):
        res = evaluate.run_set(assistant, evaluate.load_set(name))
        save(res, f"intake_{name}_results.csv")
        metric_tables.append(evaluate.metrics_table(res).assign(set=name))
    save(pd.concat(metric_tables, ignore_index=True), "intake_metrics.csv")
    save(evaluate.retrieval_recall(evaluate.load_set("dev")), "retrieval_recall_dev.csv")

    # 5. Equity.
    eq = equity.neighborhood_equity()
    save(eq, "equity_neighborhoods.csv")
    save(equity.equity_summary(eq), "equity_summary.csv")

    # 6. Figures.
    written += make_figures(fc, plan, summary, figs)

    # 7. Manifest.
    m = manifest.build_manifest(
        args.mode, written, {"run": "scripts/run_all.py", "reconciliation": "all checks passed for every plan and scenario"}
    )
    path = manifest.write_manifest(m)
    print(summary[summary["department"] == "ALL"].to_string(index=False))
    print(f"wrote {len(written)} outputs and {path.relative_to(config.REPO_ROOT)}")


def make_figures(fc: pd.DataFrame, plan: staffing.Plan, summary: pd.DataFrame, folder) -> list:
    """Three report figures: forecast, crews by month, and scenario costs."""
    paths = []
    months = range(1, 13)

    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    for ax, dept in zip(axes.ravel(), config.DEPT_CODES):
        d = fc[fc["department"] == dept]
        ax.bar(d["month"], d["forecast"], color="#4C72B0")
        ax.set_title(f"{config.DEPARTMENTS[dept].name}: 2025 forecast")
        ax.set_xticks(list(months))
    fig.supxlabel("Month of 2025")
    fig.supylabel("Requests")
    fig.tight_layout()
    paths.append(_save(fig, folder / "forecast_2025.png"))

    pf = plan.to_frame()
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    for ax, dept in zip(axes.ravel(), config.DEPT_CODES):
        d = pf[pf["department"] == dept]
        ax.bar(d["month"], d["regular_crews"], label="regular crews", color="#4C72B0")
        ax.bar(d["month"], d["seasonal_crews"], bottom=d["regular_crews"], label="seasonal crews", color="#DD8452")
        ax.axhline(config.DEPARTMENTS[dept].start_crews, color="grey", ls="--", lw=1, label="January crews (baseline)")
        ax.set_title(config.DEPARTMENTS[dept].name)
        ax.set_xticks(list(months))
        ax.set_ylim(0, (d["regular_crews"] + d["seasonal_crews"]).max() * 1.12)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9)
    fig.supxlabel("Month of 2025", y=0.06)
    fig.supylabel("Crews working")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    paths.append(_save(fig, folder / "staffing_plan.png"))

    tot = summary[summary["department"] == "ALL"].pivot(index="scenario", columns="plan", values="total_cost").reindex(list(config.SCENARIOS))
    fig, ax = plt.subplots(figsize=(7, 4))
    (tot / 1e6).plot.bar(ax=ax, color={"heuristic": "#4C72B0", "baseline": "#C44E52"})
    ax.set_ylabel("Total 2025 cost ($ millions)")
    ax.set_xlabel("Scenario")
    ax.set_title("Frozen plan vs. fixed January crews")
    ax.tick_params(axis="x", rotation=0)
    fig.tight_layout()
    paths.append(_save(fig, folder / "scenario_costs.png"))
    return paths


def _save(fig, path):
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


if __name__ == "__main__":
    main()
