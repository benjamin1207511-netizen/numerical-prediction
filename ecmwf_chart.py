#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「华南 ECMWF IFS 预报图」系列：

  - combined: 500hPa 高度 + 850hPa 风 + 6 小时降雨
  - t2m:      2m 气温
  - h500:     500hPa 高度 + 500hPa 风
  - rain24:   24 小时降雨
  - mslp:     海平面气压
  - wind10:   10m 风场
  - wind925:  925hPa 风场
  - gust24:   24 小时极大阵风
  - cape:     CAPE
  - kindex:   K 指数
  - pwat:     可降水量（PWAT）
  - rh2m:     2m 相对湿度
  - rh500:    500hPa 相对湿度
  - cloud:    总云量

数据来自 Open-Meteo 的 ECMWF IFS 0.25° 单次运行接口（底层为 ECMWF IFS）。
输出为静态 PNG 和每个产品自己的 manifest.json，供 server.py 直接读取，
网站运行时不需要安装 matplotlib / cartopy。

用法：
  python ecmwf_chart.py                         # 自动选择最新可用起报场并抓取
  python ecmwf_chart.py --run 2026-10-20T00:00  # 指定起报场
  python ecmwf_chart.py --input cache/grid.json --run 2026-10-20T00:00
  python ecmwf_chart.py --products t2m,h500    # 只更新部分产品

依赖（仅生成时需要）：
  numpy matplotlib cartopy scipy
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "ecmwf"
TZ_CN = timezone(timedelta(hours=8))
UTC = timezone.utc
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"

DOMAINS = {
    # 默认华南范围：16–28°N，105–121°E（0.5° 输入、0.25° 绘图，精度翻倍）
    "sc": {
        "west": 105.0, "south": 16.0, "east": 121.0, "north": 28.0,
        "fetch_step": 0.5, "fine_step": 0.25,
    },
    # 东亚范围：0–50°N，80–140°E
    "ea": {
        "west": 80.0, "south": 0.0, "east": 140.0, "north": 50.0,
        "fetch_step": 2.5, "fine_step": 0.5,
    },
}
DEFAULT_DOMAIN = "sc"
WEST, SOUTH, EAST, NORTH = 105.0, 16.0, 121.0, 28.0
FINE_STEP = 0.25
# 240h 数据量较大，下载网格按 domain 的 fetch_step；绘图用 fine_step。
LEADS = list(range(24, 241, 6))
SINGLE_RUN_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
MAIN_RUN_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo 对「大量点 × 22 个变量 × 11 天」的单次请求容易超时，
# 拆成 6 个并发小请求后再合并，保证 240h 数据也能稳定下载。
VAR_GROUPS = [
    [
        "temperature_2m",
        "precipitation",
        "geopotential_height_500hPa",
        "pressure_msl",
    ],
    [
        "wind_speed_500hPa",
        "wind_direction_500hPa",
        "wind_speed_850hPa",
        "wind_direction_850hPa",
    ],
    [
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_speed_925hPa",
        "wind_direction_925hPa",
    ],
    [
        "wind_gusts_10m",
        "cape",
        "total_column_integrated_water_vapour",
        "cloud_cover",
    ],
    [
        "temperature_850hPa",
        "dew_point_850hPa",
        "temperature_700hPa",
    ],
    [
        "dew_point_700hPa",
        "temperature_500hPa",
        "relative_humidity_2m",
        "relative_humidity_500hPa",
    ],
]

# 东亚区域只需要综合图和 500hPa 风场所需的变量。
EA_VAR_GROUPS = [
    ["precipitation", "geopotential_height_500hPa"],
    ["wind_speed_500hPa", "wind_direction_500hPa"],
    ["wind_speed_850hPa", "wind_direction_850hPa"],
]

