# BAMC ECMWF 华南预报

以 ECMWF IFS 预报图为主、并带 ECMWF AIFS / NOAA GEFS 热带气旋系集的轻量网站：

- 预报图：16 类产品，每天 4 个时次（00/06/12/18 UTC），从 +24h 到 +240h，每 6 小时一帧，共 37 帧。
  华南范围 **16–28°N、105–121°E**（0.5° 输入 / 0.25° 绘图）；综合图与 500hPa 风场另有 **东亚 0–50°N、80–140°E** 版本（0.5° 绘图）。
- 热带气旋系集：ECMWF IFS、ECMWF AIFS、NOAA GEFS，范围 100–140°E、10–35°N，可在 `/tc/` 查看。

- 纯 Python 标准库后端，不需要数据库
- 预报图为预生成 PNG；台风系集页读取预生成 JSON，并通过后端 `/api/jtwc` 实时读取 GDACS 转发的 JTWC 活跃系统
- 浅色 BAMC 风格界面，支持桌面和手机
- 内置反爬：会话 Cookie、IP 限速、UA 过滤、图片防盗链
- 内置自动更新器：图片由 `auto_update.py` 每 30 分钟检查 Open-Meteo 新起报；台风多模式数据由 `tc_auto_update.py` 每 10 分钟检查 AIFS / GEFS 官方源

## 快速开始

先安装 Python 3.10 或以上版本，然后在本目录执行：

```bash
python server.py
```

浏览器打开：

```text
http://127.0.0.1:8787            # 华南预报图
http://127.0.0.1:8787/tc/        # EC 系集热带气旋
```

Windows 也可以双击 `start.bat`。

网站基础运行只需要 Python 标准库，`ecmwf/` 与 `public/tc-data/` 中包含预报图和 IFS 台风 JSON；AIFS / GEFS 通过后端实时接口读取。AIFS 模式需要 `eccodes`（`python -m pip install eccodes`）。

## 热带气旋系集页

`/tc/` 支持多模式切换，默认显示 ECMWF IFS ENS，也可选择 AIFS 和 NOAA GEFS：

- 西北太平洋范围：**100–140°E，10–35°N**
- 每个成员每 6 小时一个点位，路径按 **最低海平面气压** 或 **最大 10m 风速** 着色
- 可切换模式、起报时次、播放预报时效、悬停/锁定单个成员
- 强度面板显示各模式的成员 MSLP 曲线、中位数和 10–90% 区间
- 地图可导出 PNG，导出图带模式标题与 `www.bamc.top` 落款
- **JTWC 活跃系统层**：实时列出当前中心位于框内的 JTWC 系统，红色菱形标出当前位置；每 5 分钟自动检查，后台接口为 `/api/jtwc`
- 地图框外的系集轨迹和 JTWC 系统均被裁掉，不会越出 100–140°E、10–35°N

| 模式 | 成员数 | 数据来源 |
| --- | ---: | --- |
| `ifs` ECMWF IFS ENS | 51 | 本地预生成 ECMWF Open Data TC BUFR |
| `aifs` ECMWF AIFS ENS | 52 | ECMWF Open Data，AIFS ENS TC BUFR |
| `gefs` NOAA GEFS（GFS Ensemble） | 31 | NOAA NOMADS `ens_tracker` GEFS ATCF |

模式切换也可直接用 URL，例如：

```text
/tc/?model=aifs
/tc/?model=gefs
```

多模式原始数据接口（同样受站点会话 Cookie 保护）：

```text
GET /api/tcmodel/dates?model=aifs
GET /api/tcmodel?model=aifs&date=2026102306
GET /api/tcmodel?model=gefs
```

接口返回统一的 `run / storms / members / leads` JSON，并将所有轨迹点裁剪到
100–140°E、10–35°N。

