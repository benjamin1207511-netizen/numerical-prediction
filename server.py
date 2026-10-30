#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECMWF 华南预报图 + 多模式系集热带气旋 —— 后端（基础仅标准库，AIFS 需要 eccodes）

站点内容：
  /            16 类 ECMWF 预报图（ecmwf/ 下预生成 PNG）
  /tc/         ECMWF ENS 51 成员热带气旋路径与强度（public/tc-data/ 下 JSON）

服务端图表只读取本地 manifest、PNG；台风页通过 /api/jtwc、/api/tcmodel
读取 GDACS 的实时 JTWC 系统，以及 ECMWF / Google / NOAA 的官方系集轨迹，
并统一裁剪到本地关注范围。图像更新由 ecmwf_chart.py 完成，IFS 台风数据更新由
tools/build_tc_data.py 完成。
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from anti_bot import RequestGuard, SECURITY_HEADERS
from tc_direct import (
    fetch_dates as fetch_tcmodel_dates,
    fetch_model as tc_direct_fetch_model,
)

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
ECMWF_DIR = BASE_DIR / "ecmwf"
TZ_CN = timezone(timedelta(hours=8))
ECMWF_PAGE = "https://open-meteo.com/en/docs/ecmwf-api"
CACHE_TTL = 30
STAMP_RE = re.compile(r"^\d{10}$")
GUARD = RequestGuard()

# JTWC's public product page is not always reachable from mainland networks.
# GDACS republishes JTWC's active TC alerts and provides a small, stable JSON
# endpoint, so it is used as the live relay for "which systems is JTWC tracking".
JTWC_DOMAIN = {"west": 100.0, "south": 10.0, "east": 140.0, "north": 35.0}
JTWC_API = (
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    "?eventlist=TC&fromDate={start}&toDate={end}"
)
JTWC_TTL = 300
_jtwc_lock = threading.Lock()
_jtwc_cache: dict = {"at": 0.0, "payload": None, "error": None}

SOURCES = [
    {
        "id": "ecmwf",
        "name": "ECMWF IFS",
        "en": "Local forecast charts",
        "url": ECMWF_PAGE,
        "accent": "#a78bfa",
    },
]

