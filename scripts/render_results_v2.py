#!/usr/bin/env python3
"""Create publication tables and scientific figures only from collected evidence."""

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


SPLITS = (17, 3407, 2026)
DIRECTIONS = ("gamma_to_delta", "delta_to_gamma")
DIRECTION_LABELS = {"gamma_to_delta": "γ → δ", "delta_to_gamma": "δ → γ",
                    "equal_direction_macro": "Equal-direction mean"}
PRIMARY = "64/allow_training_targets"
COLORS = ("#186A8D", "#D06B36", "#47956B", "#8552A1", "#A88820", "#666666")


def tsv(path, rows):
    rows = list(rows)
    if not rows:
        return 0
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


class Evidence:
    def __init__(self, raw):
        self.raw = raw
        self.runs = {(r["evaluation_name"], r["model_seed_index"], r["mode"]): r
                     for r in raw["reports"] if r.get("evaluation_name")}
        self.baselines = {(r["protocol_name"], r["baseline"], r["model_seed_index"]): r
                          for r in raw["reports"] if r.get("baseline")}

    def metric(self, name, seed, mode, direction, metric, prefix=PRIMARY):
        report = self.runs.get((name, seed, mode))
        if report is None:
            return None
        return self.report_metric(report, direction, metric, prefix)

    @staticmethod
    def report_metric(report, direction, metric, prefix=PRIMARY):
        summary = report["summary"]
        if direction == "equal_direction_macro":
            group = summary["equal_direction_macro"]
        elif direction in summary["directions"]:
            group = summary["directions"][direction]["query_macro"]
        else:
            return None
        values = group["metrics"]
        if metric in values:
            return values[metric]
        return values.get(prefix + "|" + metric)

    def estimate(self, *args, **kwargs):
        item = self.metric(*args, **kwargs)
        return item["estimate"] if item is not None else float("nan")

    def split_means(self, model, mode, direction, metric):
        return [statistics.mean(self.estimate(f"split_seed{s}/{model}", seed, mode, direction, metric)
                                for seed in (0, 1)) for s in SPLITS]


def compact_rows(evidence):
    for (name, seed, mode), report in sorted(evidence.runs.items()):
        if mode != "free":
            continue
        for direction in (*report["summary"]["directions"], "equal_direction_macro"):
            row = {"evaluation": name, "seed_index": seed, "training_seed": 3407 + 101 * seed,
                   "protocol": report["protocol_name"], "direction": direction}
            if direction != "equal_direction_macro":
                row.update(n_queries=report["summary"]["directions"][direction]["n_queries"],
                           n_recorded_edges=report["summary"]["directions"][direction]["n_recorded_edges"])
            for metric in ("query_mean_nll", "coverage", "partner_recovery_fraction", "valid_draw_fraction",
                           "unique_candidates", "novel_draw_fraction", "length_entropy", "terminal_motif_entropy",
                           "likelihood|hit_at_5", "ranker|hit_at_5", "fused|hit_at_5", "likelihood|mrr"):
                item = evidence.report_metric(report, direction, metric)
                if item is not None:
                    for key in ("estimate", "lower", "upper", "events", "denominator"):
                        if key in item:
                            row[metric + "|" + key] = item[key]
            yield row


def primary_descriptives(evidence):
    for model in ("paired", "constant", "random", "shuffled"):
        for direction in (*DIRECTIONS, "equal_direction_macro"):
            for metric in ("query_mean_nll", "coverage", "partner_recovery_fraction",
                           "likelihood|hit_at_5", "ranker|hit_at_5", "fused|hit_at_5"):
                values = evidence.split_means(model, "free", direction, metric)
                if not all(math.isfinite(v) for v in values):
                    continue
                yield {"model": model, "direction": direction, "metric": metric,
                       "mean": statistics.mean(values), "sd_of_three_split_means": statistics.stdev(values),
                       **{f"split_{s}_seed_average": v for s, v in zip(SPLITS, values)},
                       "uncertainty": "descriptive between-split SD; not independent-subject SEM"}


