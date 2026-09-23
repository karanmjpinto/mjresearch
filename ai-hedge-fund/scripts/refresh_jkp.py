"""Rebuild the JKP factor-return file the Factors tab reads.

Run from the repo root:

    uv run python scripts/refresh_jkp.py
    uv run --with openpyxl python scripts/refresh_jkp.py --details   # also rebuild
                                                                     # factor names,
                                                                     # citations and
                                                                     # in-sample windows

Source: Jensen, Kelly and Pedersen, "Is There a Replication Crisis in Finance?"
(Journal of Finance, 2023), published at https://jkpfactors.com. The returns are
the authors' own US, monthly, capped value-weighted long-short portfolios —
the site's default series — pulled from the public bucket the site's download
page links to. Nothing here re-estimates a factor; this script only reshapes
their CSV into one JSON file the API can serve without a network call.

Why a committed file and not a live fetch: the authors update the data about
once a year, the API should answer offline, and a factor chart that silently
changes shape between two page loads is worse than one that carries its date.
The file records the last month it covers, and the UI prints it.

The factor details (names, the paper each one comes from, the original sample
window, the sign convention) come from the authors' replication repository as
an .xlsx, which needs openpyxl. They change far less often than the returns,
so they live in their own file and are only rebuilt with --details.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import re
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("refresh_jkp")

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "factors"
RETURNS_FILE = OUT_DIR / "jkp-usa-monthly-vw_cap.json"
DETAILS_FILE = OUT_DIR / "jkp-factor-details.json"

BUCKET = "https://jkpfactors.s3.amazonaws.com/public"
REPLICATION = "https://raw.githubusercontent.com/bkelly-lab/ReplicationCrisis/master/GlobalFactors"
REGION, FREQ, WEIGHTING = "usa", "monthly", "vw_cap"


def _zip_url(kind: str) -> str:
    # The site's own naming: [usa]_[all_themes]_[monthly]_[vw_cap].zip, URL-escaped.
    name = f"[{REGION}]_[{kind}]_[{FREQ}]_[{WEIGHTING}].zip"
    return f"{BUCKET}/{urllib.request.quote(name)}"


def _get(url: str) -> bytes:
    log.info("GET %s", url)
    with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 — fixed https URLs
        return r.read()


def _csv_from_zip(url: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(_get(url))) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8")))


def theme_id(label: str) -> str:
    """'Short-Term Reversal' -> 'short_term_reversal', matching the themes CSV."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _fix_mojibake(s: str) -> str:
    # The xlsx carries UTF-8 read as cp1252 in places ("analystsâ€™").
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _in_sample(raw: object) -> tuple[int, int] | None:
    years = re.findall(r"(1[89]\d\d|20\d\d)", str(raw or ""))
    return (int(years[0]), int(years[-1])) if len(years) >= 2 else None


def build_details() -> dict:
    import openpyxl  # only needed here; see the module docstring

    labels = {
        r["characteristic"]: r["cluster"]
        for r in csv.DictReader(io.StringIO(_get(f"{REPLICATION}/Cluster%20Labels.csv").decode()))
    }
    wb = openpyxl.load_workbook(
        io.BytesIO(_get(f"{REPLICATION}/Factor%20Details.xlsx")), read_only=True
    )
    rows = list(wb["details"].iter_rows(values_only=True))
    head = rows[0]
    factors: dict[str, dict] = {}
    for raw in rows[1:]:
        r = dict(zip(head, raw, strict=False))
        fid = r.get("abr_jkp")
        if not fid or fid not in labels:
            continue
        sample = _in_sample(r.get("in-sample period"))
        tstat = r.get("t-stat")
        factors[fid] = {
            "name": _fix_mojibake(str(r.get("name_new") or r.get("name") or fid)).strip(),
            "theme": theme_id(labels[fid]),
            "cite": _fix_mojibake(str(r["cite"])).strip() if r.get("cite") else None,
            "in_sample": list(sample) if sample else None,
            "original_t": float(tstat) if isinstance(tstat, (int, float)) else None,
        }
    themes = {theme_id(v): v for v in sorted(set(labels.values()))}
    return {"source": f"{REPLICATION}/Factor%20Details.xlsx", "themes": themes, "factors": factors}


def build_returns(details: dict) -> dict:
    theme_rows = _csv_from_zip(_zip_url("all_themes"))
    factor_rows = _csv_from_zip(_zip_url("all_factors"))

    months = sorted({r["date"][:7] for r in theme_rows} | {r["date"][:7] for r in factor_rows})
    index = {m: i for i, m in enumerate(months)}

    def series(rows: list[dict[str, str]]) -> dict[str, dict]:
        by: dict[str, dict[int, float]] = defaultdict(dict)
        extra: dict[str, dict] = {}
        for r in rows:
            by[r["name"]][index[r["date"][:7]]] = float(r["ret"])
            extra[r["name"]] = r
        out = {}
        for name, pts in by.items():
            start, end = min(pts), max(pts)
            out[name] = {
                "start": start,
                # A missing month is null, not zero: zero is a return.
                "returns": [round(pts[i], 6) if i in pts else None for i in range(start, end + 1)],
                "_row": extra[name],
            }
        return out

    themes = series(theme_rows)
    factors = series(factor_rows)

    missing = set(factors) - set(details["factors"])
    if missing:
        log.warning("factors with no details (rerun with --details): %s", sorted(missing))

    return {
        "source": {
            "name": "JKP Global Factor Data",
            "url": "https://jkpfactors.com",
            "paper": "Jensen, Kelly and Pedersen (2023), “Is There a Replication Crisis in Finance?”, Journal of Finance 78(5)",
            "files": [_zip_url("all_themes"), _zip_url("all_factors")],
        },
        "region": REGION,
        "frequency": FREQ,
        "weighting": WEIGHTING,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "months": months,
        "themes": {
            k: {
                "n_factors": int(v["_row"]["n_factors"]),
                "start": v["start"],
                "returns": v["returns"],
            }
            for k, v in sorted(themes.items())
        },
        "factors": {
            k: {
                "direction": int(v["_row"]["direction"]),
                "start": v["start"],
                "returns": v["returns"],
            }
            for k, v in sorted(factors.items())
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--details", action="store_true", help="also rebuild factor details (needs openpyxl)"
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.details or not DETAILS_FILE.exists():
        details = build_details()
        DETAILS_FILE.write_text(
            json.dumps(details, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        log.info("wrote %s (%d factors)", DETAILS_FILE.relative_to(ROOT), len(details["factors"]))
    details = json.loads(DETAILS_FILE.read_text(encoding="utf-8"))

    data = build_returns(details)
    # Written whole or not at all, like the screen caches: a half-written file
    # would parse as a shorter history rather than fail.
    tmp = RETURNS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(RETURNS_FILE)
    log.info(
        "wrote %s: %d themes, %d factors, %s to %s",
        RETURNS_FILE.relative_to(ROOT),
        len(data["themes"]),
        len(data["factors"]),
        data["months"][0],
        data["months"][-1],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
