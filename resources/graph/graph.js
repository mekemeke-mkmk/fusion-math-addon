// Math Curve graph window. Python (graph_window.py) samples the curves; this file only draws
// them and sends edits back. All requests go through adsk.fusionSendData, which returns a Promise.
"use strict";

const COLORS = ["#2f6fdf", "#e8590c", "#2b8a3e", "#ae3ec9", "#0c8599", "#c92a2a", "#8d5524", "#5c940d"];

const state = {
  curves: [],
  hidden: new Set(),
  selected: -1,
  // View: center (cx, cy) and pixels per unit. Equal scale on both axes, like a drawing.
  cx: 0,
  cy: 0,
  scale: 40,
  dataView: null,
  busy: false,
  queue: [],
  editing: false
};

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const listEl = document.getElementById("curveList");
const editorEl = document.getElementById("editor");
const statusEl = document.getElementById("status");
const readoutEl = document.getElementById("readout");

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function colorOf(index) {
  return COLORS[index % COLORS.length];
}

// ---------- Communication with Fusion ----------

function hasFusion() {
  return typeof window.adsk !== "undefined" && typeof window.adsk.fusionSendData === "function";
}

function currentView() {
  const w = canvas.clientWidth || 1;
  const h = canvas.clientHeight || 1;
  return {
    xmin: state.cx - w / 2 / state.scale,
    xmax: state.cx + w / 2 / state.scale,
    ymin: state.cy - h / 2 / state.scale,
    ymax: state.cy + h / 2 / state.scale
  };
}

// Sends one request at a time. Waiting requests are merged where possible, so dragging a
// slider never queues up stale work in Fusion.
function send(action, extra) {
  if (!hasFusion()) {
    return;
  }
  const message = { action: action, extra: extra || {} };
  if (state.busy) {
    enqueue(message);
    return;
  }
  state.busy = true;
  const payload = Object.assign({ view: currentView(), hidden: Array.from(state.hidden) }, message.extra);
  statusEl.textContent = "Calculating...";
  adsk.fusionSendData(action, JSON.stringify(payload)).then(function (text) {
    state.busy = false;
    statusEl.textContent = "";
    receive(text);
    sendNext();
  }, function (error) {
    state.busy = false;
    statusEl.textContent = "Error: " + error;
    sendNext();
  });
}

function sendNext() {
  const next = state.queue.shift();
  if (next) send(next.action, next.extra);
}

// Queue a request while another is running. A data request is dropped when anything is
// already waiting (every reply carries fresh data). Edits of the same function are merged,
// so nothing typed is lost and slider drags collapse into one request.
function enqueue(message) {
  const last = state.queue[state.queue.length - 1];
  if (message.action === "graphData") {
    if (!last) state.queue.push(message);
    return;
  }
  if (last && last.action === "graphData") {
    state.queue[state.queue.length - 1] = message;
    return;
  }
  if (last && last.action === "graphEdit" && message.action === "graphEdit" &&
      last.extra.index === message.extra.index) {
    const a = last.extra.changes, b = message.extra.changes;
    const changes = Object.assign({}, a, b);
    if (a.variables || b.variables) changes.variables = Object.assign({}, a.variables, b.variables);
    last.extra = { index: message.extra.index, changes: changes, commit: last.extra.commit || message.extra.commit };
    return;
  }
  state.queue.push(message);
}

function receive(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    statusEl.textContent = String(text || "No response");
    return;
  }
  if (data.error) {
    statusEl.textContent = data.error;
    return;
  }
  state.curves = data.curves || [];
  state.dataView = data.view;
  if (state.selected >= state.curves.length) {
    state.selected = state.curves.length - 1;
  }
  if (typeof data.select === "number") {
    state.selected = data.select;
  }
  renderList();
  if (!state.editing) {
    renderEditor();
  } else {
    renderMessages();
  }
  draw();
}

function requestData() {
  send("graphData");
}

// Called by Python through palette.sendInfoToHTML.
window.fusionJavaScriptHandler = {
  handle: function (action, data) {
    try {
      if (action === "refresh") {
        requestData();
      }
    } catch (e) {
      console.log(e);
    }
    return "OK";
  }
};

// ---------- Drawing ----------

function niceStep(rough) {
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const fraction = rough / power;
  if (fraction < 1.5) return power;
  if (fraction < 3.5) return 2 * power;
  if (fraction < 7.5) return 5 * power;
  return 10 * power;
}

function toScreen(x, y) {
  return [
    canvas.clientWidth / 2 + (x - state.cx) * state.scale,
    canvas.clientHeight / 2 - (y - state.cy) * state.scale
  ];
}