def retrieval_rows(evidence):
    for report in evidence.raw["reports"]:
        if report["mode"] != "pools":
            continue
        for direction in (*report["summary"]["directions"], "equal_direction_macro"):
            values = report["summary"]["equal_direction_macro"]["metrics"] if direction == "equal_direction_macro" else report["summary"]["directions"][direction]["query_macro"]["metrics"]
            for key, item in values.items():
                pool, method, metric = key.split("|")
                if metric not in ("hit_at_5", "mrr", "recall_at_5"):
                    continue
                yield {"evaluation": report.get("evaluation_name") or report["baseline"],
                       "protocol": report["protocol_name"], "seed_index": report["model_seed_index"],
                       "direction": direction, "pool": pool, "method": method, "metric": metric,
                       **{k: item.get(k) for k in ("estimate", "lower", "upper", "events", "denominator")}}


def budget_rows(evidence):
    for (name, seed, mode), report in sorted(evidence.runs.items()):
        if mode != "free":
            continue
        for direction, entry in report["summary"]["directions"].items():
            by_prefix = {}
            for key, item in entry["query_macro"]["metrics"].items():
                if "/" not in key.split("|")[0]:
                    continue
                prefix, metric = key.split("|", 1)
                if metric not in ("coverage", "partner_recovery_fraction", "valid_draw_fraction",
                                  "unique_candidates", "novel_draw_fraction", "length_entropy",
                                  "terminal_motif_entropy", "likelihood|hit_at_5", "ranker|hit_at_5", "fused|hit_at_5"):
                    continue
                row = by_prefix.setdefault(prefix, {"evaluation": name, "seed_index": seed,
                    "direction": direction, "draws": int(prefix.split("/")[0]), "policy": prefix.split("/")[1]})
                for field in ("estimate", "lower", "upper"):
                    row[metric + "|" + field] = item[field]
            yield from by_prefix.values()


def calibration_rows(evidence):
    for evaluation in evidence.raw["evaluations"].values():
        for mode, result in evaluation["modes"].items():
            settings = result["calibration"]
            for direction, calibration in settings["calibration"].items():
                for method, threshold in calibration["methods"].items():
                    row = {"evaluation": evaluation["evaluation_name"], "seed_index": evaluation["seed"],
                           "mode": mode, "direction": direction, "method": method,
                           "ranker_weight": settings["fusion"]["alpha"],
                           "calibration_mode": threshold["mode"], "threshold_value": threshold["value"],
                           "calibration_recorded_positives": threshold["positives"],
                           "calibration_constructed_negatives": threshold["negatives"],
                           "reason": threshold["reason"], "balanced_accuracy": threshold["balanced_accuracy"],
                           "settings_sha256": result["settings_sha256"]}
                    if mode == "free":
                        values = result["analyzed"]["directions"][direction]["calibrated"][PRIMARY][method]
                        row.update({"test_" + k: v for k, v in values.items()})
                    yield row


def sampling_grid_rows(evidence):
    for grid in evidence.raw.get("sampling_grids", []):
        best = grid["summary"]["tuning_best"]
        for cell in grid["cells"]:
            for direction, values in sorted(cell["summary"]["directions"].items()):
                prefix = values["prefixes"][PRIMARY]
                yield {"evaluation": grid["evaluation"], "seed_index": grid["seed_index"],
                       "selection_data": grid["summary"]["selection_data"],
                       "temperature": cell["temperature"], "top_p": cell["top_p"],
                       "direction": direction, "n_queries": values["n_queries"],
                       "likelihood_hit_at_5": prefix["methods"]["likelihood"]["hit_at_5"],
                       "coverage": prefix["methods"]["likelihood"]["coverage"],
                       "valid_draw_fraction": prefix["valid_draw_fraction"],
                       "unique_candidates": prefix["mean_unique_candidates"],
                       "novel_draw_fraction": prefix["mean_novel_draw_fraction"],
                       "equal_direction_tuning_hit_at_5": cell["mean_hit_at_5"],
                       "tuning_best": (cell["temperature"], cell["top_p"]) == (best["temperature"], best["top_p"]),
                       "primary_replaced": grid["summary"]["primary_replaced"],
                       "cell_summary_sha256": cell["summary_sha256"]}


