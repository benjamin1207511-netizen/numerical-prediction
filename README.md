# BAMC ECMWF 华南预报

以 ECMWF IFS 预报图为主的轻量网站：16 类产品，每天 **00Z / 12Z** 两个起报场，从 +24h 到 +240h 每 6 小时一帧，共 37 帧。

- **数据源：ECMWF Open Data 直连**（`data.ecmwf.int`，IFS 0.25° GRIB2）；Open-Meteo 作为备用
- 华南区域：**16–28°N、105–121°E**（0.5° 输入、0.25° 绘图）
- 综合图与 500hPa 风场另有东亚版：**0–50°N、80–140°E**（0.5° 绘图）
- 纯 Python 标准库后端，无数据库；图像为预生成 PNG，更新后热切换，站点无需重启
- 内置反爬（会话 Cookie、限速、UA 过滤、扫描器拦截、IP 黑名单、图片防盗链）
- 内置自动更新器：只使用已经更新到 +240h 的完整 00Z / 12Z 场次，半截场次自动跳过

## 快速开始

```bash
python server.py
```

浏览器打开 `http://127.0.0.1:8787`。Windows 也可双击 `start.bat`。

站点运行只需要 Python 标准库；`ecmwf/` 里是预生成的预报图。生成/更新图片需要：

```bash
python -m pip install numpy scipy matplotlib cartopy eccodes
```

`eccodes` 只在直连 ECMWF Open Data 时需要（`--source openmeteo` 不需要）。

## 产品

| ID | 名称 |
| --- | --- |
| `ecmwf-southchina` | 华南 · 降雨 + 500hPa 高度 + 850hPa 风 |
| `ecmwf-southchina-ea` | 东亚 · 降雨 + 500hPa 高度 + 850hPa 风 |
| `ecmwf-t2m` | 2m 气温 |
| `ecmwf-h500` | 华南 · 500hPa 风场 |
| `ecmwf-h500-ea` | 东亚 · 500hPa 风场 |
| `ecmwf-rain24` | 24h 降水 |
| `ecmwf-mslp` | 海平面气压 |
| `ecmwf-wind10` | 地面风场 |
| `ecmwf-wind925` | 925hPa 风场 |
| `ecmwf-gust24` | 24h 阵风 |
| `ecmwf-cape` | CAPE |
| `ecmwf-kindex` | K 指数 |
| `ecmwf-pwat` | PWAT |
| `ecmwf-rh2m` | 2m 相对湿度 |
| `ecmwf-rh500` | 500hPa 相对湿度 |
| `ecmwf-cloud` | 总云量（成） |

### 图像样式约定

- 时次：+24h 至 +240h，每 6 小时一帧，共 37 帧；只用 00Z / 12Z 起报场。
- 空间精度：华南 0.5° 输入、0.25° 绘图；东亚版 2.5° 输入、0.5° 绘图。
- 综合图：588 dagpm 位势高度线用红色粗线描出，“588”标签在红线之上，没有该线时不画；
  850hPa 风速 ≥ 24.5 m/s 的风矢标红，其余蓝色。
- 24h 阵风、地面风场：15 级风速色阶（0.3–56.1 m/s），>56.1 m/s 红色，<0.3 m/s 白色。
- 总云量：4–9 成蓝色渐变，<4 成白色，>9 成深蓝。
- 风矢取样：华南 0.5°、东亚 1.5°，线宽较细，长度约为旧版 1.5 倍。
- 广东省界用黄色描边。
- 顶栏本地时间在电脑端和手机端都显示。

## 更新图片

```bash
python auto_update.py            # 常驻，每 30 分钟检查一次
python auto_update.py --once     # 只检查并更新一次
python auto_update.py --dry-run  # 只看有没有新场次
```

Windows 也可以：

- `start_auto_update.bat`：常驻窗口
- `install_auto_update_task.bat`：注册 Windows 计划任务（每 30 分钟静默运行）
- `uninstall_auto_update_task.bat`：卸载计划任务

更新器要点：

