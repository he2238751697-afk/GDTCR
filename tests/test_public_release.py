"""Contracts that keep a fresh public reproduction separate from reference data."""

import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("public_reproduction", Path(__file__).parents[1] / "scripts/reproduce.py")
reproduce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reproduce)


class PublicReproductionTests(unittest.TestCase):
    def test_paths_cannot_escape_or_follow_an_external_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            root.mkdir()
            (root / "outside").symlink_to(root.parent, target_is_directory=True)
            for path in ("../private", "/absolute", "outside/private", "..\\private"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    reproduce.inside(root, path)
            self.assertEqual(reproduce.inside(root, "data/raw/input.gz"), root / "data/raw/input.gz")

    def test_frozen_code_tampering_is_rejected_before_restoration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = b"print('original science')\n"
            expected = hashlib.sha256(data).hexdigest()
            files = {"scripts/fit.py": expected}
            manifest = {"files_sha256": files,
                        "digest": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}
            encoded = json.dumps(manifest).encode()
            record = {"destination": "artifacts/code/frozen", "manifest": "manifests/frozen.json",
                      "manifest_sha256": hashlib.sha256(encoded).hexdigest()}
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("INDEX.json", json.dumps([record]))
                bundle.writestr(record["manifest"], encoded)
                bundle.writestr("objects/" + expected, b"tampered")
            destination = root / "run"
            with self.assertRaises(ValueError):
                reproduce.frozen_sources(archive, destination)
            self.assertFalse(destination.exists())

    def test_porting_preserves_scientific_commands_and_supersessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "reference", root / "run"
            folder = source / "configs/completion_v2"
            folder.mkdir(parents=True)
            original_root = "/original/research/GDTCR"
            relative_snapshot = "artifacts/code/frozen"
            snapshot = target / relative_snapshot / "snapshot.json"
            reproduce.write_json(snapshot, {"digest": "frozen-digest"})
            scientific_task = {"id": "fit-0", "commands": [{"script": "scripts/train.py", "args": [
                "--seed", "3407", "--steps", "1500", "--train", "data/train.tsv"]}],
                "outputs": ["artifacts/fit-0/best.pt"]}
            manifest = {"root": original_root, "python": "/original/venv/bin/python",
                        "code_snapshot": original_root + "/" + relative_snapshot,
                        "code_digest": "frozen-digest", "tasks": [scientific_task]}
            paths = [folder / "old.json", folder / "new.json"]
            for number, path in enumerate(paths):
                reproduce.write_json(path, {**manifest, "phase": "fit-" + str(number)})
            before = {path: path.read_bytes() for path in paths}
            replacement = {"old_index": 0, "new_index": 0}
            for prefix, path in zip(("old", "new"), paths):
                replacement[prefix + "_manifest"] = original_root + "/configs/completion_v2/" + path.name
                replacement[prefix + "_manifest_sha256"] = reproduce.digest(path)
            for name in ("task_supersessions.json", "evaluation_audit_supersessions.json"):
                reproduce.write_json(folder / name, {"replacements": [replacement]})
            interpreter = root / "venv/bin/python"
            records = reproduce.port_manifests(source, target, interpreter)
            for path in paths:
                ported = reproduce.read(target / path.relative_to(source))
                self.assertEqual(ported["tasks"], [scientific_task])
                self.assertEqual(ported["python"], str(interpreter))
                self.assertEqual(ported["root"], str(target))
                self.assertEqual(path.read_bytes(), before[path])
            entry = reproduce.read(target / "configs/completion_v2/task_supersessions.json")["replacements"][0]
            for prefix, path in zip(("old", "new"), paths):
                relative = str(path.relative_to(source))
                self.assertEqual(entry[prefix + "_manifest_sha256"], records[relative]["ported_sha256"])
                self.assertEqual(entry[prefix + "_manifest"], str(target / relative))

    def test_verified_asset_rejects_conflicting_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "run"
            relative = "artifacts/runs/pretrain/a800/seed-0/last.pt"
            checkpoint = b"original checkpoint bytes"
            archive = root / "initializations.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                info = tarfile.TarInfo(relative)
                info.size = len(checkpoint)
                bundle.addfile(info, io.BytesIO(checkpoint))
            asset = {"bytes": archive.stat().st_size, "sha256": reproduce.digest(archive),
                     "files": {relative: {"bytes": len(checkpoint), "sha256": hashlib.sha256(checkpoint).hexdigest()}}}
            reproduce.write_json(workspace / "reproducibility/release.json", {"initializations": asset})
            reproduce.write_json(workspace / "reproducibility/porting_record.json", {"workspace": str(workspace)})
            result = reproduce.install_initializations(workspace, archive)
            self.assertEqual(result["installed"], 1)
            path = workspace / relative
            self.assertEqual(path.read_bytes(), checkpoint)
            path.write_bytes(b"new independently trained weights")
            with self.assertRaises(ValueError):
                reproduce.install_initializations(workspace, archive)
            self.assertEqual(path.read_bytes(), b"new independently trained weights")

    def test_legacy_diagnostic_waits_for_undeclared_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            relative = "configs/pretrain.json"
            model = "artifacts/legacy/last.pt"
            task = {"id": "sqrt-diagnostic", "commands": [{"script": "scripts/evaluate.py",
                    "args": ["--checkpoint", model]}], "outputs": ["artifacts/diagnostic.json"]}
            manifest = {"tasks": [task], "job_records": "artifacts/jobs", "phase": "pretrain"}
            reproduce.write_json(root / relative, manifest)
            reproduce.write_json(root / "reproducibility/porting_record.json", {
                "workspace": str(root), "manifests": {relative: {
                    "original_sha256": "original", "ported_sha256": reproduce.digest(root / relative)}}})
            reproduce.write_json(root / "reproducibility/tasks.json", [{
                "id": task["id"], "manifest": relative, "index": 0,
                "manifest_sha256": "original", "suite": "primary"}])
            entries, _ = reproduce.run_state(root)
            self.assertFalse(entries[0]["ready"])
            self.assertEqual(entries[0]["missing"], [model])
            path = root / model
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fixture model")
            entries, _ = reproduce.run_state(root)
            self.assertTrue(entries[0]["ready"])


if __name__ == "__main__":
    unittest.main()
