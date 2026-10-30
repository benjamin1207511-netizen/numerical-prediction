#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热带气旋多模式数据自动更新器。

每 10 分钟检查一次官方源：
  - ECMWF AIFS ENS：ECMWF Open Data BUFR
  - NOAA GEFS：NOMADS ens_tracker ATCF
  - ECMWF IFS ENS：若已安装 pybufrkit，则下载最新 BUFR 并重建静态 JSON

AIFS / GEFS 的归一化结果会写入 .tc-cache/，服务端 /api/tcmodel 会优先读取
该磁盘缓存，所以页面切换模式时不必每次等待上游下载和解析。

用法：
  python tc_auto_update.py              # 常驻，每 600 秒检查
  python tc_auto_update.py --once       # 检查并更新一次
  python tc_auto_update.py --dry-run    # 只列出当前可用起报
  python tc_auto_update.py --force      # 即使同一场次也重新生成
  python tc_auto_update.py --no-ifs     # 不检查 IFS 静态场

IFS 静态场更新需要：
  python -m pip install pybufrkit "bitstring==3.1.9"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import ssl
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / ".tc_auto_update_state.json"
LOCK_FILE = BASE_DIR / ".tc_auto_update.lock"
LOG_FILE = BASE_DIR / ".tc_auto_update.log"
INDEX_FILE = BASE_DIR / "public" / "tc-data" / "index.json"
CACHE_DIR = BASE_DIR / ".tc-cache"
TZ_CN = timezone(timedelta(hours=8))
UTC = timezone.utc
DEFAULT_INTERVAL = 10 * 60
IFS_URL = (
    "https://data.ecmwf.int/forecasts/{date}/{hour}z/ifs/0p25/enfo/"
    "{stamp}0000-360h-enfo-tf.bufr"
)
_SSL_CONTEXT = ssl._create_unverified_context()


def now_cn() -> datetime:
    return datetime.now(TZ_CN)


def log(message: str) -> None:
    line = "[%s] %s" % (now_cn().strftime("%Y-%m-%d %H:%M:%S"), message)
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except (BrokenPipeError, OSError):
            pass
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.1"))
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_lock() -> bool:
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text(encoding="ascii").strip() or "0")
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and pid_running(old_pid):
            log("已有更新器在运行（PID %s），本次退出" % old_pid)
            return False
        try:
            LOCK_FILE.unlink()
            log("清理失效锁 PID %s" % old_pid)
        except OSError:
            pass
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.close(fd)
        return True
    except OSError as exc:
        log("无法获取锁：%s" % exc)
        return False


def release_lock() -> None:
    try:
        if LOCK_FILE.exists() and LOCK_FILE.read_text(encoding="ascii").strip() == str(os.getpid()):
            LOCK_FILE.unlink()
    except OSError:
        pass


def http_ok(url: str, timeout: int = 8) -> bool:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": "BAMC-EC-TC/1.0 (+https://www.bamc.top)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_SSL_CONTEXT) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def recent_cycles(days: int = 1) -> list[str]:
    current = datetime.now(UTC)
    values = []
    for offset in range(days):
        day = current - timedelta(days=offset)
        for hour in ("18", "12", "06", "00"):
            values.append(day.strftime("%Y%m%d") + hour)
    return values


def latest_ifs_run() -> str | None:
    for stamp in recent_cycles(1):
        if http_ok(IFS_URL.format(date=stamp[:8], hour=stamp[8:10], stamp=stamp)):
            return stamp
    return None


def static_ifs_run() -> str | None:
    data = read_json(INDEX_FILE)
    latest = data.get("latest")
    return str(latest) if latest else None


def maybe_update_ifs(state: dict) -> None:
    if importlib.util.find_spec("pybufrkit") is None:
        log("IFS：未安装 pybufrkit，跳过静态场更新")
        return
    latest = latest_ifs_run()
    if not latest:
        log("IFS：当前没有检测到新 BUFR 场")
        return
    current = static_ifs_run()
    if current and latest <= current:
        log("IFS：最新场仍为 %s" % current)
        return
    log("IFS：发现新场 %s，开始重建 JSON（当前 %s）" % (latest, current or "无"))
    started = time.time()
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "tools" / "build_tc_data.py"), "--download", latest],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        log("IFS：重建失败 rc=%s %s" % (result.returncode, (result.stderr or "").strip()[-500:]))
        return
    log("IFS：重建完成，用时 %.1f 秒" % (time.time() - started))
    state["ifs"] = latest


