#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direct multi-model tropical-cyclone track adapters.

No third-party aggregator is used here.  Each model is read from its own
public source:

  AIFS   ECMWF Open Data, AIFS ENS TC-track BUFR
  GEFS   NOAA NOMADS ens_tracker ATCF a-deck files

The output schema matches public/tc-data/<run>.json.  All points are clipped to
100–140°E / 10–35°N before they reach the browser.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import ssl
import pathlib
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Iterable

DOMAIN = {"west": 100.0, "south": 10.0, "east": 140.0, "north": 35.0}
TTL = 600
DISK_TTL = 6 * 3600
DATES_TTL = 3600
CACHE_DIR = pathlib.Path(__file__).resolve().parent / ".tc-cache"
_lock = threading.Lock()
_cache: dict[tuple[str, str], dict] = {}
_dates_cache: dict[str, dict] = {}

MODEL_SPECS = {
    "aifs": {
        "name": "ECMWF AIFS ENS",
        "short": "AIFS",
        "family": "ECMWF",
        "resolution": "0.25°",
        "source": "ECMWF Open Data · AIFS ENS BUFR",
    },
    "gefs": {
        "name": "NOAA GEFS (GFS Ensemble)",
        "short": "GEFS",
        "family": "NOAA",
        "resolution": "0.5°",
        "source": "NOAA NOMADS · ens_tracker GEFS",
    },
}

AIFS_URL = (
    "https://data.ecmwf.int/forecasts/{date}/{hour}z/aifs-ens/0p25/enfo/"
    "{stamp}0000-360h-enfo-tf.bufr"
)
GEFS_BASE = (
    "https://nomads.ncep.noaa.gov/pub/data/nccf/com/ens_tracker/prod/"
    "gefs.{date}/{hour}/tctrack/"
)
_SSL_CONTEXT = ssl._create_unverified_context()