function formatTick(value, step) {
  const decimals = Math.max(0, -Math.floor(Math.log10(step)));
  return Math.abs(value) < step / 1000 ? "0" : value.toFixed(decimals);
}

function drawGrid(w, h) {
  const view = currentView();
  const step = niceStep(80 / state.scale);
  const minor = step / 5;

  ctx.lineWidth = 1;
  ctx.strokeStyle = cssVar("--grid");
  ctx.beginPath();
  for (let x = Math.ceil(view.xmin / minor) * minor; x <= view.xmax; x += minor) {
    const sx = Math.round(toScreen(x, 0)[0]) + 0.5;
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, h);
  }
  for (let y = Math.ceil(view.ymin / minor) * minor; y <= view.ymax; y += minor) {
    const sy = Math.round(toScreen(0, y)[1]) + 0.5;
    ctx.moveTo(0, sy);
    ctx.lineTo(w, sy);
  }
  ctx.stroke();

  ctx.strokeStyle = cssVar("--grid-major");
  ctx.beginPath();
  for (let x = Math.ceil(view.xmin / step) * step; x <= view.xmax; x += step) {
    const sx = Math.round(toScreen(x, 0)[0]) + 0.5;
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, h);
  }
  for (let y = Math.ceil(view.ymin / step) * step; y <= view.ymax; y += step) {
    const sy = Math.round(toScreen(0, y)[1]) + 0.5;
    ctx.moveTo(0, sy);
    ctx.lineTo(w, sy);
  }
  ctx.stroke();

  // Axes, with labels kept on screen when the origin is out of view.
  const origin = toScreen(0, 0);
  const axisX = Math.min(Math.max(origin[0], 0), w);
  const axisY = Math.min(Math.max(origin[1], 0), h);
  ctx.strokeStyle = cssVar("--axis");
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  if (origin[1] >= 0 && origin[1] <= h) {
    ctx.moveTo(0, origin[1]);
    ctx.lineTo(w, origin[1]);
  }
  if (origin[0] >= 0 && origin[0] <= w) {
    ctx.moveTo(origin[0], 0);
    ctx.lineTo(origin[0], h);
  }
  ctx.stroke();

  ctx.fillStyle = cssVar("--muted");
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const labelY = Math.min(axisY + 3, h - 14);
  for (let x = Math.ceil(view.xmin / step) * step; x <= view.xmax; x += step) {
    if (Math.abs(x) < step / 1000) continue;
    ctx.fillText(formatTick(x, step), toScreen(x, 0)[0], labelY);
  }
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  const labelX = Math.max(axisX - 4, 30);
  for (let y = Math.ceil(view.ymin / step) * step; y <= view.ymax; y += step) {
    if (Math.abs(y) < step / 1000) continue;
    ctx.fillText(formatTick(y, step), labelX, toScreen(0, y)[1]);
  }
}

function drawCurves() {
  state.curves.forEach(function (curve) {
    if (state.hidden.has(curve.index)) return;
    ctx.strokeStyle = colorOf(curve.index);
    ctx.lineWidth = curve.index === state.selected ? 3 : 2;
    ctx.lineJoin = "round";
    curve.pieces.forEach(function (piece) {
      if (piece.length < 2) return;
      ctx.beginPath();
      piece.forEach(function (p, i) {
        const s = toScreen(p[0], p[1]);
        if (i === 0) ctx.moveTo(s[0], s[1]); else ctx.lineTo(s[0], s[1]);
      });
      if (curve.closed && curve.pieces.length === 1) ctx.closePath();
      ctx.stroke();
    });
  });
}

function draw() {
  const ratio = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.fillStyle = cssVar("--bg");
  ctx.fillRect(0, 0, w, h);
  drawGrid(w, h);
  drawCurves();
}

// y = f(x) curves are sampled for the visible x range only, so ask again when the view
// leaves the area that was sampled (or zooms in enough to need more detail).
function viewNeedsData() {
  if (!state.dataView) return true;
  const v = currentView();
  const d = state.dataView;
  const width = v.xmax - v.xmin;
  return v.xmin < d.xmin || v.xmax > d.xmax || width < (d.xmax - d.xmin) / 3;
}

// ---------- Sidebar ----------

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
  });
}