def jtwc_systems() -> list[dict]:
    try:
        from server import fetch_jtwc

        data = fetch_jtwc()
        return data.get("systems") or []
    except Exception as exc:
        log("JTWC 参考位置读取失败：%s" % exc)
        return []


def update_models(models: list[str], force: bool, dry_run: bool, state: dict) -> None:
    from tc_direct import MODEL_SPECS, fetch_dates, fetch_model

    known = state.setdefault("models", {})
    systems = jtwc_systems()
    for model in models:
        spec = MODEL_SPECS.get(model)
        if not spec:
            log("跳过未知模式：%s" % model)
            continue
        try:
            dates_payload = fetch_dates(model, force=True)
            dates = dates_payload.get("dates") or []
            if not dates:
                log("%s：官方源没有列出可用起报" % spec["short"])
                continue
            latest = dates[0]["value"]
            log("%s：可用起报 %s" % (spec["short"], dates[0].get("display") or latest))
            if dry_run:
                continue
            cache_file = CACHE_DIR / ("%s-%s.json" % (model, latest))
            if not force and known.get(model, {}).get("date") == latest and cache_file.is_file():
                log("%s：%s 已缓存，跳过" % (spec["short"], latest))
                continue
            started = time.time()
            payload = fetch_model(model, latest, systems)
            storm = (payload.get("storms") or [{}])[0]
            known[model] = {
                "date": latest,
                "run": payload.get("run", {}).get("display"),
                "members": storm.get("member_count"),
                "lead_max": storm.get("lead_max"),
                "updated": now_cn().isoformat(timespec="seconds"),
            }
            log(
                "%s：%s 更新完成，%.1f 秒，%s 成员，+0–+%s h"
                % (
                    spec["short"],
                    payload.get("run", {}).get("display") or latest,
                    time.time() - started,
                    storm.get("member_count"),
                    storm.get("lead_max"),
                )
            )
        except Exception as exc:
            log("%s：更新失败 %s: %s" % (spec["short"], type(exc).__name__, str(exc)[:300]))
            if os.environ.get("TC_AUTO_DEBUG"):
                log(traceback.format_exc()[-1200:])
    state["last_success"] = now_cn().isoformat(timespec="seconds")


def run_once(models: list[str], force: bool, dry_run: bool, no_ifs: bool, state: dict) -> None:
    state["last_checked"] = now_cn().isoformat(timespec="seconds")
    update_models(models, force, dry_run, state)
    if not no_ifs and not dry_run:
        try:
            maybe_update_ifs(state)
        except Exception as exc:
            log("IFS：检查失败 %s: %s" % (type(exc).__name__, str(exc)[:300]))
    write_json(STATE_FILE, state)


def main() -> int:
    parser = argparse.ArgumentParser(description="热带气旋多模式数据自动更新器")
    parser.add_argument("--once", action="store_true", help="只执行一次")
    parser.add_argument("--dry-run", action="store_true", help="只查看可用起报，不写入")
    parser.add_argument("--force", action="store_true", help="同一场次也重新生成")
    parser.add_argument("--no-ifs", action="store_true", help="不检查 IFS 静态场")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="轮询秒数，默认 600")
    parser.add_argument(
        "--models",
        default="aifs,gefs",
        help="逗号分隔的模式列表，默认 aifs,gefs",
    )
    args = parser.parse_args()
    models = [item.strip().lower() for item in args.models.split(",") if item.strip()]
    if not acquire_lock():
        return 0
    state = read_json(STATE_FILE)
    log("热带气旋自动更新器启动；模型=%s；间隔=%s 秒" % (",".join(models), args.interval))
    try:
        run_once(models, args.force, args.dry_run, args.no_ifs, state)
        if args.once or args.dry_run:
            return 0
        while True:
            log("等待 %s 秒后再次检查" % args.interval)
            time.sleep(max(60, args.interval))
            try:
                run_once(models, args.force, False, args.no_ifs, state)
            except Exception as exc:
                log("本轮异常：%s: %s" % (type(exc).__name__, str(exc)[:300]))
                if os.environ.get("TC_AUTO_DEBUG"):
                    log(traceback.format_exc()[-1200:])
    except KeyboardInterrupt:
        log("收到中断，退出")
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
