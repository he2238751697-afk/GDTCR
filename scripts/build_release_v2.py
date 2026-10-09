#!/usr/bin/env python3
"""Verify the completed local delivery and assemble an anonymous review package."""

import argparse
import datetime
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256
from gdtcr.provenance import begin_run, finish_run


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def slurm_accounting(evidence):
    expected, parents = {}, set()
    for row in evidence["task_status"]:
        record = read(row["record"])
        parent = record.get("slurm_array_job_id")
        index = record.get("slurm_array_task_id")
        job_id = f"{parent}_{index}" if parent and index is not None else record["slurm_job_id"]
        expected[job_id] = row["task_id"]
        parents.add(parent or record["slurm_job_id"])
    require(len(expected) == len(evidence["task_status"]), "Required tasks share a Slurm task identity")
    command = ["sacct", "-X", "-n", "-P", "-j", ",".join(sorted(parents)),
               "--format=JobID,State,ExitCode,ElapsedRaw,AllocCPUS,AllocTRES,NodeList"]
    output = subprocess.check_output(command, text=True)
    rows = {}
    for line in output.splitlines():
        fields = line.split("|")
        if fields[0] in expected:
            rows[fields[0]] = dict(zip(("job_id", "state", "exit_code", "elapsed_seconds",
                                       "allocated_cpus", "allocated_tres", "nodes"), fields[:7]))
    require(set(rows) == set(expected), "Slurm accounting does not yet cover every required task")
    for job, row in rows.items():
        require(row["state"] == "COMPLETED" and row["exit_code"] == "0:0", "Slurm task unsuccessful: " + job)
        row["task_id"] = expected[job]
    return {"command": command, "tasks": rows, "passed": True,
            "scope": "authoritative task union only; superseded failures and integration checks remain separately archived"}


