"""CLI: python -m generator --n 200 --anomaly-rate 0.25 --seed 42 --out data/synthetic/dataset-v1"""

from __future__ import annotations

import argparse
from typing import Any

from generator import build_dataset, ground_truth, write_dataset
from generator.render import write_image_leg


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="generator", description=__doc__)
    cli.add_argument("--n", type=int, default=200, help="number of applications")
    cli.add_argument(
        "--anomaly-rate", type=float, default=0.25, help="fraction with planted anomalies"
    )
    cli.add_argument("--seed", type=int, default=42, help="deterministic RNG seed")
    cli.add_argument(
        "--out", type=str, default="data/synthetic/dataset-v1", help="output directory"
    )
    cli.add_argument(
        "--png",
        type=int,
        default=0,
        metavar="N",
        help="also render N documents to docs_img/ as PNG for the vision leg "
        "(needs pip install -e data/synthetic[images])",
    )
    return cli


def main(argv: list[str] | None = None) -> int:
    args: Any = parser().parse_args(argv)
    apps = build_dataset(n=args.n, anomaly_rate=args.anomaly_rate, seed=args.seed)
    labels = ground_truth(apps, seed=args.seed, anomaly_rate=args.anomaly_rate)
    out = write_dataset(apps, labels, args.out)
    counts = labels["counts"]
    print(
        f"wrote {counts['applications']} applications, {counts['documents']} documents to {out}"
        f"\n  clean={counts['clean']} anomalous={counts['anomalous']}"
        f"\n  fails by check: {counts['failByCheck']}"
        f"\n  anomalies: {counts['byAnomalyType']}"
    )
    if args.png:
        manifest = write_image_leg(apps, args.out, args.png)
        types = sorted({entry["docType"] for entry in manifest["documents"]})
        print(f"  rendered {manifest['count']} PNGs into {out}/docs_img across {len(types)} types")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
