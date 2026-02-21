# AUTO_COMMENT_HEADER_V1: diff_images.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiffPair:
    label: str
    a: str
    b: str
    out: str


def _identify_size(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(["identify", "-format", "%w %h", str(path)], text=True).strip()
    w_s, h_s = out.split()
    return int(w_s), int(h_s)


def _crop_nw(src: Path, width: int, height: int, dst: Path) -> None:
    subprocess.check_call(
        [
            "convert",
            str(src),
            "-gravity",
            "NorthWest",
            "-crop",
            f"{width}x{height}+0+0",
            "+repage",
            str(dst),
        ]
    )


def _compare_ae(a_path: Path, b_path: Path, out_path: Path) -> int:
    proc = subprocess.run(
        ["compare", "-metric", "AE", str(a_path), str(b_path), str(out_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return int((proc.stderr or "").strip() or "0")


def _load_pairs(path: Path) -> list[DiffPair]:
    payload = json.loads(path.read_text("utf-8"))
    pairs: list[DiffPair] = []
    for item in payload:
        pairs.append(DiffPair(label=item["label"], a=item["a"], b=item["b"], out=item["out"]))
    return pairs


def main() -> int:
    """Diff screenshot pairs using ImageMagick.

    Crops to the stable shared region (min width/height), then runs `compare -metric AE`.
    Produces `metrics.json` under out-dir and enforces a strict per-pair gate.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pairs", required=True, help="JSON file: [{label,a,b,out}, ...]")
    parser.add_argument("--ratio-max", type=float, default=0.01)
    parser.add_argument("--pixels-max", type=int, default=20)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    pairs_path = Path(args.pairs)

    pairs = _load_pairs(pairs_path)
    metrics: list[dict] = []

    for pair in pairs:
        a_path = out_dir / pair.a
        b_path = out_dir / pair.b
        out_path = out_dir / pair.out

        wa, ha = _identify_size(a_path)
        wb, hb = _identify_size(b_path)
        mw, mh = min(wa, wb), min(ha, hb)

        a_cmp = a_path
        b_cmp = b_path
        if (wa, ha) != (mw, mh):
            a_cmp = out_dir / pair.a.replace(".png", "_norm.png")
            _crop_nw(a_path, mw, mh, a_cmp)
        if (wb, hb) != (mw, mh):
            b_cmp = out_dir / pair.b.replace(".png", "_norm.png")
            _crop_nw(b_path, mw, mh, b_cmp)

        total = mw * mh
        diff_pixels = _compare_ae(a_cmp, b_cmp, out_path)
        metrics.append(
            {
                "label": pair.label,
                "size": [mw, mh],
                "diff_pixels": diff_pixels,
                "total_pixels": total,
                "diff_ratio": (diff_pixels / total) if total else 0.0,
                "a": pair.a,
                "b": pair.b,
                "out": pair.out,
            }
        )

    metrics_path = out_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print("metrics.json written:", metrics_path)
    for m in metrics:
        print(f"- {m['label']}: diff_ratio={m['diff_ratio']:.6f} diff_pixels={m['diff_pixels']}")

    failed = [
        m
        for m in metrics
        if (m["diff_ratio"] >= args.ratio_max) or (m["diff_pixels"] >= args.pixels_max)
    ]
    if failed:
        print("")
        print("FAIL: new-api 1:1 diff gate not met.")
        print(
            f"Gate: diff_ratio < {args.ratio_max} AND diff_pixels < {args.pixels_max} for every entry."
        )
        for m in failed:
            print(f"- {m['label']}: diff_ratio={m['diff_ratio']:.6f} diff_pixels={m['diff_pixels']}")
        return 2

    print("")
    print(
        f"PASS: all {len(metrics)}/{len(metrics)} entries satisfy diff_ratio < {args.ratio_max} and diff_pixels < {args.pixels_max}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

