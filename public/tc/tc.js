/* ============================================================
   BAMC · EC ENS Tropical Cyclone
   Vanilla SVG map + ensemble viewer
   ============================================================ */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const DATA_BASE = "/tc-data/";
  const MAP = {
    W: 1000,
    H: 660,
    left: 58,
    right: 26,
    top: 26,
    bottom: 58,
    west: 100,
    east: 140,
    south: 10,
    north: 35,
  };
  MAP.width = MAP.W - MAP.left - MAP.right;
  MAP.height = MAP.H - MAP.top - MAP.bottom;

  const PRESSURE_BINS = [
    { hi: 935, label: "≤ 935", color: "#241a4e", light: false, cat: "≤935" },
    { hi: 955, label: "936–955", color: "#2c3d88", light: false, cat: "936–955" },
    { hi: 975, label: "956–975", color: "#176b9c", light: false, cat: "956–975" },
    { hi: 990, label: "976–990", color: "#2b9b94", light: false, cat: "976–990" },
    { hi: 1000, label: "991–1000", color: "#8bc06a", light: true, cat: "991–1000" },
    { hi: Infinity, label: "> 1000", color: "#e3d96e", light: true, cat: ">1000" },
  ];

  const WIND_BINS = [
    { lo: 113, label: "≥ 113", color: "#241a4e", light: false, cat: "Cat 4–5" },
    { lo: 96, label: "96–112", color: "#2c3d88", light: false, cat: "Cat 3" },
    { lo: 83, label: "83–95", color: "#176b9c", light: false, cat: "Cat 2" },
    { lo: 64, label: "64–82", color: "#2b9b94", light: false, cat: "Cat 1" },
    { lo: 34, label: "34–63", color: "#8bc06a", light: true, cat: "TS" },
    { lo: -Infinity, label: "< 34", color: "#e3d96e", light: true, cat: "TD" },
  ];

  const CITIES = [
    { name: "Guangzhou", lon: 113.26, lat: 23.13, dx: 5, dy: -5 },
    { name: "Hong Kong", lon: 114.17, lat: 22.32, dx: 5, dy: 8 },
    { name: "Haikou", lon: 110.2, lat: 20.04, dx: 5, dy: 8 },
    { name: "Hanoi", lon: 105.85, lat: 21.03, dx: 5, dy: -5 },
    { name: "Taipei", lon: 121.56, lat: 25.04, dx: 5, dy: -5 },
    { name: "Manila", lon: 120.98, lat: 14.6, dx: 5, dy: 6 },
    { name: "Shanghai", lon: 121.47, lat: 31.23, dx: 5, dy: -5 },
  ];

  const COUNTRY_LABELS = [
    { text: "CHINA", lon: 111.8, lat: 32.2 },
    { text: "VIETNAM", lon: 106.4, lat: 15.4 },
    { text: "PHILIPPINES", lon: 122.2, lat: 11.8 },
    { text: "SOUTH CHINA SEA", lon: 114.3, lat: 15.8 },
    { text: "PHILIPPINE SEA", lon: 132.3, lat: 21.4 },
  ];

  const $ = (id) => document.getElementById(id);

  const MODEL_META = {
    ifs: {
      hero: "ECMWF Ensemble",
      label: "ECMWF IFS ENS",
      short: "IFS ENS",
      source: "ECMWF Open Data · TC track BUFR",
    },
    aifs: {
      hero: "ECMWF AIFS",
      label: "ECMWF AIFS ENS",
      short: "AIFS",
      source: "ECMWF Open Data · AIFS ENS BUFR",
    },
    gefs: {
      hero: "NOAA GEFS",
      label: "NOAA GEFS (GFS Ensemble)",
      short: "GEFS",
      source: "NOAA NOMADS · ens_tracker GEFS",
    },
  };
  const els = {
    clock: $("clock"),
    connStatus: $("connStatus"),
    connText: $("connText"),
    heroTitle: $("heroTitle"),
    modelSelect: $("modelSelect"),
    issueDate: $("issueDate"),
    issueNote: $("issueNote"),
    metaStorm: $("metaStorm"),
    metaInit: $("metaInit"),
    metaLead: $("metaLead"),
    metaJtwc: $("metaJtwc"),
    metaSource: $("metaSource"),
    deckModelText: $("deckModelText"),
    mapModelBadge: $("mapModelBadge"),
    mapModelText: $("mapModelText"),
    mapFooterMembers: $("mapFooterMembers"),
    stormTitle: $("stormTitle"),
    stormId: $("stormId"),
    chartSub: $("chartSub"),
    memberPillText: $("memberPillText"),
    leadBig: $("leadBig"),
    chartCard: $("chartCard"),
    mapWrap: $("mapWrap"),
    mapScroll: document.querySelector(".map-scroll"),
    mapSvg: $("mapSvg"),
    graticule: $("graticule"),
    landLayer: $("landLayer"),
    borderLayer: $("borderLayer"),
    cityLayer: $("cityLayer"),
    trackLayer: $("trackLayer"),
    pointLayer: $("pointLayer"),
    annotationLayer: $("annotationLayer"),
    jtwcLayer: $("jtwcLayer"),
    axisLayer: $("axisLayer"),
    plotClipRect: $("plotClipRect"),
    loading: $("loading"),
    loadingNote: $("loadingNote"),
    chartError: $("chartError"),
    chartErrorText: $("chartErrorText"),
    tooltip: $("tooltip"),
    mapRunBadge: $("mapRunBadge"),
    mapHint: $("mapHint"),
    mapInit: $("mapInit"),
    mapLeadRange: $("mapLeadRange"),
    jtwcBadge: $("jtwcBadge"),
    metaJtwc: $("metaJtwc"),
    jtwcList: $("jtwcList"),
    jtwcUpdated: $("jtwcUpdated"),
    btnJtwcRefresh: $("btnJtwcRefresh"),
    legendTitle: $("legendTitle"),
    legendScale: $("legendScale"),
    legendCaption: $("legendCaption"),
    peakMslp: $("peakMslp"),
    peakWind: $("peakWind"),
    leadNow: $("leadNow"),
    validNow: $("validNow"),
    leadSlider: $("leadSlider"),
    timeTicks: $("timeTicks"),
    frameIndex: $("frameIndex"),
    stepText: $("stepText"),
    btnFirst: $("btnFirst"),
    btnPrev: $("btnPrev"),
    btnPlay: $("btnPlay"),
    playIcon: $("playIcon"),
    btnNext: $("btnNext"),
    btnLast: $("btnLast"),
    btnFullscreen: $("btnFullscreen"),
    btnDownload: $("btnDownload"),
    btnRetry: $("btnRetry"),
    snapshotLabel: $("snapshotLabel"),
    mslpBig: $("mslpBig"),
    mslpSub: $("mslpSub"),
    windBig: $("windBig"),
    spreadBig: $("spreadBig"),
    tsCount: $("tsCount"),
    pathSpread: $("pathSpread"),
    selectedTag: $("selectedTag"),
    memberDetail: $("memberDetail"),
    memberTitle: $("memberTitle"),
    memberLead: $("memberLead"),
    memberMslp: $("memberMslp"),
    memberWind: $("memberWind"),
    memberPos: $("memberPos"),
    memberMin: $("memberMin"),
    memberMax: $("memberMax"),
    memberEnd: $("memberEnd"),
    btnUnpin: $("btnUnpin"),
    intensityChart: $("intensityChart"),
    intensityNote: $("intensityNote"),
    runSelect: $("runSelect"),
    stormSelect: $("stormSelect"),
    colorMode: $("colorMode"),
    toggleMembers: $("toggleMembers"),
    toggleMean: $("toggleMean"),
    toggleLabels: $("toggleLabels"),
    toggleCities: $("toggleCities"),
    quantileBody: $("quantileBody"),
    footerInit: $("footerInit"),
    toast: $("toast"),
  };

  const state = {
    index: null,
    model: "ifs",
    externalDates: [],
    runEntry: null,
    run: null,
    storm: null,
    geo: null,
    baseRendered: false,
    leads: [],
    leadIndex: 0,
    colorMode: "mslp",
    showMembers: true,
    showMean: true,
    showLabels: true,
    showCities: true,
    hoverMember: null,
    selectedMember: null,
    playing: false,
    timer: null,
    loadSeq: 0,
    pointEls: [],
    leadStats: [],
    statsByLead: new Map(),
    loadingTimer: null,
    toastTimer: null,
    resizeTimer: null,
    jtwc: null,
    jtwcLoading: false,
    jtwcTimer: null,
    dataTimer: null,
    jtwcError: null,
    layers: {},
  };

  const pad2 = (n) => String(n).padStart(2, "0");
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }

  function fmtNumber(n, digits) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return Number(n).toFixed(digits == null ? 0 : digits);
  }

  function svgEl(tag, attrs, parent) {
    const node = document.createElementNS(NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach((key) => {
        if (attrs[key] != null) node.setAttribute(key, attrs[key]);
      });
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function svgText(text, attrs, parent) {
    const node = svgEl("text", attrs, parent);
    node.textContent = text;
    return node;
  }

  function lonToX(lon) {
    return MAP.left + ((Number(lon) - MAP.west) / (MAP.east - MAP.west)) * MAP.width;
  }
  function latToY(lat) {
    return MAP.top + ((MAP.north - Number(lat)) / (MAP.north - MAP.south)) * MAP.height;
  }

  function pressureBin(p) {
    if (p == null) return { color: "#8a8d7d", label: "—", light: true };
    for (const bin of PRESSURE_BINS) {
      if (p <= bin.hi) return bin;
    }
    return PRESSURE_BINS[PRESSURE_BINS.length - 1];
  }

  function windBin(w) {
    if (w == null) return { color: "#8a8d7d", label: "—", light: true };
    for (const bin of WIND_BINS) {
      if (w >= bin.lo) return bin;
    }
    return WIND_BINS[WIND_BINS.length - 1];
  }

  function pointBin(point) {
    return state.colorMode === "wind" ? windBin(point.wind) : pressureBin(point.mslp);
  }

  function haversine(a, b) {
    const R = 6371;
    const toRad = Math.PI / 180;
    const dLat = (b.lat - a.lat) * toRad;
    const dLon = (b.lon - a.lon) * toRad;
    const la1 = a.lat * toRad;
    const la2 = b.lat * toRad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  function quantile(sorted, q) {
    if (!sorted.length) return null;
    if (sorted.length === 1) return sorted[0];
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }

  function median(values) {
    return quantile(values.slice().sort((a, b) => a - b), 0.5);
  }

  function parseDate(value) {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function formatLocal(iso, leadHours) {
    const base = parseDate(iso);
    if (!base) return "—";
    const d = new Date(base.getTime() + Number(leadHours || 0) * 3600000);
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);
    const map = {};
    parts.forEach((p) => { map[p.type] = p.value; });
    return `${map.month}/${map.day} ${map.hour}:${map.minute} CST`;
  }

  function updateClock() {
    const now = new Date();
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).formatToParts(now);
    const map = {};
    parts.forEach((p) => { map[p.type] = p.value; });
    els.clock.textContent = `${map.month}/${map.day} ${map.hour}:${map.minute}:${map.second} CST`;
    els.clock.title = "北京时间";
  }

  function toast(text) {
    els.toast.textContent = text;
    els.toast.classList.add("is-show");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => els.toast.classList.remove("is-show"), 2400);
  }

  function setStatus(text, kind) {
    els.connText.textContent = text;
    els.connStatus.className = "status " + (kind || "");
  }

  function setLoading(show, note) {
    clearTimeout(state.loadingTimer);
    if (show) {
      if (note) els.loadingNote.textContent = note;
      els.loading.hidden = false;
      els.loading.classList.remove("is-gone");
    } else {
      els.loading.classList.add("is-gone");
      state.loadingTimer = setTimeout(() => { els.loading.hidden = true; }, 320);
    }
  }

  function showError(message) {
    els.chartError.hidden = false;
    els.chartErrorText.textContent = message || "请稍后刷新重试。";
    setLoading(false);
    setStatus("加载失败", "is-error");
  }

  function hideError() {
    els.chartError.hidden = true;
  }

  async function fetchJSON(url) {
    const response = await fetch(url, { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        detail = body && body.error ? String(body.error) : "";
      } catch (error) {
        detail = "";
      }
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  /* ---------------- map base ---------------- */

  function drawGraticule() {
    const g = els.graticule;
    g.textContent = "";
    els.plotClipRect.setAttribute("x", MAP.left);
    els.plotClipRect.setAttribute("y", MAP.top);
    els.plotClipRect.setAttribute("width", MAP.width);
    els.plotClipRect.setAttribute("height", MAP.height);

    for (let lon = MAP.west; lon <= MAP.east; lon += 5) {
      const x = lonToX(lon);
      svgEl("line", {
        x1: x, y1: MAP.top, x2: x, y2: MAP.top + MAP.height,
        class: "graticule-line" + (lon % 10 === 0 ? " major" : ""),
      }, g);
    }
    for (let lat = MAP.south; lat <= MAP.north; lat += 5) {
      const y = latToY(lat);
      svgEl("line", {
        x1: MAP.left, y1: y, x2: MAP.left + MAP.width, y2: y,
        class: "graticule-line" + (lat % 10 === 0 ? " major" : ""),
      }, g);
    }

    const tickPath = [];
    for (let lon = MAP.west; lon <= MAP.east; lon += 1) {
      const x = lonToX(lon);
      const len = lon % 5 === 0 ? 5 : 2.5;
      tickPath.push(`M${x.toFixed(1)},${MAP.top + MAP.height}L${x.toFixed(1)},${MAP.top + MAP.height + len}`);
    }
    for (let lat = MAP.south; lat <= MAP.north; lat += 1) {
      const y = latToY(lat);
      const len = lat % 5 === 0 ? 5 : 2.5;
      tickPath.push(`M${MAP.left},${y.toFixed(1)}L${MAP.left - len},${y.toFixed(1)}`);
    }
    svgEl("path", { d: tickPath.join(""), class: "graticule-tick" }, g);

    for (let lon = MAP.west; lon <= MAP.east; lon += 5) {
      svgText(`${lon}°E`, {
        x: lonToX(lon), y: MAP.top + MAP.height + 18,
        class: "graticule-label lon",
      }, g);
    }
    for (let lat = MAP.south; lat <= MAP.north; lat += 5) {
      svgText(`${lat}°N`, {
        x: MAP.left - 9, y: latToY(lat) + 3.3,
        class: "graticule-label lat",
      }, g);
    }
    svgEl("rect", {
      x: MAP.left, y: MAP.top, width: MAP.width, height: MAP.height,
      class: "graticule-axis", fill: "none",
    }, g);
  }

  function drawLand() {
    els.landLayer.textContent = "";
    if (!state.geo || !Array.isArray(state.geo.land)) return;
    const d = [];
    state.geo.land.forEach((ring) => {
      if (!ring || ring.length < 4) return;
      d.push("M" + ring.map(([lon, lat], i) => `${i ? "L" : ""}${lonToX(lon).toFixed(1)},${latToY(lat).toFixed(1)}`).join("") + "Z");
    });
    if (d.length) svgEl("path", { d: d.join(""), class: "land-shape", "fill-rule": "evenodd" }, els.landLayer);
  }

  function drawBorders() {
    els.borderLayer.textContent = "";
    if (!state.geo || !Array.isArray(state.geo.borders)) return;
    const d = [];
    state.geo.borders.forEach((line) => {
      if (!line || line.length < 2) return;
      d.push("M" + line.map(([lon, lat], i) => `${i ? "L" : ""}${lonToX(lon).toFixed(1)},${latToY(lat).toFixed(1)}`).join(""));
    });
    if (d.length) svgEl("path", { d: d.join(""), class: "border-line" }, els.borderLayer);
  }

  function drawCities() {
    els.cityLayer.textContent = "";
    COUNTRY_LABELS.forEach((item) => {
      svgText(item.text, { x: lonToX(item.lon), y: latToY(item.lat), class: "country-label" }, els.cityLayer);
    });
    CITIES.forEach((city) => {
      const x = lonToX(city.lon);
      const y = latToY(city.lat);
      svgEl("circle", { cx: x, cy: y, r: 1.7, class: "city-dot" }, els.cityLayer);
      let dx = city.dx;
      let anchor = "start";
      if (x > MAP.left + MAP.width - 80) { dx = -5; anchor = "end"; }
      const label = svgText(city.name, {
        x: x + dx, y: y + city.dy, class: "city-label",
        "text-anchor": anchor,
      }, els.cityLayer);
      label.setAttribute("aria-hidden", "true");
    });
  }

  function drawBase() {
    if (state.baseRendered) return;
    drawGraticule();
    drawLand();
    drawBorders();
    drawCities();
    state.baseRendered = true;
    els.cityLayer.style.display = state.showCities ? "" : "none";
  }

  /* ---------------- tracks ---------------- */

  function trackPath(points) {
    return points.map((p, i) => `${i ? "L" : "M"}${lonToX(p.lon).toFixed(1)},${latToY(p.lat).toFixed(1)}`).join("");
  }

  function computeLeadStats() {
    const stats = state.leads.map((lead) => {
      const points = [];
      state.storm.members.forEach((member) => {
        const p = member.byLead.get(lead);
        if (p) points.push({ member, point: p });
      });
      const pressures = points.map((x) => x.point.mslp).filter((v) => v != null).sort((a, b) => a - b);
      const winds = points.map((x) => x.point.wind).filter((v) => v != null).sort((a, b) => a - b);
      let center = null;
      let spreadKm = 0;
      if (points.length) {
        center = {
          lat: points.reduce((sum, x) => sum + x.point.lat, 0) / points.length,
          lon: points.reduce((sum, x) => sum + x.point.lon, 0) / points.length,
        };
        spreadKm = points.reduce((max, x) => Math.max(max, haversine(center, { lat: x.point.lat, lon: x.point.lon })), 0);
      }
      return {
        lead,
        count: points.length,
        points,
        center,
        spreadKm,
        minMslp: pressures.length ? pressures[0] : null,
        p10: quantile(pressures, 0.1),
        medianMslp: quantile(pressures, 0.5),
        p90: quantile(pressures, 0.9),
        maxWind: winds.length ? winds[winds.length - 1] : null,
        medianWind: quantile(winds, 0.5),
        tsCount: winds.filter((w) => w >= 34).length,
      };
    });
    state.leadStats = stats;
    state.statsByLead = new Map(stats.map((s) => [s.lead, s]));
  }

  function meanTrackData() {
    return state.leadStats
      .filter((s) => s.center)
      .map((s) => ({ lead: s.lead, lat: s.center.lat, lon: s.center.lon }));
  }

  function renderTracks() {
    els.trackLayer.textContent = "";
    els.pointLayer.textContent = "";
    els.annotationLayer.textContent = "";
    state.pointEls = [];
    if (!state.storm) return;

    const memberGroup = svgEl("g", { id: "memberTracks" }, els.trackLayer);
    const meanGroup = svgEl("g", { id: "meanTracks" }, els.trackLayer);
    const labelGroup = svgEl("g", { id: "leadLabels" }, els.trackLayer);
    const currentGroup = svgEl("g", { id: "currentLead" }, els.annotationLayer);
    const initGroup = svgEl("g", { id: "initMarker" }, els.annotationLayer);
    const calloutGroup = svgEl("g", { id: "stormCallout" }, els.annotationLayer);

    state.layers = { memberGroup, meanGroup, labelGroup, currentGroup, initGroup, calloutGroup };

    state.storm.members.forEach((member) => {
      if (!member.track.length) return;
      const path = svgEl("path", {
        d: trackPath(member.track),
        class: "member-track",
        "data-member": member.member,
      }, memberGroup);
      member.pathEl = path;

      member.track.forEach((point) => {
        const color = pointBin(point).color;
        const cx = lonToX(point.lon);
        const cy = latToY(point.lat);
        const circle = svgEl("circle", {
          cx, cy, r: 2.75,
          fill: color,
          class: "ens-dot",
          "data-member": member.member,
          "data-lead": point.lead,
        }, els.pointLayer);
        state.pointEls.push({ x: cx, y: cy, member, point, el: circle });
      });
    });

    const mean = meanTrackData();
    if (mean.length) {
      const d = trackPath(mean);
      svgEl("path", { d, class: "mean-track-halo" }, meanGroup);
      svgEl("path", { d, class: "mean-track" }, meanGroup);
    }

    if (state.showMean) {
      meanGroup.style.display = "";
    } else {
      meanGroup.style.display = "none";
    }
    memberGroup.style.display = state.showMembers ? "" : "none";
    labelGroup.style.display = state.showLabels ? "" : "none";

    // 24-hour mean-position tags
    [24, 48, 72, 96, 120, 144, 168].forEach((lead) => {
      const s = state.statsByLead.get(lead);
      if (!s || !s.center) return;
      const x = lonToX(s.center.lon);
      const y = latToY(s.center.lat);
      const text = `+${lead}h`;
      const w = 28;
      const bx = clamp(x + 6, MAP.left + 3, MAP.left + MAP.width - w - 3);
      const by = clamp(y - 16, MAP.top + 4, MAP.top + MAP.height - 20);
      const tag = svgEl("g", { class: "lead-tag" }, labelGroup);
      svgEl("rect", {
        x: bx, y: by, width: w, height: 14, rx: 2,
        class: "lead-tag-bg",
      }, tag);
      svgText(text, { x: bx + w / 2, y: by + 9.8, class: "lead-tag-text" }, tag);
    });

    // initial-point marker and storm callout
    const initStat = state.statsByLead.get(0) || state.leadStats.find((s) => s.center);
    if (initStat && initStat.center) {
      const x = lonToX(initStat.center.lon);
      const y = latToY(initStat.center.lat);
      svgEl("circle", { cx: x, cy: y, r: 5, class: "init-ring" }, initGroup);
      svgEl("path", {
        d: `M${x - 7},${y}H${x + 7}M${x},${y - 7}V${y + 7}`,
        class: "init-cross",
      }, initGroup);

      const bx = x - 155;
      const by = y + 26;
      const bw = 128;
      const bh = 40;
      const lineTargetX = bx + bw;
      const lineTargetY = by + bh / 2;
      svgEl("path", {
        d: `M${lineTargetX},${lineTargetY}L${x - 5},${y + 4}`,
        class: "storm-callout-line",
      }, calloutGroup);
      svgEl("rect", {
        x: bx, y: by, width: bw, height: bh,
        class: "storm-callout-box",
      }, calloutGroup);
      svgText(state.storm.name, { x: bx + 8, y: by + 16.5, class: "storm-callout-title" }, calloutGroup);
      const stormId = state.storm.id;
      const initLat = initStat.center.lat.toFixed(1);
      const initLon = initStat.center.lon.toFixed(1);
      svgText(`${stormId} · ${initLat}°N ${initLon}°E`, {
        x: bx + 8, y: by + 30.5, class: "storm-callout-sub",
      }, calloutGroup);
    }

    applyTrackClasses();
    renderCurrentLead();
  }

  function applyTrackClasses() {
    if (!state.storm) return;
    const hover = state.hoverMember;
    const selected = state.selectedMember;
    state.storm.members.forEach((member) => {
      const path = member.pathEl;
      if (!path) return;
      let cls = "member-track";
      if (hover != null && member.member !== hover) cls += " is-dim";
      if (selected != null && member.member !== selected) cls += " is-dim";
      if (hover != null && member.member === hover) cls += " is-hover";
      if (selected != null && member.member === selected) cls += " is-selected";
      path.setAttribute("class", cls);
    });
    state.pointEls.forEach((entry) => {
      let cls = "ens-dot";
      if (hover != null && entry.member.member !== hover) cls += " is-dim";
      if (selected != null && entry.member.member !== selected) cls += " is-dim";
      entry.el.setAttribute("class", cls);
    });

    if (selected != null) {
      const member = state.storm.members.find((m) => m.member === selected);
      if (member && member.pathEl) member.pathEl.parentNode.appendChild(member.pathEl);
    }
    if (hover != null && hover !== selected) {
      const member = state.storm.members.find((m) => m.member === hover);
      if (member && member.pathEl) member.pathEl.parentNode.appendChild(member.pathEl);
    }
    applyIntensitySelection();
  }

  function applyIntensitySelection() {
    const hover = state.hoverMember;
    const selected = state.selectedMember;
    Array.from(els.intensityChart.querySelectorAll(".ichart-line")).forEach((line) => {
      const member = Number(line.getAttribute("data-member"));
      line.classList.toggle("is-hover", hover != null && member === hover);
      line.classList.toggle("is-selected", selected != null && member === selected && !(hover != null && member === hover));
    });
  }

  function renderCurrentLead() {
    if (!state.layers.currentGroup) return;
    const group = state.layers.currentGroup;
    group.textContent = "";
    const lead = state.leads[state.leadIndex];
    if (lead == null) return;
    const seen = new Set();
    state.storm.members.forEach((member) => {
      const point = member.byLead.get(lead);
      if (!point) return;
      const key = `${point.lat},${point.lon}`;
      if (seen.has(key)) return;
      seen.add(key);
      const x = lonToX(point.lon);
      const y = latToY(point.lat);
      svgEl("circle", { cx: x, cy: y, r: 6.1, class: "current-halo" }, group);
      svgEl("circle", { cx: x, cy: y, r: 4.35, class: "current-dot" }, group);
    });
  }

  /* ---------------- JTWC live systems ---------------- */

  function jtwcSystems() {
    const systems = state.jtwc && Array.isArray(state.jtwc.systems) ? state.jtwc.systems : [];
    return systems.filter((system) => {
      const lat = Number(system.lat);
      const lon = Number(system.lon);
      return Number.isFinite(lat) && Number.isFinite(lon)
        && lat >= 10 && lat <= 35 && lon >= 100 && lon <= 140;
    });
  }

  function findEcStorm(name) {
    if (!state.run || !state.run.storms) return null;
    const wanted = String(name || "").trim().toUpperCase();
    return state.run.storms.find((storm) => String(storm.name || "").trim().toUpperCase() === wanted) || null;
  }

  function formatJtwcTime(value) {
    if (!value) return "—";
    const raw = String(value);
    const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : raw + "Z");
    if (Number.isNaN(date.getTime())) return raw;
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(date);
    const map = {};
    parts.forEach((part) => { map[part.type] = part.value; });
    return `${map.month}/${map.day} ${map.hour}:${map.minute} CST`;
  }

  function focusJtwcSystem(system) {
    const storm = findEcStorm(system.name);
    if (storm) {
      if (!state.storm || state.storm.id !== storm.id) {
        selectStorm(storm.id);
      }
      toast(`JTWC ${system.name} · 已匹配 ${state.run && state.run.run ? state.run.run.model : "系集"} ${storm.id}`);
      return;
    }
    toast(`JTWC ${system.name} 当前没有可用的系集路径，图上保留实时位置。`);
  }

  function renderJtwcMarkers() {
    if (!els.jtwcLayer) return;
    els.jtwcLayer.textContent = "";
    const systems = jtwcSystems();
    systems.forEach((system, index) => {
      const x = lonToX(Number(system.lon));
      const y = latToY(Number(system.lat));
      const matched = Boolean(findEcStorm(system.name));
      const node = svgEl("g", {
        class: "jtwc-node" + (matched ? " is-matched" : ""),
        "data-jtwc-id": system.id,
        role: "button",
        tabindex: "0",
        "aria-label": `JTWC ${system.name}，${system.lat}°N ${system.lon}°E`,
      }, els.jtwcLayer);
      const title = svgEl("title", {}, node);
      title.textContent = `JTWC ${system.name} · ${system.wind_kt || "—"} kt · ${system.lat}°N ${system.lon}°E`;

      svgEl("circle", { cx: x, cy: y, r: 10.5, class: "jtwc-marker-halo" }, node);
      svgEl("circle", { cx: x, cy: y, r: 7.3, class: "jtwc-marker-ring" }, node);
      svgEl("path", {
        d: `M${x},${y - 5.2}L${x + 5.2},${y}L${x},${y + 5.2}L${x - 5.2},${y}Z`,
        class: "jtwc-marker",
      }, node);

      const labelW = 144;
      const labelH = 31;
      let bx = x + 14 + (index % 2) * 4;
      let by = y - 25 - (index % 3) * 5;
      if (bx + labelW > MAP.left + MAP.width - 3) bx = x - labelW - 14;
      if (by < MAP.top + 3) by = y + 13;
      if (by + labelH > MAP.top + MAP.height - 3) by = y - labelH - 12;
      const lineStartX = bx > x ? bx : bx + labelW;
      const lineStartY = by + labelH / 2;

      svgEl("path", {
        d: `M${x + (bx > x ? 6 : -6)},${y}L${lineStartX},${lineStartY}`,
        class: "jtwc-leader",
      }, node);
      svgEl("rect", {
        x: bx, y: by, width: labelW, height: labelH, rx: 1.5,
        class: "jtwc-label-bg",
      }, node);
      svgText(`JTWC ${system.name}`, {
        x: bx + 8, y: by + 12.5, class: "jtwc-label-name",
      }, node);
      const windText = system.wind_kt == null ? "强度 —" : `${system.wind_kt} kt`;
      svgText(`${windText} · ${Number(system.lat).toFixed(1)}N ${Number(system.lon).toFixed(1)}E`, {
        x: bx + 8, y: by + 23.5, class: "jtwc-label-sub",
      }, node);

      node.addEventListener("click", (event) => {
        event.stopPropagation();
        focusJtwcSystem(system);
      });
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          focusJtwcSystem(system);
        }
      });
    });
  }

  function renderJtwcPanel() {
    if (!els.jtwcList) return;
    const systems = jtwcSystems();
    const updated = state.jtwc && state.jtwc.updated ? formatJtwcTime(state.jtwc.updated) : "";
    els.jtwcUpdated.textContent = state.jtwcError && !systems.length
      ? "JTWC 源暂时不可用"
      : updated ? `更新 ${updated} · GDACS/JTWC` : "等待同步…";
    els.metaJtwc.textContent = systems.length
      ? `${systems.length} 个 · ${updated || "刚刚"}`
      : state.jtwcError ? "源暂不可用" : "范围内 0 个";
    els.jtwcBadge.innerHTML = `<span class="jtwc-dot"></span> JTWC · ${systems.length}`;

    if (!systems.length) {
      els.jtwcList.innerHTML = `<div class="jtwc-empty"><b>当前范围内没有 JTWC 活跃系统。</b><br>只显示当前中心位于 100–140°E、10–35°N 的系统；系统移出框后会从这里移除。</div>`;
      renderJtwcMarkers();
      return;
    }

    els.jtwcList.innerHTML = systems.map((system) => {
      const storm = findEcStorm(system.name);
      const alert = String(system.alert || "Green");
      const alertClass = alert.toLowerCase();
      return `<button type="button" class="jtwc-item${storm ? " is-matched" : ""}" data-jtwc-id="${esc(system.id)}">
        <div class="jtwc-item-top">
          <span class="jtwc-item-name">${esc(system.name)}<small>JTWC</small></span>
          <span class="jtwc-item-alert ${esc(alertClass)}">${esc(alert.toUpperCase())}</span>
        </div>
        <div class="jtwc-item-main"><b>${Number(system.lat).toFixed(1)}°N ${Number(system.lon).toFixed(1)}°E</b><span>${system.wind_kt == null ? "强度 —" : system.wind_kt + " kt"}</span></div>
        <div class="jtwc-item-foot">${storm ? `系集已匹配 · ${esc(storm.id)}` : "仅 JTWC 实时位置"} · ${esc(formatJtwcTime(system.updated))}</div>
      </button>`;
    }).join("");
    renderJtwcMarkers();
  }

  async function loadJtwc(force) {
    if (state.jtwcLoading) return;
    state.jtwcLoading = true;
    els.btnJtwcRefresh.classList.add("is-busy");
    try {
      const response = await fetch(`/api/jtwc?ts=${Date.now()}${force ? "&force=1" : ""}`, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
      state.jtwc = data;
      state.jtwcError = null;
      renderJtwcPanel();
    } catch (error) {
      console.warn("JTWC unavailable", error);
      state.jtwcError = error.message || "JTWC unavailable";
      if (!state.jtwc) state.jtwc = { systems: [], updated: "" };
      renderJtwcPanel();
    } finally {
      state.jtwcLoading = false;
      els.btnJtwcRefresh.classList.remove("is-busy");
    }
  }

  /* ---------------- legend ---------------- */

  function renderLegend() {
    const bins = state.colorMode === "wind" ? WIND_BINS : PRESSURE_BINS;
    els.legendTitle.textContent = state.colorMode === "wind" ? "最大风速" : "最低气压";
    els.legendCaption.textContent = state.colorMode === "wind" ? "max 10-m wind (kt)" : "minimum MSLP (hPa)";
    els.legendScale.innerHTML = bins.map((bin) => {
      return `<div class="legend-bin${bin.light ? " light" : ""}">
        <div class="legend-swatch" style="background:${bin.color}"><b>${esc(bin.label)}</b></div>
      </div>`;
    }).join("");
  }

  /* ---------------- lead / stats ---------------- */

  function activeAt(lead) {
    const exact = state.statsByLead.get(lead);
    return exact || { lead, count: 0, points: [], center: null, spreadKm: 0, minMslp: null, p10: null, medianMslp: null, p90: null, maxWind: null, medianWind: null, tsCount: 0 };
  }

  function memberPointAt(member, lead) {
    let point = member.byLead.get(lead);
    if (point) return point;
    let best = null;
    member.track.forEach((p) => {
      if (p.lead <= lead && (!best || p.lead > best.lead)) best = p;
    });
    return best;
  }

  function updateStats() {
    const lead = state.leads[state.leadIndex];
    const stat = activeAt(lead);
    const active = stat.count;
    els.snapshotLabel.textContent = `+${lead} H · 系集最低`;
    els.mslpBig.textContent = stat.minMslp == null ? "—" : fmtNumber(stat.minMslp, 0);
    els.mslpSub.textContent = active
      ? `最低海平面气压 · ${active} / ${state.storm.member_count} 位成员活跃`
      : "该时效无活跃成员";
    els.windBig.innerHTML = stat.maxWind == null ? "—" : `${fmtNumber(stat.maxWind, 0)}<small>kt</small>`;
    els.spreadBig.innerHTML = stat.p10 == null ? "—" : `${fmtNumber(stat.p90 - stat.p10, 0)}<small>hPa</small>`;
    els.tsCount.textContent = active ? `${stat.tsCount} / ${active}` : "—";
    els.pathSpread.innerHTML = active ? `±${fmtNumber(stat.spreadKm, 0)}<small>km</small>` : "—";
    els.leadBig.innerHTML = `+${lead} <small>h</small>`;
    els.leadNow.textContent = `+${lead} h`;
    els.validNow.textContent = formatLocal(state.run.run.iso, lead);
    els.leadSlider.value = String(state.leadIndex);
    const pct = state.leads.length > 1 ? (state.leadIndex / (state.leads.length - 1)) * 100 : 0;
    els.leadSlider.style.setProperty("--fill", `${pct}%`);
    els.frameIndex.textContent = `${state.leadIndex + 1} / ${state.leads.length}`;
    const diffs = [];
    for (let i = 1; i < state.leads.length; i += 1) diffs.push(state.leads[i] - state.leads[i - 1]);
    const step = diffs.length ? Math.round(median(diffs)) : 6;
    els.stepText.textContent = `${step} h`;
    updateMemberDetail();
    updateTableSelection();
  }

  function updateMemberDetail() {
    const hoverId = state.hoverMember;
    const selectedId = state.selectedMember;
    const memberId = hoverId != null ? hoverId : selectedId;
    if (memberId == null || !state.storm) {
      els.memberDetail.hidden = true;
      els.selectedTag.textContent = "全部成员";
      return;
    }
    const member = state.storm.members.find((m) => m.member === memberId);
    if (!member) {
      els.memberDetail.hidden = true;
      return;
    }
    const lead = state.leads[state.leadIndex];
    const point = memberPointAt(member, lead);
    if (!point) {
      els.memberDetail.hidden = true;
      return;
    }
    els.memberDetail.hidden = false;
    els.selectedTag.textContent = `成员 ${pad2(member.member)}`;
    els.memberTitle.textContent = `成员 ${pad2(member.member)}${member.control ? " · 控制" : ""}`;
    els.memberLead.textContent = `+${point.lead} h`;
    els.memberMslp.textContent = point.mslp == null ? "—" : `${fmtNumber(point.mslp, 1)} hPa`;
    els.memberWind.textContent = point.wind == null ? "—" : `${fmtNumber(point.wind, 0)} kt`;
    els.memberPos.textContent = `${point.lat.toFixed(1)}°N ${point.lon.toFixed(1)}°E`;
    els.memberMin.textContent = member.min_mslp == null ? "—" : `${fmtNumber(member.min_mslp, 1)} hPa`;
    els.memberMax.textContent = member.max_wind == null ? "—" : `${fmtNumber(member.max_wind, 0)} kt`;
    els.memberEnd.textContent = `+${member.last.lead} h`;
    els.btnUnpin.style.visibility = selectedId === memberId ? "visible" : "hidden";
  }

  function centerMapOnStorm() {
    if (!els.mapScroll || !els.mapWrap || window.innerWidth > 760) return;
    const stat = state.statsByLead.get(state.leads[state.leadIndex]);
    const lon = stat && stat.center ? stat.center.lon : 126;
    const scale = els.mapWrap.clientWidth / MAP.W;
    const target = lonToX(lon) * scale - els.mapScroll.clientWidth / 2;
    const max = Math.max(0, els.mapScroll.scrollWidth - els.mapScroll.clientWidth);
    els.mapScroll.scrollLeft = clamp(target, 0, max);
  }

  function updateLeadUI() {
    updateStats();
    renderCurrentLead();
    renderIntensity();
    updateTableSelection();
    if (window.innerWidth <= 760) requestAnimationFrame(centerMapOnStorm);
  }

  function setLead(index, options) {
    const opts = options || {};
    if (!state.leads.length) return;
    const next = clamp(Number(index) || 0, 0, state.leads.length - 1);
    if (opts.pause) pause();
    state.leadIndex = next;
    hideTooltip();
    state.hoverMember = null;
    applyTrackClasses();
    updateLeadUI();
    updateUrl();
  }

  function updateTimeTicks() {
    const max = state.leads.length ? state.leads[state.leads.length - 1] : 0;
    const points = [];
    [0, 24, 48, 72, 96, 120, 144, 168, 180].forEach((lead) => {
      if (lead <= max) points.push(lead);
    });
    if (points[points.length - 1] !== max) points.push(max);
    els.timeTicks.innerHTML = points.map((lead) => `<span>+${lead}h</span>`).join("");
  }

  /* ---------------- intensity chart ---------------- */

  function renderIntensity() {
    const svg = els.intensityChart;
    svg.textContent = "";
    if (!state.storm) return;
    const W = 340, H = 218;
    const m = { left: 34, right: 10, top: 12, bottom: 25 };
    const iw = W - m.left - m.right;
    const ih = H - m.top - m.bottom;
    const xMax = Math.max(6, state.storm.lead_max || state.leads[state.leads.length - 1] || 120);
    const yMin = 880;
    const yMax = 1020;
    const x = (lead) => m.left + (lead / xMax) * iw;
    const y = (p) => m.top + ((p - yMin) / (yMax - yMin)) * ih;

    [900, 940, 980, 1020].forEach((value) => {
      svgEl("line", { x1: m.left, y1: y(value), x2: m.left + iw, y2: y(value), class: "ichart-grid" }, svg);
      svgText(String(value), { x: m.left - 5, y: y(value) + 2.6, class: "ichart-text y" }, svg);
    });

    const xTicks = [0, 24, 48, 72, 96, 120, 144, 168, 180].filter((t) => t <= xMax);
    if (xTicks[xTicks.length - 1] !== xMax) xTicks.push(xMax);
    xTicks.forEach((tick) => {
      svgEl("line", { x1: x(tick), y1: m.top, x2: x(tick), y2: m.top + ih, class: "ichart-grid" }, svg);
      svgText(String(tick), { x: x(tick), y: m.top + ih + 14, class: "ichart-text x" }, svg);
    });
    svgEl("line", { x1: m.left, y1: m.top + ih, x2: m.left + iw, y2: m.top + ih, class: "ichart-axis" }, svg);
    svgText("h", { x: m.left + iw - 1, y: m.top + ih + 22, class: "ichart-text x" }, svg);

    const stats = state.leadStats.filter((s) => s.count >= 3 && s.p10 != null && s.p90 != null);
    if (stats.length >= 2) {
      const top = stats.map((s) => `${x(s.lead).toFixed(1)},${y(s.p10).toFixed(1)}`);
      const bottom = stats.slice().reverse().map((s) => `${x(s.lead).toFixed(1)},${y(s.p90).toFixed(1)}`);
      svgEl("path", {
        d: `M${top.join("L")}L${bottom.join("L")}Z`,
        fill: "#1b4938",
        opacity: ".10",
      }, svg);
    }

    state.storm.members.forEach((member) => {
      const pts = member.track.filter((p) => p.mslp != null);
      if (pts.length < 2) return;
      const d = pts.map((p, i) => `${i ? "L" : "M"}${x(p.lead).toFixed(1)},${y(p.mslp).toFixed(1)}`).join("");
      const color = pressureBin(member.min_mslp).color;
      const line = svgEl("path", {
        d, class: "ichart-line", stroke: color, "data-member": member.member,
      }, svg);
      if (state.selectedMember === member.member) line.classList.add("is-selected");
      if (state.hoverMember === member.member) line.classList.add("is-hover");
    });

    const med = state.leadStats.filter((s) => s.medianMslp != null);
    if (med.length >= 2) {
      const d = med.map((s, i) => `${i ? "L" : "M"}${x(s.lead).toFixed(1)},${y(s.medianMslp).toFixed(1)}`).join("");
      svgEl("path", { d, class: "ichart-median" }, svg);
    }

    const current = state.leads[state.leadIndex];
    const currentStat = state.statsByLead.get(current);
    if (current != null) {
      const cx = x(current);
      svgEl("line", { x1: cx, y1: m.top, x2: cx, y2: m.top + ih, class: "ichart-cursor" }, svg);
      if (currentStat && currentStat.medianMslp != null) {
        svgEl("circle", {
          cx, cy: y(currentStat.medianMslp), r: 2.7, class: "ichart-cursor-dot",
        }, svg);
      }
      const labelX = clamp(cx, m.left + 12, m.left + iw - 12);
      svgText(`+${current}h`, {
        x: labelX, y: m.top + 6, class: "ichart-current-label",
      }, svg);
    }

    els.intensityNote.textContent = `${state.storm.member_count} 条成员曲线 · 每 6 小时`;
    applyIntensitySelection();
  }

  /* ---------------- quantile table ---------------- */

  function quantileRows() {
    const max = state.storm ? state.storm.lead_max : (state.leads[state.leads.length - 1] || 0);
    const wanted = [0, 24, 48, 72, 96, 120, 144, 168, 180, max];
    const rows = [];
    wanted.forEach((lead) => {
      if (lead <= max && state.statsByLead.has(lead) && !rows.includes(lead)) rows.push(lead);
    });
    return rows.sort((a, b) => a - b);
  }

  function renderQuantiles() {
    const rows = quantileRows();
    if (!rows.length) {
      els.quantileBody.innerHTML = '<tr><td colspan="8" class="table-empty">暂无数据</td></tr>';
      return;
    }
    els.quantileBody.innerHTML = rows.map((lead) => {
      const s = activeAt(lead);
      const current = lead === state.leads[state.leadIndex] ? ' class="is-current"' : "";
      return `<tr data-lead="${lead}"${current}>
        <td class="lead-cell">+${lead} h</td>
        <td class="${s.count ? "" : "muted-cell"}">${s.count} / ${state.storm.member_count}</td>
        <td>${s.p10 == null ? "—" : fmtNumber(s.p10, 1)}</td>
        <td>${s.medianMslp == null ? "—" : fmtNumber(s.medianMslp, 1)}</td>
        <td>${s.p90 == null ? "—" : fmtNumber(s.p90, 1)}</td>
        <td>${s.medianWind == null ? "—" : fmtNumber(s.medianWind, 0)} kt</td>
        <td>${s.count ? `${s.tsCount} / ${s.count}` : "—"}</td>
        <td>${s.count ? `±${fmtNumber(s.spreadKm, 0)} km` : "—"}</td>
      </tr>`;
    }).join("");
  }

  function updateTableSelection() {
    const lead = state.leads[state.leadIndex];
    Array.from(els.quantileBody.querySelectorAll("tr[data-lead]")).forEach((tr) => {
      tr.classList.toggle("is-current", Number(tr.getAttribute("data-lead")) === lead);
    });
  }

  /* ---------------- meta / selectors ---------------- */

  function updateRunMeta() {
    const run = state.run.run;
    const storm = state.storm;
    const model = MODEL_META[state.model] || MODEL_META.ifs;
    const initLabel = `${run.date} ${run.id.slice(8, 10)} UTC`;
    els.issueDate.textContent = run.display.replace(" UTC", "");
    els.issueNote.textContent = `${run.model} · ${storm.member_count} members`;
    els.metaStorm.innerHTML = `${esc(storm.name)} <s>${esc(storm.id)}</s>`;
    els.metaInit.textContent = initLabel;
    els.metaLead.textContent = `+${storm.lead_min} – +${storm.lead_max} h`;
    els.metaSource.textContent = model.source;
    els.metaSource.title = run.source || model.source;
    els.heroTitle.innerHTML = `${esc(model.hero)}<br><em>Tropical Cyclone Tracks</em>`;
    els.deckModelText.textContent = `${model.label} 系集热带气旋路径与强度预报`;
    els.mapModelBadge.textContent = model.short;
    els.mapModelText.textContent = `${model.label} ${run.resolution || ""}`.trim();
    els.mapFooterMembers.textContent = `${storm.member_count} members`;
    document.title = `${run.model} · BAMC 热带气旋`;
    els.stormTitle.innerHTML = `${esc(storm.name)} <span id="stormId">${esc(storm.id)}</span>`;
    els.chartSub.textContent = `${run.model} · ${storm.member_count} 个成员 · 路径按强度着色 · 选择时效查看系集状态`;
    els.memberPillText.textContent = `${storm.member_count} MEMBERS`;
    els.mapRunBadge.textContent = `${run.id.slice(8, 10)}Z RUN`;
    els.mapInit.textContent = initLabel;
    els.mapLeadRange.textContent = `+${storm.lead_min} – +${storm.lead_max} h`;
    els.footerInit.textContent = initLabel;
    els.peakMslp.textContent = storm.summary && storm.summary.min_mslp != null ? fmtNumber(storm.summary.min_mslp, 0) : "—";
    els.peakWind.textContent = storm.summary && storm.summary.max_wind != null ? fmtNumber(storm.summary.max_wind, 0) : "—";
    els.intensityNote.textContent = `${storm.member_count} 条成员曲线 · 每 6 小时`;
    updateTimeTicks();
  }

  function populateRuns() {
    const runs = state.index.runs || [];
    els.runSelect.innerHTML = runs.map((run) => {
      const latest = run.id === state.index.latest ? " · 最新" : "";
      return `<option value="${esc(run.id)}">${esc(run.short)} · ${run.members}m${latest}</option>`;
    }).join("");
  }

  function populateStorms() {
    els.stormSelect.innerHTML = (state.run.storms || []).map((storm) =>
      `<option value="${esc(storm.id)}">${esc(storm.name)} / ${esc(storm.id)}</option>`
    ).join("");
  }

  /* ---------------- data loading ---------------- */

  async function loadGeo() {
    try {
      state.geo = await fetchJSON(DATA_BASE + "geo.json");
    } catch (error) {
      console.warn("basemap unavailable", error);
      state.geo = { land: [], borders: [] };
    }
    drawBase();
  }

  function prepareStorm(storm) {
    storm.members.forEach((member) => {
      member.byLead = new Map();
      member.track.forEach((point) => member.byLead.set(point.lead, point));
    });
    state.storm = storm;
    state.leads = (storm.leads || []).slice().sort((a, b) => a - b);
    computeLeadStats();
  }

  function chooseLeadFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const hasLead = params.has("lead") && params.get("lead") !== "";
    const requested = hasLead ? Number(params.get("lead")) : 24;
    if (Number.isFinite(requested) && requested >= 0) {
      let best = 0;
      state.leads.forEach((lead, i) => {
        if (Math.abs(lead - requested) < Math.abs(state.leads[best] - requested)) best = i;
      });
      return best;
    }
    return state.leads.length - 1;
  }

  async function loadRun(runId, options) {
    const opts = options || {};
    const entry = (state.index.runs || []).find((run) => run.id === runId) || state.index.runs[0];
    if (!entry) throw new Error("没有可用的起报时次");
    state.model = "ifs";
    els.modelSelect.value = "ifs";
    populateRuns();
    const seq = ++state.loadSeq;
    hideError();
    setLoading(true, "读取 ECMWF 系集成员…");
    setStatus("加载中", "is-loading");
    els.runSelect.disabled = true;
    els.stormSelect.disabled = true;

    try {
      const data = await fetchJSON(DATA_BASE + entry.file);
      if (seq !== state.loadSeq) return;
      if (!data.storms || !data.storms.length) throw new Error("该时次没有热带气旋数据");
      state.runEntry = entry;
      state.run = data;
      state.selectedMember = null;
      state.hoverMember = null;
      populateStorms();
      const params = new URLSearchParams(window.location.search);
      const wantedStorm = opts.storm || params.get("storm");
      const storm = data.storms.find((s) => s.id === wantedStorm) || data.storms[0];
      els.stormSelect.value = storm.id;
      prepareStorm(storm);
      state.leadIndex = opts.keepLead ? clamp(state.leadIndex, 0, state.leads.length - 1) : chooseLeadFromUrl();
      state.baseRendered = false;
      drawBase();
      renderLegend();
      updateRunMeta();
      renderTracks();
      renderQuantiles();
      renderIntensity();
      updateLeadUI();
      setLoading(false);
      setStatus("ECMWF 已连接", "is-ok");
      els.runSelect.disabled = false;
      els.stormSelect.disabled = false;
      els.runSelect.value = entry.id;
      updateUrl();
      if (state.jtwc) renderJtwcPanel();
    } catch (error) {
      if (seq !== state.loadSeq) return;
      console.error(error);
      showError(error.message === "HTTP 404"
        ? "找不到该时次的数据文件，请换一个起报时次。"
        : "无法读取 ECMWF 系集数据：" + error.message);
      els.runSelect.disabled = false;
      els.stormSelect.disabled = false;
    }
  }

  async function loadExternalDates(model, selected) {
    if (state.model !== model) return;
    try {
      const data = await fetchJSON(`/api/tcmodel/dates?model=${encodeURIComponent(model)}&ts=${Date.now()}`);
      if (state.model !== model) return;
      state.externalDates = Array.isArray(data.dates) ? data.dates : [];
      els.runSelect.innerHTML = state.externalDates.map((item, index) =>
        `<option value="${esc(item.value)}">${esc(item.label)}${index === 0 ? " · 最新" : ""}</option>`
      ).join("");
      if (selected && state.externalDates.some((item) => item.value === selected)) {
        els.runSelect.value = selected;
      }
    } catch (error) {
      console.warn("model dates unavailable", error);
      state.externalDates = [];
      els.runSelect.innerHTML = `<option value="${esc(selected || "")}">${esc(selected || "最新起报")}</option>`;
      if (selected) els.runSelect.value = selected;
    }
  }

  async function loadExternal(model, options) {
    const opts = options || {};
    const spec = MODEL_META[model];
    if (!spec) return;
    state.model = model;
    els.modelSelect.value = model;
    const seq = ++state.loadSeq;
    hideError();
    setLoading(true, `读取 ${spec.label} 系集成员…`);
    setStatus("加载中", "is-loading");
    els.runSelect.disabled = true;
    els.stormSelect.disabled = true;

    try {
      const date = opts.date || "";
      const suffix = date ? `&date=${encodeURIComponent(date)}` : "";
      const data = await fetchJSON(`/api/tcmodel?model=${encodeURIComponent(model)}${suffix}&ts=${Date.now()}`);
      if (seq !== state.loadSeq) return;
      if (!data.storms || !data.storms.length) throw new Error("该模式没有框内系统");
      state.run = data;
      state.runEntry = { id: data.run.id, external: true, model };
      state.selectedMember = null;
      state.hoverMember = null;
      populateStorms();
      const params = new URLSearchParams(window.location.search);
      const wantedStorm = opts.storm || params.get("storm");
      const storm = data.storms.find((s) => s.id === wantedStorm) || data.storms[0];
      els.stormSelect.value = storm.id;
      prepareStorm(storm);
      state.leadIndex = opts.keepLead ? clamp(state.leadIndex, 0, state.leads.length - 1) : chooseLeadFromUrl();
      state.baseRendered = false;
      drawBase();
      renderLegend();
      updateRunMeta();
      renderTracks();
      renderQuantiles();
      renderIntensity();
      updateLeadUI();
      await loadExternalDates(model, data.run.id);
      els.runSelect.disabled = false;
      els.stormSelect.disabled = false;
      els.runSelect.value = data.run.id;
      setLoading(false);
      setStatus(`${spec.label} 已连接`, "is-ok");
      updateUrl();
      if (state.jtwc) renderJtwcPanel();
    } catch (error) {
      if (seq !== state.loadSeq) return;
      console.error(error);
      showError("无法读取该模式数据：" + error.message);
      els.runSelect.disabled = false;
      els.stormSelect.disabled = false;
    }
  }

  function selectStorm(stormId) {
    if (!state.run) return;
    const storm = state.run.storms.find((s) => s.id === stormId);
    if (!storm) return;
    state.selectedMember = null;
    state.hoverMember = null;
    prepareStorm(storm);
    state.leadIndex = clamp(state.leadIndex, 0, state.leads.length - 1);
    els.stormSelect.value = storm.id;
    state.baseRendered = false;
    drawBase();
    updateRunMeta();
    renderLegend();
    renderTracks();
    renderQuantiles();
    renderIntensity();
    updateLeadUI();
    updateUrl();
    if (state.jtwc) renderJtwcPanel();
  }

  async function refreshLatestData() {
    if (document.hidden || !state.run || state.model !== "ifs") return;
    try {
      const latest = await fetchJSON(`${DATA_BASE}index.json?ts=${Date.now()}`);
      const latestId = latest.latest || (latest.runs && latest.runs[0] && latest.runs[0].id);
      if (!latestId) return;
      const changed = latestId !== state.run.run.id || latest.generated !== state.index.generated;
      if (!changed) return;
      state.index = latest;
      populateRuns();
      await loadRun(latestId, { keepLead: true });
      await loadJtwc(true);
    } catch (error) {
      console.warn("forecast data refresh skipped", error);
    }
  }

  async function init() {
    bindUI();
    updateClock();
    setInterval(updateClock, 1000);
    setStatus("连接中", "is-loading");
    setLoading(true, "读取系集目录…");
    try {
      state.index = await fetchJSON(DATA_BASE + "index.json");
      if (!state.index.runs || !state.index.runs.length) throw new Error("没有可用的起报数据");
      populateRuns();
      const params = new URLSearchParams(window.location.search);
      const requested = params.get("run");
      const requestedModel = params.get("model");
      const initialModel = MODEL_META[requestedModel] ? requestedModel : "ifs";
      els.modelSelect.value = initialModel;
      const entry = state.index.runs.find((run) => run.id === requested) || state.index.runs.find((run) => run.id === state.index.latest) || state.index.runs[0];
      await loadGeo();
      if (initialModel === "ifs") {
        await loadRun(entry.id);
      } else {
        await loadExternal(initialModel, { date: requested || "" });
      }
      await loadJtwc();
      state.jtwcTimer = setInterval(() => {
        if (!document.hidden) loadJtwc();
      }, 5 * 60 * 1000);
      state.dataTimer = setInterval(refreshLatestData, 10 * 60 * 1000);
    } catch (error) {
      console.error(error);
      showError("初始化失败：" + error.message);
      setLoading(false);
    }
  }
  /* ---------------- tooltip / member interaction ---------------- */

  function toSvgPoint(clientX, clientY) {
    const point = els.mapSvg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    const matrix = els.mapSvg.getScreenCTM();
    if (!matrix) return null;
    return point.matrixTransform(matrix.inverse());
  }

  function findNearest(clientX, clientY) {
    const point = toSvgPoint(clientX, clientY);
    if (!point) return null;
    let best = null;
    let bestDist = 11 * 11;
    state.pointEls.forEach((entry) => {
      const dx = entry.x - point.x;
      const dy = entry.y - point.y;
      const dist = dx * dx + dy * dy;
      if (dist < bestDist) {
        bestDist = dist;
        best = entry;
      }
    });
    return best;
  }

  function membersAtPoint(entry) {
    return entry.member;
  }

  function showTooltip(entry, event) {
    const member = entry.member;
    const point = entry.point;
    const bin = pointBin(point);
    const title = `成员 ${pad2(member.member)}${member.control ? " · 控制" : ""}`;
    const windText = point.wind == null ? "—" : `${fmtNumber(point.wind, 0)} kt · ${bin.cat}`;
    els.tooltip.innerHTML = `
      <b>${esc(title)}</b>
      <small>+${point.lead} h · ${point.lat.toFixed(1)}°N ${point.lon.toFixed(1)}°E</small>
      <div class="tt-row"><span>MSLP</span><strong>${point.mslp == null ? "—" : fmtNumber(point.mslp, 1) + " hPa"}</strong></div>
      <div class="tt-row"><span>WIND</span><strong>${windText}</strong></div>`;
    const rect = els.mapWrap.getBoundingClientRect();
    let left = event.clientX - rect.left;
    let top = event.clientY - rect.top;
    const flip = left > rect.width - 165;
    top = clamp(top, 55, rect.height - 55);
    els.tooltip.style.left = `${left}px`;
    els.tooltip.style.top = `${top}px`;
    els.tooltip.style.transform = flip ? "translate(-100%, -50%) translate(-10px, 0)" : "translate(10px, -50%)";
    els.tooltip.hidden = false;
  }

  function hideTooltip() {
    els.tooltip.hidden = true;
  }

  function onPointerMove(event) {
    if (!state.pointEls.length) return;
    const hit = findNearest(event.clientX, event.clientY);
    if (!hit) {
      if (state.hoverMember != null) {
        state.hoverMember = null;
        applyTrackClasses();
        updateMemberDetail();
      }
      hideTooltip();
      return;
    }
    if (state.hoverMember !== hit.member.member) {
      state.hoverMember = hit.member.member;
      applyTrackClasses();
      updateMemberDetail();
    }
    showTooltip(hit, event);
  }

  function onMapClick(event) {
    const hit = findNearest(event.clientX, event.clientY);
    if (!hit) {
      if (state.selectedMember != null) {
        state.selectedMember = null;
        state.hoverMember = null;
        applyTrackClasses();
        updateMemberDetail();
        updateUrl();
        toast("已取消成员锁定");
      }
      return;
    }
    if (state.selectedMember === hit.member.member) {
      state.selectedMember = null;
      state.hoverMember = null;
      toast("已取消成员锁定");
    } else {
      state.selectedMember = hit.member.member;
      state.hoverMember = hit.member.member;
      toast(`已锁定成员 ${pad2(hit.member.member)} · 悬停可查看其它成员`);
    }
    applyTrackClasses();
    updateMemberDetail();
    updateUrl();
  }

  /* ---------------- download ---------------- */

  function downloadMap() {
    if (!state.storm) {
      toast("数据尚未加载");
      return;
    }
    const clone = els.mapSvg.cloneNode(true);
    clone.setAttribute("xmlns", NS);
    clone.setAttribute("width", "2000");
    clone.setAttribute("height", "1320");
    clone.setAttribute("viewBox", `0 0 ${MAP.W} ${MAP.H}`);
    const style = document.createElementNS(NS, "style");
    style.textContent = `
      .map-paper{fill:#f8f8ec}
      .graticule-line{stroke:#d6d4c2;stroke-width:.55}
      .graticule-line.major{stroke:#c9c6b3}
      .graticule-tick{stroke:#777a6d;stroke-width:.6}
      .graticule-label{fill:#62665b;font-family:Consolas,monospace;font-size:9.5px}
      .graticule-label.lon{text-anchor:middle}.graticule-label.lat{text-anchor:end}
      .land-shape{fill:#eeeada;stroke:#575b4e;stroke-width:.72}
      .border-line{fill:none;stroke:#9c9d8e;stroke-width:.52;stroke-dasharray:2.2 2.6}
      .city-dot{fill:#3f443a;opacity:.65}
      .city-label{fill:#6c7065;font-family:Arial,sans-serif;font-size:8.8px;paint-order:stroke;stroke:#f4f3e7;stroke-width:2.3px}
      .country-label{fill:#85887a;font-family:Consolas,monospace;font-size:10px;letter-spacing:2.4px;opacity:.48;text-anchor:middle}
      .member-track{fill:none;stroke:#5d706a;stroke-width:1.05;opacity:.19}
      .member-track.is-hover{opacity:.92;stroke:#11160f;stroke-width:1.9}
      .member-track.is-selected{opacity:1;stroke:#1e5d49;stroke-width:2}
      .mean-track-halo{fill:none;stroke:#fbfaf2;stroke-width:5;opacity:.86}
      .mean-track{fill:none;stroke:#151914;stroke-width:1.7;stroke-dasharray:5.5 4.2}
      .ens-dot{stroke:#fffdf5;stroke-width:.72;opacity:.82}
      .current-halo{fill:none;stroke:#fffdf5;stroke-width:3.2;opacity:.8}
      .current-dot{fill:none;stroke:#11160f;stroke-width:1.15}
      .init-ring{fill:none;stroke:#11160f;stroke-width:1.25}
      .init-cross{stroke:#11160f;stroke-width:.9}
      .storm-callout-line{stroke:#252a22;stroke-width:.8}
      .storm-callout-box{fill:rgba(251,250,243,.94);stroke:#252a22;stroke-width:.7}
      .storm-callout-title{fill:#171a15;font-family:Arial,sans-serif;font-size:12px;font-weight:700}
      .storm-callout-sub{fill:#6f7469;font-family:Consolas,monospace;font-size:8.5px}
      .lead-tag-bg{fill:rgba(251,250,243,.92);stroke:rgba(20,24,18,.25);stroke-width:.55}
      .lead-tag-text{fill:#5d6358;font-family:Consolas,monospace;font-size:8px;text-anchor:middle}
      .jtwc-marker-halo{fill:rgba(178,58,43,.13)}
      .jtwc-marker-ring{fill:none;stroke:#8a2f22;stroke-width:1.15}
      .jtwc-marker{fill:#b23a2b;stroke:#fffdf5;stroke-width:1.1}
      .jtwc-leader{fill:none;stroke:#8a2f22;stroke-width:.85;opacity:.8}
      .jtwc-label-bg{fill:rgba(255,251,243,.96);stroke:#b23a2b;stroke-width:.7}
      .jtwc-label-name{fill:#7d281d;font-family:Arial,sans-serif;font-size:10px;font-weight:700}
      .jtwc-label-sub{fill:#7b776a;font-family:Consolas,monospace;font-size:7.5px}
    `;
    clone.insertBefore(style, clone.firstChild);
    const serializer = new XMLSerializer();
    const source = serializer.serializeToString(clone);
    const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = function () {
      const mapW = 2000;
      const mapH = 1320;
      const headerH = 240;
      const footerH = 120;
      const canvas = document.createElement("canvas");
      canvas.width = mapW;
      canvas.height = headerH + mapH + footerH;
      const ctx = canvas.getContext("2d");
      const paper = "#f4f2e7";
      const ink = "#171a15";
      const green = "#1e5d49";
      const muted = "#6f7469";
      const line = "#b9b6a5";
      const run = state.run.run;
      const lead = state.leads[state.leadIndex];
      const hero = (MODEL_META[state.model] || MODEL_META.ifs).hero;

      ctx.fillStyle = paper;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Header: title top-left, issue time top-right.
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      ctx.fillStyle = ink;
      ctx.font = '800 68px "Segoe UI", "Helvetica Neue", Arial, sans-serif';
      ctx.fillText(hero, 80, 104);
      ctx.fillStyle = green;
      ctx.fillText("Tropical Cyclone Tracks", 80, 184);
      ctx.fillStyle = ink;
      ctx.textAlign = "right";
      ctx.font = '600 30px Consolas, "Courier New", monospace';
      ctx.fillText(run.display, canvas.width - 80, 96);
      ctx.fillStyle = muted;
      ctx.font = '20px Consolas, "Courier New", monospace';
      ctx.fillText(
        `${run.model} · ${state.storm.member_count} members · ${state.storm.name} / ${state.storm.id}`,
        canvas.width - 80,
        134
      );
      ctx.strokeStyle = line;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(80, 214);
      ctx.lineTo(canvas.width - 80, 214);
      ctx.stroke();

      // Forecast chart.
      ctx.drawImage(image, 0, headerH, mapW, mapH);
      URL.revokeObjectURL(url);

      // Footer: init/lead left, site bottom-right.
      const footerLineY = headerH + mapH + 38;
      ctx.strokeStyle = line;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(80, footerLineY);
      ctx.lineTo(canvas.width - 80, footerLineY);
      ctx.stroke();

      ctx.textAlign = "left";
      ctx.fillStyle = muted;
      ctx.font = '22px Consolas, "Courier New", monospace';
      ctx.fillText(
        `Init: ${run.date} ${run.id.slice(8, 10)} UTC  ·  Lead +${lead} h  ·  ${state.storm.name} / ${state.storm.id}`,
        80,
        footerLineY + 42
      );

      ctx.textAlign = "right";
      ctx.fillStyle = ink;
      ctx.font = '600 32px "Segoe UI", "Helvetica Neue", Arial, sans-serif';
      ctx.fillText("www.bamc.top", canvas.width - 80, footerLineY + 44);

      canvas.toBlob((png) => {
        if (!png) { toast("导出失败"); return; }
        const link = document.createElement("a");
        link.href = URL.createObjectURL(png);
        link.download = `BAMC_EC_ENS_${state.storm.name}_${lead}h.png`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
        toast("高清 PNG 已导出");
      }, "image/png");
    };
    image.onerror = function () {
      URL.revokeObjectURL(url);
      toast("导出失败，请重试");
    };
    image.src = url;
  }

  /* ---------------- fullscreen ---------------- */

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      const promise = els.chartCard.requestFullscreen && els.chartCard.requestFullscreen();
      if (promise && promise.catch) promise.catch(() => {});
    } else {
      document.exitFullscreen();
    }
  }

  function onFullscreenChange() {
    const active = Boolean(document.fullscreenElement);
    els.btnFullscreen.innerHTML = `<svg><use href="#i-${active ? "shrink" : "expand"}"/></svg>`;
  }

  /* ---------------- playback ---------------- */

  function setPlayIcon() {
    els.playIcon.innerHTML = `<use href="#i-${state.playing ? "pause" : "play"}"/>`;
    els.btnPlay.setAttribute("aria-label", state.playing ? "暂停" : "播放");
    els.btnPlay.title = state.playing ? "暂停" : "播放";
  }

  function play() {
    if (state.playing || state.leads.length < 2) return;
    state.playing = true;
    setPlayIcon();
    clearInterval(state.timer);
    state.timer = setInterval(() => {
      if (!state.playing) return;
      let next = state.leadIndex + 1;
      if (next >= state.leads.length) {
        if (state.leads.length > 1) next = 0;
        else { pause(); return; }
      }
      state.leadIndex = next;
      hideTooltip();
      state.hoverMember = null;
      applyTrackClasses();
      updateLeadUI();
      updateUrl();
    }, 760);
  }

  function pause() {
    state.playing = false;
    clearInterval(state.timer);
    state.timer = null;
    setPlayIcon();
  }

  function togglePlay() {
    if (state.playing) pause(); else play();
  }

  /* ---------------- URL ---------------- */

  function updateUrl() {
    if (!state.run || !state.storm || !state.leads.length) return;
    const url = new URL(window.location.href);
    url.searchParams.set("model", state.model);
    url.searchParams.set("run", state.run.run.id);
    url.searchParams.set("storm", state.storm.id);
    url.searchParams.set("lead", String(state.leads[state.leadIndex]));
    history.replaceState(null, "", url.pathname + "?" + url.searchParams.toString());
  }

  /* ---------------- bind ---------------- */

  function bindUI() {
    if (window.matchMedia("(max-width: 760px)").matches) {
      els.mapHint.textContent = "左右滑动 · 点按圆点查看成员";
    }
    els.btnFirst.addEventListener("click", () => { pause(); setLead(0, { pause: true }); });
    els.btnPrev.addEventListener("click", () => { pause(); setLead(state.leadIndex - 1, { pause: true }); });
    els.btnPlay.addEventListener("click", togglePlay);
    els.btnNext.addEventListener("click", () => { pause(); setLead(state.leadIndex + 1, { pause: true }); });
    els.btnLast.addEventListener("click", () => { pause(); setLead(state.leads.length - 1, { pause: true }); });
    els.leadSlider.addEventListener("input", (event) => {
      pause();
      setLead(Number(event.target.value), { pause: true });
    });
    els.modelSelect.addEventListener("change", () => {
      pause();
      const model = els.modelSelect.value;
      if (model === "ifs") {
        populateRuns();
        loadRun(state.index.latest || (state.index.runs[0] && state.index.runs[0].id), { keepLead: false });
      } else {
        loadExternal(model, {});
      }
    });
    els.runSelect.addEventListener("change", () => {
      pause();
      if (state.model === "ifs") loadRun(els.runSelect.value, { keepLead: false });
      else loadExternal(state.model, { date: els.runSelect.value });
    });
    els.stormSelect.addEventListener("change", () => {
      pause();
      selectStorm(els.stormSelect.value);
    });
    els.colorMode.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-mode]");
      if (!button) return;
      const mode = button.getAttribute("data-mode");
      if (!mode || mode === state.colorMode) return;
      state.colorMode = mode;
      Array.from(els.colorMode.querySelectorAll("button")).forEach((b) => {
        b.classList.toggle("on", b.getAttribute("data-mode") === mode);
      });
      renderLegend();
      renderTracks();
      renderIntensity();
      updateMemberDetail();
    });
    els.toggleMembers.addEventListener("change", () => {
      state.showMembers = els.toggleMembers.checked;
      if (state.layers.memberGroup) state.layers.memberGroup.style.display = state.showMembers ? "" : "none";
    });
    els.toggleMean.addEventListener("change", () => {
      state.showMean = els.toggleMean.checked;
      if (state.layers.meanGroup) state.layers.meanGroup.style.display = state.showMean ? "" : "none";
    });
    els.toggleLabels.addEventListener("change", () => {
      state.showLabels = els.toggleLabels.checked;
      if (state.layers.labelGroup) state.layers.labelGroup.style.display = state.showLabels ? "" : "none";
    });
    els.toggleCities.addEventListener("change", () => {
      state.showCities = els.toggleCities.checked;
      els.cityLayer.style.display = state.showCities ? "" : "none";
    });
    els.btnUnpin.addEventListener("click", () => {
      state.selectedMember = null;
      state.hoverMember = null;
      applyTrackClasses();
      updateMemberDetail();
      updateUrl();
    });
    els.btnFullscreen.addEventListener("click", toggleFullscreen);
    document.addEventListener("fullscreenchange", onFullscreenChange);
    els.btnDownload.addEventListener("click", downloadMap);
    els.btnRetry.addEventListener("click", () => {
      if (state.model !== "ifs" && state.runEntry && state.runEntry.external) {
        loadExternal(state.model, { date: state.runEntry.id });
      } else if (state.runEntry) {
        loadRun(state.runEntry.id, { keepLead: true });
      } else {
        init();
      }
    });
    els.btnJtwcRefresh.addEventListener("click", () => loadJtwc(true));
    els.jtwcList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-jtwc-id]");
      if (!button) return;
      const system = jtwcSystems().find((item) => String(item.id) === button.getAttribute("data-jtwc-id"));
      if (system) focusJtwcSystem(system);
    });
    els.mapWrap.addEventListener("pointermove", onPointerMove);
    els.mapWrap.addEventListener("pointerleave", () => {
      hideTooltip();
      if (state.hoverMember != null) {
        state.hoverMember = null;
        applyTrackClasses();
        updateMemberDetail();
      }
    });
    els.mapWrap.addEventListener("click", onMapClick);
    document.addEventListener("keydown", (event) => {
      const tag = (event.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "select" || tag === "textarea") return;
      if (event.code === "Space") { event.preventDefault(); togglePlay(); }
      else if (event.key === "ArrowLeft") { event.preventDefault(); pause(); setLead(state.leadIndex - 1); }
      else if (event.key === "ArrowRight") { event.preventDefault(); pause(); setLead(state.leadIndex + 1); }
      else if (event.key === "Home") { event.preventDefault(); pause(); setLead(0); }
      else if (event.key === "End") { event.preventDefault(); pause(); setLead(state.leads.length - 1); }
      else if (event.key === "f" || event.key === "F") { toggleFullscreen(); }
    });
    document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
    window.addEventListener("resize", () => {
      clearTimeout(state.resizeTimer);
      state.resizeTimer = setTimeout(() => {
        if (window.matchMedia("(max-width: 760px)").matches) {
          els.mapHint.textContent = "左右滑动 · 点按圆点查看成员";
        } else {
          els.mapHint.textContent = "悬停圆点查看成员 · 点击锁定";
        }
        hideTooltip();
      }, 120);
    });
  }

  init();
})();
