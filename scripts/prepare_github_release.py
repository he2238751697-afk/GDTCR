#!/usr/bin/env python3
"""Assemble an isolated GitHub repository and checksum-addressed release assets.

This maintainer command reads the completed local artifact tree. It never
publishes, changes the original Git index, or overwrites an existing stage.
"""

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SHA256 = "5badb3b9b8ead02c57afeb5f578f85f3a5e343bad9714fb7daa08f48342b2f3b"
TEXT_SUFFIXES = {".py", ".sh", ".sbatch", ".md", ".json", ".txt", ".toml",
                 ".yaml", ".yml", ".tex", ".bib", ".tsv", ".csv"}
SECRET = re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----|"
                    rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
                    rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b")


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def copy(source, target):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Expected regular source file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def source_files(root):
    for directory in ("src", "scripts", "slurm", "tests", "configs", "paper", "release"):
        for path in sorted((root / directory).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix in TEXT_SUFFIXES or (
                    directory == "paper" and "results" in path.parts
                    and path.suffix in {".pdf", ".svg", ".png"}):
                yield path
    for filename in ("requirements.txt", "RESEARCH_PLAN.md", "PROGRESS.md",
                     "BMC_Bioinformatics_submission_revision_checklist.md"):
        yield root / filename
    for folder in ("raw", "processed", "splits", "provenance"):
        yield from sorted(path for path in (root / "data" / folder).rglob("*")
                          if path.is_file())
    yield root / "data/metadata/geo_samples.json"


def tasks(root):
    result = []
    path = root / "artifacts/completion_v2/final_evidence/task_status.tsv"
    with path.open() as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["status"] != "complete":
                raise ValueError(f"Incomplete original task: {row['task_id']}")
            manifest_path = root / row["manifest"]
            manifest = json.loads(manifest_path.read_text())
            matches = [i for i, task in enumerate(manifest["tasks"])
                       if task["id"] == row["task_id"]]
            if len(matches) != 1:
                raise ValueError(f"Ambiguous task: {row['task_id']}")
            result.append({"suite": "primary", "manifest": row["manifest"],
                           "manifest_sha256": digest(manifest_path),
                           "index": matches[0], "id": row["task_id"],
                           "phase": manifest["phase"]})
    if len(result) != 557:
        raise ValueError("Expected 557 effective original tasks")
    for phase in ("revision_training", "revision_evaluation", "revision_transfer"):
        relative = f"configs/revision_bmc/{phase}.json"
        path = root / relative
        manifest = json.loads(path.read_text())
        for index, task in enumerate(manifest["tasks"]):
            record = json.loads((root / manifest["job_records"] /
                                 (task["id"] + ".json")).read_text())
            if record["status"] != "complete" or record["manifest_sha256"] != digest(path):
                raise ValueError(f"Unverified revision task: {task['id']}")
            result.append({"suite": "revision", "manifest": relative,
                           "manifest_sha256": digest(path), "index": index,
                           "id": task["id"], "phase": phase})
    if len(result) != 600:
        raise ValueError("Expected 600 original plus revision tasks")
    return result


def zip_member(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data, compresslevel=6)


def snapshots(root, destination):
    records, objects = [], {}
    for base in ("artifacts/completion_v2/code", "artifacts/completion_v2/publication_code",
                 "artifacts/revision_bmc/code"):
        for path in sorted((root / base).glob("*/snapshot.json")):
            manifest = json.loads(path.read_text())
            relative = str(path.parent.relative_to(root))
            records.append({"destination": relative,
                            "manifest": "manifests/" + path.parent.name + ".json",
                            "manifest_sha256": digest(path), "data": manifest})
            for name, expected in manifest["files_sha256"].items():
                source = path.parent / name
                if digest(source) != expected:
                    raise ValueError(f"Frozen source mismatch: {source}")
                objects.setdefault(expected, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for expected, source in sorted(objects.items()):
            contents = source.read_bytes()
            if SECRET.search(contents):
                raise ValueError(f"Credential-like content in frozen source: {source}")
            zip_member(archive, "objects/" + expected, contents)
        for record in records:
            original = root / record["destination"] / "snapshot.json"
            zip_member(archive, record["manifest"], original.read_bytes())
        index = [{k: v for k, v in record.items() if k != "data"} for record in records]
        zip_member(archive, "INDEX.json", (json.dumps(index, sort_keys=True, indent=2) + "\n").encode())
    return {"snapshots": len(records), "distinct_objects": len(objects),
            "restored_files": sum(len(r["data"]["files_sha256"]) for r in records)}


def initialization_asset(root, path):
    files = [root / f"artifacts/runs/pretrain/{pool}/seed-{seed}/last.pt"
             for pool in ("a800", "source_holdout") for seed in (0, 1)]
    entries = {}
    with path.open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", mtime=0,
                                                 filename="", compresslevel=1) as compressed:
        with tarfile.open(fileobj=compressed, mode="w|") as archive:
            for source in files:
                name = str(source.relative_to(root))
                entries[name] = {"bytes": source.stat().st_size, "sha256": digest(source)}
                info = archive.gettarinfo(str(source), arcname=name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with source.open("rb") as contents:
                    archive.addfile(info, contents)
    return {"filename": path.name, "bytes": path.stat().st_size,
            "sha256": digest(path), "files": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=Path("output/github_release"))
    parser.add_argument("--repository", default="he2238751697-afk/GDTCR")
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    stage, assets = output / "repository", output / "assets"
    stage.mkdir(); assets.mkdir()
    for source in source_files(root):
        copy(source, stage / source.relative_to(root))
    for name in ("README.md", "REPRODUCIBILITY.md", "THIRD_PARTY_DATA.md"):
        copy(root / "release" / name, stage / name)
    (stage / ".gitignore").write_text(
        "# Inputs and frozen reference material are deliberately tracked.\n"
        "/artifacts/\n/.venv/\n__pycache__/\n*.py[cod]\n.pytest_cache/\n"
        "/tmp/\n/output/\n*.log\n*.tmp\n.DS_Store\n.env\n.env.*\n")
    # Preserve scientific bytes across Windows checkouts too.
    (stage / ".gitattributes").write_text("* -text\n")
    task_index = tasks(root)
    write_json(stage / "reproducibility/tasks.json", task_index)
    snapshot_report = snapshots(root, stage / "reproducibility/frozen_source.zip")

    inputs = set()
    for folder in ("artifacts/completion_v2/pools", "artifacts/completion_v2/distances/pretrain_delta"):
        inputs.update(p for p in (root / folder).rglob("*") if p.is_file())
    for pool in ("a800", "source_holdout"):
        for source in (root / "artifacts/runs/pretrain" / pool).glob("*/*"):
            if source.is_file() and source.suffix in (".json", ".jsonl"):
                inputs.add(source)
    for name in ("data_audit_final.json", "pool_audit.json", "environment.json",
                 "final_export_code_v2.json"):
        inputs.add(root / "artifacts/completion_v2" / name)
    for source in sorted(inputs):
        copy(source, stage / "reproducibility/reference_inputs" / source.relative_to(root))
    evidence = root / "artifacts/completion_v2/final_evidence/evidence.json"
    if digest(evidence) != PRIMARY_SHA256:
        raise ValueError("Original primary evidence changed")
    reference = stage / "reproducibility/reference"
    reference.mkdir(parents=True, exist_ok=True)
    with evidence.open("rb") as source, (reference / "evidence.json.gz").open("wb") as destination:
        with gzip.GzipFile(fileobj=destination, mode="wb", mtime=0, filename="", compresslevel=6) as gz:
            shutil.copyfileobj(source, gz)
    for name in ("summary.json", "task_status.tsv"):
        copy(evidence.parent / name, reference / name)
    for name in ("gdtcr_bmc_revision.pdf", "additional_file_1_bmc.pdf"):
        copy(root / "output/pdf" / name, stage / "paper/reading_copies" / name)

    print("Building four-checkpoint release asset", flush=True)
    asset = initialization_asset(root, assets / "gdtcr-legacy-initializations.tar.gz")
    write_json(stage / "reproducibility/release.json", {
        "schema_version": 1, "repository": args.repository, "release_tag": "reproducibility-v1",
        "primary_evidence_sha256": PRIMARY_SHA256, "initializations": asset,
        "source_snapshots": snapshot_report, "effective_primary_tasks": 557,
        "revision_tasks": 43, "code_license": "not yet selected by rights holder",
        "raw_data_terms": "See THIRD_PARTY_DATA.md; no blanket relicensing"})
    entries, oversized = {}, []
    for source in sorted(p for p in stage.rglob("*") if p.is_file()):
        name = str(source.relative_to(stage))
        size = source.stat().st_size
        if size >= 100_000_000:
            oversized.append(name)
        if source.suffix in TEXT_SUFFIXES and size < 10_000_000 and SECRET.search(source.read_bytes()):
            raise ValueError(f"Credential-like content in staged file: {name}")
        entries[name] = {"bytes": size, "sha256": digest(source)}
    if oversized:
        raise ValueError(f"Git files exceed the release's 100 MB ceiling: {oversized}")
    write_json(stage / "reproducibility/MANIFEST.json", {
        "schema_version": 1, "files": entries,
        "note": "SHA256/size of every staged payload file; this inventory excludes itself."})
    raw = [v for k, v in entries.items() if k.startswith("data/raw/")]
    report = {"status": "prepared_locally", "repository": args.repository,
              "stage": str(stage), "git_payload_files": len(entries),
              "git_payload_bytes": sum(x["bytes"] for x in entries.values()),
              "largest_git_file_bytes": max(x["bytes"] for x in entries.values()),
              "raw_files": len(raw), "raw_bytes": sum(x["bytes"] for x in raw),
              "snapshots": snapshot_report, "initializations": asset,
              "inventory_sha256": digest(stage / "reproducibility/MANIFEST.json")}
    write_json(output / "preparation_report.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "initializations"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
