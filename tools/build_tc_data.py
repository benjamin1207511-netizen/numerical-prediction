#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the EC ENS tropical-cyclone JSON used by /tc/.

The raw input is ECMWF's free "enfo" tropical-cyclone track BUFR:
  https://data.ecmwf.int/forecasts/YYYYMMDD/HHz/ifs/0p25/enfo/
      YYYYMMDDHH0000-360h-enfo-tf.bufr

The decoder uses pybufrkit (pure Python) and its WMO BUFR tables.  This
script is intentionally offline: it turns the BUFR messages into small,
browser-friendly JSON files, so the public site only serves static data.

Usage:
  python tools/build_tc_data.py --bufr data/ecmwf_ens_tc_2026102200.bufr
  python tools/build_tc_data.py --download 2026102200 --download 2026102112
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
PUBLIC_DIR = BASE_DIR / "public"
OUT_DIR = PUBLIC_DIR / "tc-data"
DATA_DIR = BASE_DIR / "data"

# The checked-in .libs folder is only a local build convenience; a normal
# installation via `pip install pybufrkit bitstring==3.1.9` works too.
for extra in (
    BASE_DIR / ".libs",
    BASE_DIR / ".libs" / "pybufrkit_src" / "pybufrkit-0.2.25",
    BASE_DIR.parent / ".libs",
    BASE_DIR.parent / ".libs" / "pybufrkit_src" / "pybufrkit-0.2.25",
):
    if extra.is_dir() and str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from pybufrkit.decoder import Decoder  # noqa: E402
from pybufrkit.renderer import NestedJsonRenderer  # noqa: E402

DOMAIN = {"west": 100.0, "south": 10.0, "east": 140.0, "north": 35.0}
RUN_URL = (
    "https://data.ecmwf.int/forecasts/{date}/{hour}z/ifs/0p25/enfo/"
    "{stamp}0000-360h-enfo-tf.bufr"
)


def child(node: dict, key: str) -> dict | None:
    for item in node.get("members") or []:
        if item.get("id") == key:
            return item
    return None


def value(node: dict, key: str) -> Any:
    item = child(node, key)
    return item.get("value") if item else None


def text(value_: Any) -> str:
    if isinstance(value_, bytes):
        return value_.decode("utf-8", "replace").strip()
    return str(value_ or "").strip()


def as_float(value_: Any) -> float | None:
    if value_ is None or isinstance(value_, (bytes, str)):
        return None
    try:
        number = float(value_)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or abs(number) > 1e30:
        return None
    return number


def position_after_significance(node: dict, wanted: int) -> tuple[float | None, float | None]:
    significance = None
    for item in node.get("members") or []:
        if item.get("id") == "008005":
            significance = item.get("value")
        elif item.get("id") == "301023" and significance == wanted:
            lat = as_float(value(item, "005002"))
            lon = as_float(value(item, "006002"))
            return lat, lon
    return None, None


def point_from(item: dict, lead: int, fallback_pos: tuple[float | None, float | None] | None = None):
    lat, lon = position_after_significance(item, 1)
    if lat is None or lon is None:
        if fallback_pos:
            lat, lon = fallback_pos
        else:
            return None
    pressure = as_float(value(item, "010051"))
    wind = as_float(value(item, "011012"))
    # Some weak/invest tracks have no pressure and wind at a given step.
    if lat is None or lon is None:
        return None
    return {
        "lead": int(lead),
        "lat": round(lat, 2),
        "lon": round(lon, 2),
        "mslp": round(pressure / 100.0, 1) if pressure is not None else None,
        "wind": round(wind * 1.943844, 1) if wind is not None else None,
    }