PRODUCTS = {
    "combined": {
        "subdir": "combined",
        "prefix": "ecmwf_southchina_",
        "title": "500hPa Height & 850hPa Wind & 6h Rainfall",
        "kind": "combined",
        "domain": "sc",
    },
    "combined_ea": {
        "subdir": "combined-ea",
        "prefix": "ecmwf_southchina_ea_",
        "title": "East Asia · 500hPa Height & 850hPa Wind & 6h Rainfall",
        "kind": "combined",
        "domain": "ea",
    },
    "t2m": {
        "subdir": "t2m",
        "prefix": "ecmwf_t2m_",
        "title": "2m Temperature",
        "kind": "t2m",
    },
    "h500": {
        "subdir": "h500",
        "prefix": "ecmwf_h500_",
        "title": "Wind & Height at 500hPa",
        "kind": "h500",
        "domain": "sc",
    },
    "h500_ea": {
        "subdir": "h500-ea",
        "prefix": "ecmwf_h500_ea_",
        "title": "East Asia · Wind & Height at 500hPa",
        "kind": "h500",
        "domain": "ea",
    },
    "rain24": {
        "subdir": "rain24",
        "prefix": "ecmwf_rain24_",
        "title": "24h Precipitation (mm)",
        "kind": "rain24",
    },
    "mslp": {
        "subdir": "mslp",
        "prefix": "ecmwf_mslp_",
        "title": "Sea-level Pressure",
        "kind": "mslp",
    },
    "wind10": {
        "subdir": "wind10",
        "prefix": "ecmwf_wind10_",
        "title": "10m Wind",
        "kind": "wind10",
    },
    "wind925": {
        "subdir": "wind925",
        "prefix": "ecmwf_wind925_",
        "title": "925hPa Wind",
        "kind": "wind925",
    },
    "gust24": {
        "subdir": "gust24",
        "prefix": "ecmwf_gust24_",
        "title": "24h Max Wind Gust",
        "kind": "gust24",
    },
    "cape": {
        "subdir": "cape",
        "prefix": "ecmwf_cape_",
        "title": "CAPE",
        "kind": "cape",
    },
    "kindex": {
        "subdir": "kindex",
        "prefix": "ecmwf_kindex_",
        "title": "K Index",
        "kind": "kindex",
    },
    "pwat": {
        "subdir": "pwat",
        "prefix": "ecmwf_pwat_",
        "title": "PWAT",
        "kind": "pwat",
    },
    "rh2m": {
        "subdir": "rh2m",
        "prefix": "ecmwf_rh2m_",
        "title": "2m Relative Humidity",
        "kind": "rh2m",
    },
    "rh500": {
        "subdir": "rh500",
        "prefix": "ecmwf_rh500_",
        "title": "500hPa Relative Humidity",
        "kind": "rh500",
    },
    "cloud": {
        "subdir": "cloud",
        "prefix": "ecmwf_cloud_",
        "title": "Total Cloud Cover",
        "kind": "cloud",
    },
}

RAIN_6H_LEVELS = [0.1, 1, 4, 13, 25, 60, 120, 250]
RAIN_6H_COLORS = [
    "#f4f9f0", "#b9e3ad", "#77c96d", "#36a35a",
    "#5d8bd9", "#294cb0", "#b2188f",
]
RAIN_24H_LEVELS = [0.1, 1, 10, 25, 50, 100, 250]
RAIN_24H_COLORS = ["#f7f7f7", "#b7e6b0", "#4daf4a", "#377eb8", "#00008b", "#ff00ff"]

TEMP_LEVELS = [-5, 0, 5, 10, 15, 20, 25, 27, 29, 31, 33, 35]
TEMP_COLORS = [
    "#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#ffffbf",
    "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026",
]

HEIGHT_FILL_LEVELS = [5760, 5800, 5840, 5880, 5920, 5960]
HEIGHT_FILL_COLORS = ["#d9f0a3", "#ffffbf", "#fee391", "#fec44f", "#fe9929"]

MSLP_LEVELS = [985, 990, 992.5, 995, 997.5, 1000, 1002.5, 1005,
               1007.5, 1010, 1012.5, 1015, 1017.5, 1020, 1022.5,
               1025, 1027.5, 1030]

# 10m 风场 / 24h 阵风统一使用参考图右侧的 15 级风速色阶。
WIND_SPEED_LEVELS = [0.3, 3.4, 8, 10.8, 13.9, 17.2, 20.8, 24.5,
                     28.5, 32.7, 37.2, 41.5, 46.2, 51, 56.1]
WIND_SPEED_LABELS = ["0.3", "3.4", "8", "10.8", "13.9", "17.2", "20.8",
                     "24.5", "28.5", "32.7", "37.2", "41.5", "46.2", "51", "56.1"]
WIND_SPEED_COLORS = [
    "#d6e2ff", "#b5c9ff", "#8eb2ff", "#7f96ff", "#6370f7",
    "#0063ff", "#009696", "#63ff00", "#96ff00", "#c6ff33",
    "#ffff00", "#ffc600", "#ffa000", "#ff7c00",
]
WIND925_LEVELS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50]
CAPE_LEVELS = [0, 100, 250, 500, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
K_LEVELS = [-10, 0, 10, 15, 20, 25, 30, 35, 40, 45, 50]
PWAT_LEVELS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70]
RH_LEVELS = [0, 20, 30, 40, 50, 60, 70, 80, 85, 90, 95, 100]

# 总云量：0–100% 映射到 0–10 成；色阶参考「Total Cloud Cover」参考图的 4–9 级蓝色渐变。
CLOUD_LEVELS = [40, 50, 60, 70, 80, 90]
CLOUD_LABELS = ["4", "5", "6", "7", "8", "9"]
CLOUD_COLORS = ["#EAFCFC", "#BAF6FC", "#96EAFC", "#78D2FC", "#54AEFC"]
CLOUD_OVER = "#3684FC"


def log(msg: str) -> None:
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def grid_points(step: float = FINE_STEP, domain: str | None = None):
    d = DOMAINS[domain or DEFAULT_DOMAIN]
    lats = []
    y = d["south"]
    while y <= d["north"] + 1e-9:
        lats.append(round(y, 2))
        y += step
    lons = []
    x = d["west"]
    while x <= d["east"] + 1e-9:
        lons.append(round(x, 2))
        x += step
    return lats, lons