- 数据源默认 `ecmwf`（ECMWF Open Data 直连），可用 `BAMC_SOURCE=openmeteo` 切回 Open-Meteo；
- 只使用 **00Z / 12Z** 且已经更新到 +240h 的完整场次，半截场次自动跳过；
- Open-Meteo 模式下载按 200 点分块并缓存到 `_cache/chunks/`，断网后重跑不重复下载；
- 单次失败自动重试 3 次（`BAMC_BUILD_RETRIES` / `BAMC_RETRY_WAIT` 可调）；
- 图片先写入 `ecmwf_build/`，校验通过后整体替换，成功后清理缓存与旧图；
- 每次发布后自动删除旧场次图片，**磁盘上只保留最新一组 16×37 张**（`prune_live`）。

手动生成：

```bash
python ecmwf_chart.py                                  # 默认 ecmwf 源，自动选最新完整场次
python ecmwf_chart.py --source openmeteo               # 改用 Open-Meteo
python ecmwf_chart.py --run 2026-11-07T12:00           # 指定场次
python ecmwf_chart.py --products cloud --jobs 1        # 只出云量，单进程
```

### 加速

- 渲染默认多进程并行（`min(4, CPU-1)`），可用 `--jobs N` 指定；
  多进程不可用时自动退回线程，再不行退回单进程。
- Open Data 模式按 step 并发下载（`BAMC_OPEN_WORKERS`，默认 4）；
  Open-Meteo 模式 3 路并发，`BAMC_FETCH_WORKERS` 可调，遇到 429 自动退避。
- 出图默认 **140 dpi**（1400×1008，比 160 dpi 小约 25%、快约 20%，画质略软）；
  想更清晰可把 `ecmwf_chart.py` 里 `fig.savefig(..., dpi=140)` 改回 160。

## 数据源：ECMWF Open Data

`ecmwf_open.py` 直连 `https://data.ecmwf.int/forecasts/…/ifs/0p25/oper/`：

- 用每个 step 的 `.index` 文件查字节偏移，**Range 请求只取需要的 22 个字段**；
  一个 step 约 11–12 MB，一轮 00Z/12Z 全部 37+ 帧约 **420–450 MB**；
- 用 `eccodes` 解码 GRIB2，按 0.25° 经纬度网格采样到站点用的地点网格；
- 时间步：+0 到 +144 为 3 小时、之后 6 小时；本项目只取 6 小时间隔；
- 变量对应：`2t/2d/tp/msl/10u/10v/10fg/mucape/tcwv/tcc/gh500/t,r,d,u,v@500·700·850·925`；
  其中 **CAPE 用 `mucape`（最不稳定 CAPE）近似**，其余为 ECMWF 原始字段；
- 2m 相对湿度由 `2t/2d` 计算，K 指数、24h 降水/阵风由逐时序列本地统计；
- 本机 TLS 链被中间代理改写，`ecmwf_open.py` 对 `data.ecmwf.int` 使用宽松校验
  （公开只读数据，仅影响该域名）。

Open Data 无需 API key、无调用配额；代价是每轮要下载几百 MB 数据。

## Open-Meteo 限额与用量（备用源）

数据来自 Open-Meteo 免费接口（非商业用途），官方限额：

| 限制 | 免费额度 |
| --- | --- |
| 每分钟 | 600 次调用 |
| 每小时 | 5,000 次 |
| 每天 | 10,000 次 |
| 每月 | 300,000 次 |

调用量按 **地点数 × 变量组份数 × 时长份数** 折算：每 10 个变量算 1 份，
超过 2 周再按时长加倍；多地点请求按地点数累加。本项目为了压额度做了这些事：

- 变量合并成 **3 组（10/10/3 个）**，东亚 6 个变量单组；
- 华南 825 点、东亚 525 点 → 一次更新约 `825×3 + 525×1 ≈ 3000` 次调用；
- 每天只跑 00Z / 12Z 两场 → 约 **6000 次/天**、**18 万次/月**，在免费额度内；
- 30 分钟轮询只做 1–2 次“完整性探测”（单点、单变量），没有新场次不会下载；
- 分块缓存：失败重试不会重复消耗额度。