> 多模式轨迹通过后端 `/api/tcmodel` 与 `/api/tcmodel/dates` 直接读取各模式官方源：
> ECMWF AIFS BUFR、NOAA NOMADS `ens_tracker`。
> JTWC 系统清单通过 [GDACS](https://www.gdacs.org/) 的 JTWC 实时转发读取（`metoc.navy.mil` 在部分网络不可达）。
> 页面只保留 **当前中心在框内** 的 JTWC 系统；系统移出范围后会从清单和地图上移除。
> IFS 系集路径仍以最新可用的 ECMWF ENS 轨迹 BUFR 为准。

IFS 页面数据位于 `public/tc-data/`，由 ECMWF Open Data 的 ENS 热带气旋轨迹 BUFR 离线生成：

```text
https://data.ecmwf.int/forecasts/YYYYMMDD/HHz/ifs/0p25/enfo/
  YYYYMMDDHH0000-360h-enfo-tf.bufr
```

更新数据（需要 `pybufrkit`，仅构建时需要）：

```bash
python -m pip install pybufrkit "bitstring==3.1.9"
python tools/build_tc_data.py --download 2026102200
# 或者重建 data/ 目录下所有已下载场次：
python tools/build_tc_data.py --all
```

构建脚本会把 BUFR 解析为 `public/tc-data/<run>.json`，并更新 `index.json`。
IFS 页面运行时不会访问 ECMWF，也不需要 `pybufrkit`；AIFS / GEFS
则由 `/api/tcmodel` 直接读取实时轨迹。

## 目录结构

```text
ecmwf-south-china/
├─ server.py             # 网站后端
├─ anti_bot.py           # 反爬模块
├─ auto_update.py        # 自动更新器（预报图）
├─ tc_auto_update.py     # 自动更新器（AIFS / GEFS / 可选 IFS）
├─ tc_direct.py          # AIFS / GEFS 官方源适配
├─ ecmwf_chart.py        # 预报图生成脚本
├─ start.bat             # 启动网站
├─ start_auto_update.bat # 启动预报图自动更新（常驻窗口）
├─ start_tc_auto_update.bat # 启动台风数据自动更新
├─ start_all_auto_update.bat # 同时启动两个更新器
├─ install_auto_update_task.bat   # 安装「每 30 分钟」计划任务（静默）
├─ uninstall_auto_update_task.bat # 卸载计划任务
├─ run_auto_update_once.bat       # 计划任务实际调用的单次更新脚本
├─ blocklist.txt         # 反爬 IP/CIDR 黑名单（热加载）
├─ README.md
├─ public/
│  ├─ index.html
│  ├─ style.css
│  ├─ app.js
│  ├─ robots.txt
│  ├─ tc/                # 多模式系集热带气旋页面
│  │  ├─ index.html
│  │  ├─ tc.css
│  │  └─ tc.js
│  └─ tc-data/           # IFS 预生成 JSON + Natural Earth 底图
│     ├─ index.json
│     ├─ 2026102200.json
│     └─ geo.json
├─ tools/
│  ├─ build_tc_data.py   # BUFR → JSON
│  └─ build_geo.py       # Natural Earth → 底图 JSON
├─ data/                 # 可选：下载的 BUFR 原始文件
└─ ecmwf/
   ├─ combined/          # 16 类产品，每类 37 张 PNG + manifest.json
   ├─ combined-ea/       # 东亚范围综合图
   ├─ h500-ea/           # 东亚范围 500hPa 风场
   ├─ t2m/
   ├─ h500/
   ├─ rain24/
   ├─ mslp/
   ├─ wind10/
   ├─ wind925/
   ├─ gust24/
   ├─ cape/
   ├─ kindex/
   ├─ pwat/
   ├─ rh2m/
   ├─ rh500/
   └─ cloud/
```

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

- 时次范围：**+24h 至 +240h**，每 6 小时一帧，共 37 帧；自动更新器只在新起报场已经更新到 +240h 后才切换，避免出现空白尾帧。
- 空间精度：华南 0.5° 输入、**0.25° 绘图**（雨、气温、湿度、云量等全部产品同步提升）；东亚版本 2.5° 输入、0.5° 绘图。
- 综合图（雨 + 500hPa 高度 + 850hPa 风）：588 dagpm 位势高度线用**红色粗线**单独描出，标签“588”放在红线之上，该时次没有 588 线时不画；850hPa 风速 **≥ 24.5 m/s** 的风矢标红，其余为蓝色。
- 24h 阵风、地面风场：风速色阶按参考图右侧的 15 级（0.3–56.1 m/s），>56.1 m/s 为红色，<0.3 m/s 为白色。
- 总云量：按成数 4–9 分级，蓝色由浅到深（参考“Total Cloud Cover”参考图），<4 成为白色，>9 成为深蓝。
- 风矢取样：华南 **0.5°**（0.25° 网格每 2 格一支）、东亚 **1.5°**（0.5° 网格每 3 格一支），线宽较细，长度约为旧版的 1.5 倍。
- 广东省界统一用黄色描边。
- 顶栏本地时间在电脑端和手机端都会显示，样式一致。

## 更新图片

自动更新有两种用法，任选其一：

**A. 常驻窗口**（适合一直开着的机器）

```bash
python -m pip install numpy scipy matplotlib cartopy
python auto_update.py
```

或双击 `start_auto_update.bat`，每 30 分钟检查一次，窗口关掉即停止。

**B. Windows 计划任务**（推荐，无窗口、开机自动）

双击 `install_auto_update_task.bat`，会创建名为 `BAMC-ECMWF-AutoUpdate` 的计划任务：

- 每 30 分钟运行一次 `run_auto_update_once.bat` → `auto_update.py --once`；
- 没有新场次时秒退，有新场次才重新出图；
- 日志在 `auto_update.log` 和 `update_task.log`；
- 卸载：双击 `uninstall_auto_update_task.bat`；
- 想立刻更新一次：`schtasks /Run /TN "BAMC-ECMWF-AutoUpdate"`。

手动更新：

```bash
python ecmwf_chart.py                 # 自动选最新完整场次
python ecmwf_chart.py --run 2026-10-29T12:00   # 指定场次
```

更新器要点：

- 只用**已经更新到 +240h 的完整场次**，新场次半截数据会自动跳过，避免出现空白尾帧；
- 下载按每块 200 个点分块，并缓存到 `_cache/chunks/`：网络中断后重跑不会重新下载已完成的分块；
- 单次失败自动重试 3 次（`BAMC_BUILD_RETRIES` / `BAMC_RETRY_WAIT` 可调），成功发布后才删除旧图；
- 图片先写入 `ecmwf_build/`，校验通过后整体替换，网站无需重启。

## 更新台风多模式数据

台风页的 AIFS / GEFS 由独立更新器维护，和图片更新器互不影响：

```bash
python tc_auto_update.py --once       # 立即检查并更新一次
python tc_auto_update.py              # 常驻，每 10 分钟检查
python tc_auto_update.py --dry-run    # 只查看可用起报
python tc_auto_update.py --force      # 同一场次也强制重新生成
python tc_auto_update.py --no-ifs     # 不检查 IFS 静态场
```

Windows 可双击 `start_tc_auto_update.bat`；若图片和台风数据都要自动更新，双击
`start_all_auto_update.bat` 会分别打开两个更新窗口。

更新器会：

- 检查 ECMWF AIFS ENS 和 NOAA GEFS 官方源的最新起报；
- 将归一化轨迹写入 `.tc-cache/`，`/api/tcmodel` 会优先读取该缓存，页面切换模式时无需重复等待上游；
- 若安装了 `pybufrkit`，会在检测到新 IFS 场次时调用
  `tools/build_tc_data.py --download <run>` 重建 `public/tc-data/` 静态 JSON。

IFS 自动更新依赖：

```bash
python -m pip install pybufrkit "bitstring==3.1.9"
```

AIFS 解析依赖 `eccodes`，GEFS 不需要额外依赖。

## 让局域网访问

```bash
python server.py --host 0.0.0.0 --port 8787
```

然后在同一 Wi-Fi 下访问：

```text
http://你的电脑局域网IP:8787
```

## 让公网访问

### 临时公网地址（最快）

使用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

命令会输出一个 `https://xxxx.trycloudflare.com` 地址，别人可以直接打开。

如果电脑没有 cloudflared，也可以用 Windows 自带的 SSH：

```bash
ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8787 nokey@localhost.run
```

它会输出一个 `https://xxxx.lhr.life` 地址。

注意：这两种都是临时隧道，电脑关闭或隧道进程结束后地址失效。

### 长期公网网站

把本目录上传到任意支持 Python 的云平台，例如：

- Render
- Railway
- 自己的 VPS
- 香港/海外云服务器

启动命令：

```bash
python server.py
```

监听地址：

```text
0.0.0.0
```

平台通常会自动注入 `PORT`。如果平台不注入，设置：

```text
PORT=8787
SITE_HOST=0.0.0.0
TRUST_PROXY=1
```

> 用 Nginx / Cloudflare / Render 反向代理时，`TRUST_PROXY=1` 必须设置，
> 否则所有访客会被识别成同一个 IP。

## 反爬说明

`anti_bot.py` 已接入 `server.py`，不需要单独启动。

限制包括：

- 页面签发 `bamc_sid` 会话 Cookie（HMAC 签名，12 小时有效）；
- `/api/*` 必须携带有效 Cookie；
- 每个 IP 滑动窗口限速：全局 420 / HTML 60 / API 180 / 图片 360 次每 60 秒；
- 拦截 requests / curl / wget / scrapy / puppeteer / playwright / 无头浏览器，
  以及 GPTBot、ClaudeBot、CCBot、Bytespider、Semrush、Ahrefs 等 AI / SEO 爬虫 UA；
- 扫描器路径（`/wp-admin`、`/.env`、`/phpmyadmin`、`/cgi-bin`、`/.git` 等）直接 404；
- `blocklist.txt` 手动黑名单：每行一个 IP 或 CIDR，保存后 30 秒内生效，无需重启；
- 图片带外站 Referer 时拒绝（防盗链）；
- 拦截记录写入 `anti_bot.log`（超过 2 MB 自动轮转），格式为
  `时间 / IP / 路径 / 原因 / UA`，方便事后加黑名单；
- `/healthz` 和 `/api/health` 为监控保留，始终可访问。

`anti_bot.py` 里直接改 `RequestGuard` 可以进一步收紧；常用开关用环境变量即可：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `RATE_GLOBAL` / `RATE_HTML` / `RATE_API` / `RATE_IMAGE` | 420 / 60 / 180 / 360 | 每 60 秒限额 |
| `ANTIBOT_LOG` | `1` | 设为 `0` 关闭拦截日志 |
| `ANTIBOT_SECRET` | 随机 | 固定 Cookie 签名密钥（建议生产环境设置） |

**注意**：任何公开网站都无法做到 100% 防抓取，这些措施只能提高批量抓取成本。
直接用 curl 请求 `/api/meta` 会返回 403，访问 `/wp-admin` 会返回 404，都是正常现象；
浏览器访问不受影响。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | 8787 | 监听端口 |
| `SITE_HOST` | 本地 `127.0.0.1`，有 `PORT` 时 `0.0.0.0` | 监听地址 |
| `TRUST_PROXY` | `0` | 反向代理后设为 `1` |
| `ANTIBOT_SECRET` | 随机生成 | Cookie 签名密钥，生产环境建议固定 |
| `ANTIBOT_LOG` | `1` | `0` 关闭拦截日志 |
| `BAMC_BUILD_RETRIES` | `3` | 自动更新失败重试次数 |
| `BAMC_RETRY_WAIT` | `120` | 重试间隔秒数 |

## 数据与声明

- 预报图数据：ECMWF IFS 0.25°，经 Open-Meteo 获取
- IFS 台风系集：ECMWF Open Data，IFS ENS 热带气旋轨迹 BUFR（WMO Essential）
- AIFS 台风系集：ECMWF Open Data，AIFS ENS 热带气旋轨迹 BUFR
- GEFS 台风系集：NOAA NOMADS `ens_tracker` ATCF
- JTWC 活跃系统当前中心：GDACS 对 JTWC 的实时转发
- 图像：本地 Python 脚本生成
- 导出图右下角：`www.bamc.top`
- 图像与台风数据仅作预报参考，ECMWF / NOAA / Open-Meteo 数据版权归原机构所有