def fetch(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Referer": "https://open-meteo.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def probe_run_state(run: str) -> str:
    """起报场状态：missing（还没出）、partial（只更新到中段）、full（到 +240h）。"""
    params = {
        "latitude": "22",
        "longitude": "114",
        "hourly": "geopotential_height_500hPa",
        "models": "ecmwf_ifs025",
        "forecast_days": "11",
        "run": run,
    }
    url = SINGLE_RUN_URL + "?" + urllib.parse.urlencode(params)
    try:
        raw = fetch(url, timeout=90)
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404):
            return "missing"
        raise
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, list):
        data = data[0] if data else {}
    values = ((data.get("hourly") or {}).get("geopotential_height_500hPa") or [])
    # 小时序列从起报时刻开始，索引 240 即 +240h。
    if len(values) > 240 and values[240] is not None:
        return "full"
    return "partial"


def probe_run(run: str) -> bool:
    return probe_run_state(run) != "missing"


def latest_run() -> str:
    """选最新且已经更新到 +240h 的起报场。

    ECMWF 新场次刚出时往往只有前面一段数据，若直接使用会生成大量空白尾帧，
    所以这里跳过还没更新完整的场次，找不到完整场次时再退回最新的可用场次。
    """
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    block = now.replace(hour=(now.hour // 6) * 6)
    fallback = ""
    for offset in range(0, 36, 6):
        candidate = block - timedelta(hours=offset)
        run = candidate.strftime("%Y-%m-%dT%H:00")
        log("检查起报场 %s" % run)
        state = probe_run_state(run)
        if state == "full":
            log("使用起报场 %s" % run)
            return run
        if state == "partial":
            log("起报场 %s 尚未更新到 +240h，跳过" % run)
            if not fallback:
                fallback = run
    if fallback:
        log("没有完整场次，回退到最新可用起报场 %s（尾部时次可能偏短）" % fallback)
        return fallback
    raise RuntimeError("没有找到可用的 ECMWF IFS 起报场")


CHUNK_POINTS = 200
CHUNK_CACHE = BASE_DIR / "_cache" / "chunks"
RETRY_DELAYS = (5, 10, 20, 30, 45, 60)


def _chunk_cache_path(run: str, domain_name: str, group_no: int,
                      variables: list[str], part: int) -> Path:
    import hashlib

    safe_run = run.replace(":", "").replace("-", "")
    tag = hashlib.md5(",".join(variables).encode("utf-8")).hexdigest()[:8]
    return CHUNK_CACHE / ("%s_%s_g%d_%s_p%d.json"
                          % (safe_run, domain_name, group_no, tag, part))


def _fetch_chunk(run: str, variables: list[str], points: list[tuple[float, float]],
                 domain_name: str, group_no: int, total_groups: int,
                 part: int, parts: int) -> list[dict]:
    cache_path = _chunk_cache_path(run, domain_name, group_no, variables, part)
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, list) and len(cached) == len(points):
                log("%s 变量组 %d 分块 %d 使用本地缓存" % (domain_name, group_no, part))
                return cached
        except (OSError, ValueError):
            pass

    params = {
        "latitude": ",".join("%g" % la for la, _ in points),
        "longitude": ",".join("%g" % lo for _, lo in points),
        "hourly": ",".join(variables),
        "models": "ecmwf_ifs025",
        "forecast_days": "11",
        "timezone": "UTC",
        "wind_speed_unit": "kn",
    }
    query = urllib.parse.urlencode(params, safe=",")
    urls = [
        SINGLE_RUN_URL + "?" + query + "&run=" + urllib.parse.quote(run),
        MAIN_RUN_URL + "?" + query,
        MAIN_RUN_URL + "?" + query,
    ]
    last_error = None
    for attempt, delay in enumerate((*RETRY_DELAYS, None)):
        started = time.time()
        try:
            log("请求 %s 变量组 %d/%d 分块 %d/%d：%d 个变量，%d 个点，第 %d 次"
                % (domain_name, group_no, total_groups, part, parts,
                   len(variables), len(points), attempt + 1))
            raw = fetch(urls[min(attempt, 2)], timeout=300)
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, list) or len(data) != len(points):
                raise RuntimeError("变量组 %d 分块 %d 返回网格数量异常" % (group_no, part))
            log("%s 变量组 %d 分块 %d 完成：%.1f KB，%.1fs"
                % (domain_name, group_no, part, len(raw) / 1024, time.time() - started))
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data), encoding="utf-8")
            except OSError:
                pass
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log("%s 变量组 %d 分块 %d 第 %d 次失败：%s"
                % (domain_name, group_no, part, attempt + 1, exc))
            if delay is None:
                break
            time.sleep(20 if "429" in str(exc) else delay)
    raise RuntimeError("%s 变量组 %d 分块 %d 下载失败：%s"
                       % (domain_name, group_no, part, last_error))