如果继续加大范围/精度（地点数翻倍，额度也翻倍）、或站点对外公开/商用，
建议购买 Open-Meteo 的 API 套餐（`customer-api.open-meteo.com` + key），
或改成自建 / 直连 ECMWF Open Data。

## 反爬说明

`anti_bot.py` 已接入 `server.py`，不需要单独启动：

- 页面签发 `bamc_sid` 会话 Cookie（HMAC 签名，12 小时）；
- `/api/*` 必须带有效 Cookie；
- 每 IP 滑动窗口限速：全局 420 / HTML 60 / API 180 / 图片 360 次每 60 秒；
- 拦截 requests / curl / scrapy / puppeteer / 无头浏览器，以及 AI / SEO 爬虫 UA；
- 扫描器路径（`/wp-admin`、`/.env`、`/phpmyadmin`、`/.git` 等）直接 404；
- `blocklist.txt` 可写 IP 或 CIDR，保存 30 秒内生效；
- 图片带外站 Referer 时拒绝；
- 拦截日志写入 `anti_bot.log`（超 2 MB 轮转）。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `RATE_GLOBAL` / `RATE_HTML` / `RATE_API` / `RATE_IMAGE` | 420 / 60 / 180 / 360 | 每 60 秒限额 |
| `ANTIBOT_LOG` | `1` | 设为 `0` 关闭拦截日志 |
| `ANTIBOT_SECRET` | 随机 | 固定 Cookie 签名密钥（生产环境建议设置） |

## 目录结构

```text
ecmwf-south-china/
├─ server.py             # 网站后端
├─ anti_bot.py           # 反爬模块
├─ auto_update.py        # 自动更新器
├─ ecmwf_chart.py        # 预报图生成脚本
├─ ecmwf_open.py         # ECMWF Open Data 直连（GRIB2 + eccodes）
├─ blocklist.txt         # 反爬 IP/CIDR 黑名单
├─ start.bat             # 启动网站
├─ start_auto_update.bat # 常驻自动更新
├─ install_auto_update_task.bat / uninstall_auto_update_task.bat
├─ run_auto_update_once.bat      # 计划任务调用的单次更新
├─ README.md
├─ public/               # 前端（index.html / style.css / app.js / robots.txt）
└─ ecmwf/                # 16 类产品，每类 37 张 PNG + manifest.json
   ├─ combined/  combined-ea/  h500/  h500-ea/ …
   └─ cloud/
```

## 让局域网 / 公网访问

```bash
python server.py --host 0.0.0.0 --port 8787
```

同一 Wi-Fi 下访问 `http://你的电脑IP:8787`。公网可用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

用 Nginx / Cloudflare / Render 反向代理时务必设置 `TRUST_PROXY=1`，
否则所有访客会被识别成同一个 IP。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | 8787 | 监听端口 |
| `SITE_HOST` | 本地 `127.0.0.1`，有 `PORT` 时 `0.0.0.0` | 监听地址 |
| `TRUST_PROXY` | `0` | 反向代理后设为 `1` |
| `ANTIBOT_SECRET` | 随机生成 | Cookie 签名密钥 |
| `ANTIBOT_LOG` | `1` | `0` 关闭拦截日志 |
| `BAMC_BUILD_RETRIES` | `3` | 自动更新失败重试次数 |
| `BAMC_RETRY_WAIT` | `120` | 重试间隔秒数 |
| `BAMC_SOURCE` | `ecmwf` | `ecmwf`（Open Data 直连）/ `openmeteo` |
| `BAMC_OPEN_WORKERS` | `4` | Open Data 按 step 下载的并发数 |
| `BAMC_FETCH_WORKERS` | `3` | Open-Meteo 下载并发数 |
| `BAMC_RENDER_MODE` | `auto` | `auto` / `process` / `thread` / `serial` |

## 数据与声明

- 预报图数据：ECMWF IFS 0.25°，经 Open-Meteo 获取
- 图像：本地 Python 脚本生成，右下角落款 `www.bamc.top`
- 图像仅作预报参考，ECMWF / Open-Meteo 数据版权归原机构所有