def training_rows(evidence):
    audit = evidence.raw.get("training_audit")
    runs = audit["runs"] if audit else []
    metadata = {row["task_id"]: row for row in evidence.raw["training"]}
    for run in runs:
        row = {key: run.get(key) for key in ("task_id", "phase", "seed", "steps", "nominal_steps", "batch_size",
                                           "selected_step", "selected_metric", "elapsed_seconds", "device_name",
                                           "parameter_count", "train_pairs", "constructed_negative_draws",
                                           "positive_pair_draws", "peak_allocated_gib")}
        details = metadata.get(run["task_id"], {})
        for key in ("parameter_count", "trainable_parameter_count"):
            if key in details.get("model_metadata", {}):
                row[key] = details["model_metadata"][key]
        for key in ("initialization_checkpoint", "initialization_sha256"):
            row[key] = details.get(key)
        for field in ("sequence_exposure", "target_token_exposure", "negative_audit"):
            row.update({field + "|" + k: v for k, v in run.get(field, {}).items()})
        yield row


def data_protocol_rows(evidence):
    for name, protocol in evidence.raw["data_audit"]["protocols"].items():
        roles = {**protocol["parts"],
                 **{"validation_" + role: value for role, value in protocol["validation_roles"].items()}}
        if "nested_subsets" in protocol:
            roles.update({"train_fraction" + fraction: value for fraction, value in protocol["nested_subsets"].items()})
        for role, value in roles.items():
            yield {"protocol": name, "evaluated_direction": protocol["direction"], "role": role,
                   "pairs": value["pairs"], "components": value["components"],
                   "largest_component_pairs": value["largest_component_pairs"],
                   "gamma_queries": value["queries"]["gamma_to_delta"],
                   "delta_queries": value["queries"]["delta_to_gamma"],
                   **{"study_" + study: count for study, count in value["studies"].items()},
                   **{f"{chains}_{parts}_exact_overlap": count
                      for parts, chains_counts in protocol["exact_chain_overlap"].items()
                      for chains, count in chains_counts.items()}}


def pretraining_exposure_rows(evidence):
    runs = []
    for run in evidence.raw["training"]:
        if run["task_id"].startswith("pretrain-"):
            runs.append({"path": run["path"], "seed": run["arguments"]["seed"],
                         "condition": run["arguments"]["sampling"], "reconstructed": False,
                         **run["summary"]})
    for run in evidence.raw["pretrain_exposure"]["recovered"]:
        runs.append({**run, "condition": "source_sqrt" if "/source_holdout/" in run["path"] else "sqrt"})
    for run in runs:
        sequences, tokens = run["chain_sequences_this_invocation"], run["chain_target_tokens_this_invocation"]
        total = sum(sequences.values())
        yield {"condition": run["condition"], "training_seed": run["seed"], "path": run["path"],
               "reconstructed": run["reconstructed"], "total_sequence_draws": total,
               "observed_gamma_fraction": sequences["gamma"] / total,
               **{"sequence_draws_" + chain: value for chain, value in sequences.items()},
               **{"target_tokens_including_eos_" + chain: value for chain, value in tokens.items()}}


