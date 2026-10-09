"""Publication plots for the prespecified completion-v2 sensitivity analyses."""

import math
import statistics

import matplotlib.pyplot as plt
import numpy as np

from render_results_v2 import COLORS, DIRECTIONS, DIRECTION_LABELS, PRIMARY


def has(evidence, names, mode="free"):
    return all((name, seed, mode) in evidence.runs for name in names for seed in (0, 1))


def seed_pair(evidence, name, mode, direction, metric, scale=1., prefix=PRIMARY):
    return np.array([evidence.estimate(name, seed, mode, direction, metric, prefix=prefix)
                     for seed in (0, 1)]) * scale


def figure_efficiency(evidence, figures):
    names = [f"data_fraction{n}/{m}" for n in (10, 25, 50) for m in ("pretrained", "random")]
    if not has(evidence, names + ["split_seed17/paired", "split_seed17/random"]):
        return
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.2), layout="constrained")
    subsets = evidence.raw["data_audit"]["protocols"]["split_seed17"]["nested_subsets"]
    x = np.array([subsets[str(fraction)]["pairs"] for fraction in (10, 25, 50, 100)])
    for i, direction in enumerate(DIRECTIONS):
        for j, metric in enumerate(("query_mean_nll", "coverage")):
            ax = axes[i, j]
            scale = 1 if j == 0 else 100
            for color, model in zip(COLORS, ("pretrained", "random")):
                ns = [f"data_fraction{n}/{model}" for n in (10, 25, 50)] + ["split_seed17/" + ("paired" if model == "pretrained" else "random")]
                values = np.array([seed_pair(evidence, n, "free", direction, metric, scale) for n in ns])
                ax.plot(x, values.mean(axis=1), "o-", color=color, label=model.capitalize(), ms=4)
                ax.fill_between(x, values.min(axis=1), values.max(axis=1), color=color, alpha=.14)
                ax.scatter(np.repeat(x, 2), values.flatten(), color=color, s=11, alpha=.6)
            ax.set_xscale("log")
            ax.set_xticks(x, [f"{n:,}" for n in x], fontsize=8, rotation=45, ha="right")
            ax.minorticks_off()
            ax.set_xlabel("Actual supervised edges (log scale)")
            ax.set_ylabel("Nats / target token" if j == 0 else "Recorded coverage (%)")
            ax.set_title(DIRECTION_LABELS[direction], loc="left", weight="bold")
            ax.grid(axis="y", alpha=.2)
            if j:
                ax.set_ylim(bottom=0)
    axes[0, 0].legend(frameon=False)
    figures.save(fig, "figure_4_data_efficiency", "Nested complete-component data-efficiency comparison on split 17. Lines are two-seed means; shading spans the two fitted-model estimates and is not a confidence interval. Actual subsets contain 725/1,814/2,249/7,254 edges (10.0/25.0/31.0/100%). The nominal 50% set is undersized. All smaller sets contain only singleton components; the largest component enters at full data, changing composition as well as sample size.")


def figure_protocols(evidence, figures):
    def names(direction):
        return ["split_seed17", "unseen_input_" + direction, "seen_input_" + direction, "source_holdout", "source_shared"]
    required = sorted({p + "/" + m for d in DIRECTIONS for p in names(d) for m in ("paired", "constant")})
    if not has(evidence, required):
        return
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.6), layout="constrained")
    labels = ("Component\ndisjoint", "Unseen\ninput", "Seen input /\nunseen edge", "Strict\nsource", "Shared\nsource")
    for i, direction in enumerate(DIRECTIONS):
        for j, metric in enumerate(("query_mean_nll", "coverage", "likelihood|hit_at_5")):
            ax = axes[i, j]
            scale = 1 if j == 0 else 100
            for k, model in enumerate(("paired", "constant")):
                values = np.array([seed_pair(evidence, p + "/" + model, "free", direction, metric, scale) for p in names(direction)])
                x = np.arange(5) + (k - .5) * .32
                ax.bar(x, values.mean(axis=1), width=.29, color=COLORS[k], alpha=.78, label="Conditional" if k == 0 else "Constant source")
                for seed in (0, 1):
                    ax.scatter(x + (seed - .5) * .065, values[:, seed], s=12, color="#222222", marker="o" if seed == 0 else "x")
            ax.set_xticks(range(5), labels, rotation=22, ha="right", fontsize=8)
            ax.set_title(DIRECTION_LABELS[direction] + ("  |  NLL" if j == 0 else "  |  Coverage" if j == 1 else "  |  Hit@5"), loc="left")
            ax.set_ylabel("Nats / target token" if j == 0 else "Query macro (%)")
            ax.grid(axis="y", alpha=.2)
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="outside upper center", ncols=2,
               frameon=False, fontsize=9)
    figures.save(fig, "figure_5_exposure_protocols", "Distinct exposure protocols at 64 draws, shown as two-seed means with individual fitted-model points. The component-disjoint reference is split 17. Directional and source protocols use different query populations and training sets; changes across columns are diagnostic, not causal effects or independent replication. Unseen gamma-to-delta checkpoint selection has only one input and no ranking distractors. Study holdout is not donor-independent validation.")