function renderList() {
  listEl.innerHTML = "";
  state.curves.forEach(function (curve) {
    const row = document.createElement("div");
    row.className = "curve-row" + (curve.index === state.selected ? " selected" : "");

    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !state.hidden.has(curve.index);
    box.title = "Show in graph";
    box.addEventListener("click", function (event) {
      event.stopPropagation();
      if (box.checked) state.hidden.delete(curve.index); else state.hidden.add(curve.index);
      requestData();
      draw();
    });

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = colorOf(curve.index);

    const name = document.createElement("span");
    name.className = "curve-name";
    name.textContent = curve.name;
    name.title = curve.name;

    row.appendChild(box);
    row.appendChild(swatch);
    row.appendChild(name);
    if (curve.errors.length) {
      row.insertAdjacentHTML("beforeend", '<span class="badge error">error</span>');
    } else if (curve.warnings.length) {
      row.insertAdjacentHTML("beforeend", '<span class="badge warning">!</span>');
    }
    row.addEventListener("click", function () {
      state.selected = curve.index;
      state.editing = false;
      renderList();
      renderEditor();
      draw();
    });
    listEl.appendChild(row);
  });
}

function selectedCurve() {
  return state.curves.find(function (c) { return c.index === state.selected; });
}

function sendEdit(changes, commit) {
  send("graphEdit", { index: state.selected, changes: changes, commit: commit });
}

function textField(label, value, onCommit) {
  const wrap = document.createElement("div");
  wrap.className = "field";
  wrap.innerHTML = "<label>" + escapeHtml(label) + "</label>";
  const input = document.createElement("input");
  input.type = "text";
  input.value = value == null ? "" : value;
  input.spellcheck = false;
  input.addEventListener("focus", function () { state.editing = true; });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") input.blur();
  });
  input.addEventListener("change", function () { onCommit(input.value); });
  input.addEventListener("blur", function () { state.editing = false; });
  wrap.appendChild(input);
  return wrap;
}

function numberField(label, value, onCommit) {
  const wrap = textField(label, value, function (text) {
    const number = Number(text);
    if (text.trim() !== "" && isFinite(number)) onCommit(number);
  });
  wrap.querySelector("input").type = "number";
  wrap.querySelector("input").step = "any";
  return wrap;
}

function variableControl(name, value) {
  const span = Math.max(Math.abs(value), 1) * 2;
  const wrap = document.createElement("div");
  wrap.className = "var";
  const head = document.createElement("div");
  head.className = "var-head";
  head.innerHTML = "<span>" + escapeHtml(name) + "</span>";
  const number = document.createElement("input");
  number.type = "number";
  number.step = "any";
  number.value = value;
  head.appendChild(number);

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = value - span;
  slider.max = value + span;
  slider.step = span / 200;
  slider.value = value;

  function changes(v) {
    const result = { variables: {} };
    result.variables[name] = v;
    return result;
  }
  // While dragging: update the graph only. On release: save to the library.
  slider.addEventListener("input", function () {
    number.value = Number(slider.value).toPrecision(6) * 1;
    sendEdit(changes(Number(slider.value)), false);
  });
  slider.addEventListener("change", function () {
    sendEdit(changes(Number(slider.value)), true);
  });
  number.addEventListener("change", function () {
    const v = Number(number.value);
    if (isFinite(v)) sendEdit(changes(v), true);
  });

  wrap.appendChild(head);
  wrap.appendChild(slider);
  return wrap;
}

function renderMessages() {
  const box = editorEl.querySelector(".messages");
  const curve = selectedCurve();
  if (!box || !curve) return;
  box.innerHTML = "";
  curve.errors.forEach(function (text) {
    box.insertAdjacentHTML("beforeend", '<div class="error">' + escapeHtml(text) + "</div>");
  });
  curve.warnings.forEach(function (text) {
    box.insertAdjacentHTML("beforeend", '<div class="warning">' + escapeHtml(text) + "</div>");
  });
}

