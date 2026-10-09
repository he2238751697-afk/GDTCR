#!/usr/bin/env python3
"""Verify public inputs and run the frozen GDTCR tasks in a fresh workspace."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def inside(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in str(name) or not name.parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    path = root / str(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes workspace: {relative}")
    return path


def check(path, record):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or nonregular file: {path}")
    if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
        raise ValueError(f"Size/SHA256 mismatch: {path}")


def frozen_sources(archive_path, destination=None):
    """Validate all objects before materializing any exact source snapshot."""
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate frozen archive members")
        records, contents = json.loads(archive.read("INDEX.json")), {}
        for record in records:
            data = archive.read(record["manifest"])
            if hashlib.sha256(data).hexdigest() != record["manifest_sha256"]:
                raise ValueError("Frozen snapshot manifest mismatch")
            manifest = json.loads(data)
            combined = hashlib.sha256(json.dumps(manifest["files_sha256"], sort_keys=True).encode()).hexdigest()
            if combined != manifest["digest"]:
                raise ValueError("Frozen snapshot aggregate digest mismatch")
            # Validate path names even in read-only verification.
            inside(Path("/tmp/gdtcr-path-validation"), record["destination"])
            for relative, expected in manifest["files_sha256"].items():
                inside(Path("/tmp/gdtcr-path-validation"), relative)
                if expected not in contents:
                    data = archive.read("objects/" + expected)
                    if hashlib.sha256(data).hexdigest() != expected:
                        raise ValueError(f"Frozen source object mismatch: {expected}")
                    contents[expected] = data
            record["parsed"] = manifest
        if destination is not None:
            for record in records:
                target = inside(destination, record["destination"])
                if target.exists():
                    raise FileExistsError(f"Snapshot destination exists: {target}")
            for record in records:
                target = inside(destination, record["destination"])
                for relative, expected in record["parsed"]["files_sha256"].items():
                    path = inside(target, relative)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents[expected])
                (target / "snapshot.json").write_bytes(archive.read(record["manifest"]))
    return {"snapshots": len(records), "distinct_objects": len(contents),
            "restored_files": sum(len(r["parsed"]["files_sha256"]) for r in records)}


def verify(root):
    inventory = read(root / "reproducibility/MANIFEST.json")["files"]
    for relative, record in inventory.items():
        check(inside(root, relative), record)
    provenance = read(root / "data/provenance/manifest.json")
    counts = {}
    for field, base in (("raw_sha256", "data/raw"), ("processed_sha256", "data/processed"),
                        ("output_sha256", "data/provenance")):
        for relative, expected in provenance[field].items():
            if digest(inside(root / base, relative)) != expected:
                raise ValueError(f"Original data hash mismatch: {base}/{relative}")
        counts[field] = len(provenance[field])
    actual_raw = {str(p.relative_to(root / "data/raw")) for p in (root / "data/raw").rglob("*") if p.is_file()}
    if actual_raw != set(provenance["raw_sha256"]):
        raise ValueError("Raw-file inventory differs from the frozen dataset")
    snapshots = frozen_sources(root / "reproducibility/frozen_source.zip")
    evidence_hash = hashlib.sha256()
    with gzip.open(root / "reproducibility/reference/evidence.json.gz", "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            evidence_hash.update(block)
    if evidence_hash.hexdigest() != read(root / "reproducibility/release.json")["primary_evidence_sha256"]:
        raise ValueError("Compressed primary reference evidence changed")
    return {"passed": True, "inventory_files": len(inventory), "data": counts,
            "frozen_source": snapshots, "primary_evidence_sha256": evidence_hash.hexdigest()}


def rebuild_processed(root, output):
    provenance = read(root / "data/provenance/manifest.json")
    # Do not produce an apparently valid reconstruction from altered inputs.
    for name, expected in provenance["raw_sha256"].items():
        if digest(inside(root / "data/raw", name)) != expected:
            raise ValueError(f"Raw input changed: {name}")
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, "-B", str(root / "src/clean_data.py"),
                    "--raw-dir", str(root / "data/raw"), "--output-dir", str(output)], check=True)
    counts = {}
    for name, expected in provenance["processed_sha256"].items():
        path = output / name
        if digest(path) != expected:
            raise ValueError(f"Reconstructed processed data differ: {name}")
        with path.open("rb") as stream:
            counts[name] = sum(1 for _ in stream)
    result = {"passed": True, "processed_sha256": provenance["processed_sha256"], "records": counts}
    write_json(output / "reconstruction.json", result)
    return result


def port_value(value, original_root, destination):
    if isinstance(value, str):
        if value == original_root or value.startswith(original_root + "/"):
            return str(destination) + value[len(original_root):]
        return value
    if isinstance(value, list):
        return [port_value(v, original_root, destination) for v in value]
    if isinstance(value, dict):
        return {k: port_value(v, original_root, destination) for k, v in value.items()}
    return value


def port_manifests(source, workspace, interpreter):
    records, hash_mapping = {}, {}
    for path in sorted((source / "configs").rglob("*.json")):
        original = read(path)
        if not isinstance(original, dict) or "tasks" not in original or "code_snapshot" not in original:
            continue
        relative = str(path.relative_to(source))
        ported = port_value(original, original["root"], workspace)
        ported["root"], ported["python"] = str(workspace), str(interpreter)
        if not Path(ported["code_snapshot"]).is_relative_to(workspace):
            raise ValueError(f"Snapshot outside new workspace: {relative}")
        snapshot = Path(ported["code_snapshot"]) / "snapshot.json"
        if not snapshot.is_file():
            raise ValueError(f"Snapshot not distributed for {relative}: {snapshot}")
        if read(snapshot)["digest"] != original["code_digest"]:
            raise ValueError(f"Wrong snapshot for {relative}")
        write_json(workspace / relative, ported)
        original_sha, new_sha = digest(path), digest(workspace / relative)
        records[relative] = {"original_sha256": original_sha, "ported_sha256": new_sha,
                             "original_root": original["root"], "original_python": original["python"]}
        hash_mapping[original_sha] = new_sha
    for name in ("task_supersessions.json", "evaluation_audit_supersessions.json"):
        relative = "configs/completion_v2/" + name
        original = read(source / relative)
        ported = json.loads(json.dumps(original))
        for entry in ported["replacements"]:
            for prefix in ("old", "new"):
                old_hash = entry[prefix + "_manifest_sha256"]
                if old_hash not in hash_mapping:
                    raise ValueError(f"Superseded manifest not ported: {old_hash}")
                entry[prefix + "_manifest_sha256"] = hash_mapping[old_hash]
                old_path = entry[prefix + "_manifest"]
                matches = [p for p in records if old_path.endswith("/" + p)]
                if len(matches) != 1:
                    raise ValueError(f"Unresolved supersession path: {old_path}")
                entry[prefix + "_manifest"] = str(workspace / matches[0])
        write_json(workspace / relative, ported)
        records[relative] = {"original_sha256": digest(source / relative),
                             "ported_sha256": digest(workspace / relative)}
    return records


def prepare(root, output, interpreter):
    verify(root)
    # Resolving the python symlink would bypass a venv and lose its dependencies.
    executable = shutil.which(interpreter)
    if not executable:
        raise ValueError(f"Python interpreter not executable: {interpreter}")
    executable = Path(os.path.abspath(executable))
    if output == root or output.is_relative_to(root):
        raise ValueError("Place the run workspace outside the reference checkout")
    output.mkdir(parents=True, exist_ok=False)
    for folder in ("src", "scripts", "slurm", "tests", "configs", "data", "paper", "reproducibility"):
        shutil.copytree(root / folder, output / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("README.md", "REPRODUCIBILITY.md", "THIRD_PARTY_DATA.md", "requirements.txt",
                 "RESEARCH_PLAN.md", "PROGRESS.md"):
        shutil.copyfile(root / name, output / name)
    shutil.copytree(root / "configs", output / "reproducibility/original_configs")
    snapshot_report = frozen_sources(root / "reproducibility/frozen_source.zip", output)
    for path in sorted((root / "reproducibility/reference_inputs").rglob("*")):
        if path.is_file():
            relative = str(path.relative_to(root / "reproducibility/reference_inputs"))
            if relative == "artifacts/completion_v2/environment.json":
                # Keep the original inventory in reference_inputs; record the
                # actual new interpreter instead of mislabeling the old host.
                continue
            destination = inside(output, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    evidence = output / "artifacts/completion_v2/final_evidence/evidence.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(root / "reproducibility/reference/evidence.json.gz", "rb") as source, evidence.open("wb") as target:
        shutil.copyfileobj(source, target)
    records = port_manifests(root, output, executable)
    subprocess.run([str(executable), "-B", str(output / "scripts/record_environment.py")],
                   cwd=output, check=True)
    report = {"source_checkout": str(root), "workspace": str(output), "python": str(executable),
              "source_inventory_sha256": digest(root / "reproducibility/MANIFEST.json"),
              "source_snapshots": snapshot_report, "manifests": records,
              "initializations_installed": False,
              "note": "New run workspace; no original completed task records copied."}
    write_json(output / "reproducibility/porting_record.json", report)
    return {"prepared": str(output), "ported_manifests": len(records), "frozen_source": snapshot_report}


def require_workspace(workspace):
    path = workspace / "reproducibility/porting_record.json"
    record = read(path)
    if record["workspace"] != str(workspace):
        raise ValueError("Run workspace was moved; prepare it again from the reference checkout")
    return record


def install_initializations(workspace, archive):
    require_workspace(workspace)
    asset = read(workspace / "reproducibility/release.json")["initializations"]
    check(archive, asset)
    expected = asset["files"]
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError("Initialization archive membership differs from release")
        for member in members:
            if not member.isfile() or member.size != expected[member.name]["bytes"]:
                raise ValueError(f"Invalid checkpoint member: {member.name}")
            target = inside(workspace, member.name)
            if target.exists():
                check(target, expected[member.name])
        for member in members:
            target = inside(workspace, member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                continue
            descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as output, bundle.extractfile(member) as contents:
                    shutil.copyfileobj(contents, output)
                check(Path(temporary), expected[member.name])
                Path(temporary).replace(target)
            finally:
                Path(temporary).unlink(missing_ok=True)
    record = require_workspace(workspace)
    record["initializations_installed"] = True
    record["initializations_sha256"] = asset["sha256"]
    write_json(workspace / "reproducibility/porting_record.json", record)
    return {"installed": len(expected), "archive_sha256": asset["sha256"]}


def fetch_initializations(workspace, archive=None, repository=None):
    require_workspace(workspace)
    release = read(workspace / "reproducibility/release.json")
    if archive is not None:
        return install_initializations(workspace, archive)
    repository = repository or release["repository"]
    if len(repository.split("/")) != 2 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/" for c in repository):
        raise ValueError("Expected a GitHub OWNER/REPOSITORY name")
    asset = release["initializations"]
    url = f"https://github.com/{repository}/releases/download/{release['release_tag']}/{asset['filename']}"
    cache = workspace / "reproducibility/downloads"
    cache.mkdir(exist_ok=True)
    destination = cache / asset["filename"]
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > asset["bytes"]:
                        raise ValueError("Download exceeds recorded asset size")
                    output.write(block)
            check(temporary, asset)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return install_initializations(workspace, destination)


def run_state(workspace, verified=None):
    """Load the effective task graph and verify completed local task records."""
    porting = require_workspace(workspace)
    verified = {} if verified is None else verified
    manifests, entries, producers = {}, [], {}
    for row in read(workspace / "reproducibility/tasks.json"):
        relative = row["manifest"]
        if relative not in manifests:
            record = porting["manifests"][relative]
            if record["original_sha256"] != row["manifest_sha256"]:
                raise ValueError(f"Task index differs from original manifest: {relative}")
            if digest(workspace / relative) != record["ported_sha256"]:
                raise ValueError(f"Ported manifest changed: {relative}")
            manifests[relative] = read(workspace / relative)
        manifest = manifests[relative]
        task = manifest["tasks"][row["index"]]
        if task["id"] != row["id"]:
            raise ValueError("Task index/identity mismatch")
        record_path = str(Path(manifest["job_records"]) / (task["id"] + ".json"))
        entry = {**row, "task": task, "record_path": record_path, "status": "pending"}
        local = inside(workspace, record_path)
        if local.exists():
            record = read(local)
            if record["task"] != task or record["manifest_sha256"] != porting["manifests"][relative]["ported_sha256"]:
                raise ValueError(f"Task record does not match ported command: {local}")
            entry["status"] = record["status"]
            if record["status"] == "complete":
                if set(record["output_sha256"]) != set(task["outputs"]):
                    raise ValueError(f"Incomplete recorded output inventory: {local}")
                for name, expected in record["output_sha256"].items():
                    path = inside(workspace, name)
                    stat = path.stat()
                    key = (str(path), stat.st_size, stat.st_mtime_ns)
                    if key not in verified:
                        verified[key] = digest(path)
                    if verified[key] != expected:
                        raise ValueError(f"Completed output changed: {path}")
        identity = (relative, row["index"])
        for name in [*task["outputs"], record_path]:
            if name in producers and producers[name] != identity:
                raise ValueError(f"Multiple active producers for {name}")
            producers[name] = identity
        # The original pretraining commands write checksums as a side effect;
        # a few original task output lists did not declare that file explicitly.
        if manifest["phase"] == "pretrain":
            for name in task["outputs"]:
                if name.endswith("/last.pt"):
                    producers[str(Path(name).with_name("checksums.json"))] = identity
        entries.append(entry)
    states = {(r["manifest"], r["index"]): r["status"] for r in entries}
    for entry in entries:
        missing, waiting = [], []
        dependencies = set(entry["task"].get("requires", []))
        # Two historical sqrt diagnostic tasks omitted their inherited model
        # from `requires`. Honor explicit model inputs without changing the
        # frozen task or waiting for outputs produced earlier in the same task.
        for command in entry["task"]["commands"]:
            arguments = command["args"]
            for index, value in enumerate(arguments[:-1]):
                if value in ("--checkpoint", "--init", "--generator", "--ranker"):
                    name = arguments[index + 1]
                    if name not in entry["task"]["outputs"]:
                        dependencies.add(name)
        for name in sorted(dependencies):
            if not inside(workspace, name).is_file():
                missing.append(name)
            owner = producers.get(name)
            if owner is not None and states[owner] != "complete":
                waiting.append(name)
        entry["missing"], entry["waiting"] = missing, waiting
        entry["ready"] = entry["status"] == "pending" and not missing and not waiting
    return entries, manifests


def status(workspace):
    entries, _ = run_state(workspace)
    return {"workspace": str(workspace), "tasks": len(entries),
            "states": dict(Counter(r["status"] for r in entries)),
            "ready": sum(r["ready"] for r in entries),
            "ready_examples": [{k: r[k] for k in ("id", "suite", "phase")} for r in entries if r["ready"]][:10],
            "missing_initializations": [name for name in read(workspace / "reproducibility/release.json")["initializations"]["files"]
                                        if not inside(workspace, name).is_file()]}


def run(workspace, suite, maximum, task_id=None):
    if maximum < 1:
        raise ValueError("max-tasks must be positive")
    completed, verified = [], {}
    for _ in range(maximum):
        entries, manifests = run_state(workspace, verified)
        selected = [r for r in entries if (suite == "all" or r["suite"] == suite)
                    and (task_id is None or r["id"] == task_id)]
        if not selected:
            raise ValueError("No matching task in effective task index")
        failed = [r for r in selected if r["status"] not in ("pending", "complete")]
        if failed:
            raise RuntimeError("Inspect existing failed/running records before continuing: " + ", ".join(r["id"] for r in failed))
        ready = [r for r in selected if r["ready"]]
        if not ready:
            pending = [r for r in selected if r["status"] != "complete"]
            if pending:
                raise RuntimeError("No ready task; unresolved inputs/producers: " + json.dumps(
                    [{"id": r["id"], "missing": r["missing"][:4], "waiting": r["waiting"][:4]} for r in pending[:5]]))
            break
        entry = ready[0]
        existing = [p for p in entry["task"]["outputs"] if inside(workspace, p).exists()]
        if existing:
            raise FileExistsError(f"Unrecorded outputs exist for {entry['id']}: {existing}")
        manifest = manifests[entry["manifest"]]
        argv = [manifest["python"], "-B", str(workspace / "scripts/execute_manifest.py"),
                "--manifest", str(workspace / entry["manifest"]), "--task", str(entry["index"])]
        print(json.dumps({"executing": entry["id"], "argv": argv}), flush=True)
        subprocess.run(argv, cwd=workspace, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=True)
        completed.append(entry["id"])
    return {"executed": completed, "count": len(completed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Reference checkout")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    rebuild = commands.add_parser("rebuild-processed")
    rebuild.add_argument("--output", type=Path, required=True)
    initialize = commands.add_parser("prepare")
    initialize.add_argument("--output", type=Path, required=True)
    initialize.add_argument("--python", default=sys.executable)
    fetch = commands.add_parser("fetch-initializations")
    fetch.add_argument("--workspace", type=Path, required=True)
    fetch.add_argument("--archive", type=Path)
    fetch.add_argument("--repository")
    inspect = commands.add_parser("status")
    inspect.add_argument("--workspace", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--workspace", type=Path, required=True)
    execute.add_argument("--suite", choices=("all", "primary", "revision"), default="all")
    execute.add_argument("--max-tasks", type=int, default=1)
    execute.add_argument("--task-id")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "verify":
        result = verify(root)
    elif args.command == "rebuild-processed":
        result = rebuild_processed(root, args.output.resolve())
    elif args.command == "prepare":
        result = prepare(root, args.output.resolve(), args.python)
    elif args.command == "fetch-initializations":
        result = fetch_initializations(args.workspace.resolve(), args.archive, args.repository)
    elif args.command == "status":
        result = status(args.workspace.resolve())
    else:
        result = run(args.workspace.resolve(), args.suite, args.max_tasks, args.task_id)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
