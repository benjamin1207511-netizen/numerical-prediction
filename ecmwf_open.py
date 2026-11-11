#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ECMWF Open Data 数据源（data.ecmwf.int）。

直接按 step 下载 IFS 0.25° GRIB2（用 .index 里的字节偏移做 Range 请求，只取需要的字段），
再用 eccodes 解码、采样到与 Open-Meteo 完全相同的地点网格结构：

    {"run": "2026-11-07T00:00", "points": [{"latitude":..., "longitude":...,
      "hourly": {"time": [...], "temperature_2m": [...], ...}}, ...]}

这样 ecmwf_chart.py 的绘图流程可以原样复用。

需要：eccodes（pip install eccodes）、numpy。
"""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

try:
    import eccodes
except ImportError:  # 运行到下载阶段再报错，便于 --help 等场景
    eccodes = None

# eccodes 的 definitions 初始化不是线程安全的，多线程并发解码会直接崩溃，这里串行化。
ECC_LOCK = threading.Lock()

BASE_DIR = Path(__file__).resolve().parent
UTC = timezone.utc
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

# 这台机器的 TLS 被中间代理改写，证书链验证不过；ECMWF 公开数据只读，故对该域名放宽校验。
SSL_CTX = ssl._create_unverified_context()

GRID_STEP = 0.25
NI, NJ = 1440, 721  # 0.25° 全球网格
LEADS = list(range(24, 241, 6))
TP_STEPS = list(range(0, 241, 6))
OPEN_WORKERS = max(1, int(os.environ.get("BAMC_OPEN_WORKERS", "4")))
RETRY_DELAYS = (5, 10, 20, 30, 45)

# (输出键, GRIB 参数, 层次)
FIELDS = [
    ("t2m", "2t", None),
    ("d2m", "2d", None),
    ("msl", "msl", None),
    ("u10", "10u", None),
    ("v10", "10v", None),
    ("gust", ("10fg", "10fg3"), None),  # 96h 之后 Open Data 只提供 3 小时阵风 10fg3
    ("cape", "mucape", None),
    ("tcwv", "tcwv", None),
    ("tcc", "tcc", None),
    ("gh500", "gh", "500"),
    ("t500", "t", "500"),
    ("t700", "t", "700"),
    ("t850", "t", "850"),
    ("r700", "r", "700"),
    ("r850", "r", "850"),
    ("r500", "r", "500"),
    ("u200", "u", "200"),
    ("v200", "v", "200"),
    ("d200", "d", "200"),      # 200hPa 散度（s^-1）
    ("vo500", "vo", "500"),    # 500hPa 相对涡度（s^-1）
    ("u500", "u", "500"),
    ("v500", "v", "500"),
    ("u850", "u", "850"),
    ("v850", "v", "850"),
    ("u925", "u", "925"),
    ("v925", "v", "925"),
    ("t925", "t", "925"),
    ("r925", "r", "925"),
]

_index_cache: dict[tuple[str, int], list[dict]] = {}
_log = print


def _base_url(run_dt: datetime, step: int) -> str:
    stamp = run_dt.strftime("%Y%m%d%H%M%S")
    day = run_dt.strftime("%Y%m%d")
    hh = run_dt.strftime("%H")
    return ("https://data.ecmwf.int/forecasts/%s/%sz/ifs/0p25/oper/%s-%dh-oper-fc"
            % (day, hh, stamp, step))


def _get(url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return resp.read()


def _index(run_dt: datetime, step: int) -> list[dict]:
    key = (run_dt.isoformat(), step)
    if key in _index_cache:
        return _index_cache[key]
    raw = _get(_base_url(run_dt, step) + ".index", timeout=60)
    entries = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    _index_cache[key] = entries
    return entries


def _pick(entries: list[dict], params, level: str | None) -> dict | None:
    names = (params,) if isinstance(params, str) else tuple(params)
    for item in entries:
        if item.get("param") not in names:
            continue
        if level is None and item.get("levelist") is None:
            return item
        if level is not None and str(item.get("levelist")) == level:
            return item
    return None


def _cache_path(run_dt: datetime, step: int) -> Path:
    stamp = run_dt.strftime("%Y%m%d%H")
    return BASE_DIR / "_cache" / "open_steps" / stamp / ("%03d.json" % step)


def _load_cached_step(run_dt: datetime, step: int) -> dict | None:
    path = _cache_path(run_dt, step)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        domains = {}
        for name, fields in (raw.get("domains") or {}).items():
            domains[name] = {
                key: (None if value is None else np.asarray(value, dtype="float32"))
                for key, value in fields.items()
            }
        return {"step": step, "domains": domains}
    except (OSError, ValueError):
        return None


def _save_cached_step(run_dt: datetime, step: int, payload: dict) -> None:
    path = _cache_path(run_dt, step)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialisable = {
            "step": step,
            "domains": {
                name: {key: (None if value is None else value.tolist())
                       for key, value in fields.items()}
                for name, fields in payload["domains"].items()
            },
        }
        path.write_text(json.dumps(serialisable), encoding="utf-8")
    except OSError:
        pass


def _fetch_field(run_dt: datetime, step: int, params, level: str | None,
                 lat_idx: np.ndarray, lon_idx: np.ndarray) -> np.ndarray | None:
    entries = _index(run_dt, step)
    item = _pick(entries, params, level)
    if item is None:
        _log("  !! 缺少字段 %s %s step %d"
             % ("/".join((params,) if isinstance(params, str) else params), level, step))
        return None
    offset = int(item["_offset"])
    length = int(item["_length"])
    url = _base_url(run_dt, step) + ".grib2"
    last = None
    for delay in (*RETRY_DELAYS, None):
        try:
            raw = _get(url, {"Range": "bytes=%d-%d" % (offset, offset + length - 1)}, timeout=180)
            if eccodes is None:
                raise RuntimeError("未安装 eccodes：python -m pip install eccodes")
            with ECC_LOCK:
                gid = eccodes.codes_new_from_message(raw)
                try:
                    if eccodes.codes_get_long(gid, "Ni") != NI or eccodes.codes_get_long(gid, "Nj") != NJ:
                        raise RuntimeError("网格尺寸异常 %s" % param)
                    values = np.asarray(eccodes.codes_get_values(gid), dtype="float32")
                finally:
                    eccodes.codes_release(gid)
            return values[lat_idx * NI + lon_idx]
        except Exception as exc:  # noqa: BLE001
            last = exc
            if delay is None:
                break
            time.sleep(delay)
    raise RuntimeError("下载字段失败 %s %s step %d: %s" % (param, level, step, last))


def _sample_indices(lats: list[float], lons: list[float]) -> tuple[np.ndarray, np.ndarray]:
    lat_idx = np.rint((90.0 - np.asarray(lats, dtype=float)) / GRID_STEP).astype(int)
    lon_idx = np.rint(np.asarray(lons, dtype=float) / GRID_STEP).astype(int) % NI
    return lat_idx, lon_idx


def _rh_from_dewpoint(t_k: np.ndarray, td_k: np.ndarray) -> np.ndarray:
    """由 2m 气温/露点计算相对湿度；无效值（0 K）按 0 处理，避免 exp 溢出。"""
    valid = (t_k > 100.0) & (td_k > 100.0) & (td_k <= t_k + 0.5)
    t_c = np.clip(t_k - 273.15, -80.0, 60.0)
    td_c = np.clip(td_k - 273.15, -80.0, 60.0)

    def es(c):
        return 6.112 * np.exp(17.67 * c / (c + 243.5))

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        rh = 100.0 * es(td_c) / es(t_c)
    rh = np.where(valid, np.clip(rh, 0.0, 100.0), 0.0)
    return rh


def _dewpoint_c(t_k: np.ndarray, rh: np.ndarray) -> np.ndarray:
    """由气温（K）和相对湿度（%）反算露点（°C）。"""
    t_c = np.clip(t_k - 273.15, -80.0, 60.0)
    rh = np.clip(rh, 1.0, 100.0)
    es = 6.112 * np.exp(17.67 * t_c / (t_c + 243.5))
    e = np.maximum(rh / 100.0 * es, 1e-6)
    ln = np.log(e / 6.112)
    return 243.5 * ln / (17.67 - ln)


def _theta_e_k(t_k: np.ndarray, rh: np.ndarray, pressure: float = 850.0) -> np.ndarray:
    """假相当位温（K），由气温与相对湿度计算（Bolton 1980）。"""
    tdk = np.clip(_dewpoint_c(t_k, rh) + 273.15, 150.0, 340.0)
    tk = np.clip(t_k, 150.0, 340.0)
    td_c = tdk - 273.15
    es = 6.112 * np.exp(17.67 * td_c / np.clip(td_c + 243.5, 1e-3, None))
    q = np.clip(0.622 * es / np.maximum(pressure - es, 1.0), 0.0, 0.05)
    theta = tk * (1000.0 / pressure) ** 0.2854
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        tlcl = 1.0 / (1.0 / (tdk - 56.0) + np.log(tk / tdk) / 800.0) + 56.0
        theta_e = theta * np.exp((3376.0 / tlcl - 2.54) * q * (1.0 + 0.81 * q))
    return np.clip(theta_e, 250.0, 420.0)


def _step_fields(run_dt: datetime, step: int, domains: dict) -> dict:
    """下载一个 step 的所有字段并采样到各区域的地点网格（带本地缓存）。"""
    cached = _load_cached_step(run_dt, step)
    if cached is not None and set(domains).issubset(cached["domains"]):
        required = set()
        if step in LEADS:
            required = {key for key, _, _ in FIELDS}
        else:
            required = {"t2m"}
        if step in TP_STEPS:
            required = set(required) | {"tp"}
        have = set(next(iter(cached["domains"].values())).keys())
        missing = required - have
        if not missing:
            _log("  step %3dh 使用缓存" % step)
            return cached
        _log("  step %3dh 缓存缺 %d 个字段，补下载" % (step, len(missing)))
        for out_key, param, level in FIELDS:
            if out_key not in missing:
                continue
            for name, dom in domains.items():
                lat_idx, lon_idx = dom["indices"]
                cached["domains"][name][out_key] = _fetch_field(
                    run_dt, step, param, level, lat_idx, lon_idx)
        if "tp" in missing:
            for name, dom in domains.items():
                lat_idx, lon_idx = dom["indices"]
                cached["domains"][name]["tp"] = _fetch_field(
                    run_dt, step, "tp", None, lat_idx, lon_idx)
        _save_cached_step(run_dt, step, cached)
        return cached

    result = {"step": step, "domains": {}}
    for name, dom in domains.items():
        result["domains"][name] = {}
    for out_key, param, level in FIELDS:
        if step not in LEADS and out_key != "t2m":
            # 24h 变温需要 lead-24h 的 2m 气温，0/6/12/18h 也取 t2m
            continue
        for name, dom in domains.items():
            lat_idx, lon_idx = dom["indices"]
            values = _fetch_field(run_dt, step, param, level, lat_idx, lon_idx)
            result["domains"][name][out_key] = values
    if step in TP_STEPS:
        for name, dom in domains.items():
            lat_idx, lon_idx = dom["indices"]
            values = _fetch_field(run_dt, step, "tp", None, lat_idx, lon_idx)
            result["domains"][name]["tp"] = values
    _save_cached_step(run_dt, step, result)
    return result


def fetch_grid(run_iso: str, domains_cfg: dict, log=print) -> dict:
    """下载一个起报场，返回 {"run":..., "points": [...]}（与 Open-Meteo 结构一致）。"""
    global _log
    _log = log
    run_dt = datetime.fromisoformat(run_iso.replace("Z", "+00:00"))
    if run_dt.tzinfo is None:
        run_dt = run_dt.replace(tzinfo=UTC)
    run_dt = run_dt.astimezone(UTC)

    domains = {}
    for name, cfg in domains_cfg.items():
        lats = []
        y = cfg["south"]
        while y <= cfg["north"] + 1e-9:
            lats.append(round(y, 2))
            y += cfg["fetch_step"]
        lons = []
        x = cfg["west"]
        while x <= cfg["east"] + 1e-9:
            lons.append(round(x, 2))
            x += cfg["fetch_step"]
        points = [(la, lo) for la in lats for lo in lons]
        la_arr = [p[0] for p in points]
        lo_arr = [p[1] for p in points]
        domains[name] = {"points": points, "indices": _sample_indices(la_arr, lo_arr)}

    steps = sorted(set(LEADS) | set(TP_STEPS))
    log("ECMWF Open Data：%d 个 step × %d 个字段，%d 并发"
        % (len(steps), len(FIELDS), OPEN_WORKERS))

    step_data: dict[int, dict] = {}
    started = time.time()
    with ThreadPoolExecutor(max_workers=OPEN_WORKERS) as pool:
        futures = {pool.submit(_step_fields, run_dt, step, domains): step for step in steps}
        for future in as_completed(futures):
            step = futures[future]
            step_data[step] = future.result()
            log("  step %3dh 完成（%.0fs）" % (step, time.time() - started))

    result = {"run": run_dt.strftime("%Y-%m-%dT%H:%M"), "points": {}}
    times = [run_dt + timedelta(hours=h) for h in range(0, 241)]
    time_keys = [t.strftime("%Y-%m-%dT%H:%M") for t in times]

    for name, dom in domains.items():
        npoints = len(dom["points"])
        hourly = {key: np.zeros((npoints, 241), dtype="float32")
                  for key in ("t2m", "d2m", "msl", "u10", "v10", "gust", "cape",
                              "tcwv", "tcc", "gh500", "t500", "t700", "t850",
                              "r700", "r850", "r500", "u500", "v500", "u850",
                              "v850", "u925", "v925", "t925", "r925",
                              "u200", "v200", "d200", "vo500", "tp")}

        for step, payload in step_data.items():
            fields = payload["domains"][name]
            for key, values in fields.items():
                if values is None or key not in hourly:
                    continue
                hourly[key][:, step] = values

        # 派生：降水增量（mm/6h）、风、湿度
        tp_mm = hourly["tp"] * 1000.0
        rain = np.zeros_like(tp_mm)
        rain[:, 6:] = np.maximum(tp_mm[:, 6:] - tp_mm[:, :-6], 0.0)
        hourly["precipitation"] = rain

        def wind(u, v):
            speed = np.hypot(u, v) * 1.943844  # m/s -> kn
            direction = (270.0 - np.degrees(np.arctan2(v, u))) % 360.0
            return speed, direction

        for tag, ukey, vkey in (("500hPa", "u500", "v500"),
                                ("200hPa", "u200", "v200"),
                                ("850hPa", "u850", "v850"),
                                ("925hPa", "u925", "v925"),
                                ("10m", "u10", "v10")):
            speed, direction = wind(hourly[ukey], hourly[vkey])
            hourly["wind_speed_" + tag] = speed
            hourly["wind_direction_" + tag] = direction

        points_out = []
        for i, (la, lo) in enumerate(dom["points"]):
            out = {
                "latitude": la,
                "longitude": lo,
                "hourly": {
                    "time": time_keys,
                    "temperature_2m": (hourly["t2m"][i] - 273.15).tolist(),
                    "precipitation": hourly["precipitation"][i].tolist(),
                    "geopotential_height_500hPa": hourly["gh500"][i].tolist(),
                    "pressure_msl": (hourly["msl"][i] / 100.0).tolist(),
                    "wind_speed_500hPa": hourly["wind_speed_500hPa"][i].tolist(),
                    "wind_direction_500hPa": hourly["wind_direction_500hPa"][i].tolist(),
                    "wind_speed_850hPa": hourly["wind_speed_850hPa"][i].tolist(),
                    "wind_direction_850hPa": hourly["wind_direction_850hPa"][i].tolist(),
                    "wind_speed_10m": hourly["wind_speed_10m"][i].tolist(),
                    "wind_direction_10m": hourly["wind_direction_10m"][i].tolist(),
                    "wind_speed_925hPa": hourly["wind_speed_925hPa"][i].tolist(),
                    "wind_direction_925hPa": hourly["wind_direction_925hPa"][i].tolist(),
                    "wind_speed_200hPa": hourly["wind_speed_200hPa"][i].tolist(),
                    "wind_direction_200hPa": hourly["wind_direction_200hPa"][i].tolist(),
                    "divergence_200hPa": (hourly["d200"][i] * 1e5).tolist(),
                    "vorticity_500hPa": (hourly["vo500"][i] * 1e5).tolist(),
                    "wind_gusts_10m": (hourly["gust"][i] * 1.943844).tolist(),
                    "cape": hourly["cape"][i].tolist(),
                    "total_column_integrated_water_vapour": hourly["tcwv"][i].tolist(),
                    "cloud_cover": (hourly["tcc"][i] * 100.0).tolist(),
                    "temperature_850hPa": (hourly["t850"][i] - 273.15).tolist(),
                    "dew_point_850hPa": _dewpoint_c(hourly["t850"][i], hourly["r850"][i]).tolist(),
                    "relative_humidity_850hPa": hourly["r850"][i].tolist(),
                    "theta_e_850": _theta_e_k(hourly["t850"][i], hourly["r850"][i]).tolist(),
                    "temperature_700hPa": (hourly["t700"][i] - 273.15).tolist(),
                    "dew_point_700hPa": _dewpoint_c(hourly["t700"][i], hourly["r700"][i]).tolist(),
                    "temperature_500hPa": (hourly["t500"][i] - 273.15).tolist(),
                    "relative_humidity_500hPa": hourly["r500"][i].tolist(),
                    "temperature_925hPa": (hourly["t925"][i] - 273.15).tolist(),
                    "relative_humidity_925hPa": hourly["r925"][i].tolist(),
                    "relative_humidity_2m": _rh_from_dewpoint(
                        hourly["t2m"][i], hourly["d2m"][i]).tolist(),
                },
            }
            points_out.append(out)
        result["points"][name] = {"run": result["run"], "points": points_out}
    return result


def latest_run(log=print) -> str:
    """返回最新的、已提供到 +240h 的 00Z / 12Z 起报场。"""
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    block = now.replace(hour=(now.hour // 12) * 12)
    for offset in range(0, 96, 12):
        run_dt = block - timedelta(hours=offset)
        run_iso = run_dt.strftime("%Y-%m-%dT%H:%M")
        try:
            _index(run_dt, 240)
            log("Open Data 起报场 %s 可用" % run_iso)
            return run_iso
        except Exception:  # noqa: BLE001
            log("Open Data 起报场 %s 尚不可用" % run_iso)
    raise RuntimeError("没有找到可用的 ECMWF Open Data 起报场")