def fetch_group(run: str, variables: list[str], group_no: int,
                domain_name: str, total_groups: int) -> list[dict]:
    d = DOMAINS[domain_name]
    lats, lons = grid_points(d["fetch_step"], domain_name)
    points = [(la, lo) for la in lats for lo in lons]
    chunks = [points[i:i + CHUNK_POINTS] for i in range(0, len(points), CHUNK_POINTS)]
    merged: list[dict] = []
    for part, chunk in enumerate(chunks, 1):
        merged.extend(
            _fetch_chunk(run, variables, chunk, domain_name, group_no,
                         total_groups, part, len(chunks))
        )
    return merged


def fetch_grid(run: str, domain_name: str, groups: list[list[str]]) -> dict:
    log("请求 ECMWF IFS 网格：%s（%d 组）" % (domain_name, len(groups)))
    started = time.time()
    parts: dict[int, list[dict]] = {}
    # Open-Meteo 对并发很敏感；240h 数据量变大后用 2 路并发，避免 429。
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(fetch_group, run, variables, idx + 1, domain_name, len(groups)): idx
            for idx, variables in enumerate(groups)
        }
        for future in as_completed(futures):
            idx = futures[future]
            parts[idx] = future.result()

    base = parts[0]
    merged: list[dict] = []
    for i, point in enumerate(base):
        coords = {
            (round(part[i]["latitude"], 4), round(part[i]["longitude"], 4))
            for part in parts.values()
        }
        if len(coords) != 1:
            raise RuntimeError("变量组合并时坐标不一致")
        hourly = {}
        for part in parts.values():
            hourly.update(part[i]["hourly"])
        merged.append(
            {
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "hourly": hourly,
            }
        )
    log("%s 网格合并完成：%d 个点，%.1fs" % (domain_name, len(merged), time.time() - started))
    return {"run": run, "points": merged}


def prepare_grid(data: dict, domain: str | None = None):
    import numpy as np
    from scipy.interpolate import griddata

    d = DOMAINS[domain or DEFAULT_DOMAIN]
    points = data["points"]
    lat = np.asarray([p["latitude"] for p in points], dtype=float)
    lon = np.asarray([p["longitude"] for p in points], dtype=float)
    times = points[0]["hourly"]["time"]
    lats, lons = grid_points(d["fine_step"], domain or DEFAULT_DOMAIN)
    target_lon, target_lat = np.meshgrid(np.asarray(lons), np.asarray(lats))

    def interpolate(values):
        values = np.asarray(values, dtype=float)
        return griddata((lon, lat), values, (target_lon, target_lat), method="linear")

    return {
        "points": points,
        "lat": lat,
        "lon": lon,
        "times": times,
        "target_lon": target_lon,
        "target_lat": target_lat,
        "interpolate": interpolate,
    }


def safe_values(values, idx):
    out = values[idx]
    return float(out) if out is not None else 0.0


def accumulate(points, key: str, idx: int, hours: int):
    total = []
    for p in points:
        vals = p["hourly"][key][max(0, idx - hours + 1):idx + 1] or []
        total.append(sum(float(v) for v in vals if v is not None))
    return total


def maximum_over(points, key: str, idx: int, hours: int):
    values = []
    for p in points:
        vals = [float(v) for v in (p["hourly"][key][max(0, idx - hours + 1):idx + 1] or []) if v is not None]
        values.append(max(vals) if vals else 0.0)
    return values


def wind_uv(points, speed_key: str, direction_key: str, idx: int):
    import numpy as np

    speed = np.asarray([safe_values(p["hourly"][speed_key], idx) for p in points])
    direction = np.asarray([safe_values(p["hourly"][direction_key], idx) for p in points])
    u = -speed * np.sin(np.deg2rad(direction))
    v = -speed * np.cos(np.deg2rad(direction))
    return u, v


