"""Visualization module for pipeline evaluation results.

Generates publication-ready charts comparing our multi-agent pipeline
against a configurable baseline.  All plots use a cohesive dark theme
with accent gradients designed for readability and research papers.

Usage
-----
    from evaluation.visualizer import ResultVisualizer
    viz = ResultVisualizer(results, summary)
    viz.plot_all(output_dir="evaluation/plots")

    # Or individually:
    viz.plot_pass_rate_by_difficulty()
    viz.plot_baseline_comparison()
    viz.plot_iteration_distribution()
    viz.plot_timing_breakdown()
    viz.plot_confidence_heatmap()
    viz.plot_radar_comparison()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

import matplotlib
matplotlib.use("Agg")  # headless backend — no display needed

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.gridspec import GridSpec

if TYPE_CHECKING:
    from evaluation.evaluator import TestResult, EvaluationSummary


# =====================================================================
#  Baseline definition
# =====================================================================

@dataclass
class BaselineMetrics:
    """Simulated or measured metrics for a naive single-pass baseline.

    These numbers represent a typical single-LLM-call translation
    without the multi-agent pipeline, debug loop, or RAG context.
    Override with real measurements when available.
    """
    name: str = "Single-Pass LLM"
    pass_rate_easy: float    = 70.0
    pass_rate_medium: float  = 40.0
    pass_rate_hard: float    = 15.0
    overall_pass_rate: float = 42.0
    exec_success_rate: float = 60.0
    avg_confidence: float    = 45.0
    avg_time_seconds: float  = 3.5
    avg_iterations: float    = 1.0   # no debug loop

    @property
    def pass_rates_by_difficulty(self) -> dict[str, float]:
        return {
            "easy": self.pass_rate_easy,
            "medium": self.pass_rate_medium,
            "hard": self.pass_rate_hard,
        }


# =====================================================================
#  Color palette — cohesive dark theme
# =====================================================================

_COLORS = {
    "bg":           "#0f1117",
    "card_bg":      "#1a1d29",
    "grid":         "#2a2d3a",
    "text":         "#e8e8f0",
    "text_dim":     "#8b8fa3",
    "accent_blue":  "#4f8cf7",
    "accent_green": "#34d399",
    "accent_red":   "#f87171",
    "accent_amber": "#fbbf24",
    "accent_purple":"#a78bfa",
    "gradient_1":   "#6366f1",
    "gradient_2":   "#8b5cf6",
    "gradient_3":   "#a78bfa",
    "baseline":     "#ff6b6b",
    "ours":         "#4f8cf7",
}

_DIFFICULTY_COLORS = {
    "easy":   "#34d399",
    "medium": "#fbbf24",
    "hard":   "#f87171",
}


def _apply_theme(ax: plt.Axes) -> None:
    """Apply the dark-card theme to an axes."""
    ax.set_facecolor(_COLORS["card_bg"])
    ax.tick_params(colors=_COLORS["text"], labelsize=9)
    ax.xaxis.label.set_color(_COLORS["text"])
    ax.yaxis.label.set_color(_COLORS["text"])
    ax.title.set_color(_COLORS["text"])
    for spine in ax.spines.values():
        spine.set_color(_COLORS["grid"])
    ax.grid(True, color=_COLORS["grid"], alpha=0.3, linestyle="--")


def _dark_figure(figsize: tuple = (10, 6), **kwargs) -> tuple[plt.Figure, Any]:
    """Create a figure with the dark background."""
    fig, ax = plt.subplots(figsize=figsize, **kwargs)
    fig.patch.set_facecolor(_COLORS["bg"])
    if isinstance(ax, np.ndarray):
        for a in ax.flat:
            _apply_theme(a)
    else:
        _apply_theme(ax)
    return fig, ax


# =====================================================================
#  Visualizer class
# =====================================================================

class ResultVisualizer:
    """Generates evaluation charts from test results."""

    def __init__(
        self,
        results: list[TestResult],
        summary: EvaluationSummary,
        baseline: BaselineMetrics | None = None,
    ) -> None:
        self._results = results
        self._summary = summary
        self._baseline = baseline or BaselineMetrics()

    # ── Master method ─────────────────────────────────────────────

    def plot_all(self, output_dir: str | Path = "evaluation/plots") -> list[Path]:
        """Generate all charts and save to *output_dir*."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        saved: list[Path] = []
        plots = [
            ("pass_rate_by_difficulty", self.plot_pass_rate_by_difficulty),
            ("baseline_comparison", self.plot_baseline_comparison),
            ("iteration_distribution", self.plot_iteration_distribution),
            ("timing_breakdown", self.plot_timing_breakdown),
            ("confidence_per_test", self.plot_confidence_per_test),
            ("radar_comparison", self.plot_radar_comparison),
            ("summary_dashboard", self.plot_summary_dashboard),
        ]

        for name, fn in plots:
            try:
                fig = fn()
                path = out / f"{name}.png"
                fig.savefig(path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
                plt.close(fig)
                saved.append(path)
                print(f"  📊 Saved → {path}")
            except Exception as exc:
                print(f"  ⚠  Failed to generate {name}: {exc}")

        return saved

    # ── Individual plots ──────────────────────────────────────────

    def plot_pass_rate_by_difficulty(self) -> plt.Figure:
        """Grouped bar chart: pass rate per difficulty tier."""
        fig, ax = _dark_figure((9, 5.5))

        difficulties = list(self._summary.by_difficulty.keys())
        if not difficulties:
            difficulties = ["easy", "medium", "hard"]

        ours_rates = []
        baseline_rates = []
        for d in difficulties:
            metrics = self._summary.by_difficulty.get(d, {})
            ours_rates.append(metrics.get("pass_rate", 0))
            baseline_rates.append(self._baseline.pass_rates_by_difficulty.get(d, 0))

        x = np.arange(len(difficulties))
        width = 0.32

        bars_b = ax.bar(x - width/2, baseline_rates, width,
                        color=_COLORS["baseline"], alpha=0.85, label=self._baseline.name,
                        edgecolor="white", linewidth=0.5, zorder=3)
        bars_o = ax.bar(x + width/2, ours_rates, width,
                        color=_COLORS["ours"], alpha=0.9, label="Our Pipeline",
                        edgecolor="white", linewidth=0.5, zorder=3)

        # Value labels
        for bars in [bars_b, bars_o]:
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, h + 1.5,
                        f"{h:.0f}%", ha="center", va="bottom",
                        fontsize=9, fontweight="bold", color=_COLORS["text"])

        ax.set_xticks(x)
        ax.set_xticklabels([d.capitalize() for d in difficulties], fontsize=11)
        ax.set_ylabel("Pass Rate (%)", fontsize=11)
        ax.set_title("Pass Rate by Difficulty Level", fontsize=14, fontweight="bold", pad=15)
        ax.set_ylim(0, 115)
        ax.legend(loc="upper right", fontsize=10, facecolor=_COLORS["card_bg"],
                  edgecolor=_COLORS["grid"], labelcolor=_COLORS["text"])

        fig.tight_layout()
        return fig

    def plot_baseline_comparison(self) -> plt.Figure:
        """Side-by-side metric comparison: our pipeline vs baseline."""
        fig, ax = _dark_figure((10, 5.5))

        metrics = ["Pass Rate", "Exec Success", "Confidence", "Debug Iters\n(lower=better)"]
        ours = [
            self._summary.test_pass_rate,
            self._summary.execution_success_rate,
            self._summary.avg_confidence_score,
            max(0, 100 - self._summary.avg_debug_iterations * 20),  # inverse scale
        ]
        baseline = [
            self._baseline.overall_pass_rate,
            self._baseline.exec_success_rate,
            self._baseline.avg_confidence,
            max(0, 100 - self._baseline.avg_iterations * 20),
        ]

        x = np.arange(len(metrics))
        width = 0.30

        bars_b = ax.barh(x + width/2, baseline, width,
                         color=_COLORS["baseline"], alpha=0.85, label=self._baseline.name,
                         edgecolor="white", linewidth=0.5, zorder=3)
        bars_o = ax.barh(x - width/2, ours, width,
                         color=_COLORS["ours"], alpha=0.9, label="Our Pipeline",
                         edgecolor="white", linewidth=0.5, zorder=3)

        for bars in [bars_b, bars_o]:
            for bar in bars:
                w = bar.get_width()
                ax.text(w + 1.5, bar.get_y() + bar.get_height()/2,
                        f"{w:.1f}", ha="left", va="center",
                        fontsize=9, fontweight="bold", color=_COLORS["text"])

        ax.set_yticks(x)
        ax.set_yticklabels(metrics, fontsize=10)
        ax.set_xlabel("Score", fontsize=11)
        ax.set_title("Pipeline vs Baseline — Key Metrics", fontsize=14, fontweight="bold", pad=15)
        ax.set_xlim(0, 115)
        ax.legend(loc="lower right", fontsize=10, facecolor=_COLORS["card_bg"],
                  edgecolor=_COLORS["grid"], labelcolor=_COLORS["text"])
        ax.invert_yaxis()
        fig.tight_layout()
        return fig

    def plot_iteration_distribution(self) -> plt.Figure:
        """Bar chart showing debug iterations per test case."""
        fig, ax = _dark_figure((10, 5))

        names = [r.name for r in self._results]
        iters = [r.debug_iterations for r in self._results]
        diffs = [r.difficulty for r in self._results]
        colors = [_DIFFICULTY_COLORS.get(d, _COLORS["accent_blue"]) for d in diffs]

        bars = ax.bar(range(len(names)), iters, color=colors, alpha=0.85,
                      edgecolor="white", linewidth=0.5, zorder=3)

        for bar, it in zip(bars, iters):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.08,
                    str(it), ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color=_COLORS["text"])

        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
        ax.set_ylabel("Debug Iterations", fontsize=11)
        ax.set_title("Debug Iterations per Test Case", fontsize=14, fontweight="bold", pad=15)

        # Legend for difficulty
        patches = [mpatches.Patch(color=c, label=d.capitalize())
                   for d, c in _DIFFICULTY_COLORS.items()]
        ax.legend(handles=patches, loc="upper right", fontsize=9,
                  facecolor=_COLORS["card_bg"], edgecolor=_COLORS["grid"],
                  labelcolor=_COLORS["text"])

        fig.tight_layout()
        return fig

    def plot_timing_breakdown(self) -> plt.Figure:
        """Horizontal bar chart — execution time per test."""
        fig, ax = _dark_figure((10, 5))

        names = [r.name for r in self._results]
        times = [r.elapsed_seconds for r in self._results]
        statuses = [r.status for r in self._results]
        colors = [_COLORS["accent_green"] if s == "PASS"
                  else _COLORS["accent_red"] if s == "FAIL"
                  else _COLORS["accent_amber"] for s in statuses]

        y = np.arange(len(names))
        bars = ax.barh(y, times, color=colors, alpha=0.85,
                       edgecolor="white", linewidth=0.5, zorder=3)

        for bar, t in zip(bars, times):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                    f"{t:.1f}s", ha="left", va="center",
                    fontsize=9, color=_COLORS["text"])

        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=9)
        ax.set_xlabel("Time (seconds)", fontsize=11)
        ax.set_title("Execution Time per Test Case", fontsize=14, fontweight="bold", pad=15)
        ax.invert_yaxis()

        patches = [
            mpatches.Patch(color=_COLORS["accent_green"], label="PASS"),
            mpatches.Patch(color=_COLORS["accent_red"], label="FAIL"),
            mpatches.Patch(color=_COLORS["accent_amber"], label="ERROR"),
        ]
        ax.legend(handles=patches, loc="lower right", fontsize=9,
                  facecolor=_COLORS["card_bg"], edgecolor=_COLORS["grid"],
                  labelcolor=_COLORS["text"])

        fig.tight_layout()
        return fig

    def plot_confidence_per_test(self) -> plt.Figure:
        """Lollipop chart of confidence scores per test."""
        fig, ax = _dark_figure((10, 5.5))

        names = [r.name for r in self._results]
        confs = [r.confidence_score for r in self._results]
        diffs = [r.difficulty for r in self._results]
        colors = [_DIFFICULTY_COLORS.get(d, _COLORS["accent_blue"]) for d in diffs]

        y = np.arange(len(names))

        # Stems
        for i, (c, col) in enumerate(zip(confs, colors)):
            ax.plot([0, c], [i, i], color=col, linewidth=2, alpha=0.6, zorder=2)

        # Dots
        ax.scatter(confs, y, c=colors, s=100, zorder=3, edgecolors="white", linewidth=1)

        # Threshold line
        ax.axvline(x=self._baseline.avg_confidence, color=_COLORS["baseline"],
                   linestyle="--", linewidth=1.5, alpha=0.7, label=f"Baseline ({self._baseline.avg_confidence:.0f}%)")

        for i, c in enumerate(confs):
            ax.text(c + 2, i, f"{c:.0f}%", va="center", fontsize=9,
                    color=_COLORS["text"], fontweight="bold")

        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=9)
        ax.set_xlabel("Confidence Score (%)", fontsize=11)
        ax.set_title("Confidence Score per Test Case", fontsize=14, fontweight="bold", pad=15)
        ax.set_xlim(-5, 115)
        ax.invert_yaxis()
        ax.legend(fontsize=9, facecolor=_COLORS["card_bg"],
                  edgecolor=_COLORS["grid"], labelcolor=_COLORS["text"])

        fig.tight_layout()
        return fig

    def plot_radar_comparison(self) -> plt.Figure:
        """Radar (spider) chart comparing our pipeline vs baseline."""
        categories = [
            "Pass Rate", "Exec\nSuccess", "Confidence",
            "Speed\n(inv)", "Debug\nEfficiency",
        ]
        N = len(categories)

        # Normalize all to 0–1
        ours = [
            self._summary.test_pass_rate / 100,
            self._summary.execution_success_rate / 100,
            self._summary.avg_confidence_score / 100,
            min(1.0, 10 / max(self._summary.avg_elapsed_seconds, 0.1)),  # inverse time
            min(1.0, 1 / max(self._summary.avg_debug_iterations, 0.1)),   # fewer = better
        ]
        base = [
            self._baseline.overall_pass_rate / 100,
            self._baseline.exec_success_rate / 100,
            self._baseline.avg_confidence / 100,
            min(1.0, 10 / max(self._baseline.avg_time_seconds, 0.1)),
            min(1.0, 1 / max(self._baseline.avg_iterations, 0.1)),
        ]

        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        ours += ours[:1]
        base += base[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
        fig.patch.set_facecolor(_COLORS["bg"])
        ax.set_facecolor(_COLORS["card_bg"])

        ax.plot(angles, base, "o-", color=_COLORS["baseline"], linewidth=2,
                label=self._baseline.name, alpha=0.8)
        ax.fill(angles, base, color=_COLORS["baseline"], alpha=0.15)

        ax.plot(angles, ours, "o-", color=_COLORS["ours"], linewidth=2,
                label="Our Pipeline", alpha=0.9)
        ax.fill(angles, ours, color=_COLORS["ours"], alpha=0.2)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=10, color=_COLORS["text"])
        ax.tick_params(axis="y", labelsize=8, colors=_COLORS["text_dim"])
        ax.set_ylim(0, 1.1)
        ax.set_title("Pipeline vs Baseline — Radar", fontsize=14, fontweight="bold",
                      color=_COLORS["text"], pad=25)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10,
                  facecolor=_COLORS["card_bg"], edgecolor=_COLORS["grid"],
                  labelcolor=_COLORS["text"])
        ax.grid(color=_COLORS["grid"], alpha=0.3)

        fig.tight_layout()
        return fig

    def plot_summary_dashboard(self) -> plt.Figure:
        """Multi-panel summary dashboard combining key visuals."""
        fig = plt.figure(figsize=(16, 10))
        fig.patch.set_facecolor(_COLORS["bg"])
        gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.35)

        s = self._summary
        bl = self._baseline

        # ── Panel 1: Score cards (text) ──────────────────────────────
        ax0 = fig.add_subplot(gs[0, 0])
        _apply_theme(ax0)
        ax0.axis("off")
        ax0.set_title("Key Metrics", fontsize=13, fontweight="bold",
                       color=_COLORS["text"], pad=10)

        card_lines = [
            (f"Pass Rate",       f"{s.test_pass_rate:.0f}%",        _COLORS["accent_green"] if s.test_pass_rate > 70 else _COLORS["accent_red"]),
            (f"Exec Success",    f"{s.execution_success_rate:.0f}%", _COLORS["accent_green"]),
            (f"Avg Confidence",  f"{s.avg_confidence_score:.0f}%",   _COLORS["accent_blue"]),
            (f"Avg Iterations",  f"{s.avg_debug_iterations:.1f}",    _COLORS["accent_amber"]),
            (f"Total Time",      f"{s.total_elapsed_seconds:.1f}s",  _COLORS["accent_purple"]),
        ]
        for i, (label, value, color) in enumerate(card_lines):
            y = 0.85 - i * 0.17
            ax0.text(0.05, y, label, fontsize=11, color=_COLORS["text_dim"],
                     transform=ax0.transAxes, va="center")
            ax0.text(0.95, y, value, fontsize=15, fontweight="bold", color=color,
                     transform=ax0.transAxes, va="center", ha="right")

        # ── Panel 2: Pass rate comparison bars ───────────────────────
        ax1 = fig.add_subplot(gs[0, 1])
        _apply_theme(ax1)
        diffs = list(s.by_difficulty.keys()) or ["easy", "medium", "hard"]
        x = np.arange(len(diffs))
        w = 0.32
        ours_r = [s.by_difficulty.get(d, {}).get("pass_rate", 0) for d in diffs]
        base_r = [bl.pass_rates_by_difficulty.get(d, 0) for d in diffs]
        ax1.bar(x - w/2, base_r, w, color=_COLORS["baseline"], alpha=0.8, label=bl.name)
        ax1.bar(x + w/2, ours_r, w, color=_COLORS["ours"], alpha=0.9, label="Ours")
        ax1.set_xticks(x)
        ax1.set_xticklabels([d.capitalize() for d in diffs], fontsize=9)
        ax1.set_ylabel("%", fontsize=9)
        ax1.set_title("Pass Rate by Difficulty", fontsize=11, fontweight="bold",
                       color=_COLORS["text"], pad=8)
        ax1.set_ylim(0, 115)
        ax1.legend(fontsize=8, facecolor=_COLORS["card_bg"],
                   edgecolor=_COLORS["grid"], labelcolor=_COLORS["text"])

        # ── Panel 3: Donut chart — overall pass/fail ─────────────────
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.set_facecolor(_COLORS["card_bg"])
        sizes = [s.passed, s.failed, s.errors]
        labels_d = ["Pass", "Fail", "Error"]
        colors_d = [_COLORS["accent_green"], _COLORS["accent_red"], _COLORS["accent_amber"]]
        # Remove zeros
        filtered = [(sz, lb, cl) for sz, lb, cl in zip(sizes, labels_d, colors_d) if sz > 0]
        if filtered:
            sz_f, lb_f, cl_f = zip(*filtered)
            wedges, texts, autotexts = ax2.pie(
                sz_f, labels=lb_f, colors=cl_f, autopct="%1.0f%%",
                startangle=90, pctdistance=0.75,
                wedgeprops=dict(width=0.4, edgecolor=_COLORS["bg"], linewidth=2),
            )
            for t in texts:
                t.set_color(_COLORS["text"])
                t.set_fontsize(9)
            for t in autotexts:
                t.set_color("white")
                t.set_fontweight("bold")
                t.set_fontsize(10)
        ax2.set_title("Test Outcomes", fontsize=11, fontweight="bold",
                       color=_COLORS["text"], pad=8)

        # ── Panel 4: Iterations bar ──────────────────────────────────
        ax3 = fig.add_subplot(gs[1, 0])
        _apply_theme(ax3)
        names = [r.name[:15] for r in self._results]
        iters = [r.debug_iterations for r in self._results]
        col = [_DIFFICULTY_COLORS.get(r.difficulty, _COLORS["accent_blue"]) for r in self._results]
        ax3.barh(range(len(names)), iters, color=col, alpha=0.85, edgecolor="white", linewidth=0.5)
        ax3.set_yticks(range(len(names)))
        ax3.set_yticklabels(names, fontsize=8)
        ax3.set_xlabel("Iterations", fontsize=9)
        ax3.set_title("Debug Iterations", fontsize=11, fontweight="bold",
                       color=_COLORS["text"], pad=8)
        ax3.invert_yaxis()

        # ── Panel 5: Timing bars ─────────────────────────────────────
        ax4 = fig.add_subplot(gs[1, 1])
        _apply_theme(ax4)
        times = [r.elapsed_seconds for r in self._results]
        st_colors = [_COLORS["accent_green"] if r.status == "PASS" else _COLORS["accent_red"]
                     for r in self._results]
        ax4.barh(range(len(names)), times, color=st_colors, alpha=0.85,
                 edgecolor="white", linewidth=0.5)
        ax4.set_yticks(range(len(names)))
        ax4.set_yticklabels(names, fontsize=8)
        ax4.set_xlabel("Seconds", fontsize=9)
        ax4.set_title("Execution Time", fontsize=11, fontweight="bold",
                       color=_COLORS["text"], pad=8)
        ax4.invert_yaxis()

        # ── Panel 6: Confidence lollipop ─────────────────────────────
        ax5 = fig.add_subplot(gs[1, 2])
        _apply_theme(ax5)
        confs = [r.confidence_score for r in self._results]
        for i, (c, cl) in enumerate(zip(confs, col)):
            ax5.plot([0, c], [i, i], color=cl, linewidth=2, alpha=0.6)
        ax5.scatter(confs, range(len(names)), c=col, s=60, zorder=3,
                    edgecolors="white", linewidth=0.8)
        ax5.axvline(x=bl.avg_confidence, color=_COLORS["baseline"],
                    linestyle="--", linewidth=1, alpha=0.6)
        ax5.set_yticks(range(len(names)))
        ax5.set_yticklabels(names, fontsize=8)
        ax5.set_xlabel("Confidence %", fontsize=9)
        ax5.set_title("Confidence Scores", fontsize=11, fontweight="bold",
                       color=_COLORS["text"], pad=8)
        ax5.set_xlim(-5, 115)
        ax5.invert_yaxis()

        fig.suptitle("COBOL → Python Pipeline — Evaluation Dashboard",
                     fontsize=16, fontweight="bold", color=_COLORS["text"], y=0.98)
        return fig