PRODUCTS = [
    {
        "id": "ecmwf-southchina",
        "source": "ecmwf",
        "name": "雨+高度+风",
        "title": "ECMWF IFS · 华南综合预报图",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "6h 雨 + 500hPa 高度 + 850hPa 风",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "combined",
    },
    {
        "id": "ecmwf-southchina-ea",
        "source": "ecmwf",
        "name": "雨+高度+风（东亚）",
        "title": "ECMWF IFS · 东亚综合预报图",
        "kind": "chart",
        "interval": 360,
        "coverage": "0–50°N · 80–140°E",
        "level": "6h 雨 + 500hPa 高度 + 850hPa 风",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "combined-ea",
    },
    {
        "id": "ecmwf-t2m",
        "source": "ecmwf",
        "name": "2m 气温",
        "title": "ECMWF IFS · 华南 2m 气温",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "2m 气温",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "t2m",
    },
    {
        "id": "ecmwf-h500",
        "source": "ecmwf",
        "name": "500hPa 风场",
        "title": "ECMWF IFS · 华南 500hPa 高度与风场",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "500hPa 高度 + 风",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "h500",
    },
    {
        "id": "ecmwf-h500-ea",
        "source": "ecmwf",
        "name": "500hPa 风场（东亚）",
        "title": "ECMWF IFS · 东亚 500hPa 高度与风场",
        "kind": "chart",
        "interval": 360,
        "coverage": "0–50°N · 80–140°E",
        "level": "500hPa 高度 + 风",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "h500-ea",
    },
    {
        "id": "ecmwf-rain24",
        "source": "ecmwf",
        "name": "24h 降水",
        "title": "ECMWF IFS · 华南 24 小时降水",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "24h 累计降水",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "rain24",
    },
    {
        "id": "ecmwf-mslp",
        "source": "ecmwf",
        "name": "海平面气压",
        "title": "ECMWF IFS · 华南海平面气压",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "海平面气压",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "mslp",
    },
    {
        "id": "ecmwf-wind10",
        "source": "ecmwf",
        "name": "地面风场",
        "title": "ECMWF IFS · 华南地面风场",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "10m 风速 + 风向",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "wind10",
    },
    {
        "id": "ecmwf-wind925",
        "source": "ecmwf",
        "name": "925hPa 风场",
        "title": "ECMWF IFS · 华南 925hPa 风场",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "925hPa 风速 + 风向",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "wind925",
    },
    {
        "id": "ecmwf-gust24",
        "source": "ecmwf",
        "name": "24h 阵风",
        "title": "ECMWF IFS · 华南 24 小时极大阵风",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "24h 极大阵风",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "gust24",
    },
    {
        "id": "ecmwf-cape",
        "source": "ecmwf",
        "name": "CAPE",
        "title": "ECMWF IFS · 华南 CAPE",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "对流有效位能",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "cape",
    },
    {
        "id": "ecmwf-kindex",
        "source": "ecmwf",
        "name": "K 指数",
        "title": "ECMWF IFS · 华南 K 指数",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "K-index",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "kindex",
    },
    {
        "id": "ecmwf-pwat",
        "source": "ecmwf",
        "name": "PWAT",
        "title": "ECMWF IFS · 华南 PWAT",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "可降水量",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "pwat",
    },
    {
        "id": "ecmwf-rh2m",
        "source": "ecmwf",
        "name": "2m 湿度",
        "title": "ECMWF IFS · 华南 2m 相对湿度",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "2m 相对湿度",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "rh2m",
    },
    {
        "id": "ecmwf-rh500",
        "source": "ecmwf",
        "name": "500hPa 湿度",
        "title": "ECMWF IFS · 华南 500hPa 相对湿度",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "500hPa 相对湿度",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "rh500",
    },
    {
        "id": "ecmwf-cloud",
        "source": "ecmwf",
        "name": "总云量",
        "title": "ECMWF IFS · 华南 总云量",
        "kind": "chart",
        "interval": 360,
        "coverage": "16–28°N · 105–121°E",
        "level": "总云量（成）",
        "page": ECMWF_PAGE,
        "defaultWindow": 1440,
        "forecast": True,
        "subdir": "cloud",
    },
]
PRODUCT_MAP = {p["id"]: p for p in PRODUCTS}
DEFAULT_PRODUCT = "ecmwf-southchina"

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def _jtwc_display_name(raw: str) -> str:
    name = str(raw or "").strip().upper()
    name = re.sub(r"-\d{2}$", "", name)
    return name or "UNNAMED"