def base_map(ax, ccrs, cfeature, domain: str = DEFAULT_DOMAIN):
    import numpy as np

    d = DOMAINS[domain]
    ax.set_extent(
        [d["west"], d["east"], d["south"], d["north"]],
        crs=ccrs.PlateCarree(),
    )
    # 10m 地图包含更完整的海岸线、岛屿、湖泊和省界。
    ax.add_feature(cfeature.OCEAN.with_scale("10m"), facecolor="#f4f8fb", edgecolor="none", zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("10m"), facecolor="#f5f0e4", edgecolor="none", zorder=0)
    try:
        ax.add_feature(
            cfeature.LAKES.with_scale("10m"),
            facecolor="#f4f8fb", edgecolor="#7e8b93", linewidth=0.25, zorder=1,
        )
    except Exception:
        pass
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        linewidth=0.55, linestyle=":", edgecolor="#9d978b", zorder=4,
    )
    try:
        ax.add_feature(
            cfeature.STATES.with_scale("50m"),
            linewidth=0.32, edgecolor="#aaa49a", zorder=4,
        )
    except Exception:
        pass
    ax.coastlines("10m", linewidth=0.6, color="#4d5a52", zorder=5)

    # 广东省界单独加粗标黄（先画一层暗色底衬，保证浅色底图上仍然清楚）。
    try:
        from cartopy.feature import ShapelyFeature
        from cartopy.io import shapereader

        provinces = shapereader.natural_earth(
            resolution="50m", category="cultural",
            name="admin_1_states_provinces",
        )
        guangdong = []
        for record in shapereader.Reader(provinces).records():
            attrs = record.attributes
            labels = [
                str(attrs.get(key) or "")
                for key in ("name", "name_en", "name_local", "iso_3166_2")
            ]
            if any("guangdong" in label.lower() or label == "CN-GD" for label in labels):
                guangdong.append(record.geometry)
        if guangdong:
            ax.add_feature(
                ShapelyFeature(
                    guangdong, ccrs.PlateCarree(), facecolor="none",
                    edgecolor="#6b5a00", linewidth=4.0, alpha=0.35, zorder=9,
                )
            )
            ax.add_feature(
                ShapelyFeature(
                    guangdong, ccrs.PlateCarree(), facecolor="none",
                    edgecolor="#FFE000", linewidth=2.4, zorder=10,
                )
            )
    except Exception:
        pass

    step = 1 if domain == "sc" else (10 if (d["east"] - d["west"]) > 30 else 5)
    xlocs = np.arange(np.ceil(d["west"] / step) * step, d["east"] + 0.1, step)
    ylocs = np.arange(np.ceil(d["south"] / step) * step, d["north"] + 0.1, step)
    gl = ax.gridlines(
        draw_labels=True, xlocs=xlocs, ylocs=ylocs,
        linewidth=0.35, color="#9aa4ad", linestyle="--", alpha=0.5, zorder=2,
    )
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 8}
    gl.ylabel_style = {"size": 8}
    cities = {
        "Guangzhou": (113.26, 23.13),
        "Hong Kong": (114.17, 22.32),
        "Macau": (113.54, 22.20),
        "Haikou": (110.20, 20.04),
    }
    if domain == "ea":
        cities.update({
            "Beijing": (116.40, 39.90),
            "Shanghai": (121.47, 31.23),
            "Seoul": (126.98, 37.57),
            "Tokyo": (139.69, 35.68),
            "Taipei": (121.56, 25.03),
            "Manila": (120.98, 14.60),
            "Hanoi": (105.85, 21.03),
        })
    for name, (x, y) in cities.items():
        ax.plot(x, y, "o", ms=3, color="#222", transform=ccrs.PlateCarree(), zorder=11)
        ax.text(
            x + 0.06, y + 0.06, name,
            fontsize=6.5, color="#222", transform=ccrs.PlateCarree(), zorder=11,
        )
    return ax


def finish_figure(fig, ax, cf, colorbar_ticks, colorbar_labels, colorbar_title,
                  title: str, valid: datetime, run_dt: datetime, lead: int, out_path: Path):
    fig.text(
        0.065, 0.955, title,
        fontsize=16.5, fontweight="bold", ha="left", va="top",
    )
    fig.text(
        0.955, 0.955, valid.strftime("%Y/%m/%d %H(UTC)"),
        fontsize=11, ha="right", va="top",
    )
    fig.text(
        0.065, 0.923,
        "ECMWF IFS 0.25°",
        fontsize=9.5, color="#555", ha="left", va="top",
    )
    fig.text(
        0.065, 0.032,
        "Init: %s  ·  Lead +%d h" % (run_dt.strftime("%Y-%m-%d %H UTC"), lead),
        fontsize=8, color="#666", ha="left", va="bottom",
    )
    fig.text(
        0.955, 0.032, "www.bamc.top",
        fontsize=11, color="#000000", ha="right", va="bottom",
    )
    cax = fig.add_axes([0.885, 0.16, 0.022, 0.62])
    cb = fig.colorbar(cf, cax=cax, ticks=colorbar_ticks)
    cb.ax.tick_params(labelsize=7.5, length=2)
    cb.set_ticklabels(colorbar_labels)
    cb.set_label(colorbar_title, fontsize=8, labelpad=6)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160, facecolor="white")
    log("已生成 %s（+%dh，%s）" % (out_path.name, lead, valid.strftime("%Y/%m/%d %H UTC")))


