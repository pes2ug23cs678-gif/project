"""Publication-ready charts for multi-system comparison.

Generates charts comparing Baseline, RAG-Only, and Full Agentic RAG
across all evaluation metrics with a cohesive dark theme.

Usage
-----
    from evaluation.visualizer_research import ResearchVisualizer
    viz = ResearchVisualizer(system_metrics, system_results, ablation_results)
    viz.plot_all("evaluation/plots")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.gridspec import GridSpec

if TYPE_CHECKING:
    from evaluation.evaluator import TestResult, SystemMetrics, AblationConfig


# =====================================================================
#  Theme
# =====================================================================

_C = {
    "bg":         "#0f1117",
    "card":       "#1a1d29",
    "grid":       "#2a2d3a",
    "text":       "#e8e8f0",
    "dim":        "#8b8fa3",
    "baseline":   "#f87171",
    "rag":        "#fbbf24",
    "full":       "#34d399",
    "blue":       "#4f8cf7",
    "purple":     "#a78bfa",
}

_SYS_COLORS = {
    "Baseline LLM":     _C["baseline"],
    "RAG-Only":         _C["rag"],
    "Full Agentic RAG": _C["full"],
}

_DIFF_COLORS = {"easy": "#34d399", "medium": "#fbbf24", "hard": "#f87171"}


def _theme(ax: plt.Axes) -> None:
    ax.set_facecolor(_C["card"])
    ax.tick_params(colors=_C["text"], labelsize=9)
    ax.xaxis.label.set_color(_C["text"])
    ax.yaxis.label.set_color(_C["text"])
    ax.title.set_color(_C["text"])
    for sp in ax.spines.values():
        sp.set_color(_C["grid"])
    ax.grid(True, color=_C["grid"], alpha=0.3, linestyle="--")


def _fig(figsize=(10, 6)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_C["bg"])
    _theme(ax)
    return fig, ax


def _sys_color(name: str) -> str:
    return _SYS_COLORS.get(name, _C["blue"])


# =====================================================================
#  Visualizer
# =====================================================================

class ResearchVisualizer:

    def __init__(
        self,
        system_metrics: dict[str, SystemMetrics],
        system_results: dict[str, list[TestResult]],
        ablation_results: list[AblationConfig] | None = None,
    ) -> None:
        self._metrics = system_metrics
        self._results = system_results
        self._ablation = ablation_results or []

    def plot_all(self, output_dir: str | Path = "evaluation/plots") -> list[Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        plots = [
            ("01_system_comparison",     self.plot_system_comparison),
            ("02_pass_rate_by_difficulty", self.plot_pass_rate_by_difficulty),
            ("03_pass_rate_by_category",  self.plot_pass_rate_by_category),
            ("04_metric_radar",           self.plot_radar),
            ("05_silent_errors",          self.plot_silent_errors),
            ("06_per_test_heatmap",       self.plot_per_test_heatmap),
            ("07_summary_dashboard",      self.plot_dashboard),
        ]
        if self._ablation:
            plots.append(("08_ablation_study", self.plot_ablation))

        saved: list[Path] = []
        for name, fn in plots:
            try:
                f = fn()
                p = out / f"{name}.png"
                f.savefig(p, dpi=200, bbox_inches="tight", facecolor=f.get_facecolor())
                plt.close(f)
                saved.append(p)
                print(f"  📊 Saved → {p}")
            except Exception as exc:
                print(f"  ⚠  {name}: {exc}")
        return saved

    # ── Charts ────────────────────────────────────────────────────

    def plot_system_comparison(self) -> plt.Figure:
        """Grouped horizontal bars for 6 key metrics."""
        fig, ax = _fig((11, 6))

        metrics_list = [
            ("Pass Rate (%)",        "test_pass_rate"),
            ("Exec Success (%)",     "execution_success_rate"),
            ("Confidence (%)",       "avg_confidence"),
            ("Failure Detection (%)", "failure_detection_rate"),
        ]
        systems = list(self._metrics.values())
        n_metrics = len(metrics_list)
        n_sys = len(systems)
        y = np.arange(n_metrics)
        height = 0.8 / n_sys

        for i, m in enumerate(systems):
            vals = [getattr(m, attr) for _, attr in metrics_list]
            offset = (i - n_sys / 2 + 0.5) * height
            bars = ax.barh(y + offset, vals, height * 0.9,
                           color=_sys_color(m.system_name), alpha=0.85,
                           label=m.system_name, edgecolor="white", linewidth=0.5, zorder=3)
            for bar, v in zip(bars, vals):
                ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
                        f"{v:.1f}", va="center", fontsize=8, fontweight="bold",
                        color=_C["text"])

        ax.set_yticks(y)
        ax.set_yticklabels([label for label, _ in metrics_list], fontsize=10)
        ax.set_xlabel("Score", fontsize=11)
        ax.set_title("System Comparison — Key Metrics", fontsize=14, fontweight="bold", pad=15)
        ax.set_xlim(0, 115)
        ax.invert_yaxis()
        ax.legend(fontsize=9, facecolor=_C["card"], edgecolor=_C["grid"], labelcolor=_C["text"])
        fig.tight_layout()
        return fig

    def plot_pass_rate_by_difficulty(self) -> plt.Figure:
        fig, ax = _fig((9, 5.5))
        difficulties = ["easy", "medium", "hard"]
        systems = list(self._metrics.values())
        x = np.arange(len(difficulties))
        w = 0.8 / len(systems)

        for i, m in enumerate(systems):
            rates = [m.by_difficulty.get(d, {}).get("pass_rate", 0) for d in difficulties]
            offset = (i - len(systems) / 2 + 0.5) * w
            bars = ax.bar(x + offset, rates, w * 0.9, color=_sys_color(m.system_name),
                          alpha=0.85, label=m.system_name, edgecolor="white",
                          linewidth=0.5, zorder=3)
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2, h + 1,
                        f"{h:.0f}%", ha="center", fontsize=8, fontweight="bold",
                        color=_C["text"])

        ax.set_xticks(x)
        ax.set_xticklabels([d.capitalize() for d in difficulties], fontsize=11)
        ax.set_ylabel("Pass Rate (%)", fontsize=11)
        ax.set_title("Pass Rate by Difficulty", fontsize=14, fontweight="bold", pad=15)
        ax.set_ylim(0, 115)
        ax.legend(fontsize=9, facecolor=_C["card"], edgecolor=_C["grid"], labelcolor=_C["text"])
        fig.tight_layout()
        return fig

    def plot_pass_rate_by_category(self) -> plt.Figure:
        fig, ax = _fig((10, 5.5))
        categories = sorted({
            cat for m in self._metrics.values() for cat in m.by_category
        })
        systems = list(self._metrics.values())
        x = np.arange(len(categories))
        w = 0.8 / max(len(systems), 1)

        for i, m in enumerate(systems):
            rates = [m.by_category.get(c, {}).get("pass_rate", 0) for c in categories]
            offset = (i - len(systems) / 2 + 0.5) * w
            ax.bar(x + offset, rates, w * 0.9, color=_sys_color(m.system_name),
                   alpha=0.85, label=m.system_name, edgecolor="white",
                   linewidth=0.5, zorder=3)

        ax.set_xticks(x)
        ax.set_xticklabels([c.capitalize() for c in categories], fontsize=10)
        ax.set_ylabel("Pass Rate (%)", fontsize=11)
        ax.set_title("Pass Rate by Category", fontsize=14, fontweight="bold", pad=15)
        ax.set_ylim(0, 115)
        ax.legend(fontsize=9, facecolor=_C["card"], edgecolor=_C["grid"], labelcolor=_C["text"])
        fig.tight_layout()
        return fig

    def plot_radar(self) -> plt.Figure:
        labels = ["Pass Rate", "Exec\nSuccess", "Confidence",
                  "Failure\nDetection", "Low Silent\nErrors"]
        N = len(labels)
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
        fig.patch.set_facecolor(_C["bg"])
        ax.set_facecolor(_C["card"])

        for m in self._metrics.values():
            vals = [
                m.test_pass_rate / 100,
                m.execution_success_rate / 100,
                m.avg_confidence / 100,
                m.failure_detection_rate / 100,
                max(0, (100 - m.silent_error_rate)) / 100,
            ]
            vals += vals[:1]
            ax.plot(angles, vals, "o-", color=_sys_color(m.system_name),
                    linewidth=2, label=m.system_name, alpha=0.9)
            ax.fill(angles, vals, color=_sys_color(m.system_name), alpha=0.12)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=10, color=_C["text"])
        ax.tick_params(axis="y", labelsize=8, colors=_C["dim"])
        ax.set_ylim(0, 1.1)
        ax.set_title("Multi-system Radar", fontsize=14, fontweight="bold",
                      color=_C["text"], pad=25)
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9,
                  facecolor=_C["card"], edgecolor=_C["grid"], labelcolor=_C["text"])
        ax.grid(color=_C["grid"], alpha=0.3)
        fig.tight_layout()
        return fig

    def plot_silent_errors(self) -> plt.Figure:
        """Bar chart: silent error rate + failure detection rate."""
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        fig.patch.set_facecolor(_C["bg"])

        systems = list(self._metrics.values())
        names = [m.system_name for m in systems]
        x = np.arange(len(names))

        # Silent error rate
        ax = axes[0]
        _theme(ax)
        silent = [m.silent_error_rate for m in systems]
        colors = [_sys_color(n) for n in names]
        ax.bar(x, silent, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
        for i, v in enumerate(silent):
            ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10,
                    fontweight="bold", color=_C["text"])
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=9, rotation=15, ha="right")
        ax.set_ylabel("Rate (%)", fontsize=10)
        ax.set_title("Silent Error Rate (↓ lower = better)", fontsize=12,
                      fontweight="bold", color=_C["text"], pad=10)

        # Failure detection rate
        ax = axes[1]
        _theme(ax)
        fdr = [m.failure_detection_rate for m in systems]
        ax.bar(x, fdr, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
        for i, v in enumerate(fdr):
            ax.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10,
                    fontweight="bold", color=_C["text"])
        ax.set_xticks(x)
        ax.set_xticklabels(names, fontsize=9, rotation=15, ha="right")
        ax.set_ylabel("Rate (%)", fontsize=10)
        ax.set_title("Failure Detection Rate (↑ higher = better)", fontsize=12,
                      fontweight="bold", color=_C["text"], pad=10)

        fig.suptitle("Error Analysis", fontsize=14, fontweight="bold",
                     color=_C["text"], y=1.02)
        fig.tight_layout()
        return fig

    def plot_per_test_heatmap(self) -> plt.Figure:
        """Heatmap: test × system showing pass/fail."""
        systems = list(self._results.keys())
        sys_labels = [self._metrics[s].system_name for s in systems]
        test_names = [r.name for r in self._results[systems[0]]]
        n_tests = len(test_names)
        n_sys = len(systems)

        matrix = np.zeros((n_tests, n_sys))
        for j, sk in enumerate(systems):
            for i, r in enumerate(self._results[sk]):
                if r.status == "PASS":
                    matrix[i, j] = 1.0
                elif r.silent_error:
                    matrix[i, j] = 0.5  # ran but wrong
                else:
                    matrix[i, j] = 0.0  # crashed or wrong

        fig, ax = plt.subplots(figsize=(8, max(6, n_tests * 0.5 + 1)))
        fig.patch.set_facecolor(_C["bg"])
        ax.set_facecolor(_C["card"])

        from matplotlib.colors import ListedColormap
        cmap = ListedColormap([_C["baseline"], _C["rag"], _C["full"]])
        im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=1, interpolation="nearest")

        # Annotate cells
        for i in range(n_tests):
            for j in range(n_sys):
                v = matrix[i, j]
                label = "✓" if v == 1.0 else "△" if v == 0.5 else "✗"
                color = "white" if v < 0.5 else "#0f1117"
                ax.text(j, i, label, ha="center", va="center",
                        fontsize=12, fontweight="bold", color=color)

        ax.set_xticks(range(n_sys))
        ax.set_xticklabels(sys_labels, fontsize=9, color=_C["text"])
        ax.set_yticks(range(n_tests))
        ax.set_yticklabels(test_names, fontsize=8, color=_C["text"])
        ax.set_title("Per-Test Results (✓ Pass  △ Silent Error  ✗ Fail)",
                      fontsize=13, fontweight="bold", color=_C["text"], pad=12)
        ax.tick_params(axis="both", colors=_C["text"])

        for sp in ax.spines.values():
            sp.set_color(_C["grid"])

        fig.tight_layout()
        return fig

    def plot_ablation(self) -> plt.Figure:
        """Bar chart for ablation study results."""
        if not self._ablation:
            fig, ax = _fig()
            ax.text(0.5, 0.5, "No ablation data", transform=ax.transAxes,
                    ha="center", va="center", fontsize=14, color=_C["dim"])
            return fig

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.patch.set_facecolor(_C["bg"])

        configs = self._ablation
        names = [c.config_name[:20] for c in configs]
        x = np.arange(len(names))
        colors = [_C["full"], _C["rag"], _C["blue"], _C["baseline"]]

        for ax_idx, (attr, title) in enumerate([
            ("test_pass_rate", "Pass Rate (%)"),
            ("execution_success_rate", "Execution Success (%)"),
            ("silent_error_rate", "Silent Error Rate (%)"),
        ]):
            ax = axes[ax_idx]
            _theme(ax)
            vals = [getattr(c.metrics, attr, 0) for c in configs]
            ax.bar(x, vals, color=colors[:len(configs)], alpha=0.85,
                   edgecolor="white", linewidth=0.5, zorder=3)
            for i, v in enumerate(vals):
                ax.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=9,
                        fontweight="bold", color=_C["text"])
            ax.set_xticks(x)
            ax.set_xticklabels(names, fontsize=7, rotation=20, ha="right")
            ax.set_title(title, fontsize=11, fontweight="bold", color=_C["text"], pad=8)

        fig.suptitle("Ablation Study", fontsize=14, fontweight="bold",
                     color=_C["text"], y=1.02)
        fig.tight_layout()
        return fig

    def plot_dashboard(self) -> plt.Figure:
        """6-panel summary dashboard."""
        fig = plt.figure(figsize=(18, 11))
        fig.patch.set_facecolor(_C["bg"])
        gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

        systems = list(self._metrics.values())
        sys_names = [m.system_name for m in systems]
        x = np.arange(len(sys_names))
        colors = [_sys_color(n) for n in sys_names]

        # Panel 1: Score cards
        ax0 = fig.add_subplot(gs[0, 0])
        _theme(ax0)
        ax0.axis("off")
        ax0.set_title("Best System Metrics", fontsize=12, fontweight="bold",
                       color=_C["text"], pad=10)
        best = max(systems, key=lambda m: m.test_pass_rate)
        cards = [
            ("System",       best.system_name, _C["full"]),
            ("Pass Rate",    f"{best.test_pass_rate:.0f}%", _C["full"]),
            ("Exec Success", f"{best.execution_success_rate:.0f}%", _C["blue"]),
            ("Confidence",   f"{best.avg_confidence:.0f}%", _C["purple"]),
            ("Silent Errs",  f"{best.silent_error_rate:.1f}%", _C["rag"]),
        ]
        for i, (label, value, color) in enumerate(cards):
            y = 0.85 - i * 0.17
            ax0.text(0.05, y, label, fontsize=11, color=_C["dim"],
                     transform=ax0.transAxes, va="center")
            ax0.text(0.95, y, value, fontsize=14, fontweight="bold", color=color,
                     transform=ax0.transAxes, va="center", ha="right")

        # Panel 2: Pass rate bars
        ax1 = fig.add_subplot(gs[0, 1])
        _theme(ax1)
        rates = [m.test_pass_rate for m in systems]
        ax1.bar(x, rates, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
        for i, v in enumerate(rates):
            ax1.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=10,
                     fontweight="bold", color=_C["text"])
        ax1.set_xticks(x)
        ax1.set_xticklabels(sys_names, fontsize=8, rotation=10, ha="right")
        ax1.set_title("Overall Pass Rate", fontsize=11, fontweight="bold",
                       color=_C["text"], pad=8)
        ax1.set_ylim(0, 115)

        # Panel 3: Donut
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.set_facecolor(_C["card"])
        sizes = [best.passed, best.failed, best.errors]
        labels_d = ["Pass", "Fail", "Error"]
        colors_d = [_C["full"], _C["baseline"], _C["rag"]]
        filtered = [(s, l, c) for s, l, c in zip(sizes, labels_d, colors_d) if s > 0]
        if filtered:
            sz, lb, cl = zip(*filtered)
            _, texts, auto = ax2.pie(sz, labels=lb, colors=cl, autopct="%1.0f%%",
                                     startangle=90, pctdistance=0.75,
                                     wedgeprops=dict(width=0.4, edgecolor=_C["bg"], linewidth=2))
            for t in texts:
                t.set_color(_C["text"]); t.set_fontsize(9)
            for t in auto:
                t.set_color("white"); t.set_fontweight("bold")
        ax2.set_title(f"Best System Outcomes", fontsize=11, fontweight="bold",
                       color=_C["text"], pad=8)

        # Panel 4: Difficulty breakdown
        ax3 = fig.add_subplot(gs[1, 0])
        _theme(ax3)
        diffs = ["easy", "medium", "hard"]
        xd = np.arange(len(diffs))
        w = 0.8 / len(systems)
        for i, m in enumerate(systems):
            r = [m.by_difficulty.get(d, {}).get("pass_rate", 0) for d in diffs]
            ax3.bar(xd + (i - len(systems)/2 + 0.5) * w, r, w * 0.9,
                    color=_sys_color(m.system_name), alpha=0.85, label=m.system_name)
        ax3.set_xticks(xd)
        ax3.set_xticklabels([d.capitalize() for d in diffs], fontsize=9)
        ax3.set_title("Pass Rate by Difficulty", fontsize=11, fontweight="bold",
                       color=_C["text"], pad=8)
        ax3.set_ylim(0, 115)
        ax3.legend(fontsize=7, facecolor=_C["card"], edgecolor=_C["grid"], labelcolor=_C["text"])

        # Panel 5: Silent error comparison
        ax4 = fig.add_subplot(gs[1, 1])
        _theme(ax4)
        silent = [m.silent_error_rate for m in systems]
        ax4.bar(x, silent, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
        for i, v in enumerate(silent):
            ax4.text(i, v + 0.5, f"{v:.1f}%", ha="center", fontsize=9,
                     fontweight="bold", color=_C["text"])
        ax4.set_xticks(x)
        ax4.set_xticklabels(sys_names, fontsize=8, rotation=10, ha="right")
        ax4.set_title("Silent Error Rate (↓ better)", fontsize=11,
                       fontweight="bold", color=_C["text"], pad=8)

        # Panel 6: Confidence comparison
        ax5 = fig.add_subplot(gs[1, 2])
        _theme(ax5)
        conf = [m.avg_confidence for m in systems]
        ax5.bar(x, conf, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5, zorder=3)
        for i, v in enumerate(conf):
            ax5.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=9,
                     fontweight="bold", color=_C["text"])
        ax5.set_xticks(x)
        ax5.set_xticklabels(sys_names, fontsize=8, rotation=10, ha="right")
        ax5.set_title("Average Confidence", fontsize=11, fontweight="bold",
                       color=_C["text"], pad=8)
        ax5.set_ylim(0, 115)

        fig.suptitle("COBOL → Python · Multi-System Evaluation Dashboard",
                     fontsize=16, fontweight="bold", color=_C["text"], y=0.99)
        return fig