def anonymize(text):
    # Only a derivative review copy is transformed; the private originals retain
    # their byte hashes. Scientific scores and data sequences are unchanged.
    replacements = ((str(ROOT), "<WORKSPACE>"),
                    ("/gpfs/work/bio/zihanhe25/miniconda3/envs/mhcii-esm2", "<PYTHON_ENV>"),
                    ("/gpfs/work/bio/zihanhe25", "<USER_ROOT>"),
                    ("/gpfs/work/bio/", "<CLUSTER_ROOT>/"),
                    ("zihanhe25", "anonymous_user"), ("jiameng_mres", "anonymous_account"))
    for original, replacement in replacements:
        text = text.replace(original, replacement)
    text = re.sub(r"\b(?:gpua800|gpu3090|gpu4090|cpu\d+)[nN]\d+\b", "<COMPUTE_NODE>", text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--manuscript", type=Path, default=Path("paper/manuscript_v2.tex"))
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--visual-audit", type=Path, required=True)
    parser.add_argument("--journal-assessment", type=Path, default=Path("paper/JOURNAL_ASSESSMENT.md"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", type=Path, default=Path("output/gdtcr_anonymous_review.zip"))
    args = parser.parse_args()
    evidence, presentation = read(args.evidence), read(args.presentation / "summary.json")
    require(evidence["complete"] and presentation["complete"], "Evidence/figures are incomplete")
    require(evidence["task_counts"] == {"complete": 557}, "Required task inventory differs")
    require(len(evidence["reports"]) == 193 and len(evidence["paired_comparisons"]) == 552, "Statistical report coverage differs")
    require(presentation["evidence_sha256"] == file_sha256(args.evidence), "Figures use different evidence")
    require(len(presentation["figures"]) == 8, "Six main and two supplementary figures required")
    for path, digest in presentation["output_sha256"].items():
        require(file_sha256(args.presentation / path) == digest, "Presentation file changed: " + path)
    manuscript_text = args.manuscript.read_text()
    require(len(presentation.get("latex_tables", [])) == 3, "Three generated manuscript tables required")
    for name in presentation["latex_tables"]:
        require((args.presentation / "tables" / name).read_text().strip() in manuscript_text,
                "Manuscript table differs from the evidence-generated source: " + name)
    rendering = read(args.pdf.with_suffix(".render.json"))
    visual = read(args.visual_audit)
    require(not rendering["draft"] and rendering["pdf_sha256"] == file_sha256(args.pdf), "PDF is a draft or changed")
    require(rendering["source_sha256"] == file_sha256(args.manuscript), "PDF source differs from the saved manuscript")
    require(rendering["renderer_source_sha256"] == file_sha256(ROOT / "scripts/render_manuscript_pdf.py"),
            "PDF renderer differs from the packaged source")
    require(rendering["figures"] == 8 and rendering["tables"] == 3, "PDF must contain all eight figures and three tables")
    require(visual["passed"] and visual["pdf_sha256"] == file_sha256(args.pdf), "Current PDF needs visual acceptance")
    require(set(visual["inspected_pages"]) == set(range(1, rendering["pages"] + 1)), "Not every final PDF page was inspected")
    require(args.journal_assessment.is_file(), "Final journal-scope assessment missing")
    journal_text = args.journal_assessment.read_text()
    require("Decision status: final" in journal_text and file_sha256(args.evidence) in journal_text,
            "Journal decision must identify the completed evidence")
    completion_text = Path("paper/COMPLETION_AUDIT.md").read_text()
    require("Audit status: complete" in completion_text and file_sha256(args.evidence) in completion_text,
            "Completion audit must identify and accept the final evidence")
    require(not args.package.exists(), "Refusing to overwrite an existing release package")
    accounting = slurm_accounting(evidence)
    inputs = [args.evidence, args.presentation / "summary.json", args.manuscript, args.pdf,
              args.pdf.with_suffix(".render.json"), args.visual_audit, args.journal_assessment]
    begin_run(args.output, args, inputs)
    (args.output / "slurm_accounting.json").write_text(json.dumps(accounting, indent=2, sort_keys=True) + "\n")

    inventory, content, transformed = {}, {}, []

    def add(name, path, textual=False, transform=None):
        require(name not in content, "Package path collision: " + name)
        data = Path(path).read_bytes()
        original_hash = hashlib.sha256(data).hexdigest()
        if textual:
            value = anonymize(data.decode("utf-8"))
            if transform:
                value = transform(value)
            data = value.encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        inventory[name] = {"sha256": digest, "bytes": len(data), "original_sha256": original_hash,
                           "derivative": digest != original_hash}
        if digest != original_hash:
            transformed.append(name)
        content[name] = data

    figure_prefix = Path(os.path.relpath(args.presentation.resolve(), args.manuscript.resolve().parent), "figures").as_posix() + "/"
    add("manuscript.tex", args.manuscript, textual=True,
        transform=lambda s: s.replace(figure_prefix, "figures/"))
    add("manuscript.pdf", args.pdf)
    add("manuscript.txt", args.pdf.with_suffix(".txt"), textual=True)
    add("manuscript.render.json", args.pdf.with_suffix(".render.json"), textual=True)
    add("documentation/visual_audit.json", args.visual_audit, textual=True)
    for name in ("DATA_CARD.md", "MODEL_CARD.md", "LICENSE_AND_ACCESS.md", "REPRODUCIBILITY.md",
                 "SUPPLEMENT_INDEX.md", "RELATED_WORK.md", "COMPLETION_AUDIT.md", "REPOSITORY_RETENTION.md",
                 "protocol_v2.md", "protocol_v2_implementation_notes.md", "references_v2.json"):
        add("documentation/" + name, Path("paper") / name, textual=True)
    add("documentation/JOURNAL_ASSESSMENT.md", args.journal_assessment, textual=True)
    add("documentation/journal_guidelines_v2.json", "paper/reference_metadata/journal_guidelines_v2.json", textual=True)
    for label, folder in (("collection", args.evidence.parent), ("presentation", args.presentation)):
        for name in ("provenance.json", "summary.json", "checksums.json"):
            add("supplement/" + label + "/" + name, folder / name, textual=True)
    add("supplement/collection/task_status.tsv", args.evidence.parent / "task_status.tsv", textual=True)
    for folder in ("figures", "tables"):
        for path in sorted((args.presentation / folder).iterdir()):
            add(folder + "/" + path.name, path, textual=path.suffix in (".tsv", ".csv", ".json", ".txt", ".tex"))
    for name in ("evidence.json", "metrics.tsv", "strata.tsv"):
        path = args.evidence if name == "evidence.json" else args.evidence.parent / name
        original = path.read_bytes()
        data = anonymize(original.decode("utf-8")).encode("utf-8")
        compressed = gzip.compress(data, compresslevel=9, mtime=0)
        key = "supplement/" + name + ".gz"
        content[key] = compressed
        inventory[key] = {"sha256": hashlib.sha256(compressed).hexdigest(), "bytes": len(compressed),
                          "uncompressed_sha256": hashlib.sha256(data).hexdigest(),
                          "original_uncompressed_sha256": hashlib.sha256(original).hexdigest(),
                          "derivative": data != original}
        if data != original:
            transformed.append(key)
    for folder in ("src", "scripts", "tests"):
        for path in sorted(Path(folder).rglob("*.py")):
            add("source/" + str(path), path, textual=True)
    for path in sorted(Path("slurm").iterdir()):
        if path.suffix in (".sbatch", ".sh"):
            add("source/" + str(path), path, textual=True)
    add("source/README.md", "README.md", textual=True)
    add("source/requirements.txt", "requirements.txt", textual=True)
    for path in sorted(Path("configs/completion_v2").iterdir()):
        if path.suffix in (".json", ".txt"):
            add("source/" + str(path), path, textual=True)
    # Small, safe data/split manifests identify scientific content without
    # distributing source-owned raw downloads or claiming a blanket license.
    for path in (Path("data/provenance/manifest.json"), Path("data/splits/completion_v2/manifest.json")):
        add("source/" + str(path), path, textual=True)
    snapshots = set()
    for row in evidence["task_status"]:
        record_path = Path(row["record"])
        record = read(record_path)
        snapshots.add(Path(record["code_snapshot"]))
        add("supplement/task_records/" + row["task_id"] + ".json", record_path, textual=True)
    for folder in sorted(snapshots):
        snapshot = read(folder / "snapshot.json")
        for relative, digest in sorted(snapshot["files_sha256"].items()):
            path = folder / relative
            require(file_sha256(path) == digest, "Frozen source changed: " + str(path))
            add("source/frozen/" + folder.name + "/" + relative, path, textual=True)
        add("source/frozen/" + folder.name + "/snapshot.json", folder / "snapshot.json", textual=True)
    for label, folder in (("collection", args.evidence.parent), ("presentation", args.presentation)):
        provenance = read(folder / "provenance.json")
        frozen_root = Path(provenance["source_root"])
        for relative, digest in sorted(provenance["source_sha256"].items()):
            path = frozen_root / relative
            require(file_sha256(path) == digest, "Export source changed: " + str(path))
            add("source/exports/" + label + "/" + relative, path, textual=True)
    note = ("# Anonymous scientific review package\n\n"
            "The manuscript, eight figure exports and numerical supplements derive from the completed v2 evidence. "
            "The PDF is a visually inspected ReportLab reading copy of the saved TeX source; native TeX compilation "
            "was unavailable because of a platform-directory error.\n\n"
            "The source directory is a review replica. Workspace/interpreter/account strings are anonymized; "
            "execution manifests must be ported to a fresh workspace as described in REPRODUCIBILITY.md. "
            "Executed code snapshots are retained under source/frozen, and task records under supplement/task_records. "
            "Original and derivative file hashes are both retained in PACKAGE_MANIFEST.json. "
            "The unmodified local experiment tree and its private release inventory remain authoritative for "
            "byte-level provenance. No raw-data redistribution license, public repository DOI or author declaration "
            "is invented by this package.\n\n"
            "Primary metrics use 64 draws. Three splits and two model seeds are descriptive repetitions, "
            "not six independent biological subjects. All unrecorded pairs are constructed comparisons, "
            "not validated biological negatives.\n")
    content["README.md"] = note.encode()
    inventory["README.md"] = {"sha256": hashlib.sha256(content["README.md"]).hexdigest(), "bytes": len(content["README.md"])}
    manifest = {"schema_version": 2, "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "complete_experiment_tasks": 557, "run_statistical_reports": 193, "paired_comparisons": 552,
                "evidence_sha256": file_sha256(args.evidence), "files": inventory,
                "anonymized_derivatives": transformed, "external_publication_performed": False}
    content["PACKAGE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    for name, data in content.items():
        if name.endswith(".gz"):
            data = gzip.decompress(data)
        if name.endswith((".py", ".md", ".json", ".txt", ".tex", ".tsv", ".gz", ".sh", ".sbatch", ".toml", ".yaml", ".yml", ".bib")) or name.endswith(".gitignore"):
            value = data.decode("utf-8")
            require(not any(token in value for token in ("zihanhe25", "jiameng_mres", "/gpfs/work/bio/")), "Identity remains in anonymous file: " + name)
    args.package.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.package, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(content):
            archive.writestr(name, content[name])
    with zipfile.ZipFile(args.package) as archive:
        require(archive.testzip() is None, "ZIP integrity failure")
        for name, item in inventory.items():
            require(hashlib.sha256(archive.read(name)).hexdigest() == item["sha256"], "Packaged file hash differs")
    private = {"schema_version": 2, "complete": True, "package": str(args.package),
               "package_sha256": file_sha256(args.package), "input_sha256": {str(p): file_sha256(p) for p in inputs},
               "experiment_output_sha256": evidence["verified_output_sha256"],
               "model_content_audits": evidence["evaluation_audits"],
               "training_audit_sha256": file_sha256("artifacts/completion_v2/training_audit/summary.json"),
               "slurm_successful_tasks": len(accounting["tasks"]), "package_files": len(content),
               "anonymous_metadata_check": True, "pdf_visual_audit": visual,
               "retention": "historical/failed runs and raw webpages remain in the local audit archive"}
    (args.output / "release_manifest.json").write_text(json.dumps(private, indent=2, sort_keys=True) + "\n")
    (args.output / "summary.json").write_text(json.dumps({k: v for k, v in private.items()
        if k not in ("experiment_output_sha256", "model_content_audits", "input_sha256", "pdf_visual_audit")}, indent=2, sort_keys=True) + "\n")
    finish_run(args.output)
    print(json.dumps(read(args.output / "summary.json")), flush=True)


if __name__ == "__main__":
    main()