def parse_member(root: dict) -> dict | None:
    member = value(root, "001091")
    if member is None:
        return None
    member = int(member)
    ensemble_type = value(root, "001092")
    storm_id = text(value(root, "001025"))
    storm_name = text(value(root, "001027"))
    if not storm_name:
        storm_name = storm_id

    track: list[dict] = []
    lat, lon = position_after_significance(root, 1)
    init_pressure = as_float(value(root, "010051"))
    init_wind = as_float(value(root, "011012"))
    if lat is not None and lon is not None:
        track.append(
            {
                "lead": 0,
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "mslp": round(init_pressure / 100.0, 1) if init_pressure is not None else None,
                "wind": round(init_wind * 1.943844, 1) if init_wind is not None else None,
            }
        )

    group = child(root, "116000")
    if group:
        for item in group.get("members") or []:
            if not isinstance(item, list):
                continue
            values = {x.get("id"): x.get("value") for x in item if x.get("id") != "301023"}
            lead = as_float(values.get("004024"))
            if lead is None:
                continue
            point = point_from({"members": item}, int(round(lead)))
            if point is None:
                continue
            if track and point["lead"] <= track[-1]["lead"]:
                continue
            track.append(point)

    if not track:
        return None
    track.sort(key=lambda p: p["lead"])

    pressures = [p["mslp"] for p in track if p["mslp"] is not None]
    winds = [p["wind"] for p in track if p["wind"] is not None]
    return {
        "member": member,
        "type": ensemble_type,
        "control": member == 51,
        "track": track,
        "min_mslp": min(pressures) if pressures else None,
        "max_wind": max(winds) if winds else None,
        "first": track[0],
        "last": track[-1],
        "storm_id": storm_id,
        "storm_name": storm_name,
    }


def parse_message(message: Any) -> dict | None:
    out = NestedJsonRenderer().render(message)
    subsets = out[4][2]["value"]
    if not subsets:
        return None
    roots = [subset[0] for subset in subsets if subset]
    if not roots:
        return None
    first = roots[0]
    storm_id = text(value(first, "001025"))
    storm_name = text(value(first, "001027"))
    if not storm_name or storm_name == storm_id:
        return None  # skip unnamed invests (70W/71W ...)
    members = []
    for root in roots:
        parsed = parse_member(root)
        if parsed and parsed["storm_id"] == storm_id:
            members.append(parsed)
    if not members:
        return None

    all_tracks = [p for m in members for p in m["track"]]
    in_domain = any(
        DOMAIN["west"] <= p["lon"] <= DOMAIN["east"] and DOMAIN["south"] <= p["lat"] <= DOMAIN["north"]
        for p in all_tracks
    )
    if not in_domain:
        return None

    return {
        "id": storm_id,
        "name": storm_name,
        "members": members,
        "member_count": len(members),
        "track_points": len(all_tracks),
    }


def split_messages(raw: bytes) -> list[bytes]:
    messages = []
    offset = 0
    while offset + 8 <= len(raw):
        if raw[offset:offset + 4] != b"BUFR":
            # tolerate padding / junk between messages
            offset += 1
            continue
        length = int.from_bytes(raw[offset + 4:offset + 7], "big")
        if length < 8 or offset + length > len(raw):
            break
        messages.append(raw[offset:offset + length])
        offset += length
    return messages


