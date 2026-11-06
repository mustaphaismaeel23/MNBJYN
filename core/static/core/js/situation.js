/* Situation Room.
   Two modes share the same screen:

   * SIMULATION - animated sample results for the configured LGAs and wards, "submitted"
     over time as agents would on election day. Not real data.
   * LIVE       - real results sent by the field app, read from the results API
     (/api/v1/public/...). The admin switches the mode in /admin > Situation Room settings
     (or PATCH /api/v1/admin/situation-room/). Simulated numbers are NEVER shown in live mode.

   You can drill down: State > LGA > Ward > Polling unit. */
(function () {
  "use strict";

  var root = document.getElementById("sit-live");
  var dataNode = document.getElementById("lga-data");
  if (!root || !dataNode) return;
  var LGAS, CFG = { mode: "simulation", refresh_seconds: 10, state_code: "20", state_name: "Kano", api: "/api/v1" };
  try { LGAS = JSON.parse(dataNode.textContent); } catch (e) { return; }
  try {
    var cfgNode = document.getElementById("sit-config");
    if (cfgNode) { var c = JSON.parse(cfgNode.textContent); for (var k in c) CFG[k] = c[k]; }
  } catch (e) { /* keep defaults */ }

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- helpers ---------- */
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function fmt(n) { return Math.round(n).toLocaleString("en-NG"); }
  function pct(a, b) { return b ? (a / b) * 100 : 0; }
  function z(n, w) { n = String(n); while (n.length < w) n = "0" + n; return n; }
  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) {            // mulberry32
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function clock(d) {
    d = d || new Date();
    return z(d.getHours(), 2) + ":" + z(d.getMinutes(), 2) + ":" + z(d.getSeconds(), 2);
  }
  function puCode(li, wi, num) { return CFG.state_code + "/" + z(li + 1, 2) + "/" + z(wi + 1, 2) + "/" + z(num, 3); }
  function puLabel(pu) {
    var base = "PU " + z(pu.num, 3);
    return pu.generic ? base : base + " \u00B7 " + pu.name;
  }

  // Animated number: tweens the displayed value to `to`.
  function setNum(node, to) {
    to = Math.round(to);
    if (node._to === to) return;
    node._to = to;
    if (reduceMotion) { node.textContent = fmt(to); return; }
    var from = node._v || 0, t0 = null, dur = 650;
    if (node._raf) cancelAnimationFrame(node._raf);
    function step(ts) {
      if (t0 === null) t0 = ts;
      var k = Math.min((ts - t0) / dur, 1), e = 1 - Math.pow(1 - k, 3);
      node._v = from + (to - from) * e;
      node.textContent = fmt(node._v);
      if (k < 1) node._raf = requestAnimationFrame(step); else node._v = to;
    }
    node._raf = requestAnimationFrame(step);
  }

  /* ---------- model ---------- */
  var SIM_PARTIES = [
    { name: "Malam Nasiru Bala Ja'oji", short: "MNBJ", color: "#14B8A6" },
    { name: "Candidate B", short: "B", color: "#FFFFFF" },
    { name: "Candidate C", short: "C", color: "#99F6E4" },
    { name: "Others", short: "Oth", color: "#6F86A6" }
  ];
  var PARTIES = SIM_PARTIES;
  var BASE = [0.36, 0.32, 0.2, 0.12];
  var FIRST = ["Aminu", "Abubakar", "Ibrahim", "Musa", "Yusuf", "Usman", "Hauwa", "Fatima", "Zainab", "Aisha", "Sani", "Bashir", "Umar", "Halima", "Idris", "Maryam", "Suleiman", "Nasiru", "Rabi", "Garba"];
  var LAST = ["Mohammed", "Abdullahi", "Danjuma", "Bello", "Lawal", "Adamu", "Sule", "Ahmad", "Yakubu", "Baba", "Haruna", "Kabir", "Tanko", "Isah", "Gambo"];

  function zeros() { var a = []; for (var i = 0; i < PARTIES.length; i++) a.push(0); return a; }
  function blank() { return { n: 0, rep: 0, reg: 0, acc: 0, rej: 0, valid: 0, votes: zeros() }; }
  function add(t, r, sign) {
    sign = sign || 1;
    t.rep += sign; t.reg += sign * r.reg; t.acc += sign * r.acc; t.rej += sign * r.rej; t.valid += sign * r.valid;
    for (var i = 0; i < t.votes.length; i++) t.votes[i] += sign * (r.votes[i] || 0);
  }
  function addAll(m, lga, ward, r, sign) { add(ward.tot, r, sign); add(lga.tot, r, sign); add(m.state, r, sign); }

  var mode = "sim";           // "sim" | "live"
  var model;                  // the data currently on screen

  function newModel() {
    return { lgas: [], state: blank(), wardsTotal: 0, history: [], order: [], pos: 0, seed: 0 };
  }

  /* ----- simulation ----- */
  function buildSim(seed) {
    var r0 = rng(seed), s = newModel();
    s.seed = seed;
    LGAS.forEach(function (l, li) {
      var lga = { i: li, key: l.key, name: l.name, wards: [], tot: blank() };
      l.wards.forEach(function (wn, wi) {
        var r = rng(hash(seed + ":" + l.key + ":" + wi));
        var n = 8 + Math.floor(r() * 8);
        var lean = BASE.map(function (b) { return b * Math.exp((r() - 0.5) * 1.5); });
        var sum = lean.reduce(function (a, b) { return a + b; }, 0);
        lean = lean.map(function (v) { return v / sum; });
        var ward = { name: wn, lga: li, idx: wi, n: n, lean: lean, pus: [], tot: blank() };
        ward.tot.n = n; lga.tot.n += n; s.state.n += n;
        for (var p = 0; p < n; p++) {
          var rr = rng(hash(seed + ":" + l.key + ":" + wi + ":" + p + ":reg"));
          ward.pus.push({
            num: p + 1, code: puCode(li, wi, p + 1), name: "Polling Unit " + z(p + 1, 3), generic: true,
            reg: 380 + Math.floor(rr() * 560), res: null
          });
          s.order.push([li, wi, p]);
        }
        lga.wards.push(ward);
        s.wardsTotal++;
      });
      s.lgas.push(lga);
    });
    for (var i = s.order.length - 1; i > 0; i--) {   // Fisher-Yates
      var j = Math.floor(r0() * (i + 1)), t = s.order[i]; s.order[i] = s.order[j]; s.order[j] = t;
    }
    return s;
  }

  function makeResult(ward, p) {
    var pu = ward.pus[p];
    var r = rng(hash(model.seed + ":" + ward.lga + ":" + ward.idx + ":" + p + ":r"));
    var reg = pu.reg;
    var acc = Math.round(reg * (0.38 + r() * 0.34));
    var rej = Math.round(acc * (0.008 + r() * 0.02));
    var valid = acc - rej;
    var sh = ward.lean.map(function (v) { return v * Math.exp((r() - 0.5) * 0.55); });
    var sum = sh.reduce(function (a, b) { return a + b; }, 0);
    var votes = sh.map(function (v) { return Math.floor(valid * v / sum); });
    var left = valid - votes.reduce(function (a, b) { return a + b; }, 0);
    var top = 0; for (var i = 1; i < 4; i++) if (votes[i] > votes[top]) top = i;
    votes[top] += left;
    return {
      reg: reg, acc: acc, rej: rej, valid: valid, votes: votes,
      rep: FIRST[Math.floor(r() * FIRST.length)] + " " + LAST[Math.floor(r() * LAST.length)],
      time: clock()
    };
  }

  function recordHistory(lga, ward, pu, res, fresh) {
    model.history = model.history.filter(function (h) { return h.pu !== pu; });
    model.history.unshift({ lga: lga, ward: ward, pu: pu, res: res, fresh: fresh });
    if (model.history.length > 400) model.history.length = 400;
  }

  function simSubmit(item) {
    var lga = model.lgas[item[0]], ward = lga.wards[item[1]], pu = ward.pus[item[2]];
    var res = makeResult(ward, item[2]);
    pu.res = res;
    addAll(model, lga, ward, res, 1);
    recordHistory(lga, ward, pu, res, true);
  }

  /* ----- live ----- */
  var live = { timer: null, cursor: null, fails: 0, busy: false, electionId: null, byCode: {}, ready: false, gen: 0 };

  function buildLive(structure) {
    var s = newModel(), byKey = {};
    structure.lgas.forEach(function (sl) { byKey[sl.key] = sl; });
    live.byCode = {};
    LGAS.forEach(function (l, li) {
      var sl = byKey[l.key] || { wards: [] };
      var lga = { i: li, key: l.key, name: l.name, wards: [], tot: blank() };
      l.wards.forEach(function (wn, wi) {
        var sw = null;
        for (var k = 0; k < sl.wards.length; k++) if (sl.wards[k].index === wi) { sw = sl.wards[k]; break; }
        var ward = { name: wn, lga: li, idx: wi, n: 0, pus: [], tot: blank() };
        (sw ? sw.pus : []).forEach(function (a) {
          // a = [number, code, name, registered_voters]
          var pu = { num: a[0], code: a[1], name: a[2], generic: /^Polling Unit \d+$/.test(a[2]), reg: a[3] || 0, res: null };
          ward.pus.push(pu);
          live.byCode[pu.code] = { lga: lga, ward: ward, pu: pu };
        });
        ward.n = ward.pus.length; ward.tot.n = ward.n; lga.tot.n += ward.n; s.state.n += ward.n;
        lga.wards.push(ward);
        s.wardsTotal++;
      });
      s.lgas.push(lga);
    });
    return s;
  }

  function liveResult(r) {
    var d = r.at ? new Date(r.at) : new Date();
    var votes = [];
    for (var i = 0; i < PARTIES.length; i++) votes.push(r.votes[i] || 0);
    return { reg: r.registered, acc: r.accredited, rej: r.rejected, valid: r.valid, votes: votes,
             rep: r.by || "Agent", time: isNaN(d.getTime()) ? "" : clock(d) };
  }

  function applyLive(data) {
    var changed = false;
    model.history.forEach(function (h) { h.fresh = false; });
    (data.results || []).forEach(function (r) {
      var loc = live.byCode[r.pu];
      if (!loc) return;
      if (loc.pu.res) addAll(model, loc.lga, loc.ward, loc.pu.res, -1);
      var res = liveResult(r);
      loc.pu.res = res;
      addAll(model, loc.lga, loc.ward, res, 1);
      recordHistory(loc.lga, loc.ward, loc.pu, res, true);
      changed = true;
    });
    (data.withdrawn || []).forEach(function (code) {
      var loc = live.byCode[code];
      if (!loc || !loc.pu.res) return;
      addAll(model, loc.lga, loc.ward, loc.pu.res, -1);
      loc.pu.res = null;
      model.history = model.history.filter(function (h) { return h.pu !== loc.pu; });
      changed = true;
    });
    return changed;
  }

  /* ---------- DOM refs ---------- */
  var lgaSel = $("sit-lga"), wardSel = $("sit-ward"), wardWrap = $("sit-ward-wrap");
  var puSel = $("sit-pu"), puWrap = $("sit-pu-wrap");
  var elTitle = $("sit-scope-title"), elSub = $("sit-scope-sub"), elFill = $("sit-progress-fill");
  var elParties = $("sit-parties"), elFacts = $("sit-facts");
  var elFeed = $("sit-feed"), elFeedTitle = $("sit-feed-title");
  var elClock = $("sit-clock"), elMode = $("sit-mode-label");
  var btnPause = $("sit-pause"), btnRestart = $("sit-restart");

  var scope = { lga: -1, ward: -1, pu: -1 };
  var partyRows = [], factEls = {}, puOpts = [];

  function buildParties() {
    elParties.innerHTML = ""; partyRows = [];
    PARTIES.forEach(function (p) {
      var li = el("li", "sit-party");
      li.style.setProperty("--c", p.color);
      var head = el("div", "sit-party-head");
      head.appendChild(el("span", "sit-dot"));
      head.appendChild(el("span", "sit-party-name", p.name));
      var lead = el("span", "sit-lead", "Leading"); lead.hidden = true;
      head.appendChild(lead);
      var votes = el("strong", "sit-party-votes", "0");
      var share = el("span", "sit-party-share", "0.0%");
      head.appendChild(votes); head.appendChild(share);
      var bar = el("div", "sit-bar-track"), fill = el("div", "sit-bar-fill");
      bar.appendChild(fill);
      li.appendChild(head); li.appendChild(bar);
      elParties.appendChild(li);
      partyRows.push({ li: li, votes: votes, share: share, fill: fill, lead: lead });
    });
  }

  function buildStatic() {
    LGAS.forEach(function (l, i) {
      var o = el("option", null, l.name); o.value = i; lgaSel.appendChild(o);
    });
    buildParties();
    [["reg", "Registered voters"], ["valid", "Valid votes"], ["turn", "Turnout"]].forEach(function (f) {
      var wrap = el("div"); wrap.appendChild(el("dt", null, f[1]));
      var dd = el("dd", null, "0"); wrap.appendChild(dd); elFacts.appendChild(wrap);
      factEls[f[0]] = dd;
    });
  }

  /* ---------- rendering ---------- */
  function curLga() { return scope.lga >= 0 ? model.lgas[scope.lga] : null; }
  function curWard() { return scope.ward >= 0 ? model.lgas[scope.lga].wards[scope.ward] : null; }
  function curPu() { return scope.pu >= 0 ? curWard().pus[scope.pu] : null; }

  function scopeTotals() {
    if (scope.lga < 0) return model.state;
    if (scope.ward < 0) return curLga().tot;
    if (scope.pu < 0) return curWard().tot;
    var pu = curPu(), t = blank();
    t.n = 1;
    if (pu.res) add(t, pu.res, 1);
    return t;
  }

  function renderTotals() {
    var s = model.state, wardsRep = 0;
    model.lgas.forEach(function (l) {
      l.wards.forEach(function (w) { if (w.tot.rep > 0) wardsRep++; });
    });
    setNum($("sit-total-votes"), s.valid + s.rej);
    setNum($("sit-total-pus"), s.rep);
    $("sit-total-pus-all").textContent = fmt(s.n);
    setNum($("sit-total-wards"), wardsRep);
    $("sit-total-wards-all").textContent = model.wardsTotal;
  }

  function renderScope() {
    var t = scopeTotals(), title, sub, pu = curPu();
    if (scope.lga < 0) { title = CFG.state_name + " State"; sub = "All " + LGAS.length + " LGAs \u00B7 " + model.wardsTotal + " wards"; }
    else if (scope.ward < 0) {
      var l = curLga(); title = l.name + " LGA"; sub = l.wards.length + " wards";
    } else if (!pu) {
      var w = curWard(); title = w.name; sub = curLga().name + " LGA \u00B7 ward";
    } else {
      title = curWard().name + " \u00B7 " + puLabel(pu);
      sub = curLga().name + " LGA \u00B7 " + pu.code;
    }
    elTitle.textContent = title;
    if (pu) {
      elSub.textContent = sub + " \u00B7 " + (pu.res
        ? "result received from " + pu.res.rep + (pu.res.time ? " at " + pu.res.time : "")
        : "awaiting result");
    } else {
      elSub.textContent = sub + " \u00B7 " + fmt(t.rep) + " of " + fmt(t.n) + " polling units reported (" + pct(t.rep, t.n).toFixed(0) + "%)";
    }
    elFill.style.width = pct(t.rep, t.n) + "%";

    var top = -1, max = 0;
    for (var i = 0; i < PARTIES.length; i++) if (t.votes[i] > max) { max = t.votes[i]; top = i; }
    PARTIES.forEach(function (p, i) {
      var r = partyRows[i];
      setNum(r.votes, t.votes[i]);
      var share = pct(t.votes[i], t.valid);
      r.share.textContent = share.toFixed(1) + "%";
      r.fill.style.width = share + "%";
      r.lead.hidden = i !== top;
      r.li.classList.toggle("is-lead", i === top);
    });
    // A single polling unit shows its registered voters even before its result arrives.
    setNum(factEls.reg, pu && !pu.res ? pu.reg : t.reg);
    setNum(factEls.valid, t.valid);
    factEls.turn.textContent = pct(t.acc, t.reg).toFixed(1) + "%";
  }

  function chips(votes) {
    var wrap = el("span", "sit-chips");
    votes.forEach(function (v, i) {
      var c = el("span", "sit-chip"); c.style.setProperty("--c", PARTIES[i].color);
      c.appendChild(el("b", null, PARTIES[i].short)); c.appendChild(document.createTextNode(" " + fmt(v)));
      wrap.appendChild(c);
    });
    return wrap;
  }

  function renderFeed() {
    elFeed.innerHTML = "";
    var where = scope.lga < 0 ? CFG.state_name + " State" : (scope.ward < 0 ? curLga().name : (scope.pu < 0 ? curWard().name : puLabel(curPu())));
    elFeedTitle.textContent = "Latest submissions \u00B7 " + where;
    var shown = 0, pu = scope.pu >= 0 ? curPu() : null;
    for (var i = 0; i < model.history.length && shown < 3; i++) {
      var h = model.history[i];
      if (scope.lga >= 0 && h.lga.i !== scope.lga) continue;
      if (scope.ward >= 0 && h.ward.idx !== scope.ward) continue;
      if (pu && h.pu !== pu) continue;
      var li = el("li", "sit-item" + (h.fresh ? " fresh" : ""));
      var top = el("div", "sit-item-top");
      top.appendChild(el("strong", null, h.ward.name + " \u00B7 PU " + z(h.pu.num, 3)));
      top.appendChild(el("span", "sit-item-meta", h.res.rep + (h.res.time ? " \u00B7 " + h.res.time : "")));
      li.appendChild(top); li.appendChild(chips(h.res.votes));
      elFeed.appendChild(li); shown++;
    }
    if (!shown) elFeed.appendChild(el("li", "sit-item pending", "Waiting for results\u2026"));
  }

  function renderAll() { renderTotals(); renderScope(); renderFeed(); updatePuMarks(); }

  /* ---------- selectors ---------- */
  function fillWards() {
    wardSel.innerHTML = "";
    var o = el("option", null, "All wards"); o.value = ""; wardSel.appendChild(o);
    if (scope.lga >= 0) {
      model.lgas[scope.lga].wards.forEach(function (w, i) {
        var op = el("option", null, w.name); op.value = i; wardSel.appendChild(op);
      });
    }
    wardWrap.hidden = scope.lga < 0;
    wardSel.value = scope.ward >= 0 ? scope.ward : "";
  }

  function fillPus() {
    puSel.innerHTML = ""; puOpts = [];
    var o = el("option", null, "All polling units"); o.value = ""; puSel.appendChild(o);
    if (scope.lga >= 0 && scope.ward >= 0) {
      curWard().pus.forEach(function (pu, i) {
        var op = el("option", null, puLabel(pu)); op.value = i; puSel.appendChild(op);
        puOpts.push(op);
      });
    }
    puWrap.hidden = !(scope.lga >= 0 && scope.ward >= 0);
    puSel.value = scope.pu >= 0 ? scope.pu : "";
  }

  // Tick the polling units that already have a result (updates text in place, so an open list is not disturbed).
  function updatePuMarks() {
    if (scope.lga < 0 || scope.ward < 0) return;
    var pus = curWard().pus;
    puOpts.forEach(function (op, i) {
      var txt = puLabel(pus[i]) + (pus[i].res ? "  \u2713" : "");
      if (op.textContent !== txt) op.textContent = txt;
    });
  }

  function selectScope(l, w, p) {
    scope.lga = l; scope.ward = w; scope.pu = p;
    lgaSel.value = l >= 0 ? l : "";
    fillWards(); fillPus(); renderAll();
  }
  // After the data is rebuilt keep the user's place if it still exists.
  function restoreScope() {
    if (scope.lga >= model.lgas.length) scope.lga = -1;
    if (scope.lga < 0) { scope.ward = -1; scope.pu = -1; }
    else if (scope.ward >= model.lgas[scope.lga].wards.length) { scope.ward = -1; scope.pu = -1; }
    else if (scope.ward >= 0 && scope.pu >= curWard().pus.length) scope.pu = -1;
    lgaSel.value = scope.lga >= 0 ? scope.lga : "";
    fillWards(); fillPus();
  }

  lgaSel.addEventListener("change", function () {
    selectScope(lgaSel.value === "" ? -1 : +lgaSel.value, -1, -1);
  });
  wardSel.addEventListener("change", function () {
    selectScope(scope.lga, wardSel.value === "" ? -1 : +wardSel.value, -1);
  });
  puSel.addEventListener("change", function () {
    selectScope(scope.lga, scope.ward, puSel.value === "" ? -1 : +puSel.value);
  });

  /* ---------- simulation loop ---------- */
  var timer = null, userPaused = false, visible = false, restartTimer = null;

  function simTick() {
    if (mode !== "sim" || !model) return;
    var left = model.order.length - model.pos;
    if (left <= 0) return simFinish();
    model.history.forEach(function (h) { h.fresh = false; });
    var batch = Math.min(left, 5 + Math.floor(Math.random() * 10));
    for (var i = 0; i < batch; i++) simSubmit(model.order[model.pos++]);
    elClock.textContent = "Updated " + clock();
    renderAll();
    if (model.pos >= model.order.length) simFinish();
  }

  function simFinish() {
    simStop();
    root.classList.add("complete");
    elClock.textContent = "Collation complete \u00B7 " + clock();
    clearTimeout(restartTimer);
    restartTimer = setTimeout(function () { if (mode === "sim" && !userPaused) simRestart(); }, 15000);
  }

  function simStart() {
    if (mode !== "sim" || timer || userPaused || !visible || !model || model.pos >= model.order.length) return;
    timer = setInterval(simTick, 900);
  }
  function simStop() { clearInterval(timer); timer = null; }

  function simRestart() {
    clearTimeout(restartTimer); simStop();
    root.classList.remove("complete");
    model = buildSim((Date.now() & 0x7fffffff) || 1);
    restoreScope();
    elClock.textContent = "Waiting for first results\u2026";
    renderAll();
    if (visible && !userPaused) { simTick(); simStart(); }
  }

  /* ---------- live loop ---------- */
  function api(path) {
    return fetch(CFG.api + path, { cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }

  function liveStop() { clearTimeout(live.timer); live.timer = null; }
  function liveSchedule(ms) {
    liveStop();
    if (mode !== "live" || userPaused || !visible) return;
    live.timer = setTimeout(livePoll, ms == null ? CFG.refresh_seconds * 1000 : ms);
  }

  function enterLive() {
    var gen = ++live.gen;
    simStop(); clearTimeout(restartTimer); liveStop();
    mode = "live"; live.ready = false; live.cursor = null; live.fails = 0; live.busy = false;
    root.classList.remove("complete"); root.classList.add("is-live");
    elMode.textContent = "LIVE \u2022 Polling-unit results";
    btnRestart.hidden = true;
    elClock.textContent = "Connecting to live results\u2026";
    Promise.all([api("/public/config/"), api("/public/structure/")]).then(function (res) {
      if (gen !== live.gen) return;
      var cfg = res[0], structure = res[1];
      if (cfg.mode !== "live") return enterSim();
      CFG.refresh_seconds = cfg.refresh_seconds || CFG.refresh_seconds;
      if (!cfg.election) {
        elClock.textContent = "Live mode is on but no election is set up yet.";
        live.timer = setTimeout(enterLive, 15000);
        return;
      }
      live.electionId = cfg.election.id;
      PARTIES = cfg.election.candidates.map(function (c) {
        return { name: c.name, short: c.short_name, color: c.color };
      });
      buildParties();
      model = buildLive(structure);
      restoreScope();
      live.ready = true;
      elClock.textContent = structure.total_polling_units
        ? "Waiting for first results\u2026"
        : "Live mode is on but polling units are not loaded yet.";
      renderAll();
      livePoll();
    }).catch(function () {
      if (gen !== live.gen) return;
      elClock.textContent = "Live results unavailable \u00B7 retrying\u2026";
      live.timer = setTimeout(enterLive, 10000);     // never fall back to simulated numbers
    });
  }

  function livePoll() {
    if (mode !== "live" || !live.ready || live.busy || userPaused || !visible) return;
    live.busy = true;
    var gen = live.gen;
    api("/public/results/" + (live.cursor ? "?since=" + encodeURIComponent(live.cursor) : "")).then(function (data) {
      live.busy = false;
      if (gen !== live.gen) return;
      if (data.mode !== "live") return enterSim();
      if (data.election_id !== live.electionId) return enterLive();      // a different election is now current
      live.fails = 0;
      var changed = applyLive(data);
      live.cursor = data.cursor;
      // Safety net: if our count differs from the server's, download everything again next time.
      if (model.state.rep !== data.public_count) live.cursor = null;
      elClock.textContent = "Updated " + clock();
      if (changed || data.full) renderAll();
      liveSchedule();
    }).catch(function () {
      live.busy = false;
      if (gen !== live.gen) return;
      live.fails++;
      elClock.textContent = "Connection problem \u00B7 showing last results \u00B7 retrying\u2026";
      liveSchedule(Math.min(30000, 3000 * live.fails));
    });
  }

  function enterSim() {
    live.gen++; liveStop(); live.ready = false; live.busy = false;
    mode = "sim";
    root.classList.remove("is-live", "complete");
    elMode.textContent = "LIVE \u2022 Results simulation";
    btnRestart.hidden = false;
    PARTIES = SIM_PARTIES; buildParties();
    simRestart();
  }

  // While showing the simulation, notice if an administrator switches to live.
  setInterval(function () {
    if (mode !== "sim" || document.hidden) return;
    api("/public/config/").then(function (cfg) { if (cfg.mode === "live" && mode === "sim") enterLive(); }).catch(function () {});
  }, 30000);

  /* ---------- controls ---------- */
  btnPause.addEventListener("click", function () {
    userPaused = !userPaused;
    btnPause.textContent = userPaused ? "Resume" : "Pause";
    btnPause.setAttribute("aria-pressed", userPaused ? "true" : "false");
    root.classList.toggle("paused", userPaused);
    if (mode === "live") { if (userPaused) liveStop(); else livePoll(); return; }
    if (userPaused) simStop();
    else if (model.pos >= model.order.length) simRestart(); else simStart();
  });
  btnRestart.addEventListener("click", function () {
    if (mode !== "sim") return;
    userPaused = false; btnPause.textContent = "Pause"; btnPause.setAttribute("aria-pressed", "false");
    root.classList.remove("paused");
    simRestart();
  });

  /* ---------- boot ---------- */
  buildStatic();
  if (CFG.mode === "live") {
    // Never start the sample data: go straight to the real results.
    model = newModel();
    renderAll();
    enterLive();
  } else {
    model = buildSim((Date.now() & 0x7fffffff) || 1);
    elClock.textContent = "Waiting for first results\u2026";
    renderAll();
  }

  function setVisible(v) {
    visible = v;
    if (mode === "live") { if (v) livePoll(); else liveStop(); return; }
    if (v) { if (model.pos === 0) simTick(); simStart(); } else simStop();
  }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      setVisible(entries[0].isIntersecting && !document.hidden);
    }, { threshold: 0.05 }).observe(root);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { if (mode === "live") liveStop(); else simStop(); }
      else if (visible) { if (mode === "live") livePoll(); else simStart(); }
    });
  } else {
    setVisible(true);
  }
})();