def paired_endpoint_rows(evidence):
    for report in evidence.raw["paired_comparisons"]:
        summary = report["summary"]
        for direction in (*summary["directions"], "equal_direction_macro"):
            group = summary["equal_direction_macro"] if direction == "equal_direction_macro" else summary["directions"][direction]["query_macro"]
            for key, values in group["metrics"].items():
                metric = key.split("|")[-1]
                if metric not in ("query_mean_nll", "coverage", "partner_recovery_fraction", "hit_at_5", "mrr", "recall_at_5"):
                    continue
                if report["mode"] == "free" and key != "query_mean_nll" and not key.startswith(PRIMARY + "|"):
                    continue
                yield {"comparison": report["comparison_name"], "seed_index": report["model_seed_index"],
                       "mode": report["mode"], "protocol": report["protocol_name"], "direction": direction,
                       "metric": key, "definition": summary["definition"], "left": summary["left"],
                       "right": summary["right"], "interpretation": summary["interpretation"], **values}


class Figures:
    def __init__(self, output, partial):
        self.output, self.partial, self.records = output, partial, []
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                             "axes.spines.top": False, "axes.spines.right": False,
                             "savefig.dpi": 300, "pdf.fonttype": 42})

    def save(self, fig, key, caption):
        if self.partial:
            fig.text(.99, .005, "PROVISIONAL - INCOMPLETE EVIDENCE", ha="right", fontsize=7, color="#9F241C")
        fig.savefig(self.output / (key + ".pdf"), bbox_inches="tight")
        fig.savefig(self.output / (key + ".png"), bbox_inches="tight")
        plt.close(fig)
        self.records.append({"id": key, "caption": caption,
                             "pdf": key + ".pdf", "png": key + ".png"})


def figure_data(evidence, figures):
    master = evidence.raw["data_audit"]["master"]
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), layout="constrained")
    values = [master["largest_component_pairs"], master["pairs"] - master["largest_component_pairs"]]
    bars = axes[0].bar(["Largest component", "All other components"], values, color=COLORS[:2], width=.58)
    axes[0].bar_label(bars, labels=[f"{v:,} ({v / master['pairs']:.1%})" for v in values], padding=4)
    axes[0].set_ylim(0, max(values) * 1.2)
    axes[0].set_ylabel("Unique recorded pairs")
    axes[0].set_title("A  Pairing-graph concentration", loc="left", weight="bold")
    strata = evidence.raw["distance_audit"]["test_strata"]
    # Exact distance-bin counts are read from the inspected distance audit.
    gamma = []
    for split in SPLITS:
        item = strata[f"split_seed{split}"]
        bins = item["gamma"]["pretraining"]
        gamma.append([bins.get(label, 0) for label in ("0", "1", "2", "ge3")])
    array = np.array(gamma, dtype=float)
    bottom = np.zeros(3)
    for j, label in enumerate(("0 edits", "1 edit", "2 edits", "≥3 edits")):
        percent = 100 * array[:, j] / array.sum(axis=1)
        axes[1].bar(range(3), percent, bottom=bottom, color=COLORS[j], label=label, width=.6)
        bottom += percent
    axes[1].set_xticks(range(3), [str(s) for s in SPLITS])
    axes[1].set_xlabel("Component split seed")
    axes[1].set_ylabel("Test γ queries (%)")
    axes[1].set_title("B  Nearest pretraining γ sequence", loc="left", weight="bold")
    axes[1].legend(loc="upper center", bbox_to_anchor=(.5, -.19), ncols=2, frameon=False)
    figures.save(fig, "figure_1_data", "Pairing-graph concentration and exact full-sequence Levenshtein proximity of test gamma queries to pretraining. Exact-chain exclusion does not remove near neighbors. The distant-edge counts are 5, 5 and 3 across the primary splits.")


