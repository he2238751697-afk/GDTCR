#!/usr/bin/env python3
"""Record immutable installed-package and Python/CUDA versions for a run."""

import argparse
import datetime
import importlib.metadata
import json
import platform
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gdtcr.fileio import file_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/completion_v2/environment.json"))
    parser.add_argument("--lock", type=Path,
                        default=ROOT / "configs/completion_v2/requirements-lock.txt")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Environment inventory already exists: {args.output}")
    installations = defaultdict(list)
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", distribution.metadata.get("Name", "")).lower()
        if not name:
            continue
        entry = {"version": distribution.version,
                 "location": str(Path(distribution.locate_file("")).resolve())}
        if entry not in installations[name]:
            installations[name].append(entry)
    packages = {name: importlib.metadata.version(name) for name in installations}
    shadowing = {}
    for name, entries in installations.items():
        if len(entries) > 1:
            effective = importlib.metadata.distribution(name)
            shadowing[name] = {"resolved_version": effective.version,
                              "resolved_location": str(Path(effective.locate_file("")).resolve()),
                              "installations": entries}
    record = {"created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "python": sys.version, "platform": platform.platform(),
              "executable": sys.executable, "prefix": sys.prefix,
              "base_prefix": sys.base_prefix, "sys_path": sys.path,
              "torch": torch.__version__, "torch_cuda": torch.version.cuda,
              "packages": dict(sorted(packages.items())),
              "package_installations": dict(sorted(installations.items())),
              "shadowed_packages": dict(sorted(shadowing.items())),
              "script_sha256": file_sha256(__file__),
              "lock_path": str(args.lock.resolve()), "lock_sha256": file_sha256(args.lock)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "packages": len(packages),
                      "python": platform.python_version(), "torch": torch.__version__,
                      "shadowed_packages": sorted(shadowing)}))


if __name__ == "__main__":
    main()
