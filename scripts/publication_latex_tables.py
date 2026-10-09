"""Generate the manuscript's numeric tables from the collected evidence."""

import statistics

SPLITS = (17, 3407, 2026)
PRIMARY = "64/allow_training_targets"


def table(caption, label, headings, rows):
    first = .22 if len(headings) >= 6 else .42 if len(headings) > 2 else .62
    widths = [first] + [(.90 - first) / (len(headings) - 1)] * (len(headings) - 1)
    columns = "".join(r"p{" + f"{width:.4f}" + r"\linewidth}" for width in widths)
    lines = [r"\begin{table}[ht]", r"\centering", r"\caption{" + caption + "}",
             r"\label{" + label + "}", r"\small", r"\setlength{\tabcolsep}{3pt}",
             r"\begin{tabular}{" + columns + "}",
             r"\toprule", " & ".join(headings) + r"\\", r"\midrule"]
    lines.extend(" & ".join(str(cell) for cell in row) + r"\\" for row in rows)
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", r"\end{table}"]) + "\n"


def generate(evidence):
    raw = evidence.raw
    warning = "" if raw["complete"] else "PROVISIONAL: incomplete overall evidence. "
    protocols = raw["data_audit"]["protocols"]
    distances = raw["distance_audit"]["test_strata"]
    rows = []
    metrics = (
        ("Training/validation/test edges", lambda p, d: "/".join(str(p["parts"][r]["pairs"]) for r in ("train", "validation", "test"))),
        ("Test gamma queries", lambda p, d: d["gamma"]["queries"]),
        ("Test delta queries", lambda p, d: d["delta"]["queries"]),
        ("Gamma queries one edit from pretraining", lambda p, d: d["gamma"]["pretraining"].get("1", 0)),
        ("Gamma queries at least three edits from pretraining", lambda p, d: d["gamma"]["pretraining"].get("ge3", 0)),
        ("Distant test edges", lambda p, d: d["distant_edges"]))
    for label, value in metrics:
        rows.append([label] + [value(protocols[f"split_seed{s}"], distances[f"split_seed{s}"]) for s in SPLITS])
    output = {"data_table.tex": table(warning + "Primary split structure and proximity to the pretraining pool. "
              "Distance bins use unique test gamma queries. Distant edges require both chains to be at least three "
              "edits from supervised and pretraining references.", "tab:data", ["Split seed", *map(str, SPLITS)], rows)}

    if not all((f"split_seed{s}/{m}", seed, "free") in evidence.runs
               for s in SPLITS for m in ("paired", "constant", "random", "shuffled") for seed in (0, 1)):
        return output

    def descriptive(model, direction, metric, scale):
        values = []
        for s in SPLITS:
            items = [evidence.metric(f"split_seed{s}/{model}", seed, "free", direction, metric) for seed in (0, 1)]
            if any(item is None for item in items):
                return "--"
            values.append(statistics.mean(item["estimate"] for item in items) * scale)
        digits = 3 if scale == 1 else 2
        return f"{statistics.mean(values):.{digits}f}" + r" $\pm$ " + f"{statistics.stdev(values):.{digits}f}"

    rows = []
    for model, name in (("paired", "Conditional"), ("constant", "Constant source"),
                        ("random", "Random init."), ("shuffled", "Shuffled input")):
        for direction, label in (("gamma_to_delta", r"\gtd{}"), ("delta_to_gamma", r"\dtg{}"),
                                 ("equal_direction_macro", "Equal mean")):
            rows.append([name + " / " + label] + [descriptive(model, direction, metric, scale)
                for metric, scale in (("query_mean_nll", 1), ("coverage", 100), ("likelihood|hit_at_5", 100),
                                      ("ranker|hit_at_5", 100), ("fused|hit_at_5", 100))])
    output["primary_table.tex"] = table(warning + "Free generation at 64 draws with training targets allowed. "
        "Values are means and descriptive standard deviations of three split means, each averaging two model seeds. "
        "NLL is in nats per target token; coverage and Hit@5 are percentages. The equal mean weights directions equally. "
        "A dash denotes an unavailable scorer, not a zero outcome.", "tab:primary",
        ["Model / direction", "NLL", "Coverage", "Likelihood Hit@5", "Ranker Hit@5", "Fused Hit@5"], rows)

    comparisons = {(r["comparison_name"], r["model_seed_index"], r["mode"]): r for r in raw["paired_comparisons"]}
    needed = [f"split_seed{s}/{name}" for s in SPLITS for name in (
        "constant/versus_primary", "random/versus_primary", "paired/ranker_minus_likelihood", "paired/fused_minus_likelihood")]
    if not all((name, seed, "free") in comparisons for name in needed for seed in (0, 1)):
        return output

    def difference(name, seed, metric, scale, invert=False):
        item = comparisons[(name, seed, "free")]["summary"]["equal_direction_macro"]["metrics"][metric]
        estimate, low, high = item["estimate"], item["lower"], item["upper"]
        if invert:
            estimate, low, high = -estimate, -high, -low
        digits = 3 if scale == 1 else 2
        def number(value):
            value = round(value * scale, digits) or 0.0
            return f"{value:.{digits}f}"
        return f"{number(estimate)} [{number(low)}, {number(high)}]"

    rows = []
    for split in SPLITS:
        for seed in (0, 1):
            base = f"split_seed{split}/"
            rows.append([str(split) + " / " + str(3407 + 101 * seed),
                         difference(base + "constant/versus_primary", seed, "query_mean_nll", 1, True),
                         difference(base + "constant/versus_primary", seed, PRIMARY + "|likelihood|hit_at_5", 100, True),
                         difference(base + "random/versus_primary", seed, "query_mean_nll", 1, True),
                         difference(base + "paired/ranker_minus_likelihood", seed, PRIMARY + "|hit_at_5", 100),
                         difference(base + "paired/fused_minus_likelihood", seed, PRIMARY + "|hit_at_5", 100)])
    output["paired_primary_table.tex"] = table(warning + r"Primary paired contrasts, with 95\% component-bootstrap "
        "percentile intervals conditional on each fitted model pair and its saved samples. All endpoints are equal-direction "
        "query means at 64 draws. C denotes the pretrained conditional model and P the matched constant-source prior. "
        "NLL differences are nats per token; Hit@5 differences are percentage points. Negative NLL and positive Hit@5 "
        "differences favor the first named condition. Ranker and fusion contrasts reorder the conditional model's identical "
        "candidates. Intervals are not adjusted for multiple comparisons; a zero-event [0,0] interval is not a population upper bound.",
        "tab:paired", ["Split / model seed", "NLL: C minus P", "Hit@5: C minus P", "NLL: C minus random",
                        "Hit@5: ranker minus likelihood", "Hit@5: fused minus likelihood"], rows)
    return output