def build_run(path: Path, generated: str) -> dict | None:
    stamp = path.stem.replace("ecmwf_ens_tc_", "")
    if len(stamp) != 10:
        return None
    run_dt = datetime.strptime(stamp, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    raw = path.read_bytes()
    messages = split_messages(raw)
    decoder = Decoder()
    storms = []
    for raw_message in messages:
        try:
            storm = parse_message(decoder.process(raw_message))
        except Exception:
            continue
        if storm:
            storms.append(storm)
    if not storms:
        return None

    storms.sort(key=lambda s: s["member_count"], reverse=True)
    for storm in storms:
        leads = sorted({p["lead"] for m in storm["members"] for p in m["track"]})
        storm["leads"] = leads
        storm["lead_min"] = leads[0] if leads else 0
        storm["lead_max"] = leads[-1] if leads else 0
        storm["domain"] = DOMAIN
        # Compact summary used by the run picker.
        storm["summary"] = {
            "id": storm["id"],
            "name": storm["name"],
            "member_count": storm["member_count"],
            "lead_max": storm["lead_max"],
            "min_mslp": min(
                (m["min_mslp"] for m in storm["members"] if m["min_mslp"] is not None),
                default=None,
            ),
            "max_wind": max(
                (m["max_wind"] for m in storm["members"] if m["max_wind"] is not None),
                default=None,
            ),
        }

    return {
        "schema": "bamc-ec-tc-v1",
        "run": {
            "id": stamp,
            "stamp": stamp,
            "date": run_dt.strftime("%Y-%m-%d"),
            "utc": run_dt.strftime("%Y-%m-%d %H:%M UTC"),
            "iso": run_dt.isoformat().replace("+00:00", "Z"),
            "display": run_dt.strftime("%Y/%m/%d %H") + " UTC",
            "short": run_dt.strftime("%m/%d %HZ"),
            "model": "ECMWF IFS ENS",
            "resolution": "0.25°",
            "members": max((s["member_count"] for s in storms), default=0),
        },
        "domain": DOMAIN,
        "generated": generated,
        "source": "ECMWF open data · TC track BUFR (enfo)",
        "source_url": RUN_URL.format(
            date=stamp[:8], hour=stamp[8:10], stamp=stamp
        ),
        "storms": storms,
    }


def download(stamp: str, target_dir: Path = DATA_DIR) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"ecmwf_ens_tc_{stamp}.bufr"
    if target.is_file() and target.stat().st_size > 0:
        return target
    url = RUN_URL.format(date=stamp[:8], hour=stamp[8:10], stamp=stamp)
    print("download", url)
    req = urllib.request.Request(url, headers={"User-Agent": "bamc-ec-tc/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        target.write_bytes(response.read())
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Build EC ENS TC JSON for the website")
    parser.add_argument("--bufr", nargs="*", type=Path, default=[], help="local BUFR file(s)")
    parser.add_argument("--download", nargs="*", default=[], help="run stamps, e.g. 2026102200")
    parser.add_argument("--all", action="store_true", help="build every data/*.bufr file")
    args = parser.parse_args()

    paths = list(args.bufr)
    for stamp in args.download:
        paths.append(download(stamp))
    if args.all:
        paths = sorted(DATA_DIR.glob("ecmwf_ens_tc_*.bufr"))
    if not paths:
        parser.error("give --bufr, --download or --all")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = []
    for path in paths:
        print("build", path)
        run = build_run(path, generated)
        if not run:
            print("  skipped (no named storm in domain)")
            continue
        filename = f"{run['run']['stamp']}.json"
        (OUT_DIR / filename).write_text(
            json.dumps(run, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        runs.append(
            {
                "id": run["run"]["id"],
                "stamp": run["run"]["stamp"],
                "display": run["run"]["display"],
                "short": run["run"]["short"],
                "iso": run["run"]["iso"],
                "members": run["run"]["members"],
                "file": filename,
                "storms": [s["summary"] for s in run["storms"]],
                "bytes": (OUT_DIR / filename).stat().st_size,
            }
        )
        for storm in run["storms"]:
            print(f"  {storm['id']} {storm['name']} members={storm['member_count']} leads={storm['lead_min']}..{storm['lead_max']}")

    runs.sort(key=lambda r: r["id"], reverse=True)
    index = {
        "schema": "bamc-ec-tc-index-v1",
        "generated": generated,
        "latest": runs[0]["id"] if runs else None,
        "runs": runs,
        "domain": DOMAIN,
    }
    (OUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("wrote", OUT_DIR / "index.json")
    for run in runs:
        print(f"  {run['id']} {run['bytes'] / 1024:.0f} KB  {len(run['storms'])} storm(s)")


if __name__ == "__main__":
    main()