def fetch_jtwc(force: bool = False) -> dict:
    """Return active JTWC-sourced systems whose current centre is in our box.

    GDACS is used as the relay because metoc.navy.mil is not reachable from all
    networks.  Only systems explicitly credited to JTWC are returned, and the
    current centre must be inside 100–140°E / 10–35°N.
    """
    now = time.time()
    with _jtwc_lock:
        cached = _jtwc_cache.get("payload")
        if not force and cached is not None and now - float(_jtwc_cache.get("at") or 0) < JTWC_TTL:
            return cached

    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=45)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    url = JTWC_API.format(start=start, end=end)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BAMC-EC-TC/1.0 (+https://www.bamc.top)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            body = json.loads(response.read().decode("utf-8"))
        systems = []
        latest_update = ""
        for feature in body.get("features") or []:
            props = feature.get("properties") or {}
            if str(props.get("source") or "").upper() != "JTWC":
                continue
            if str(props.get("iscurrent") or "").lower() not in ("true", "1"):
                continue
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            if not (
                JTWC_DOMAIN["west"] <= lon <= JTWC_DOMAIN["east"]
                and JTWC_DOMAIN["south"] <= lat <= JTWC_DOMAIN["north"]
            ):
                continue
            severity = props.get("severitydata") or {}
            speed_kmh = severity.get("severity")
            wind_kt = round(float(speed_kmh) * 0.539957) if speed_kmh is not None else None
            name = _jtwc_display_name(props.get("eventname"))
            update = str(props.get("datemodified") or props.get("todate") or "")
            if update > latest_update:
                latest_update = update
            systems.append(
                {
                    "id": str(props.get("eventid") or name),
                    "episode": props.get("episodeid"),
                    "name": name,
                    "eventname": props.get("eventname") or name,
                    "lat": round(lat, 1),
                    "lon": round(lon, 1),
                    "wind_kt": wind_kt,
                    "alert": props.get("alertlevel") or "Green",
                    "updated": update,
                    "from": props.get("fromdate"),
                    "to": props.get("todate"),
                    "source": "JTWC",
                    "details": (props.get("url") or {}).get("details"),
                }
            )
        systems.sort(key=lambda item: item["wind_kt"] or 0, reverse=True)
        payload = {
            "ok": True,
            "source": "GDACS / JTWC",
            "sourceNote": "JTWC 活跃系统由 GDACS 实时转发；只保留当前中心位于 100–140°E、10–35°N 的系统。",
            "fetched": int(now),
            "updated": latest_update,
            "count": len(systems),
            "ttl": JTWC_TTL,
            "domain": JTWC_DOMAIN,
            "systems": systems,
        }
        with _jtwc_lock:
            _jtwc_cache["at"] = now
            _jtwc_cache["payload"] = payload
            _jtwc_cache["error"] = None
        return payload
    except Exception as exc:  # noqa: BLE001
        with _jtwc_lock:
            _jtwc_cache["error"] = str(exc)
            cached = _jtwc_cache.get("payload")
        if cached is not None:
            stale = dict(cached)
            stale["stale"] = True
            stale["error"] = "JTWC 源暂时不可达，显示上次成功结果"
            return stale
        raise


def public_product(product: dict) -> dict:
    keys = (
        "id", "source", "name", "title", "kind", "interval",
        "coverage", "level", "page", "defaultWindow", "forecast",
    )
    return {k: product[k] for k in keys if k in product}


def public_frame(frame: dict) -> dict:
    return {k: frame[k] for k in ("s", "ts", "d", "t", "full")}


def make_frame(valid_utc: datetime) -> dict:
    dt = valid_utc.astimezone(TZ_CN)
    return {
        "s": valid_utc.strftime("%Y%m%d%H"),
        "ts": int(dt.timestamp()),
        "d": dt.strftime("%m/%d"),
        "t": dt.strftime("%H:%M"),
        "full": dt.strftime("%Y-%m-%d %H:%M"),
    }


_cache_lock = threading.Lock()
_frames_cache: dict[str, dict] = {}


def load_frames(pid: str) -> dict:
    product = PRODUCT_MAP[pid]
    subdir = str(product.get("subdir") or "")
    manifest_path = ECMWF_DIR / subdir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("ECMWF 图尚未生成，请先运行 ecmwf_chart.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    frames = []
    for item in manifest.get("frames") or []:
        name = str(item.get("file") or "")
        relative = (Path(subdir) / name).as_posix() if subdir else name
        target = (ECMWF_DIR / relative).resolve()
        try:
            target.relative_to(ECMWF_DIR.resolve())
        except ValueError:
            continue
        if not target.is_file():
            continue
        try:
            valid = datetime.strptime(
                str(item["valid_utc"]).replace(" UTC", "").strip(),
                "%Y-%m-%d %H:%M",
            ).replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        frame = make_frame(valid)
        frame["s"] = str(item.get("s") or frame["s"])
        frame["file"] = relative
        frame["lead"] = item.get("lead")
        frames.append(frame)

    if not frames:
        raise RuntimeError("ECMWF 图清单为空，请运行 ecmwf_chart.py")
    frames.sort(key=lambda f: f["ts"])
    return {
        "frames": frames,
        "fetched": int(time.time()),
        "run": manifest.get("run"),
        "generated": manifest.get("generated"),
        "source": ECMWF_PAGE,
    }


def get_frames(pid: str, force: bool = False) -> dict:
    now = time.time()
    with _cache_lock:
        hit = _frames_cache.get(pid)
        if hit and not force and now - hit["fetched"] < CACHE_TTL:
            return hit
        try:
            data = load_frames(pid)
        except Exception:
            if hit:
                stale = dict(hit)
                stale["stale"] = True
                return stale
            raise
        _frames_cache[pid] = data
        return data


def resolve_frame(pid: str, stamp: str) -> dict | None:
    data = get_frames(pid)
    for frame in data["frames"]:
        if frame["s"] == stamp:
            return frame
    return None


def fetch_tcmodel(model: str, date: str | None = None) -> dict:
    """Read a direct official/primary source through the tc_direct adapters."""
    systems = []
    try:
        systems = fetch_jtwc().get("systems") or []
    except Exception:
        pass
    return tc_direct_fetch_model(model, date, systems)


class Handler(BaseHTTPRequestHandler):
    server_version = "ECMWFSouthChina/1.0"
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        if getattr(self, "_set_cookie", ""):
            self.send_header("Set-Cookie", self._set_cookie)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, obj, status: int = 200, cache: str = "no-store") -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": cache})

    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[0]).startswith(("GET /api/img", "HEAD /api/img")):
            return
        log("%s %s" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        self._set_cookie = ""
        try:
            ip = GUARD.client_ip(self.headers, self.client_address[0])
            decision = GUARD.check(ip, path, self.headers, parsed.query)
            if not decision.allowed:
                headers = {}
                if decision.retry_after:
                    headers["Retry-After"] = str(decision.retry_after)
                return self._send(
                    decision.status,
                    decision.reason.encode("utf-8"),
                    "text/plain; charset=utf-8",
                    headers,
                )
            if decision.set_cookie:
                secure = str(self.headers.get("X-Forwarded-Proto") or "").lower() == "https"
                self._set_cookie = GUARD.issue_cookie(secure=secure)

            if path == "/api/meta":
                return self.api_meta()
            if path == "/api/jtwc":
                return self.api_jtwc(qs)
            if path == "/api/tcmodel/dates":
                return self.api_tcmodel_dates(qs)
            if path == "/api/tcmodel":
                return self.api_tcmodel(qs)
            if path == "/api/frames":
                return self.api_frames(qs)
            if path == "/api/img":
                return self.api_img(qs)
            if path == "/api/health":
                with _cache_lock:
                    cached = sorted(_frames_cache)
                return self._json({"ok": True, "products": cached})
            if path == "/healthz":
                return self._send(200, b"ok", "text/plain; charset=utf-8", {"Cache-Control": "no-store"})
            return self.serve_static(path)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001
            log("处理 %s 出错：%r" % (self.path, exc))
            try:
                self._json({"error": str(exc)}, 500)
            except Exception:
                pass

    do_HEAD = do_GET

    def api_meta(self) -> None:
        now = datetime.now(TZ_CN)
        self._json(
            {
                "products": [public_product(p) for p in PRODUCTS],
                "sources": SOURCES,
                "default": DEFAULT_PRODUCT,
                "now": now.strftime("%Y-%m-%d %H:%M:%S"),
                "timezone": "Asia/Shanghai",
                "notice": "ECMWF IFS 数据经 Open-Meteo 获取，图表由本地脚本生成。",
            }
        )

    def api_jtwc(self, qs: dict) -> None:
        force = (qs.get("force") or ["0"])[0] in ("1", "true")
        try:
            payload = fetch_jtwc(force=force)
        except Exception as exc:  # noqa: BLE001
            return self._json(
                {
                    "ok": False,
                    "error": "无法读取 JTWC 活跃系统：%s" % exc,
                    "domain": JTWC_DOMAIN,
                },
                502,
            )
        self._json(payload)

    def api_tcmodel_dates(self, qs: dict) -> None:
        model = (qs.get("model") or [""])[0]
        try:
            payload = fetch_tcmodel_dates(model)
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": "无法读取 %s 起报时次：%s" % (model, exc)}, 502)
        self._json(payload)

    def api_tcmodel(self, qs: dict) -> None:
        model = (qs.get("model") or [""])[0]
        date = (qs.get("date") or [None])[0] or None
        try:
            payload = fetch_tcmodel(model, date)
        except ValueError as exc:
            return self._json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            return self._json({"ok": False, "error": "无法读取 %s 数据：%s" % (model, exc)}, 502)
        self._json(payload)

    def api_frames(self, qs: dict) -> None:
        pid = (qs.get("p") or [DEFAULT_PRODUCT])[0]
        if pid not in PRODUCT_MAP:
            return self._json({"error": "未知产品 %s" % pid}, 400)
        force = (qs.get("force") or ["0"])[0] in ("1", "true")
        try:
            data = get_frames(pid, force=force)
        except Exception as exc:  # noqa: BLE001
            return self._json({"error": "无法读取 ECMWF 图：%s" % exc}, 502)

        frames = data["frames"]
        if not frames:
            return self._json({"error": "该产品当前没有图像"}, 502)
        product = PRODUCT_MAP[pid]
        latest = frames[-1]
        now = time.time()
        self._json(
            {
                "product": pid,
                "title": product["title"],
                "source": product["source"],
                "sourceName": "ECMWF IFS",
                "kind": product["kind"],
                "interval": product["interval"],
                "coverage": product["coverage"],
                "level": product["level"],
                "page": product["page"],
                "forecast": True,
                "run": data.get("run"),
                "generated": data.get("generated"),
                "count": len(frames),
                "frames": [public_frame(f) for f in frames],
                "stale": bool(data.get("stale")),
                "fetched": data["fetched"],
                "delayMin": max(0, int(round((now - latest["ts"]) / 60))),
                "spanMin": int(round((latest["ts"] - frames[0]["ts"]) / 60)),
            }
        )

    def api_img(self, qs: dict) -> None:
        pid = (qs.get("p") or [""])[0]
        stamp = (qs.get("s") or [""])[0]
        dl = (qs.get("dl") or ["0"])[0] in ("1", "true")
        if pid not in PRODUCT_MAP or not STAMP_RE.fullmatch(stamp or ""):
            return self._json({"error": "参数不合法"}, 400)
        frame = resolve_frame(pid, stamp)
        if not frame:
            return self._json({"error": "图像不存在"}, 404)

        target = (ECMWF_DIR / frame["file"]).resolve()
        try:
            target.relative_to(ECMWF_DIR.resolve())
        except ValueError:
            return self._json({"error": "图像路径不合法"}, 400)
        if not target.is_file():
            return self._json({"error": "图像文件不存在"}, 404)
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        # 图片文件名在重新生成后通常保持不变，不能使用 immutable 长缓存。
        headers = {"Cache-Control": "no-cache"}
        if dl:
            fname = "%s_%s.png" % (pid, stamp)
            headers["Content-Disposition"] = (
                "attachment; filename=\"%s\"; filename*=UTF-8''%s"
                % (fname, urllib.parse.quote(fname))
            )
            headers["Cache-Control"] = "no-store"
        self._send(200, data, mime, headers)

    def serve_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        if path in ("/tc", "/tc/"):
            path = "/tc/index.html"
        rel = urllib.parse.unquote(path).lstrip("/")
        root = PUBLIC_DIR.resolve()
        target = (PUBLIC_DIR / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._send(404, b"404 Not Found", "text/plain; charset=utf-8")
        if target.is_dir():
            target = (target / "index.html").resolve()
            try:
                target.relative_to(root)
            except ValueError:
                return self._send(404, b"404 Not Found", "text/plain; charset=utf-8")
        if not target.is_file():
            return self._send(404, b"404 Not Found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype, {"Cache-Control": "no-cache"})


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):  # noqa: N802
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def pick_port(host: str, preferred: int) -> int:
    bind_host = "0.0.0.0" if host in ("0.0.0.0", "") else host
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((bind_host, port))
                return port
            except OSError:
                continue
    raise SystemExit("找不到可用端口")


def main() -> None:
    ap = argparse.ArgumentParser(description="ECMWF 华南预报图站")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    ap.add_argument(
        "--host",
        default=os.environ.get("SITE_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"),
    )
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()

    port = pick_port(args.host, args.port)
    server = Server((args.host, port), Handler)
    url = "http://%s:%d" % ("127.0.0.1" if args.host in ("0.0.0.0", "") else args.host, port)
    log("ECMWF 华南预报站已启动：%s" % url)
    log("共 %d 个预报产品；台风系集页：%s/tc/" % (len(PRODUCTS), url))
    log("图像目录：%s" % ECMWF_DIR)
    log("按 Ctrl+C 停止服务")

    if args.open:
        threading.Timer(0.6, lambda: __import__("webbrowser").open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