def figure_main(evidence, figures):
    if not all((f"split_seed{s}/paired", seed, "free") in evidence.runs for s in SPLITS for seed in (0, 1)):
        return
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.8), layout="constrained")
    for i, direction in enumerate(DIRECTIONS):
        for j, metric in enumerate(("query_mean_nll", "coverage", "likelihood|hit_at_5")):
            ax = axes[i, j]
            groups = [("paired", metric, "Conditional"), ("constant", metric, "Constant"),
                      ("random", metric, "Random init."), ("shuffled", metric, "Shuffled input")]
            if j == 2:
                groups = [("paired", "likelihood|hit_at_5", "Likelihood"), ("paired", "ranker|hit_at_5", "Ranker"),
                          ("paired", "fused|hit_at_5", "Fusion"), ("constant", metric, "Constant"),
                          ("random", metric, "Random init."), ("shuffled", metric, "Shuffled input")]
            scale = 1 if j == 0 else 100
            plotted = []
            for x, (model, name, label) in enumerate(groups):
                vals = np.asarray(evidence.split_means(model, "free", direction, name)) * scale
                if not np.isfinite(vals).all():
                    continue
                plotted.extend(vals)
                color_index = {"paired": 0, "constant": 1, "random": 2, "shuffled": 3}[model]
                if model == "paired" and j == 2 and name != "likelihood|hit_at_5":
                    color_index = 4 if name.startswith("ranker") else 5
                color = COLORS[color_index]
                ax.scatter(x + np.array([-.13, 0, .13]), vals, color=color, s=19, alpha=.6)
                ax.errorbar(x, vals.mean(), yerr=vals.std(ddof=1), color=color, fmt="D", ms=5, capsize=3)
            if j == 2 and plotted and not any(plotted):
                ax.text(.5, .55, "No recorded top-5 hits\nin any primary fit", transform=ax.transAxes,
                        ha="center", va="center", fontsize=10, color="#555555")
            ax.set_xticks(range(len(groups)), [g[2] for g in groups], rotation=32, ha="right")
            ax.set_title(DIRECTION_LABELS[direction] + ("  |  NLL" if j == 0 else "  |  Coverage" if j == 1 else "  |  Hit@5"), loc="left")
            ax.set_ylabel("Nats / target token" if j == 0 else "Query macro (%)")
            if j:
                ax.set_ylim(bottom=0)
            ax.grid(axis="y", alpha=.2)
    figures.save(fig, "figure_2_primary", "Primary free-generation results at 64 draws. Small points are the three split means after averaging two model seeds. Diamonds and bars are their mean and descriptive standard deviation, not independent-subject confidence intervals. Likelihood, ranker and fusion order the same conditional candidates.")