def figure_budget_rejection(evidence, figures):
    if not has(evidence, ["split_seed17/paired", "split_seed17/constant"]):
        return
    evaluations = {r["seed"]: r for r in evidence.raw["evaluations"].values()
                   if r["evaluation_name"] == "split_seed17/paired"}
    if len(evaluations) != 2:
        return
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), layout="constrained")
    for i, direction in enumerate(DIRECTIONS):
        ax = axes[i, 0]
        for k, model in enumerate(("paired", "constant")):
            for policy, style in (("allow_training_targets", "-"), ("exclude_training_targets", "--")):
                values = np.array([seed_pair(evidence, "split_seed17/" + model, "free", direction,
                                             "likelihood|hit_at_5", 100, f"{n}/{policy}") for n in (16, 64, 256)])
                ax.plot((16, 64, 256), values.mean(axis=1), style, marker="o", ms=4, color=COLORS[k],
                        label=("Conditional" if k == 0 else "Constant") + (", allow" if style == "-" else ", exclude"))
        ax.set_xscale("log", base=4)
        ax.set_xticks((16, 64, 256), ("16", "64", "256"))
        ax.set_xlabel("Saved sampling prefix (draws)")
        ax.set_ylabel("Likelihood Hit@5 (%)")
        ax.set_title(DIRECTION_LABELS[direction] + "  |  Budget and target policy", loc="left")
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", alpha=.2)
        ax = axes[i, 1]
        recorded_hits = []
        for seed, result in sorted(evaluations.items()):
            summary = result["modes"]["free"]["analyzed"]["directions"][direction]
            for k, method in enumerate(("likelihood", "ranker", "fused")):
                curve = summary["acceptance_curves"][method]
                points = curve["points"]
                recorded_hits.extend(p["recorded_hit_at_5"] for p in points)
                ax.plot([100 * p["accepted_query_fraction"] for p in points],
                        [100 * p["recorded_hit_at_5"] for p in points], color=COLORS[k],
                        linestyle="-" if seed == 0 else "--", linewidth=1.1,
                        label=method.capitalize() if seed == 0 else None)
                chosen = summary["calibrated"][PRIMARY][method]
                ax.scatter(100 * chosen["accepted_query_fraction"], 100 * chosen["hit_at_5"],
                           color=COLORS[k], marker="o" if seed == 0 else "x", s=25)
        ax.set_xlabel("Queries with accepted candidates (%)")
        ax.set_ylabel("Recorded Hit@5 / all queries (%)")
        ax.set_title(DIRECTION_LABELS[direction] + "  |  64-draw rejection", loc="left")
        ax.set_xlim(-2, 102)
        ax.set_ylim(bottom=0)
        if recorded_hits and not any(recorded_hits):
            ax.set_ylim(0, .1)
            ax.text(.5, .5, "Zero recorded Hit@5\nat all thresholds", transform=ax.transAxes,
                    ha="center", va="center", color="#555555", fontsize=10)
        ax.grid(alpha=.2)
    axes[0, 0].legend(frameon=False, fontsize=7.5, ncols=2)
    axes[0, 1].legend(frameon=False, fontsize=8)
    figures.save(fig, "figure_6_budget_rejection", "Split-17 sampling-budget and rejection sensitivity. Left: two-seed mean likelihood Hit@5 from nested 16/64/256-draw prefixes with training targets allowed or excluded. Right: calibration-quantile acceptance curves for each seed (solid/dashed); markers are independently calibrated thresholds. All test queries remain in the Hit@5 denominator. No point selects a threshold using test results.")