def _http_bytes(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BAMC-EC-TC/1.0 (+https://www.bamc.top)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as response:
        return response.read()


def _http_text(url: str, timeout: int = 40) -> str:
    return _http_bytes(url, timeout).decode("utf-8", "replace")


def _http_ok(url: str, timeout: int = 12) -> bool:
    req = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "BAMC-EC-TC/1.0 (+https://www.bamc.top)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _inside(lat: float, lon: float) -> bool:
    return (
        DOMAIN["south"] <= lat <= DOMAIN["north"]
        and DOMAIN["west"] <= lon <= DOMAIN["east"]
    )


def _deg_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = a[0] - b[0]
    dlon = (a[1] - b[1]) * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlon)


def _recent_cycles(days: int = 2) -> list[str]:
    now = datetime.now(timezone.utc)
    out = []
    for day in range(days):
        cur = now - timedelta(days=day)
        for hour in ("18", "12", "06", "00"):
            out.append(cur.strftime("%Y%m%d") + hour)
    return out


def _stamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def _run_block(spec: dict, date: str, members: list[dict], storm: dict) -> dict:
    dt = _stamp(date)
    return {
        "schema": "bamc-ec-tc-v1",
        "run": {
            "id": date,
            "stamp": date,
            "date": dt.strftime("%Y-%m-%d"),
            "utc": dt.strftime("%Y-%m-%d %H:%M UTC"),
            "iso": dt.isoformat().replace("+00:00", "Z"),
            "display": dt.strftime("%Y/%m/%d %H") + " UTC",
            "short": dt.strftime("%m/%d %HZ"),
            "model": spec["name"],
            "modelShort": spec["short"],
            "family": spec["family"],
            "resolution": spec["resolution"],
            "members": len(members),
        },
        "domain": DOMAIN,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": spec["source"],
        "storms": [storm],
    }


def _make_storm(
    spec: dict,
    name: str,
    system_id: str,
    members: list[dict],
    source_id: str | None = None,
) -> dict:
    all_points = [p for member in members for p in member["track"]]
    leads = sorted({p["lead"] for p in all_points})
    pressures = [p["mslp"] for p in all_points if p.get("mslp") is not None]
    winds = [p["wind"] for p in all_points if p.get("wind") is not None]
    return {
        "id": system_id,
        "name": name,
        "members": members,
        "member_count": len(members),
        "track_points": len(all_points),
        "leads": leads,
        "lead_min": leads[0] if leads else 0,
        "lead_max": leads[-1] if leads else 0,
        "domain": DOMAIN,
        "summary": {
            "id": system_id,
            "name": name,
            "member_count": len(members),
            "lead_max": leads[-1] if leads else 0,
            "min_mslp": min(pressures) if pressures else None,
            "max_wind": max(winds) if winds else None,
        },
        "source_id": source_id,
    }


def _reference(jtwc_systems: list[dict] | None) -> tuple[float, float] | None:
    if not jtwc_systems:
        return None
    system = jtwc_systems[0]
    try:
        return float(system["lat"]), float(system["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _match_name(jtwc_systems: list[dict] | None, point: tuple[float, float]) -> tuple[str, str | None]:
    best = None
    for system in jtwc_systems or []:
        try:
            target = (float(system["lat"]), float(system["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        distance = _deg_distance(point, target)
        if distance <= 6.0 and (best is None or distance < best[0]):
            best = (distance, system)
    if best:
        return str(best[1].get("name") or "SYSTEM"), best[1].get("id")
    return "SYSTEM", None


# ---------------- AIFS ----------------

def _aifs_url(date: str) -> str:
    return AIFS_URL.format(date=date[:8], hour=date[8:10], stamp=date)


def _aifs_dates(force: bool = False) -> list[dict]:
    now = time.time()
    if not force:
        with _lock:
            hit = _dates_cache.get("aifs")
            if hit and now - hit["at"] < TTL:
                return hit["payload"]
    dates = []
    for stamp in _recent_cycles(1):
        if _http_ok(_aifs_url(stamp), timeout=5):
            dt = _stamp(stamp)
            dates.append({"value": stamp, "label": dt.strftime("%m/%d %HZ"), "display": dt.strftime("%Y/%m/%d %H UTC")})
            if len(dates) >= 4:
                break
    payload = {"ok": True, "model": "aifs", "name": MODEL_SPECS["aifs"]["name"], "short": "AIFS", "dates": dates}
    with _lock:
        _dates_cache["aifs"] = {"at": now, "payload": payload}
    return payload


def _aifs_candidates(raw: bytes, reference: tuple[float, float] | None = None) -> list[dict]:
    from eccodes import (
        codes_bufr_new_from_file,
        codes_get,
        codes_get_array,
        codes_release,
        codes_set,
    )

    candidates = []
    # ecCodes' Python binding requires a real file object (fileno).
    tmp = tempfile.NamedTemporaryFile(suffix=".bufr", delete=False)
    tmp.write(raw)
    tmp.close()
    handle = open(tmp.name, "rb")
    try:
        while True:
            bid = codes_bufr_new_from_file(handle)
            if bid is None:
                break
            try:
                codes_set(bid, "unpack", 1)
                n = int(codes_get(bid, "numberOfSubsets"))
                storm_id = str(codes_get(bid, "stormIdentifier") or "").strip()
                lat = codes_get_array(bid, "latitude")
                lon = codes_get_array(bid, "longitude")
                pressure = codes_get_array(bid, "pressureReducedToMeanSeaLevel")
                member_ids = codes_get_array(bid, "ensembleMemberNumber")
                periods = []
                try:
                    periods = [int(v) for v in codes_get_array(bid, "timePeriod")]
                except Exception:
                    periods = []
                if n < 2 or len(lat) < n * 2 or len(pressure) < n:
                    continue
                times = len(pressure) // n
                leads = [0] + periods[: max(0, times - 1)]
                if len(leads) < times:
                    leads = [i * 6 for i in range(times)]
                before = len(candidates)
                for m in range(n):
                    points = []
                    for t in range(times):
                        idx = t * 2 * n + m
                        if idx >= len(lat) or t >= len(leads):
                            continue
                        try:
                            la = float(lat[idx])
                            lo = float(lon[idx])
                            pr = float(pressure[t * n + m])
                        except (IndexError, TypeError, ValueError):
                            continue
                        if abs(pr) > 1e30:
                            pr = None
                        if not _inside(la, lo):
                            continue
                        points.append(
                            {
                                "lead": int(leads[t]),
                                "lat": round(la, 2),
                                "lon": round(lo, 2),
                                "mslp": round(pr / 100.0, 1) if pr is not None else None,
                                "wind": None,
                            }
                        )
                    if not points:
                        continue
                    points.sort(key=lambda p: p["lead"])
                    mid = int(member_ids[m]) if m < len(member_ids) else m + 1
                    candidates.append(
                        {
                            "member": mid,
                            "track": points,
                            "first": (points[0]["lat"], points[0]["lon"]),
                            "storm_id": storm_id,
                        }
                    )
                new_candidates = candidates[before:]
                if new_candidates and not storm_id.startswith("70"):
                    if reference is None:
                        break
                    if any(_deg_distance(c["first"], reference) < 5.0 for c in new_candidates):
                        break
            finally:
                codes_release(bid)
    finally:
        handle.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return candidates


def fetch_aifs(date: str, jtwc_systems: list[dict] | None) -> dict:
    raw = _http_bytes(_aifs_url(date), timeout=90)
    reference = _reference(jtwc_systems)
    candidates = _aifs_candidates(raw, reference)
    if not candidates:
        raise RuntimeError("AIFS BUFR 中没有框内轨迹")
    # AIFS BUFR may repeat the same system under two identifiers.  Keep the
    # first identifier with the largest member set (36W before the duplicate
    # 70W in the current files) so members are not counted twice.
    by_storm: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_storm.setdefault(candidate.get("storm_id") or "UNKNOWN", []).append(candidate)
    preferred = max(by_storm, key=lambda key: (len(by_storm[key]), -list(by_storm).index(key)))
    candidates = by_storm[preferred]
    if reference:
        candidates.sort(key=lambda c: (_deg_distance(c["first"], reference), -len(c["track"])))
        seed = candidates[0]
    else:
        seed = candidates[0]
    name, jtwc_id = _match_name(jtwc_systems, seed["first"])
    if name == "SYSTEM" and seed.get("storm_id"):
        name = seed["storm_id"]
    members = []
    for c in candidates:
        if _deg_distance(c["first"], seed["first"]) > 1.8:
            continue
        points = c["track"]
        mslps = [p["mslp"] for p in points if p["mslp"] is not None]
        members.append(
            {
                "member": c["member"],
                "type": 4,
                "control": False,
                "track": points,
                "min_mslp": min(mslps) if mslps else None,
                "max_wind": None,
                "first": points[0],
                "last": points[-1],
                "storm_id": seed.get("storm_id", ""),
                "storm_name": name,
            }
        )
    if not members:
        raise RuntimeError("AIFS 无法识别目标系集")
    members.sort(key=lambda m: m["member"])
    storm = _make_storm(MODEL_SPECS["aifs"], name, "AIFS", members, seed.get("storm_id"))
    return _run_block(MODEL_SPECS["aifs"], date, members, storm)


# ---------------- GEFS ----------------

def _gefs_url(date: str, hour: str, filename: str) -> str:
    return GEFS_BASE.format(date=date, hour=hour) + filename


def _gefs_dates(force: bool = False) -> list[dict]:
    now = time.time()
    if not force:
        with _lock:
            hit = _dates_cache.get("gefs")
            if hit and now - hit["at"] < TTL:
                return hit["payload"]
    dates = []
    for stamp in _recent_cycles(1):
        url = _gefs_url(stamp[:8], stamp[8:10], f"ac00.t{stamp[8:10]}z.cyclone.trackatcfunix")
        if _http_ok(url):
            dt = _stamp(stamp)
            dates.append({"value": stamp, "label": dt.strftime("%m/%d %HZ"), "display": dt.strftime("%Y/%m/%d %H UTC")})
            if len(dates) >= 4:
                break
    payload = {"ok": True, "model": "gefs", "name": MODEL_SPECS["gefs"]["name"], "short": "GEFS", "dates": dates}
    with _lock:
        _dates_cache["gefs"] = {"at": now, "payload": payload}
    return payload


def _parse_atcf(text: str) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], dict[int, dict]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 12:
            continue
        try:
            basin = parts[0]
            number = parts[1]
            lead = int(parts[5])
            lat = _atcf_coord(parts[6], "N", "S")
            lon = _atcf_coord(parts[7], "E", "W")
            wind = float(parts[8])
            pressure = float(parts[9])
            radius = int(parts[11])
        except (ValueError, IndexError):
            continue
        if not _inside(lat, lon):
            continue
        key = (basin, number)
        grouped.setdefault(key, {})
        previous = grouped[key].get(lead)
        if previous is None or radius == 34:
            grouped[key][lead] = {
                "lead": lead,
                "lat": round(lat, 2),
                "lon": round(lon, 2),
                "mslp": round(pressure, 1) if pressure else None,
                "wind": round(wind, 1) if wind else None,
            }
    return {key: sorted(values.values(), key=lambda p: p["lead"]) for key, values in grouped.items()}


def _atcf_coord(value: str, positive: str, negative: str) -> float:
    value = value.strip().upper()
    if value.endswith(positive) or value.endswith(negative):
        number = float(value[:-1]) / 10.0
        return -number if value.endswith(negative) else number
    return float(value)


def fetch_gefs(date: str, jtwc_systems: list[dict] | None) -> dict:
    hour = date[8:10]
    filenames = [f"ac00.t{hour}z.cyclone.trackatcfunix"] + [
        f"ap{i:02d}.t{hour}z.cyclone.trackatcfunix" for i in range(1, 31)
    ]

    def load(index_name: tuple[int, str]):
        index, filename = index_name
        text = _http_text(_gefs_url(date[:8], hour, filename), timeout=35)
        return index + 1, _parse_atcf(text)

    parsed_members = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(load, pair) for pair in enumerate(filenames)]
        for future in as_completed(futures):
            try:
                member, tracks = future.result()
                parsed_members[member] = tracks
            except Exception:
                continue
    if not parsed_members:
        raise RuntimeError("GEFS ens_tracker 文件不可用")

    reference = _reference(jtwc_systems)
    groups: dict[tuple[str, str], list[tuple[int, list[dict]]]] = {}
    for member, tracks in parsed_members.items():
        for key, points in tracks.items():
            if points:
                groups.setdefault(key, []).append((member, points))
    best_key = None
    best_score = (-1, -1.0)
    for key, group in groups.items():
        first = (group[0][1][0]["lat"], group[0][1][0]["lon"])
        score = (len(group), -(_deg_distance(first, reference) if reference else 0))
        if score > best_score:
            best_score = score
            best_key = key
    if best_key is None:
        raise RuntimeError("GEFS 没有框内系统")

    group = groups[best_key]
    first = (group[0][1][0]["lat"], group[0][1][0]["lon"])
    name, jtwc_id = _match_name(jtwc_systems, first)
    if name == "SYSTEM":
        name = f"{best_key[0]}{best_key[1]}"
    members = []
    for member, points in sorted(group, key=lambda item: item[0]):
        if not points:
            continue
        mslps = [p["mslp"] for p in points if p["mslp"] is not None]
        winds = [p["wind"] for p in points if p["wind"] is not None]
        members.append(
            {
                "member": member,
                "type": 4,
                "control": member == 1,
                "track": points,
                "min_mslp": min(mslps) if mslps else None,
                "max_wind": max(winds) if winds else None,
                "first": points[0],
                "last": points[-1],
                "storm_id": f"{best_key[0]}{best_key[1]}",
                "storm_name": name,
            }
        )
    if not members:
        raise RuntimeError("GEFS 目标系统没有可用成员")
    storm = _make_storm(MODEL_SPECS["gefs"], name, "GEFS", members, f"{best_key[0]}{best_key[1]}")
    return _run_block(MODEL_SPECS["gefs"], date, members, storm)


# ---------------- public API ----------------

def _dates_path(model: str) -> pathlib.Path:
    return CACHE_DIR / ("%s-dates.json" % model)


def _read_dates_disk(model: str) -> dict | None:
    path = _dates_path(model)
    try:
        if time.time() - path.stat().st_mtime > DATES_TTL:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("dates"):
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_dates_disk(model: str, payload: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _dates_path(model)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def fetch_dates(model: str, force: bool = False) -> dict:
    if not force:
        with _lock:
            hit = _dates_cache.get(model)
            if hit and time.time() - hit["at"] < DATES_TTL:
                return hit["payload"]
        disk_hit = _read_dates_disk(model)
        if disk_hit is not None:
            with _lock:
                _dates_cache[model] = {"at": time.time(), "payload": disk_hit}
            return disk_hit
    if model == "aifs":
        payload = _aifs_dates(force)
    elif model == "gefs":
        payload = _gefs_dates(force)
    else:
        raise ValueError("未知模式：%s" % model)
    payload["fetched"] = int(time.time())
    with _lock:
        _dates_cache[model] = {"at": time.time(), "payload": payload}
    _write_dates_disk(model, payload)
    return payload


def _cache_path(model: str, date: str) -> pathlib.Path:
    return CACHE_DIR / ("%s-%s.json" % (model, date))


def _read_disk_cache(model: str, date: str) -> dict | None:
    path = _cache_path(model, date)
    try:
        if time.time() - path.stat().st_mtime > DISK_TTL:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("schema") == "bamc-ec-tc-v1":
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_disk_cache(model: str, date: str, payload: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path(model, date)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def fetch_model(model: str, date: str | None = None, jtwc_systems: list[dict] | None = None) -> dict:
    spec = MODEL_SPECS.get(model)
    if not spec:
        raise ValueError("未知模式：%s" % model)
    if not date:
        dates = fetch_dates(model).get("dates") or []
        if not dates:
            raise RuntimeError("%s 的官方源当前没有可用起报" % spec["name"])
        date = dates[0]["value"]
    if not (len(date) == 10 and date.isdigit()):
        raise ValueError("起报时次格式不合法")
    cache_key = (model, date)
    now = time.time()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and now - hit["at"] < TTL:
            return hit["payload"]
    disk_hit = _read_disk_cache(model, date)
    if disk_hit is not None:
        with _lock:
            _cache[cache_key] = {"at": now, "payload": disk_hit}
        return disk_hit
    if model == "aifs":
        payload = fetch_aifs(date, jtwc_systems)
    elif model == "gefs":
        payload = fetch_gefs(date, jtwc_systems)
    else:
        raise ValueError("未知模式：%s" % model)
    with _lock:
        _cache[cache_key] = {"at": now, "payload": payload}
    _write_disk_cache(model, date, payload)
    return payload