function renderEditor() {
  const curve = selectedCurve();
  editorEl.innerHTML = "";
  if (!curve) {
    editorEl.innerHTML = '<p class="hint">Select a function to edit it.</p>';
    return;
  }
  const title = document.createElement("h3");
  title.style.color = colorOf(curve.index);
  title.textContent = curve.name;
  editorEl.appendChild(title);

  editorEl.appendChild(textField("Name", curve.name, function (v) { sendEdit({ name: v }, true); }));

  const labels = { expr: "y =", x_expr: "x(t) =", y_expr: "y(t) =", z_expr: "z(t) =  (not shown: x-y view)" };
  Object.keys(curve.fields).forEach(function (field) {
    editorEl.appendChild(textField(labels[field] || field, curve.fields[field], function (v) {
      const change = {};
      change[field] = v;
      sendEdit(change, true);
    }));
  });

  if (curve.type !== "implicit") {
    const row = document.createElement("div");
    row.className = "row2";
    row.appendChild(numberField("t start", curve.t_start, function (v) { sendEdit({ t_start: v }, true); }));
    row.appendChild(numberField("t end", curve.t_end, function (v) { sendEdit({ t_end: v }, true); }));
    editorEl.appendChild(row);
  }

  const names = Object.keys(curve.variables);
  if (names.length) {
    const label = document.createElement("div");
    label.className = "hint";
    label.textContent = "Variables (drag to preview, release to save)";
    label.style.margin = "4px 0 6px";
    editorEl.appendChild(label);
    names.forEach(function (name) { editorEl.appendChild(variableControl(name, curve.variables[name])); });
  } else {
    editorEl.insertAdjacentHTML("beforeend",
      '<p class="hint">No variables. Add them in the Library tab (for example a=1,b=2) to get sliders.</p>');
  }

  const messages = document.createElement("div");
  messages.className = "messages";
  editorEl.appendChild(messages);
  renderMessages();
}

// ---------- View controls ----------

let drag = null;

canvas.addEventListener("mousedown", function (event) {
  drag = { x: event.clientX, y: event.clientY, cx: state.cx, cy: state.cy };
  canvas.classList.add("dragging");
});

window.addEventListener("mousemove", function (event) {
  const rect = canvas.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;
  if (mx >= 0 && my >= 0 && mx <= rect.width && my <= rect.height) {
    const x = state.cx + (mx - rect.width / 2) / state.scale;
    const y = state.cy - (my - rect.height / 2) / state.scale;
    const digits = Math.max(0, Math.ceil(Math.log10(state.scale)) + 1);
    readoutEl.textContent = "x = " + x.toFixed(digits) + "   y = " + y.toFixed(digits);
  }
  if (!drag) return;
  state.cx = drag.cx - (event.clientX - drag.x) / state.scale;
  state.cy = drag.cy + (event.clientY - drag.y) / state.scale;
  draw();
});

window.addEventListener("mouseup", function () {
  if (!drag) return;
  drag = null;
  canvas.classList.remove("dragging");
  if (viewNeedsData()) requestData();
});

let wheelTimer = null;
canvas.addEventListener("wheel", function (event) {
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = event.clientX - rect.left - rect.width / 2;
  const my = event.clientY - rect.top - rect.height / 2;
  const before = [state.cx + mx / state.scale, state.cy - my / state.scale];
  const factor = Math.exp(-event.deltaY * 0.0015);
  state.scale = Math.min(Math.max(state.scale * factor, 1e-4), 1e7);
  // Keep the point under the cursor fixed.
  state.cx = before[0] - mx / state.scale;
  state.cy = before[1] + my / state.scale;
  draw();
  clearTimeout(wheelTimer);
  wheelTimer = setTimeout(function () { if (viewNeedsData()) requestData(); }, 150);
}, { passive: false });

function fitView() {
  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  state.curves.forEach(function (curve) {
    if (state.hidden.has(curve.index)) return;
    curve.pieces.forEach(function (piece) {
      piece.forEach(function (p) {
        xmin = Math.min(xmin, p[0]); xmax = Math.max(xmax, p[0]);
        ymin = Math.min(ymin, p[1]); ymax = Math.max(ymax, p[1]);
      });
    });
  });
  if (!isFinite(xmin)) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const spanX = Math.max(xmax - xmin, 1e-6), spanY = Math.max(ymax - ymin, 1e-6);
  state.scale = 0.85 * Math.min(w / spanX, h / spanY);
  state.cx = (xmin + xmax) / 2;
  state.cy = (ymin + ymax) / 2;
  draw();
  requestData();
}

document.getElementById("fit").addEventListener("click", fitView);
document.getElementById("home").addEventListener("click", function () {
  state.cx = 0;
  state.cy = 0;
  draw();
  requestData();
});
document.getElementById("refresh").addEventListener("click", requestData);
document.getElementById("addCurve").addEventListener("click", function () {
  send("graphAdd");
});

let resizeTimer = null;
window.addEventListener("resize", function () {
  draw();
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(requestData, 200);
});

// ---------- Start ----------

function start() {
  draw();
  if (!hasFusion()) {
    // Fusion injects the adsk object shortly after load; give it a moment.
    setTimeout(function () {
      if (hasFusion()) {
        requestData();
      } else {
        document.getElementById("offline").style.display = "flex";
      }
    }, 500);
    return;
  }
  requestData();
}

window.addEventListener("load", start);
