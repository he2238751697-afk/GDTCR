#!/usr/bin/env python3
"""Compile the author-review PDFs from TeX, retaining logs and input hashes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ("manuscript_bmc.tex", "gdtcr_bmc_revision"),
    ("supplementary_methods_bmc.tex", "additional_file_1_bmc"),
)
SUPERVISOR_DOCUMENTS = (
    ("supervisor_review/manuscript.tex", "GDTCR_supervisor_review"),
    ("supervisor_review/supplementary.tex", "GDTCR_supplementary"),
)
REVIEW_NOTES = (
    ("supervisor_review/review_notes.tex", "GDTCR_review_notes"),
    ("supervisor_review/journal_comparison.tex", "GDTCR_journal_comparison"),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(source_name, name, engine, destination, epoch="1791504000"):
    source = ROOT / "paper" / source_name
    build_dir = destination / "tex" / name
    build_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    # Stable PDF metadata dates; scientific data and manuscript dates are fixed.
    environment["SOURCE_DATE_EPOCH"] = epoch
    environment["FORCE_SOURCE_DATE"] = "1"
    command = [
        engine, "-no-shell-escape", "-halt-on-error", "-interaction=nonstopmode",
        "-file-line-error", "-output-directory=" + str(build_dir), source.name,
    ]
    previous_aux = None
    passes = 0
    for passes in range(1, 6):
        run = subprocess.run(command, cwd=source.parent, env=environment,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (build_dir / f"pass_{passes}.txt").write_text(run.stdout)
        if run.returncode:
            raise RuntimeError(f"TeX failed for {source_name}; see {build_dir}")
        auxiliary = digest(build_dir / (source.stem + ".aux"))
        log = (build_dir / (source.stem + ".log")).read_text(errors="replace")
        unresolved = re.search(
            r"undefined (?:references|citations)|Label\(s\) may have changed|Rerun to get",
            log, re.I)
        if passes >= 2 and auxiliary == previous_aux and not unresolved:
            break
        previous_aux = auxiliary
    else:
        raise RuntimeError(f"Cross-references did not stabilize: {source_name}")
    problems = re.findall(
        r"^.*(?:Overfull \\[hv]box|Missing character|LaTeX Error|undefined references|"
        r"undefined citations|multiply defined|Token not allowed).*$", log, re.M)
    if problems:
        raise RuntimeError(f"Resolve TeX diagnostics in {source_name}: " + "; ".join(problems))
    pdf = destination / (name + ".pdf")
    shutil.copyfile(build_dir / (source.stem + ".pdf"), pdf)
    subprocess.run(["pdftotext", "-layout", str(pdf), str(destination / (name + ".txt"))],
                   check=True)
    info = subprocess.check_output(["pdfinfo", str(pdf)], text=True)
    fonts = subprocess.check_output(["pdffonts", str(pdf)], text=True)
    (destination / (name + ".fonts.txt")).write_text(fonts)
    text = (destination / (name + ".txt")).read_text()
    if any(token in text for token in ("\ufffd", "??", "PERCENTTOKEN", "XMLTOKEN")):
        raise RuntimeError(f"Broken extracted glyph/reference marker: {source_name}")
    figures = {}
    for relative in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", source.read_text()):
        asset = (source.parent / relative).resolve()
        figures[str(asset.relative_to(ROOT))] = digest(asset)
    result = {
        "source": str(source.relative_to(ROOT)), "source_sha256": digest(source),
        "pdf": str(pdf.relative_to(ROOT)), "pdf_sha256": digest(pdf),
        "engine": subprocess.check_output([engine, "--version"], text=True).splitlines()[0],
        "native_compilation_verified": True, "passes": passes,
        "pages": int(re.search(r"^Pages:\s+(\d+)", info, re.M)[1]),
        "figure_sha256": figures, "critical_tex_diagnostics": problems,
        "visual_inspection": "Recorded separately after rendering every page.",
    }
    (destination / (name + ".render.json")).write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("bmc", "supervisor-review"), default="bmc")
    parser.add_argument("--include-review-notes", action="store_true")
    parser.add_argument("--pdflatex", default=shutil.which("pdflatex"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--copy-reading-copies", action="store_true")
    args = parser.parse_args()
    if not args.pdflatex:
        parser.error("Install TeX Live with pdflatex or supply --pdflatex /absolute/path")
    supervisor = args.profile == "supervisor-review"
    destination = (args.output or ROOT / ("output/supervisor_review" if supervisor else "output/pdf")).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    documents = SUPERVISOR_DOCUMENTS if supervisor else DOCUMENTS
    if args.include_review_notes:
        if not supervisor:
            parser.error("--include-review-notes requires --profile supervisor-review")
        documents += REVIEW_NOTES
    epoch = "1793664000" if supervisor else "1791504000"
    records = [build(source, name, args.pdflatex, destination, epoch) for source, name in documents]
    if args.copy_reading_copies:
        reading = ROOT / ("paper/supervisor_review" if supervisor else "paper/reading_copies")
        reading.mkdir(exist_ok=True)
        for _, name in documents:
            shutil.copyfile(destination / (name + ".pdf"), reading / (name + ".pdf"))
    report = ROOT / ("paper/supervisor_review/native_compile.json" if supervisor else "paper/final_submission/native_compile.json")
    report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps({"native_compilation_verified": True,
                                 "documents": records}, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
