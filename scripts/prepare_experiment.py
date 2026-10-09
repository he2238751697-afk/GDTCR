#!/usr/bin/env python3
"""Create component-disjoint pair splits and leakage-free pretraining pools."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gdtcr.data import prepare_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "splits")
    parser.add_argument("--seeds", type=int, nargs="+", default=[17, 3407, 2026])
    parser.add_argument("--minimum-pretraining-length", type=int, default=6)
    args = parser.parse_args()
    manifest = prepare_experiment(ROOT, args.output, args.seeds,
                                  min_pretrain_length=args.minimum_pretraining_length)
    print(f"unique pairs: {manifest['unique_pairs']}")
    print(f"graph components: {manifest['component_splits'][0]['n_components']}")
    print(f"largest component: {manifest['component_splits'][0]['largest_component_edges']}")
    print(f"pretraining sequences: gamma={manifest['pretrain_gamma_train']:,}, "
          f"delta={manifest['pretrain_delta_train']:,}")
    print(f"manifest: {args.output / 'manifest.json'}")


if __name__ == "__main__":
    main()