def render_product(data: dict, run_dt: datetime, lead: int, spec: dict, out_path: Path) -> None:
    import cartopy
    cartopy.config["data_dir"] = str(BASE_DIR / ".cartopy")

    import matplotlib
    matplotlib.use("Agg")
    import numpy as np
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    valid = run_dt + timedelta(hours=lead)
    valid_key = valid.strftime("%Y-%m-%dT%H:%M")
    domain = spec.get("domain", DEFAULT_DOMAIN)
    barb_step = 3 if domain == "ea" else 2  # 东亚 1.5°，华南 0.5°（0.25° 网格每 2 格一个）
    barb_slice = (slice(None, None, barb_step), slice(None, None, barb_step))
    grid = prepare_grid(data, domain)
    if valid_key not in grid["times"]:
        raise RuntimeError("网格中缺少有效时间 %s" % valid_key)
    idx = grid["times"].index(valid_key)
    points = grid["points"]
    LON, LAT = grid["target_lon"], grid["target_lat"]
    kind = spec["kind"]

    fig = Figure(figsize=(10, 7.2), dpi=140, facecolor="white")
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0.065, 0.075, 0.80, 0.80], projection=ccrs.PlateCarree())
    base_map(ax, ccrs, cfeature, domain)

    if kind == "combined":
        rain = grid["interpolate"](accumulate(points, "precipitation", idx, 6))
        height = grid["interpolate"]([safe_values(p["hourly"]["geopotential_height_500hPa"], idx) for p in points])
        u, v = wind_uv(points, "wind_speed_850hPa", "wind_direction_850hPa", idx)
        u = grid["interpolate"](u)
        v = grid["interpolate"](v)
        cf = ax.contourf(
            LON, LAT, rain, levels=RAIN_6H_LEVELS, colors=RAIN_6H_COLORS,
            extend="max", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, height,
            levels=[lv for lv in np.arange(5640, 5941, 20) if lv != 5880],
            colors="#1b1b1b",
            linewidths=1.15, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=7, fmt=lambda x: f"{x / 10:.0f}", colors="#1b1b1b")

        # 588 位势高度线单独标红，标签放在红线之上；没有 588 线时自动跳过。
        if np.nanmin(height) <= 5880 <= np.nanmax(height):
            cs588 = ax.contour(
                LON, LAT, height, levels=[5880], colors="#d62728",
                linewidths=2.4, transform=ccrs.PlateCarree(), zorder=8,
            )
            ax.clabel(cs588, inline=False, fontsize=8.5, fmt=lambda x: "588", colors="#d62728")

        # 850hPa 风速 >= 24.5 m/s（约 47.62 kn）的风矢标红，其余保持蓝色。
        speed_kn = np.hypot(u, v)
        high_wind = speed_kn >= 47.62
        barb_style = dict(
            transform=ccrs.PlateCarree(), length=5.8, linewidth=0.38,
            barb_increments={"half": 5, "full": 10, "flag": 50}, zorder=7,
        )
        u_barb = u[barb_slice]
        v_barb = v[barb_slice]
        high_barb = high_wind[barb_slice]
        lon_barb = LON[barb_slice]
        lat_barb = LAT[barb_slice]
        ax.barbs(lon_barb, lat_barb,
                 np.ma.masked_where(high_barb, u_barb),
                 np.ma.masked_where(high_barb, v_barb),
                 color="#2847c7", **barb_style)
        ax.barbs(lon_barb, lat_barb,
                 np.ma.masked_where(~high_barb, u_barb),
                 np.ma.masked_where(~high_barb, v_barb),
                 color="#e31a1c", **barb_style)
        finish_figure(
            fig, ax, cf, RAIN_6H_LEVELS,
            ["0.1", "1", "4", "13", "25", "60", "120", "250"],
            "6h rainfall (mm)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "t2m":
        temp = grid["interpolate"]([safe_values(p["hourly"]["temperature_2m"], idx) for p in points])
        cf = ax.contourf(
            LON, LAT, temp, levels=TEMP_LEVELS, colors=TEMP_COLORS,
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, temp, levels=np.arange(0, 36, 2), colors="#7a5b34",
            linewidths=0.55, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%d", colors="#684c2b")
        finish_figure(
            fig, ax, cf, TEMP_LEVELS,
            [str(x) for x in TEMP_LEVELS], "2m temperature (°C)",
            spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "h500":
        height = grid["interpolate"]([safe_values(p["hourly"]["geopotential_height_500hPa"], idx) for p in points])
        u, v = wind_uv(points, "wind_speed_500hPa", "wind_direction_500hPa", idx)
        u = grid["interpolate"](u)
        v = grid["interpolate"](v)
        cf = ax.contourf(
            LON, LAT, height, levels=HEIGHT_FILL_LEVELS, colors=HEIGHT_FILL_COLORS,
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, height, levels=np.arange(5700, 6001, 20), colors="#1b1b1b",
            linewidths=1.0, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=7, fmt=lambda x: f"{x / 10:.0f}", colors="#1b1b1b")
        ax.barbs(
            LON[barb_slice], LAT[barb_slice], u[barb_slice], v[barb_slice],
            transform=ccrs.PlateCarree(), color="#14a3b8",
            length=5.8, linewidth=0.38,
            barb_increments={"half": 5, "full": 10, "flag": 50}, zorder=7,
        )
        finish_figure(
            fig, ax, cf, [5800, 5840, 5880, 5920, 5960],
            ["580", "584", "588", "592", "596"],
            "500hPa height (dam)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "rain24":
        rain = grid["interpolate"](accumulate(points, "precipitation", idx, 24))
        cf = ax.contourf(
            LON, LAT, rain, levels=RAIN_24H_LEVELS, colors=RAIN_24H_COLORS,
            extend="max", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, rain, levels=[1, 10, 25, 50, 100], colors="#385a3b",
            linewidths=0.55, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%g", colors="#244426")
        finish_figure(
            fig, ax, cf, RAIN_24H_LEVELS,
            ["0.1", "1", "10", "25", "50", "100", "250"],
            "24h rainfall (mm)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "mslp":
        pressure = grid["interpolate"]([safe_values(p["hourly"]["pressure_msl"], idx) for p in points])
        cf = ax.contourf(
            LON, LAT, pressure, levels=MSLP_LEVELS, cmap="RdYlBu",
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, pressure, levels=MSLP_LEVELS, colors="#2a2a2a",
            linewidths=0.7, transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%g", colors="#222222")
        finish_figure(
            fig, ax, cf, [990, 995, 1000, 1005, 1010, 1015, 1020, 1025, 1030],
            ["990", "995", "1000", "1005", "1010", "1015", "1020", "1025", "1030"],
            "MSLP (hPa)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind in ("wind10", "wind925"):
        if kind == "wind10":
            speed_key, dir_key = "wind_speed_10m", "wind_direction_10m"
            levels, labels, unit = WIND_SPEED_LEVELS, WIND_SPEED_LABELS, "10m wind (m/s)"
        else:
            speed_key, dir_key = "wind_speed_925hPa", "wind_direction_925hPa"
            levels, labels, unit = WIND925_LEVELS, [str(x) for x in WIND925_LEVELS], "925hPa wind (m/s)"
        speed_kn = np.asarray([safe_values(p["hourly"][speed_key], idx) for p in points])
        speed_ms = grid["interpolate"](speed_kn * 0.514444)
        u, v = wind_uv(points, speed_key, dir_key, idx)
        u = grid["interpolate"](u)
        v = grid["interpolate"](v)
        if kind == "wind10":
            cf = ax.contourf(
                LON, LAT, speed_ms, levels=levels, colors=WIND_SPEED_COLORS,
                extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
            )
            cf.cmap.set_over("#ff1900")
            cf.cmap.set_under("#ffffff")
        else:
            cf = ax.contourf(
                LON, LAT, speed_ms, levels=levels, cmap="YlGnBu",
                extend="max", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
            )
        ax.barbs(
            LON[barb_slice], LAT[barb_slice], u[barb_slice], v[barb_slice],
            transform=ccrs.PlateCarree(), color="#08306b",
            length=5.8, linewidth=0.38,
            barb_increments={"half": 5, "full": 10, "flag": 50}, zorder=7,
        )
        finish_figure(
            fig, ax, cf, levels, labels, unit,
            spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "gust24":
        gust_kn = np.asarray(maximum_over(points, "wind_gusts_10m", idx, 24))
        gust = grid["interpolate"](gust_kn * 0.514444)
        cf = ax.contourf(
            LON, LAT, gust, levels=WIND_SPEED_LEVELS, colors=WIND_SPEED_COLORS,
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cf.cmap.set_over("#ff1900")
        cf.cmap.set_under("#ffffff")
        finish_figure(
            fig, ax, cf, WIND_SPEED_LEVELS, WIND_SPEED_LABELS,
            "24h gust (m/s)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "cape":
        cape = grid["interpolate"]([safe_values(p["hourly"]["cape"], idx) for p in points])
        cf = ax.contourf(
            LON, LAT, cape, levels=CAPE_LEVELS, cmap="YlOrRd",
            extend="max", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, cape, levels=[250, 500, 1000, 2000, 3000, 4000],
            colors="#5a2b16", linewidths=0.45,
            transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=5.5, fmt="%d", colors="#4a220f")
        finish_figure(
            fig, ax, cf, CAPE_LEVELS, [str(x) for x in CAPE_LEVELS],
            "CAPE (J/kg)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "kindex":
        t850 = np.asarray([safe_values(p["hourly"]["temperature_850hPa"], idx) for p in points])
        td850 = np.asarray([safe_values(p["hourly"]["dew_point_850hPa"], idx) for p in points])
        t700 = np.asarray([safe_values(p["hourly"]["temperature_700hPa"], idx) for p in points])
        td700 = np.asarray([safe_values(p["hourly"]["dew_point_700hPa"], idx) for p in points])
        t500 = np.asarray([safe_values(p["hourly"]["temperature_500hPa"], idx) for p in points])
        k_index = (t850 - t500) + td850 - (t700 - td700)
        k_index = grid["interpolate"](k_index)
        cf = ax.contourf(
            LON, LAT, k_index, levels=K_LEVELS, cmap="Spectral_r",
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, k_index, levels=[20, 25, 30, 35, 40],
            colors="#3b2a26", linewidths=0.5,
            transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%d", colors="#2c1f1c")
        finish_figure(
            fig, ax, cf, K_LEVELS, [str(x) for x in K_LEVELS],
            "K index (°C)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "pwat":
        pwat = grid["interpolate"](
            [safe_values(p["hourly"]["total_column_integrated_water_vapour"], idx) for p in points]
        )
        cf = ax.contourf(
            LON, LAT, pwat, levels=PWAT_LEVELS, cmap="YlGnBu",
            extend="max", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, pwat, levels=[20, 30, 40, 50, 60],
            colors="#174f5c", linewidths=0.5,
            transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%d", colors="#123f49")
        finish_figure(
            fig, ax, cf, PWAT_LEVELS, [str(x) for x in PWAT_LEVELS],
            "PWAT (mm)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind in ("rh2m", "rh500"):
        key = "relative_humidity_2m" if kind == "rh2m" else "relative_humidity_500hPa"
        rh = grid["interpolate"]([safe_values(p["hourly"][key], idx) for p in points])
        cf = ax.contourf(
            LON, LAT, rh, levels=RH_LEVELS, cmap="YlGnBu",
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cs = ax.contour(
            LON, LAT, rh, levels=[50, 70, 80, 90, 95],
            colors="#234b55", linewidths=0.45,
            transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt="%d", colors="#173942")
        finish_figure(
            fig, ax, cf, RH_LEVELS, [str(x) for x in RH_LEVELS],
            "relative humidity (%)", spec["title"], valid, run_dt, lead, out_path,
        )

    elif kind == "cloud":
        cloud = grid["interpolate"](
            [safe_values(p["hourly"]["cloud_cover"], idx) for p in points]
        )
        cf = ax.contourf(
            LON, LAT, cloud, levels=CLOUD_LEVELS, colors=CLOUD_COLORS,
            extend="both", transform=ccrs.PlateCarree(), zorder=2, antialiased=True,
        )
        cf.cmap.set_under("#ffffff")
        cf.cmap.set_over(CLOUD_OVER)
        cs = ax.contour(
            LON, LAT, cloud, levels=[40, 50, 60, 70, 80, 90],
            colors="#2f5bd0", linewidths=0.55,
            transform=ccrs.PlateCarree(), zorder=6,
        )
        ax.clabel(cs, inline=True, fontsize=6, fmt=lambda x: f"{x / 10:.0f}", colors="#1b3fa8")
        finish_figure(
            fig, ax, cf, CLOUD_LEVELS, CLOUD_LABELS,
            "total cloud cover (tenths)", spec["title"], valid, run_dt, lead, out_path,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="生成华南 ECMWF IFS 预报图")
    ap.add_argument("--run", default="", help="起报场，例如 2026-10-20T00:00")
    ap.add_argument("--input", default="", help="已有网格 JSON（调试/避免重复下载）")
    ap.add_argument("--out", default=str(OUT_DIR), help="输出目录")
    ap.add_argument(
        "--products",
        default="combined,combined_ea,t2m,h500,h500_ea,rain24,mslp,wind10,wind925,gust24,cape,kindex,pwat,rh2m,rh500,cloud",
        help="要生成的产品，逗号分隔",
    )
    args = ap.parse_args()

    run = args.run or latest_run()
    run_dt = datetime.strptime(run, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    out_dir = Path(args.out)
    selected = [x.strip() for x in args.products.split(",") if x.strip()]
    unknown = [x for x in selected if x not in PRODUCTS]
    if unknown:
        raise SystemExit("未知产品：%s" % ", ".join(unknown))

    required_domains = {PRODUCTS[p].get("domain", DEFAULT_DOMAIN) for p in selected}
    groups_by_domain = {"sc": VAR_GROUPS, "ea": EA_VAR_GROUPS}
    data_by_domain: dict[str, dict] = {}

    if args.input:
        loaded = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and "sc" in loaded and "ea" in loaded:
            data_by_domain = loaded
            log("使用已有双区域网格：%s" % args.input)
        else:
            if isinstance(loaded, list):
                loaded = {"run": run, "points": loaded}
            if required_domains != {"sc"}:
                raise SystemExit("该输入只包含单区域数据，请提供包含 sc/ea 的 JSON")
            data_by_domain["sc"] = loaded
            log("使用已有网格：%s（%d 点）" % (args.input, len(loaded["points"])))
    else:
        for domain_name in sorted(required_domains):
            data_by_domain[domain_name] = fetch_grid(
                run, domain_name, groups_by_domain[domain_name]
            )

    generated = datetime.now(TZ_CN).strftime("%Y-%m-%d %H:%M HKT")
    for product_id in selected:
        spec = PRODUCTS[product_id]
        domain_name = spec.get("domain", DEFAULT_DOMAIN)
        data = data_by_domain[domain_name]
        subdir = out_dir / spec["subdir"]
        frames = []
        for lead in LEADS:
            valid = run_dt + timedelta(hours=lead)
            stamp = valid.strftime("%Y%m%d%H")
            name = spec["prefix"] + stamp + ".png"
            render_product(data, run_dt, lead, spec, subdir / name)
            frames.append(
                {
                    "s": stamp,
                    "valid_utc": valid.strftime("%Y-%m-%d %H:%M UTC"),
                    "lead": lead,
                    "file": name,
                }
            )
        manifest = {
            "product": product_id,
            "run": run_dt.strftime("%Y-%m-%d %H:%M UTC"),
            "run_iso": run_dt.isoformat(),
            "generated": generated,
            "source": "ECMWF IFS 0.25° via Open-Meteo",
            "region": {
                "west": DOMAINS[domain_name]["west"],
                "south": DOMAINS[domain_name]["south"],
                "east": DOMAINS[domain_name]["east"],
                "north": DOMAINS[domain_name]["north"],
            },
            "frames": frames,
        }
        (subdir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log("已更新 %s" % (subdir / "manifest.json"))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
