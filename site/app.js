/* Prefill & the Frame: tabs, scroll reveals, tables built from data.js, and the frame-replay demo. */
(() => {
  const D = window.DART_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const E4 = Object.fromEntries(D.e4.map(c => [c.condition, c]));
  const REPLAY = Object.fromEntries(D.replays.map(r => [r.condition, r]));
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ── formatting ──
  const pct = v => v == null ? "—" : (v >= 10 ? v.toFixed(1) : v.toFixed(v === 0 ? 0 : 1)) + "%";
  const ms = v => v == null ? "—" : v.toFixed(1) + " ms";
  const secs = v => v == null ? "—" : (v >= 100000 ? Math.round(v / 1000) : (v / 1000).toFixed(1)) + " s";
  const tps = v => v == null ? "—" : v.toFixed(1);
  const int = v => v == null ? "—" : Math.round(v).toLocaleString("en-US");
  const ph = (c, phase, k) => c && c.phases[phase] ? c.phases[phase][k] : null;
  const ttft = c => c && c.ttft ? c.ttft.median : null;
  const delta = (a, b) => a && b ? (b / a - 1) * 100 : null;
  const signed = v => v == null ? "—" : (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(0) + "%";
  const meter = (v, max = 85) => {
    if (v == null) return "—";
    const cls = v >= 5 ? "hot" : v <= 2 ? "ok" : "";
    return `<span class="meter ${cls}"><span>${pct(v)}</span><i><b style="width:${Math.min(100, v / max * 100)}%"></b></i></span>`;
  };
  const table = (el, head, rows, numeric) => {
    const th = head.map((h, i) => `<th class="${numeric(i) ? "n" : ""}">${h}</th>`).join("");
    const tr = rows.map(r => `<tr>${r.map((v, i) => `<td class="${numeric(i) ? "n" : ""}">${v}</td>`).join("")}</tr>`).join("");
    $(el).innerHTML = `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  };
  const numFrom = k => i => i >= k;

  // ── pages ──
  const PAGES = [
    ["aquarium", "WebGL Aquarium", "20,000 fish", "7B-Q4 gpu ub512 @aquarium", "7B-Q4 gpu ub64 @aquarium", "no-model aquarium"],
    ["heavy", "Shader page", "raymarch + scroll", "7B-Q4 gpu ub512 heavy-page", "7B-Q4 gpu ub64 heavy-page", "no-model heavy"],
    ["arcs", "MotionMark Arcs", "canvas, complexity 10k", "7B-Q4 gpu ub512 @mm-arcs", "7B-Q4 gpu ub64 @mm-arcs", "no-model mm-arcs"],
    ["safari", "Safari, shader page", "WebKit at 60 Hz", "7B-Q4 gpu ub512 safari-heavy", "7B-Q4 gpu ub64 safari-heavy", "no-model safari-heavy"],
    ["multiply", "MotionMark Multiply", "CPU-bound DOM, 3–4% idle", "7B-Q4 gpu ub512 @mm-multiply", "7B-Q4 gpu ub64 @mm-multiply", "no-model mm-multiply"],
    ["bbc", "BBC News", "scrolling", "7B-Q4 gpu ub512 @bbc", "7B-Q4 gpu ub64 @bbc", "no-model bbc"],
    ["light", "Light page", "WebGL + scroll", "7B-Q4 gpu ub512", "7B-Q4 gpu ub64", "no-model light"],
  ];

  // ── findings: stats, marquee, bars ──
  const R = D.records;
  const h512 = E4["7B-Q4 gpu ub512 heavy-page"], h64 = E4["7B-Q4 gpu ub64 heavy-page"];
  const aq = E4["7B-Q4 gpu ub512 @aquarium"];
  $("#headline-stats").innerHTML = [
    [pct(ph(aq, "prefill", "dropped_pct")), "bad", "of frames dropped on WebGL Aquarium while 7B reads a 4,000-token page (0% idle)"],
    [`${pct(ph(h512, "prefill", "dropped_pct"))} → ${pct(ph(h64, "prefill", "dropped_pct"))}`, "", "on the shader page, from batch 512 to batch 64"],
    [signed(delta(ttft(h512), ttft(h64))), "", "time to first token for that fix (11.5 s → 12.8 s)"],
    [pct(ph(E4["14B-Q4 gpu ub64 heavy-page"], "prefill", "dropped_pct")), "bad", "still dropped by 14B at batch 64, the stand-in for a base M2"],
  ].map(([n, c, t], i) => `<div class="stat rv d${i % 4}"><div class="num ${c}">${n}</div><p class="muted small">${t}</p></div>`).join("");

  const mq = [
    [`${R.trials}`, "measured trials"], [`${R.errors}`, "errors"], [`${R.sessions}`, "sessions"], [`${R.hours} h`, "of runs"],
    [int(R.tokens_prefilled), "prompt tokens"], [int(R.tokens_generated), "generated tokens"],
    [D.e4.length, "E4 conditions"], ["0%", "decode drops on GPU-heavy pages"],
  ].map(([b, t]) => `<span><b>${b}</b> ${t}</span>`).join("");
  $("#marquee").innerHTML = mq + mq;

  $("#page-bars").innerHTML = PAGES.map(([, name, sub, a, b]) => {
    const va = ph(E4[a], "prefill", "dropped_pct"), vb = ph(E4[b], "prefill", "dropped_pct");
    return `<div class="bar-row"><div class="name">${name}<small>${sub}</small></div><div class="bar-pair">
      <div class="bar def"><div class="track"><div class="fill" data-w="${va}"></div></div><span class="v">${pct(va)}</span></div>
      <div class="bar fix"><div class="track"><div class="fill" data-w="${vb}"></div></div><span class="v">${pct(vb)}</span></div></div></div>`;
  }).join("");

  // ── report ──
  $("#rep-lede").textContent = `${R.trials} measured trials across ${R.sessions} sessions and ${R.hours} hours, with ${R.errors} errors. `
    + `${int(R.tokens_prefilled)} prompt tokens and ${int(R.tokens_generated)} generated tokens. Every table below is built from the same SQLite database as bench/reports/report.md (generated ${D.generated}).`;
  const M = D.machine;
  const hz = (M.displays || [])[0]?._spdisplays_resolution?.split("@")[1]?.trim() || "120 Hz";
  $("#machine-kv").innerHTML = [
    ["Machine", `${M.chip}, ${M.ram_gb} GB`], ["CPU · GPU", `${M.perf_cores}P + ${M.eff_cores}E cores · ${M.gpu_cores}-core GPU`],
    ["Display", `built-in, ${hz}`], ["OS", `macOS ${M.macos}`], ["Runtime", `llama.cpp ${M.llama_cpp}`],
    ["Browser", `Brave ${M.brave}, Safari`], ["Models", "Qwen 2.5 Instruct 3B · 7B · 14B"],
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");

  table("#t-pages", ["Page", "Idle", "Prefill · 512", "p95 · 512", "Decode · 512", "Prefill · 64", "TTFT · 512", "TTFT · 64", "Cost of 64"],
    PAGES.map(([, name, sub, a, b, idle]) => {
      const A = E4[a], B = E4[b];
      return [`${name}<br><span class="muted small">${sub}</span>`, pct(ph(E4[idle], "idle", "dropped_pct")), meter(ph(A, "prefill", "dropped_pct")),
        ms(ph(A, "prefill", "p95")), pct(ph(A, "decode", "dropped_pct")), meter(ph(B, "prefill", "dropped_pct")),
        secs(ttft(A)), secs(ttft(B)), signed(delta(ttft(A), ttft(B)))];
    }), numFrom(1));

  table("#t-models", ["Model", "Light · 512", "Shader · 512", "p95", "LoAF/s", "Shader · 64", "p95", "TTFT · 512", "TTFT · 64"],
    ["3B", "7B", "14B"].map(m => {
      const L = E4[`${m}-Q4 gpu ub512`], A = E4[`${m}-Q4 gpu ub512 heavy-page`], B = E4[`${m}-Q4 gpu ub64 heavy-page`];
      return [`${m} Q4_K_M`, meter(ph(L, "prefill", "dropped_pct")), meter(ph(A, "prefill", "dropped_pct")), ms(ph(A, "prefill", "p95")),
        tps(ph(A, "prefill", "loaf_per_s")), meter(ph(B, "prefill", "dropped_pct")), ms(ph(B, "prefill", "p95")), secs(ttft(A)), secs(ttft(B))];
    }), numFrom(1));

  const sweep = [
    ["light", "ubatch 32", "7B-Q4 gpu ub32"], ["light", "ubatch 64", "7B-Q4 gpu ub64"], ["light", "ubatch 128", "7B-Q4 gpu ub128"],
    ["light", "ubatch 256", "7B-Q4 gpu ub256"], ["light", "ubatch 512 (default)", "7B-Q4 gpu ub512"], ["light", "ubatch 1024", "7B-Q4 gpu ub1024"],
    ["light", "ubatch 2048", "7B-Q4 gpu ub2048"], ["light", "paced c256 g16", "7B-Q4 paced c256 g16"], ["light", "paced c128 g0", "7B-Q4 paced c128 g0"],
    ["light", "paced c128 g16", "7B-Q4 paced c128 g16"], ["light", "paced c128 g50", "7B-Q4 paced c128 g50"], ["light", "paced c64 g16", "7B-Q4 paced c64 g16"],
    ["shader", "ubatch 512 (default)", "7B-Q4 gpu ub512 heavy-page"], ["shader", "ubatch 128", "7B-Q4 gpu ub128 heavy-page"],
    ["shader", "ubatch 64", "7B-Q4 gpu ub64 heavy-page"], ["shader", "paced c128 g16", "7B-Q4 paced c128 g16 heavy-page"],
    ["shader", "paced c128 g50", "7B-Q4 paced c128 g50 heavy-page"], ["shader", "paced c64 g0", "7B-Q4 paced c64 g0 heavy-page"],
    ["shader", "paced c64 g16", "7B-Q4 paced c64 g16 heavy-page"], ["shader", "paced c64 g50", "7B-Q4 paced c64 g50 heavy-page"],
    ["shader", "paced c32 g0", "7B-Q4 paced c32 g0 heavy-page"], ["shader", "CPU only (-ngl 0)", "7B-Q4 cpu-only heavy-page"],
    ["aquarium", "paced c64 g16", "7B-Q4 paced c64 g16 @aquarium"], ["arcs", "paced c64 g16", "7B-Q4 paced c64 g16 @mm-arcs"],
    ["bbc", "paced c64 g16", "7B-Q4 paced c64 g16 @bbc"],
  ];
  const base = { light: "7B-Q4 gpu ub512", shader: "7B-Q4 gpu ub512 heavy-page", aquarium: "7B-Q4 gpu ub512 @aquarium",
    arcs: "7B-Q4 gpu ub512 @mm-arcs", bbc: "7B-Q4 gpu ub512 @bbc" };
  table("#t-sweep", ["Page", "Setting", "Prefill", "p95", "Decode", "TTFT", "vs 512"],
    sweep.filter(r => E4[r[2]]).map(([pg, label, c]) => {
      const C = E4[c];
      return [pg, label, meter(ph(C, "prefill", "dropped_pct")), ms(ph(C, "prefill", "p95")), pct(ph(C, "decode", "dropped_pct")),
        secs(ttft(C)), signed(delta(ttft(E4[base[pg]]), ttft(C)))];
    }), numFrom(2));

  const eng = [
    ["Safari · shader · ubatch 512", "7B-Q4 gpu ub512 safari-heavy", "17 ms"], ["Safari · shader · ubatch 64", "7B-Q4 gpu ub64 safari-heavy", "17 ms"],
    ["Safari · light · ubatch 512", "7B-Q4 gpu ub512 safari-light", "17 ms"], ["Multiply · GPU · ubatch 512", "7B-Q4 gpu ub512 @mm-multiply", "8.3 ms"],
    ["Multiply · GPU · ubatch 64", "7B-Q4 gpu ub64 @mm-multiply", "8.3 ms"], ["Multiply · CPU only, 8 threads (default)", "7B-Q4 cpu-only @mm-multiply", "8.3 ms"],
    ["Multiply · CPU only, 4 threads", "7B-Q4 cpu-only t4 @mm-multiply", "8.3 ms"],
  ];
  table("#t-engines", ["Condition", "Budget", "Idle", "Prefill", "p95", "Decode", "TTFT", "Decode tok/s"],
    eng.map(([label, c, b]) => {
      const C = E4[c];
      return [label, b, pct(ph(C, "idle", "dropped_pct")), meter(ph(C, "prefill", "dropped_pct")), ms(ph(C, "prefill", "p95")),
        meter(ph(C, "decode", "dropped_pct")), secs(ttft(C)), tps(C?.gen_tps?.median)];
    }), numFrom(1));

  const pass = v => v == null ? "—" : v ? '<span class="chip good">pass</span>' : '<span class="chip bad">fail</span>';
  table("#t-e1", ["Model", "Context", "TTFT", "Prompt tok/s", "Decode tok/s", "Memory", "TTFT ≤ 900 ms", "≥ 18 tok/s", "≤ 60% RAM"],
    D.e1.map(r => [r.model, int(r.ctx), secs(r.ttft?.median), tps(r.prompt_tps?.median), tps(r.gen_tps?.median),
      `${(r.mem_mb / 1024).toFixed(1)} GB · ${(r.mem_frac * 100).toFixed(0)}%`, pass(r.pass?.ttft), pass(r.pass?.gen_tps), pass(r.pass?.mem)]),
    numFrom(1));

  table("#t-e1b", ["Model", "Cold", "Cached", "Speed-up"],
    D.e1b.map(r => [r.model, secs(r.cold?.median), ms(r.warm?.median), `${Math.round(r.speedup)}×`]), numFrom(1));

  table("#t-e0", ["Model", "pp512", "pp4096", "tg128", "4k implied"],
    D.e0.map(r => [r.model.replace("~battery", " (battery)"), tps(r.pp512), tps(r.pp4096), tps(r.tg128), secs(r.implied_ttft_4k_ms)]), numFrom(1));

  table("#t-e2", ["Model", "Ballast", "Decode tok/s", "Slowdown", "TTFT", "Pages swapped out", "Peak pressure"],
    D.e2.flatMap(m => m.levels.map(l => [m.model, `${l.ballast_gb} GB`, tps(l.gen_tps?.median), `${(l.tps_penalty_x || 1).toFixed(2)}×`,
      secs(l.ttft?.median), int(l.swapouts), l.pressure_max ?? "—"])), numFrom(1));

  const dec = D.decision;
  $("#dec-verdict").textContent = dec.verdict;
  $("#dec-why").textContent = `The worst page decides. ${dec.why}.`;
  $("#dec-orig").textContent = dec.original?.why || "";

  table("#t-all", ["Condition", "Page", "Budget", "Idle", "Prefill", "p95", "Max", "LoAF/s", "Decode", "TTFT", "Decode tok/s"],
    D.e4.map(c => [c.condition, c.load, `${c.budget_ms} ms`, pct(ph(c, "idle", "dropped_pct")), pct(ph(c, "prefill", "dropped_pct")),
      ms(ph(c, "prefill", "p95")), ms(ph(c, "prefill", "max")), tps(ph(c, "prefill", "loaf_per_s")), pct(ph(c, "decode", "dropped_pct")),
      secs(ttft(c)), tps(c.gen_tps?.median)]), numFrom(2));
  $("#foot-gen").textContent = `data generated ${D.generated} · ${D.db}`;

  // ── stage 2 ──
  const fix = [
    ["3B · shader page", "3B-Q4 gpu ub512 heavy-page", "3B-Q4 gpu ub64 heavy-page"],
    ["7B · shader page", "7B-Q4 gpu ub512 heavy-page", "7B-Q4 gpu ub64 heavy-page"],
    ["7B · WebGL Aquarium", "7B-Q4 gpu ub512 @aquarium", "7B-Q4 gpu ub64 @aquarium"],
    ["7B · MotionMark Arcs", "7B-Q4 gpu ub512 @mm-arcs", "7B-Q4 gpu ub64 @mm-arcs"],
    ["7B · Safari, shader page", "7B-Q4 gpu ub512 safari-heavy", "7B-Q4 gpu ub64 safari-heavy"],
    ["7B · BBC News", "7B-Q4 gpu ub512 @bbc", "7B-Q4 gpu ub64 @bbc"],
    ["14B · shader page", "14B-Q4 gpu ub512 heavy-page", "14B-Q4 gpu ub64 heavy-page"],
  ];
  table("#t-fix", ["Model · page", "Batch 512", "Batch 64", "TTFT cost"],
    fix.map(([l, a, b]) => [l, meter(ph(E4[a], "prefill", "dropped_pct")), meter(ph(E4[b], "prefill", "dropped_pct")),
      signed(delta(ttft(E4[a]), ttft(E4[b])))]), numFrom(1));

  const chips = [
    ["M1", 7, 107.81, "worse than the proxy: safe batch ≈ 16–20"], ["M1", 8, 117.96, "worse than the proxy: safe batch ≈ 16–20"],
    ["M2", 8, 145.91, "between the proxy and M1: ≈ 24–32"], ["M2", 10, 179.57, "≈ the 14B proxy: ~30% dropped at 64, safe ≈ 32"],
    ["M3", 10, 186.75, "≈ the 14B proxy: ~30% dropped at 64, safe ≈ 32"], ["M4", 10, 221.29, "between: 64 is borderline"],
    ["M1 Pro", 16, 266.25, "close to measured: 64 probably fine"], ["M4 Pro", 16, 364.06, "<b>measured</b>: 1.3% at 64"],
    ["M4 Pro", 20, 439.78, "faster than measured"],
  ];
  table("#t-chips", ["Chip", "GPU cores", "pp512 tok/s", "Slower than this M4 Pro", "7B at batch 64 (predicted)"],
    chips.map(([c, g, p, n]) => [c, g, tps(p), `${(364.06 / p).toFixed(2)}×`, `<span class="${n.startsWith("<b>") ? "" : "muted"}">${n}</span>`]),
    i => i === 1 || i === 2 || i === 3);

  // ── tabs + reveal ──
  const io = "IntersectionObserver" in window ? new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    $$(".fill[data-w]", e.target).forEach(f => f.style.width = Math.max(0.6, Math.min(100, +f.dataset.w / 85 * 100)) + "%");
    io.unobserve(e.target);
  }), { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }) : null;
  const reveal = root => $$(".rv", root).forEach(el => io ? io.observe(el) : el.classList.add("in"));
  if (!io || reduce) $$(".fill[data-w]").forEach(f => f.style.width = Math.max(0.6, Math.min(100, +f.dataset.w / 85 * 100)) + "%");

  const TABS = ["findings", "report", "stage2", "application"];
  let current = null;
  function route() {
    const h = location.hash.slice(1);
    const tab = TABS.includes(h) ? h : (h && document.getElementById(h)?.closest("[data-view]")?.dataset.view) || "findings";
    if (tab !== current) {
      $$("[data-view]").forEach(v => v.hidden = v.dataset.view !== tab);
      $$(".tabs a").forEach(a => a.setAttribute("aria-current", a.dataset.tab === tab ? "page" : "false"));
      const v = $(`[data-view="${tab}"]`);
      v.style.animation = "none"; void v.offsetWidth; v.style.animation = "";
      reveal(v);
      current = tab;
      if (TABS.includes(h) || !h) scrollTo({ top: 0, behavior: "instant" });
    }
    if (h && !TABS.includes(h)) document.getElementById(h)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
    if (tab === "findings") demo.resize();
  }

  $("#copy-email").addEventListener("click", e => {
    const t = $("#email").textContent;
    navigator.clipboard?.writeText(t).then(() => { e.target.textContent = "Copied"; setTimeout(() => e.target.textContent = "Copy", 1600); })
      .catch(() => getSelection().selectAllChildren($("#email")));
  });

  // ── demo: replay recorded rAF intervals ──
  const demo = (() => {
    const scene = $("#d-scene"), sc = scene.getContext("2d"), tl = $("#d-tl"), tc = tl.getContext("2d");
    const st = { machine: "m4", page: "heavy", model: "7B", batch: "512", speed: "1" };
    let rp = null, idleMed = 8.3, budget = 12.5, t0 = 0, playing = false, i = 0, lastT = 0, hover = null, outLen = 0;
    const ANSWER = "The page compares three ways to run a model next to a busy page. Reading it in one go fights the page for the GPU; " +
      "writing the answer one token at a time leaves room for every frame, so the stutter only shows up while the model reads.";

    function condFor() {
      const { machine, page, model, batch } = st;
      if (machine === "m2") return `14B-Q4 gpu ub${batch} heavy-page`;
      if (batch === "cpu") return "7B-Q4 cpu-only heavy-page";
      if (page === "aquarium") return `7B-Q4 gpu ub${batch} @aquarium`;
      if (page === "safari") return `7B-Q4 gpu ub${batch} safari-heavy`;
      return `${model}-Q4 gpu ub${batch} heavy-page`;
    }
    function allowed(k, v) {
      const s = { ...st, [k]: v };
      if (k === "machine" || k === "speed") return true;
      if (s.machine === "m2") return (k === "page" && v === "heavy") || (k === "model" && v === "7B") || (k === "batch" && (v === "512" || v === "64"));
      if (k === "page") return true;
      const c = (() => { const o = { ...st }; st[k] = v; const r = condFor(); Object.assign(st, o); return r; })();
      return !!REPLAY[c];
    }
    function normalise() {
      if (st.machine === "m2") Object.assign(st, { page: "heavy", model: "7B", batch: st.batch === "64" ? "64" : "512" });
      if (st.page !== "heavy") { st.model = "7B"; if (!["512", "64"].includes(st.batch)) st.batch = "512"; }
      if (st.batch === "cpu") st.model = "7B";
      if (!REPLAY[condFor()]) st.batch = "512";
    }
    function sync() {
      $$(".controls .seg").forEach(seg => {
        const k = seg.dataset.ctl;
        $$("button", seg).forEach(b => {
          b.setAttribute("aria-pressed", String(st[k] === b.dataset.v));
          b.disabled = !allowed(k, b.dataset.v);
        });
      });
    }
    function load() {
      normalise(); sync();
      const c = condFor(); rp = REPLAY[c];
      const C = E4[c];
      const lead = rp.frames.filter(f => f[0] < rp.phases[0][2]).map(f => f[1]).sort((a, b) => a - b);
      idleMed = lead.length ? lead[lead.length >> 1] : 8.3;
      budget = idleMed * 1.5;
      const pred = st.machine === "m2";
      $("#d-url").textContent = pred ? "bench/pages/heavy.html · predicted base M2 (14B on the M4 Pro as proxy)"
        : st.page === "aquarium" ? "webglsamples.org/aquarium · 20,000 fish" : st.page === "safari" ? "Safari · bench/pages/heavy.html" : "bench/pages/heavy.html";
      const pn = $("#d-pred");
      pn.hidden = !pred;
      pn.innerHTML = pred ? "<b>Predicted, not measured.</b> This replays 14B on the M4 Pro, which prefills about 2× slower than 7B. That's the same ratio as a 10-core M2 to this M4 Pro. A real Air also has a 60 Hz screen, which would hide some of these drops." : "";
      $("#r-cond").textContent = `${pct(ph(C, "prefill", "dropped_pct"))} prefill · ${pct(ph(C, "decode", "dropped_pct"))} decode`;
      $("#r-ttft").textContent = pred ? `${secs(ttft(C))} (14B here)` : secs(ttft(C));
      const name = pred ? "Base M2 (predicted)" : `${st.model} on the ${st.page === "aquarium" ? "Aquarium" : st.page === "safari" ? "shader page in Safari" : "shader page"}`;
      $("#d-cap").textContent = `${name}, ${st.batch === "cpu" ? "CPU only" : "batch " + st.batch}: trial ${rp.trial_id}, the middle of 5 measured trials, with ${rp.frames.length.toLocaleString()} recorded frames. `
        + (rp.truncated ? `The full prefill took ${secs(rp.prefill_ms)}, and this replay cuts it at 14 s. ` : "")
        + (st.page === "safari" ? "Safari ran at 60 Hz, so on-time frames are 17 ms apart. " : "")
        + "Your screen may refresh slower than the recorded 120 Hz, but every drop longer than one of your frames still shows.";
      start();
    }
    function start() { t0 = performance.now(); i = 0; lastT = 0; outLen = 0; playing = true; $("#d-out").innerHTML = ""; drawScene(0); }
    function phaseAt(t) { const p = rp.phases.find(([, a, b]) => t >= a && t < b); return p ? p[0] : "done"; }

    function resize() {
      for (const cv of [scene, tl]) {
        const r = cv.getBoundingClientRect(), dpr = Math.min(2, devicePixelRatio || 1);
        if (!r.width) continue;
        cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
        cv.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
      }
      if (rp) { drawScene(lastT); drawTimeline(clock()); }
    }
    const clock = () => playing ? (performance.now() - t0) * +st.speed : lastT;

    // a GPU-heavy-looking page whose motion is a pure function of the recorded frame time
    function drawScene(t) {
      const w = scene.clientWidth, h = scene.clientHeight, s = t / 1000;
      if (!w) return;
      const g = sc.createLinearGradient(0, 0, w, h);
      g.addColorStop(0, "#14162B"); g.addColorStop(1, "#2A1E3D");
      sc.fillStyle = g; sc.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2, R = Math.min(w, h) * .32;
      for (let k = 0; k < 14; k++) {
        const a = s * (0.9 + k * .07) + k * 0.45, r = R * (0.45 + 0.55 * Math.sin(k * 1.7 + s * .5) ** 2);
        const x = cx + Math.cos(a) * r * 1.35, y = cy + Math.sin(a * 1.1) * r * .8;
        const rg = sc.createRadialGradient(x, y, 0, x, y, 26 + k * 2);
        const hue = (220 + k * 18 + s * 30) % 360;
        rg.addColorStop(0, `hsla(${hue},85%,72%,.95)`); rg.addColorStop(1, `hsla(${hue},85%,60%,0)`);
        sc.fillStyle = rg; sc.beginPath(); sc.arc(x, y, 26 + k * 2, 0, 7); sc.fill();
      }
      sc.strokeStyle = "rgba(255,255,255,.55)"; sc.lineWidth = 2;
      sc.beginPath(); sc.arc(cx, cy, R * .5, s * 2.4, s * 2.4 + 4.2); sc.stroke();
      // scrolling article strip
      const off = (s * 60) % 44;
      sc.fillStyle = "rgba(255,255,255,.08)"; sc.fillRect(18, 0, 150, h);
      for (let y = -off; y < h; y += 44) {
        sc.fillStyle = "rgba(255,255,255,.55)"; sc.fillRect(30, y + 12, 110, 7);
        sc.fillStyle = "rgba(255,255,255,.25)"; sc.fillRect(30, y + 25, 126, 5); sc.fillRect(30, y + 33, 84, 5);
      }
      // a sweeping bar makes every missed frame visible as a jump
      const bx = 180 + ((s * 220) % Math.max(1, w - 200));
      sc.fillStyle = "rgba(255,255,255,.85)"; sc.fillRect(bx, h - 18, 34, 6);
    }

    function drawTimeline(now) {
      const w = tl.clientWidth, h = tl.clientHeight;
      if (!w || !rp) return;
      const end = rp.phases[rp.phases.length - 1][2], X = t => t / end * w, top = 18, base = h - 16, ymax = 60;
      const Y = v => base - Math.min(v, ymax) / ymax * (base - top);
      tc.clearRect(0, 0, w, h);
      const col = { idle: "#E7E7E7", prefill: "#FFD9C7", decode: "#CFF3E2" };
      for (const [p, a, b] of rp.phases) { tc.fillStyle = col[p]; tc.globalAlpha = .6; tc.fillRect(X(a), top, X(b) - X(a), base - top); }
      tc.globalAlpha = 1;
      tc.font = "500 10.5px 'DM Mono', monospace"; tc.fillStyle = "#696969";
      for (const [p, a] of rp.phases) tc.fillText(p.toUpperCase(), X(a) + 6, top + 12);
      tc.fillText("60 ms+", 4, top - 5);
      tc.strokeStyle = "#B3402D"; tc.setLineDash([3, 3]); tc.lineWidth = 1;
      tc.beginPath(); tc.moveTo(0, Y(budget)); tc.lineTo(w, Y(budget)); tc.stroke(); tc.setLineDash([]);
      tc.fillStyle = "#B3402D"; tc.fillText(`drop line ${budget.toFixed(1)} ms`, w - 120, Y(budget) - 4);
      for (const [t, d] of rp.frames) {
        const past = t <= now, drop = d > budget;
        tc.strokeStyle = drop ? "#B3402D" : "#696969"; tc.globalAlpha = past ? (drop ? 1 : .55) : .1;
        tc.lineWidth = drop ? 1.5 : 1;
        tc.beginPath(); tc.moveTo(X(t), base); tc.lineTo(X(t), Y(d)); tc.stroke();
      }
      tc.globalAlpha = 1;
      tc.fillStyle = "#9A9A9A";
      for (let s = 0; s * 1000 < end; s += end > 16000 ? 4 : 2) tc.fillText(`${s}s`, X(s * 1000) + 2, h - 3);
      tc.strokeStyle = "#141414"; tc.lineWidth = 1.5;
      tc.beginPath(); tc.moveTo(X(now), top - 4); tc.lineTo(X(now), base); tc.stroke();
      if (hover != null) {
        const t = hover / w * end;
        let best = null;
        for (const f of rp.frames) if (!best || Math.abs(f[0] - t) < Math.abs(best[0] - t)) best = f;
        if (best) {
          const lbl = `${(best[0] / 1000).toFixed(2)} s · ${best[1].toFixed(1)} ms${best[1] > budget ? " · dropped" : ""}`;
          tc.strokeStyle = "rgba(0,0,0,.35)"; tc.beginPath(); tc.moveTo(X(best[0]), top); tc.lineTo(X(best[0]), base); tc.stroke();
          const tw = tc.measureText(lbl).width + 12, lx = Math.min(w - tw, Math.max(0, X(best[0]) - tw / 2));
          tc.fillStyle = "#141414"; tc.fillRect(lx, 0, tw, 16); tc.fillStyle = "#fff"; tc.fillText(lbl, lx + 6, 11.5);
        }
      }
    }

    function tick() {
      requestAnimationFrame(tick);
      if (!rp || current !== "findings") return;
      const now = clock(), end = rp.phases[rp.phases.length - 1][2];
      let drew = false;
      while (i < rp.frames.length && rp.frames[i][0] <= now) { lastT = rp.frames[i][0]; i++; drew = true; }
      if (drew) drawScene(lastT);
      if (playing && now >= end) { playing = false; lastT = end; }
      drawTimeline(playing ? now : end);
      // readouts
      const p = playing ? phaseAt(now) : "done";
      const pre = rp.phases[1], seen = rp.frames.slice(0, i);
      const recent = seen.filter(f => f[0] > now - 500).length;
      const fps = Math.round(recent * 2);
      const badge = $("#d-fps");
      badge.textContent = playing ? `${fps} fps` : "—"; badge.classList.toggle("bad", playing && seen.length > 0 && seen[seen.length - 1][1] > budget * 1.3);
      const inPre = seen.filter(f => f[0] >= pre[1] && f[0] < pre[2]);
      const drops = inPre.filter(f => f[1] > budget).length;
      $("#r-phase").textContent = p;
      $("#r-drop").textContent = inPre.length ? `${drops} of ${inPre.length} · ${(drops / inPre.length * 100).toFixed(0)}%` : "—";
      $("#r-worst").textContent = inPre.length ? ms(Math.max(...inPre.map(f => f[1]))) : "—";
      const stEl = $("#d-status");
      stEl.className = "status " + (p === "prefill" ? "prefill" : p === "decode" || p === "done" ? "decode" : "");
      const span = pre[2] - pre[1], frac = rp.truncated ? 14000 / rp.prefill_ms : 1;
      const prog = p === "idle" ? 0 : p === "prefill" ? (now - pre[1]) / span * frac : 1;
      $("#d-prog").style.width = (prog * 100).toFixed(1) + "%";
      $("#d-tokens").textContent = `${Math.round(prog * 4000).toLocaleString()} / 4,000 tokens read`;
      $("span", stEl).textContent = p === "idle" ? "Waiting for a page" : p === "prefill" ? "Reading the page (prefill)" : "Answering (decode)";
      if (p === "decode" || p === "done") {
        const tokS = (E4[condFor()]?.gen_tps?.median || 40) * (st.machine === "m2" ? 1 : 1);
        const n = Math.min(ANSWER.length, Math.round(((p === "done" ? end : now) - pre[2]) / 1000 * tokS * 4.2));
        if (n !== outLen) { outLen = n; $("#d-out").innerHTML = ANSWER.slice(0, n) + '<span class="caret"></span>'; }
      }
    }

    $$(".controls .seg").forEach(seg => seg.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      st[seg.dataset.ctl] = b.dataset.v;
      if (seg.dataset.ctl === "speed") { sync(); return; }
      load();
    }));
    $("#d-play").addEventListener("click", start);
    tl.addEventListener("pointermove", e => { hover = e.offsetX; });
    tl.addEventListener("pointerleave", () => { hover = null; });
    addEventListener("resize", resize);

    let begun = false;
    const go = () => { if (begun) return; begun = true; resize(); load(); if (reduce) { playing = false; } requestAnimationFrame(tick); };
    if (io) new IntersectionObserver((es, o) => es.forEach(e => { if (e.isIntersecting) { go(); o.disconnect(); } }), { threshold: .2 }).observe($(".browser"));
    else go();
    return { resize: () => begun && resize() };
  })();

  addEventListener("hashchange", route);
  route();
})();
