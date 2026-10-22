/* Pixel-art forge on the application tab: me hammering a Chromium block into a Dart window.
   Drawn on a 128×104 canvas and scaled up with image-rendering: pixelated. */
(() => {
  const cv = document.getElementById("forge");
  if (!cv) return;
  const c = cv.getContext("2d");
  const W = 128, H = 104, FLOOR = 92;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const PAL = {
    H: "#101018", h: "#2c2a3a", S: "#c68a63", s: "#9c6646", G: "#07070b", g: "#7d8cc0", B: "#4a3326",
    J: "#6e4a33", j: "#4e3324", k: "#8c6247", T: "#18181c", P: "#262a36", p: "#1b1e27", K: "#0e0e12",
  };
  // curly hair, square shades, stubble, brown fleece over a black tee
  const ME = [
    "......hhHHh.........", "....hHHHHHHHh.......", "...HHhHHHHhHHH......", "..HHHHHHHHHHHHH.....",
    "..HHhHHHHHHHhHHH....", "..HHHHHHHHHHHHHH....", "..HHHHSSSSSHHHH.....", "..HHHSSSSSSSSHH.....",
    "...HHSGGGGsGGGG.....", "...HSSGgGGsGgGG.....", "...HSSGGGSSSGGS.....", "...HSSSSSSSSSSS.....",
    "....sSSSSSSSSS......", "....BSSSSBBSSS......", "....BBSSSSSSBB......", ".....BBBBBBBB.......",
    "......sSSSs.........", "...kJJJTTTJJJk......", "..kJJJJTTTJJJJJ.....", ".kJJJJJTTTJJJJJj....",
    ".JJJJJJTTTJJJJJj....", ".JJjJJJTTTJJJjJj....", ".JJjJJJTTTJJJjJj....", ".JJjJJJTTTJJJjJj....",
    ".SSjJJJTTTJJJjJj....", ".SS.jJJJJJJJJj......", "....PPPPPPPPPP......", "....PPPPppPPPP......",
    "....PPPP..PPPP......", "....PPPP..PPPP......", "....PPPP..PPPP......", "....PPPP..PPPP......",
    "...KKKKK..KKKKK.....", "...KKKKK..KKKKKK....",
  ];
  const MX = 6, MY = FLOOR - ME.length;
  const PIVOT = { x: MX + 14, y: MY + 19 };

  const FONT = {
    C: ["111", "100", "100", "100", "111"], H: ["101", "101", "111", "101", "101"], R: ["110", "101", "110", "101", "101"],
    O: ["111", "101", "101", "101", "111"], M: ["10001", "11011", "10101", "10001", "10001"], I: ["111", "010", "010", "010", "111"],
    U: ["101", "101", "101", "101", "111"], D: ["110", "101", "101", "101", "110"], A: ["010", "101", "111", "101", "101"],
    T: ["111", "010", "010", "010", "010"], " ": ["0", "0", "0", "0", "0"],
  };
  const px = (x, y, col) => { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), 1, 1); };
  const rect = (x, y, w, h, col) => { c.fillStyle = col; c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h)); };
  function text(str, cx, y, col) {
    const glyphs = [...str].map(ch => FONT[ch] || FONT[" "]);
    const w = glyphs.reduce((a, g) => a + g[0].length + 1, -1);
    let x = Math.round(cx - w / 2);
    for (const g of glyphs) {
      g.forEach((row, r) => [...row].forEach((b, i) => b === "1" && px(x + i, y + r, col)));
      x += g[0].length + 1;
    }
  }
  // rotated rectangle in the arm's frame: u along the arm, v across it
  function rot(ang, u0, u1, v0, v1, col) {
    const cs = Math.cos(ang), sn = Math.sin(ang), R = Math.hypot(Math.max(Math.abs(u0), Math.abs(u1)), Math.max(Math.abs(v0), Math.abs(v1))) + 1;
    c.fillStyle = col;
    for (let y = Math.floor(PIVOT.y - R); y <= PIVOT.y + R; y++)
      for (let x = Math.floor(PIVOT.x - R); x <= PIVOT.x + R; x++) {
        const dx = x + .5 - PIVOT.x, dy = y + .5 - PIVOT.y, u = dx * cs + dy * sn, v = -dx * sn + dy * cs;
        if (u >= u0 && u < u1 && v >= v0 && v < v1) c.fillRect(x, y, 1, 1);
      }
  }
  const lerp = (a, b, t) => a + (b - a) * t;
  const mix = (a, b, t) => {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const A = p(a), B = p(b);
    return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], t))).join(",")})`;
  };

  const ANVIL_TOP = 76, PIECE_CX = 52;
  function anvil() {
    rect(36, ANVIL_TOP, 32, 4, "#4b5060"); rect(36, ANVIL_TOP, 32, 1, "#7a8194");
    rect(30, ANVIL_TOP, 6, 2, "#4b5060"); rect(33, ANVIL_TOP + 2, 3, 1, "#4b5060");
    rect(45, ANVIL_TOP + 4, 14, 7, "#3a3e4b"); rect(41, ANVIL_TOP + 11, 22, 5, "#444958"); rect(41, ANVIL_TOP + 11, 22, 1, "#5a6072");
  }
  // the piece goes from a grey ball to a browser window over the hits
  function piece(t) {
    const w = Math.round(lerp(14, 28, t)), h = Math.round(lerp(14, 18, t)), r = lerp(7, 1, t);
    const x0 = PIECE_CX - w / 2, y0 = ANVIL_TOP - h;
    const body = mix("#7d8aa3", "#f4f4f6", t), edge = mix("#5b6680", "#c9cbd6", t);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const dx = Math.max(0, Math.max(r - x - .5, x + .5 - (w - r))), dy = Math.max(0, Math.max(r - y - .5, y + .5 - (h - r)));
      const d = Math.hypot(dx, dy);
      if (d > r && r > 1) continue;
      px(x0 + x, y0 + y, d > r - 1.2 && r > 1 ? edge : body);
    }
    if (t < .5) { // a blue core while it's still a ball
      const k = 1 - t * 2, rr = 3 * k + .5;
      for (let y = -4; y <= 4; y++) for (let x = -4; x <= 4; x++) if (Math.hypot(x, y) <= rr) px(PIECE_CX + x - .5, y0 + h / 2 + y, mix("#4b6cb7", "#9aa4bd", t * 2));
    }
    if (t >= .55) { // title bar, three dots, a page with one blue line
      const a = Math.min(1, (t - .55) / .3);
      rect(x0, y0, w, 3, mix("#f4f4f6", "#e1e2ea", a));
      [0, 3, 6].forEach(i => px(x0 + 2 + i, y0 + 1, mix("#e1e2ea", "#9a9aa8", a)));
      rect(x0 + 3, y0 + 6, (w - 6) * a, 1, mix("#f4f4f6", "#4B55DB", a));
      rect(x0 + 3, y0 + 9, (w - 10) * a, 1, mix("#f4f4f6", "#c9cbd6", a));
      rect(x0 + 3, y0 + 12, (w - 14) * a, 1, mix("#f4f4f6", "#c9cbd6", a));
    }
    return { top: y0 };
  }

  const HITS = 6, PERIOD = 1000, HOLD = 2600, CYCLE = HITS * PERIOD + HOLD;
  let sparks = [], lastHit = -1, shakeUntil = 0, start = performance.now();
  const ease = t => 1 - (1 - t) ** 3;

  function frame(now) {
    requestAnimationFrame(frame);
    if (!cv.offsetParent) return; // tab hidden
    const T = reduce ? HITS * PERIOD + 100 : (now - start) % CYCLE;
    const hitIdx = Math.min(HITS, Math.floor(T / PERIOD)), p = (T % PERIOD) / PERIOD;
    const done = T >= HITS * PERIOD;
    let stage = Math.min(HITS, hitIdx + (p >= .72 ? 1 : 0)), t = stage / HITS;
    if (done) { stage = HITS; t = 1; }

    // scene
    const shake = now < shakeUntil ? 1 : 0;
    c.setTransform(1, 0, 0, 1, 0, shake);
    rect(0, -1, W, H + 2, "#15161E");
    for (let y = 6; y < FLOOR; y += 8) for (let x = 4 + (y % 16 ? 4 : 0); x < W; x += 8) px(x, y, "#1d1f2b");
    rect(0, FLOOR, W, H - FLOOR + 1, "#1e1f2a"); rect(0, FLOOR, W, 1, "#2c2e3d");
    for (let x = 28; x < 78; x++) px(x, FLOOR + 1, "#25273a");
    anvil();
    const pc = piece(t);
    const label = t >= 1 ? "DART" : "CHROMIUM";
    text(label, PIECE_CX + 8, 10, t >= 1 ? "#8f97ff" : mix("#9aa0ad", "#6c7080", t));
    if (t >= 1) for (let i = 0; i < 3; i++) { // a little sparkle on the finished window
      const a = now / 300 + i * 2.1;
      if (Math.sin(a) > .6) px(PIECE_CX - 12 + i * 11, pc.top - 3 - i % 2 * 2, "#fff2b0");
    }

    // me
    ME.forEach((row, y) => [...row].forEach((ch, x) => PAL[ch] && px(MX + x, MY + y, PAL[ch])));

    // arm + hammer: aim the hammer head at the top of the piece
    const target = { x: PIECE_CX - 3, y: pc.top - 1 };
    const L = Math.hypot(target.x - PIVOT.x, target.y - PIVOT.y);
    const hitA = Math.atan2(target.y - PIVOT.y, target.x - PIVOT.x), upA = hitA - 1.95;
    let ang;
    if (done) ang = lerp(hitA, upA, .35 + Math.sin(now / 500) * .04);
    else if (p < .5) ang = lerp(hitA, upA, ease(p / .5));
    else if (p < .62) ang = upA;
    else if (p < .72) ang = lerp(upA, hitA, ((p - .62) / .1) ** 2);
    else ang = hitA;
    rot(ang, 0, 11, -1.5, 1.5, PAL.J); rot(ang, 0, 11, .6, 1.5, PAL.j);
    rot(ang, 10, 13, -1.4, 1.4, PAL.S);
    rot(ang, 12, L - 1, -.6, .6, "#7a5232");
    rot(ang, L - 3, L + 1, -4.5, 4.5, "#9aa0ad"); rot(ang, L - 3, L - 2, -4.5, 4.5, "#c9cdd6");

    // impact
    const key = Math.floor((now - start) / CYCLE) * 100 + hitIdx;
    if (!reduce && !done && p >= .72 && key !== lastHit) {
      lastHit = key; shakeUntil = now + 70;
      for (let i = 0; i < 9; i++) {
        const a = -Math.PI / 2 + (Math.random() - .5) * 2.4, v = .6 + Math.random() * 1.2;
        sparks.push({ x: target.x, y: target.y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 26 + Math.random() * 14,
          col: ["#ffd36b", "#ff9a3c", "#fff2b0"][i % 3] });
      }
    }
    sparks = sparks.filter(s => s.life-- > 0);
    for (const s of sparks) { s.x += s.vx; s.y += s.vy; s.vy += .06; px(s.x, s.y, s.col); }
  }
  requestAnimationFrame(frame);
})();