def figure_retrieval(evidence, figures):
    if not all((f"split_seed{s}/paired", seed, "pools") in evidence.runs for s in SPLITS for seed in (0, 1)):
        return
    methods = ("likelihood", "ranker", "fused", "prior", "shuffled", "difference", "edit_neighbor", "shallow", "frequency", "random")
    pools = ("random", "length", "motif", "edit", "full")
    fig, axes = plt.subplots(1, 2, figsize=(10.3, 5), layout="constrained")
    matrices = []
    for direction in DIRECTIONS:
        matrix = []
        for method in methods:
            row = []
            for pool in pools:
                values = []
                for split in SPLITS:
                    for seed in (0, 1):
                        if method in ("edit_neighbor", "frequency", "shallow"):
                            kind, bseed = ("shallow", seed) if method == "shallow" else ("exact_neighbor", None)
                            report = evidence.baselines.get((f"split_seed{split}", kind, bseed))
                            item = evidence.report_metric(report, direction, pool + "|" + method + "|hit_at_5") if report else None
                        else:
                            item = evidence.metric(f"split_seed{split}/paired", seed, "pools", direction, pool + "|" + method + "|hit_at_5")
                        if item:
                            values.append(item["estimate"])
                row.append(100 * statistics.mean(values) if len(values) == 6 else np.nan)
            matrix.append(row)
        matrices.append(np.asarray(matrix))
    vmax = max(np.nanmax(m) for m in matrices)
    for ax, matrix, direction in zip(axes, matrices, DIRECTIONS):
        im = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(5), ["Random", "Length", "Motif", "Edit", "Full"])
        ax.set_yticks(range(len(methods)), [m.replace("_", " ") for m in methods])
        ax.set_title(DIRECTION_LABELS[direction], loc="left", weight="bold")
        for i in range(len(methods)):
            for j in range(5):
                value = matrix[i, j]
                ax.text(j, i, f"{value:.1f}" if math.isfinite(value) else "NA", ha="center", va="center", fontsize=8,
                        color="white" if value > vmax * .55 else "#111111")
    fig.colorbar(im, ax=axes, label="Mean query-macro Hit@5 (%)", shrink=.8)
    figures.save(fig, "figure_3_retrieval", "Fixed-pool retrieval, averaged over two seeds within each of three primary splits and then equally over splits. Pools include all recorded positives by construction and up to 100 unrecorded distractors, or the full role-specific target universe. Deterministic baselines have one value per split. Frequency scores are all zero under primary chain exclusion; that row reflects lexicographic tie breaking, not informative frequency prediction.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    raw = json.loads(args.evidence.read_text())
    if not raw["complete"] and not args.allow_partial:
        raise ValueError("Final figures require complete evidence")
    begin_run(args.output, args, [args.evidence])
    evidence = Evidence(raw)
    tables = args.output / "tables"
    tables.mkdir()
    figures_path = args.output / "figures"
    figures_path.mkdir()
    exports = {"free_runs.tsv": compact_rows(evidence), "primary_descriptives.tsv": primary_descriptives(evidence),
               "retrieval.tsv": retrieval_rows(evidence), "budgets_and_policies.tsv": budget_rows(evidence),
               "calibration.tsv": calibration_rows(evidence), "training.tsv": training_rows(evidence),
               "data_protocols.tsv": data_protocol_rows(evidence),
               "pretraining_exposure.tsv": pretraining_exposure_rows(evidence),
               "paired_endpoints.tsv": paired_endpoint_rows(evidence),
               "qualitative_examples.tsv": ({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                                             for key, value in row.items()}
                                            for row in raw.get("qualitative_examples", {}).get("rows", [])),
               "validation_information.tsv": raw.get("validation_candidate_information", []),
               "frequency_ties.tsv": raw.get("frequency_tie_information", []),
               "source_event_clusters.tsv": raw.get("source_event_clusters", []),
               "sampling_grid.tsv": sampling_grid_rows(evidence)}
    counts = {name: tsv(tables / name, rows) for name, rows in exports.items()}
    denoising = [{"condition": name.split("/")[0], "seed_index": int(name.split("/")[1].removeprefix("seed-")),
                  "chain": chain, **values} for name, report in raw["denoising"].items()
                 for chain, values in report["chains"].items()]
    counts["denoising.tsv"] = tsv(tables / "denoising.tsv", denoising)
    figures = Figures(figures_path, not raw["complete"])
    figure_data(evidence, figures)
    figure_main(evidence, figures)
    figure_retrieval(evidence, figures)
    from plot_sensitivity_v2 import additional_figures
    additional_figures(evidence, figures)
    from publication_latex_tables import generate
    latex_tables = generate(evidence)
    for name, value in latex_tables.items():
        (tables / name).write_text(value)
    result = {"schema_version": 2, "complete": raw["complete"], "evidence_sha256": file_sha256(args.evidence),
              "tables": counts, "figures": figures.records,
              "latex_tables": list(latex_tables),
              "units": "probabilities in TSV; percentages explicitly labeled in plots",
              "aggregation": "two seeds within split, then equal split weight; descriptive SD across three dependent splits"}
    result["output_sha256"] = {str(p.relative_to(args.output)): file_sha256(p)
                               for folder in (tables, figures_path) for p in sorted(folder.iterdir())}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps({"output": str(args.output), "tables": counts, "figures": len(figures.records)}), flush=True)


if __name__ == "__main__":
    main()