def figure_pretraining(evidence, figures):
    names = ("split_seed17/paired", "pretrain_raw", "pretrain_balanced", "pretrain_gamma", "pretrain_delta")
    conditions = ("sqrt", "raw", "balanced", "gamma", "delta")
    denoising = evidence.raw["denoising"]
    if not all(f"{c}/seed-{s}/denoising_audit.json" in denoising for c in conditions for s in (0, 1)):
        return
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), layout="constrained")
    labels = ("Sqrt", "Raw", "Balanced", "Gamma only", "Delta only")
    for j, chain in enumerate(("gamma", "delta")):
        x = np.arange(5) + (j - .5) * .25
        vals = np.array([[denoising[f"{c}/seed-{s}/denoising_audit.json"]["chains"][chain]["damaged_residue_accuracy"]
                          for s in (0, 1)] for c in conditions]) * 100
        axes[0].plot(x, vals.mean(axis=1), "o-", color=COLORS[j], label=chain.capitalize())
        axes[0].vlines(x, vals.min(axis=1), vals.max(axis=1), color=COLORS[j])
        copy = [100 * statistics.mean(denoising[f"{c}/seed-{s}/denoising_audit.json"]["chains"][chain]["aligned_copy_damaged_residue_accuracy"] for s in (0, 1)) for c in conditions]
        axes[0].plot(x, copy, ":", color=COLORS[j], alpha=.7)
    axes[0].set_title("A  Frozen corruption validation", loc="left")
    axes[0].set_ylabel("Accuracy at selected sites (%)")
    axes[0].legend(frameon=False, fontsize=8)
    for i, direction in enumerate(DIRECTIONS):
        ax = axes[i + 1]
        if has(evidence, names):
            for j, name in enumerate(names):
                values = seed_pair(evidence, name, "free", direction, "query_mean_nll")
                ax.scatter(j + np.array([-.07, .07]), values, color=COLORS[j], s=26)
                ax.plot((j - .2, j + .2), (values.mean(), values.mean()), color=COLORS[j])
        ax.set_title(chr(66 + i) + "  Downstream " + DIRECTION_LABELS[direction], loc="left")
        ax.set_ylabel("Nats / target token")
    for ax in axes:
        ax.set_xticks(range(5), labels, rotation=28, ha="right")
        ax.grid(axis="y", alpha=.2)
    figures.save(fig, "figure_S1_pretraining", "Pretraining mixtures and downstream split-17 NLL. Left: two-seed reconstruction accuracy at corruption-selected sites, including the unchanged fraction of the 80/10/10 rule and deleted sites; aligned-copy accuracy is dotted and vertical ranges span fitted seeds. Other panels retain each downstream fitted-model estimate. All mixtures use 20,480,000 sequence draws; equal draws do not imply equal chain-specific or token exposure.")


def figure_negatives(evidence, figures):
    names = ["negative_ranker/" + x for x in ("random1", "random3", "random5", "mixed1", "mixed5")]
    if not has(evidence, names + ["split_seed17/paired"], "pools"):
        return
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.2), layout="constrained")
    labels = ("Random 1", "Random 3", "Random 5", "Mixed 1", "Mixed 3", "Mixed 5")
    names.insert(4, "split_seed17/paired")
    for i, direction in enumerate(DIRECTIONS):
        for j, (mode, metric) in enumerate((("free", "ranker|hit_at_5"), ("pools", "random|ranker|hit_at_5"))):
            ax = axes[i, j]
            plotted = []
            for k, name in enumerate(names):
                values = seed_pair(evidence, name, mode, direction, metric, 100)
                if not np.isfinite(values).all():
                    continue
                plotted.extend(values)
                ax.bar(k, values.mean(), width=.62, color=COLORS[0] if k < 3 else COLORS[1], alpha=.7)
                ax.scatter(k + np.array([-.08, .08]), values, s=20, color="#222222")
            ax.set_xticks(range(6), labels, rotation=30, ha="right")
            ax.set_ylabel("Ranker Hit@5 (%)")
            ax.set_title(DIRECTION_LABELS[direction] + ("  |  Free 64 draws" if mode == "free" else "  |  Random retrieval pool"), loc="left")
            ax.set_ylim(bottom=0)
            if plotted and not any(plotted):
                ax.text(.5, .5, "No recorded top-5 hits\nin any fitted condition", transform=ax.transAxes,
                        ha="center", va="center", color="#555555", fontsize=10)
            ax.grid(axis="y", alpha=.2)
    figures.save(fig, "figure_S2_negative_training", "Ranker negative-training sensitivity on split 17. Ratios 1/3/5 use random-only or mixed random/length-motif negatives. Bars average two model seeds; points retain each fitted ranker. Every setting reuses the primary generator's exact saved candidates and fixed pools, so differences reflect ranking and calibration rather than a new sampling budget.")


def additional_figures(evidence, figures):
    figure_efficiency(evidence, figures)
    figure_protocols(evidence, figures)
    figure_budget_rejection(evidence, figures)
    figure_pretraining(evidence, figures)
    figure_negatives(evidence, figures)
