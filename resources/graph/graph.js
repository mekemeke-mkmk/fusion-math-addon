// Math Curve graph window. Python (graph_window.py) samples the curves; this file only draws
// them and sends edits back. All requests go through adsk.fusionSendData, which returns a Promise.
"use strict";

const COLORS = ["#2f6fdf", "#e8590c", "#2b8a3e", "#ae3ec9", "#0c8599", "#c92a2a", "#8d5524", "#5c940d"];
const UNITS = ["mm", "cm", "m", "in", "ft"];

const state = {
  curves: [],
  presets: [],
  types: [],
  closeModes: [],
  params: [],
  hidden: new Set(),
  selected: -1,
  // View: center (cx, cy) and pixels per unit. Equal scale on both axes, like a drawing.
  cx: 0,
  cy: 0,
  scale: 40,
  dataView: null,
  busy: false,
  queue: [],
  // Structure of the editor currently shown; the editor is rebuilt only when this changes,
  // otherwise values are updated in place so a slider being dragged is never replaced.
  editorKey: null,
  draggingVariable: null,
  deleteArmed: false
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

function storageGet(key, fallback) {
  try {
    const value = window.localStorage.getItem("mathCurveGraph." + key);
    return value === null ? fallback : JSON.parse(value);
  } catch (e) {
    return fallback;
  }
}

function storageSet(key, value) {
  try {
    window.localStorage.setItem("mathCurveGraph." + key, JSON.stringify(value));
  } catch (e) {
    // Storage can be unavailable; settings then last for this session only.
  }
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
  adsk.fusionSendData(action, JSON.stringify(payload)).then(function (text) {
    state.busy = false;
    receive(text);
    sendNext();
  }, function (error) {
    state.busy = false;
    showStatus("Error: " + error, true);
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
      last.extra.index === message.extra.index && isMergeable(last.extra.changes) &&
      isMergeable(message.extra.changes)) {
    const a = last.extra.changes, b = message.extra.changes;
    const changes = Object.assign({}, a, b);
    if (a.variables || b.variables) changes.variables = Object.assign({}, a.variables, b.variables);
    if (a.variable_ranges || b.variable_ranges) {
      changes.variable_ranges = Object.assign({}, a.variable_ranges, b.variable_ranges);
    }
    last.extra = { index: message.extra.index, changes: changes, commit: last.extra.commit || message.extra.commit };
    return;
  }
  state.queue.push(message);
}

// Adding or removing a variable must not be merged with other edits (order matters).
function isMergeable(changes) {
  return !("add_variable" in changes) && !("remove_variable" in changes) && !("type" in changes);
}

let statusTimer = null;
function showStatus(text, isError) {
  statusEl.textContent = text || "";
  statusEl.classList.toggle("error", !!isError);
  clearTimeout(statusTimer);
  if (text && !isError) statusTimer = setTimeout(function () { statusEl.textContent = ""; }, 4000);
}

function receive(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    showStatus(String(text || "No response"), true);
    return;
  }
  if (data.error) {
    showStatus(data.error, true);
    return;
  }
  if (data.created) {
    showStatus(data.created, false);
    return;
  }
  if (data.message) showStatus(data.message, true);
  state.curves = data.curves || [];
  state.presets = data.presets || state.presets;
  state.types = data.types || state.types;
  state.closeModes = data.close_modes || state.closeModes;
  state.params = data.params || state.params;
  state.dataView = data.view;
  if (typeof data.select === "number") {
    state.selected = data.select;
  }
  if (state.selected >= state.curves.length) {
    state.selected = state.curves.length - 1;
  }
  renderAddMenu();
  renderList();
  renderEditor();
  updateCreateButton();
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

// Shaded band for the x range that Create in Sketch uses for y = f(x) curves.
function drawSketchRange(h) {
  const hasImplicit = state.curves.some(function (c) { return c.type === "implicit" && !state.hidden.has(c.index); });
  const range = sketchXRange();
  if (!hasImplicit || !range) return;
  const a = toScreen(range[0], 0)[0], b = toScreen(range[1], 0)[0];
  ctx.fillStyle = cssVar("--band");
  ctx.fillRect(Math.min(a, b), 0, Math.abs(b - a), h);
  ctx.fillStyle = cssVar("--muted");
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText("sketch x range", Math.min(a, b) + 4, 34);
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
  drawSketchRange(h);
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


// ---------- Sidebar: function list ----------

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
  });
}

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (key) {
    if (key === "text") node.textContent = attrs[key];
    else if (key === "class") node.className = attrs[key];
    else node.setAttribute(key, attrs[key]);
  });
  (children || []).forEach(function (child) { if (child) node.appendChild(child); });
  return node;
}

function renderAddMenu() {
  const menu = document.getElementById("addMenu");
  const signature = state.types.length + ":" + state.presets.length;
  if (menu.dataset.signature === signature) return;
  menu.dataset.signature = signature;
  menu.innerHTML = "";
  menu.appendChild(el("option", { value: "", text: "+ Add function..." }));
  const blank = el("optgroup", { label: "New" });
  state.types.forEach(function (type) {
    blank.appendChild(el("option", { value: "kind:" + type.id, text: type.label }));
  });
  menu.appendChild(blank);
  const presets = el("optgroup", { label: "Presets" });
  state.presets.forEach(function (label, index) {
    presets.appendChild(el("option", { value: "preset:" + index, text: label }));
  });
  menu.appendChild(presets);
}

function renderList() {
  listEl.innerHTML = "";
  state.curves.forEach(function (curve) {
    const row = el("div", { class: "curve-row" + (curve.index === state.selected ? " selected" : "") });

    const box = el("input", { type: "checkbox", title: "Show in graph (and create in sketch)" });
    box.checked = !state.hidden.has(curve.index);
    box.addEventListener("click", function (event) {
      event.stopPropagation();
      if (box.checked) state.hidden.delete(curve.index); else state.hidden.add(curve.index);
      updateCreateButton();
      requestData();
      draw();
    });

    const swatch = el("span", { class: "swatch" });
    swatch.style.background = colorOf(curve.index);
    const name = el("span", { class: "curve-name", text: curve.name, title: curve.name });

    row.appendChild(box);
    row.appendChild(swatch);
    row.appendChild(name);
    if (curve.errors.length) {
      row.appendChild(el("span", { class: "badge error", text: "error" }));
    } else if (curve.warnings.length) {
      row.appendChild(el("span", { class: "badge warning", text: "!" }));
    }
    row.addEventListener("click", function () {
      if (state.selected === curve.index) return;
      state.selected = curve.index;
      state.deleteArmed = false;
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

// ---------- Sidebar: editor ----------

const FIELD_LABELS = { expr: "y =", x_expr: "x(t) =", y_expr: "y(t) =", z_expr: "z(t) =" };

function editorKey(curve) {
  return [curve.index, curve.type, Object.keys(curve.fields).join(","), Object.keys(curve.variables).join(",")].join("|");
}

function field(label, input, hint) {
  return el("div", { class: "field" }, [el("label", { text: label }), input, hint ? el("div", { class: "hint", text: hint }) : null]);
}

// Text input that previews while typing and saves on Enter / leaving the box.
function liveText(key, value, onPreview, onCommit) {
  const input = el("input", { type: "text", spellcheck: "false", "data-key": key });
  input.value = value == null ? "" : value;
  let timer = null;
  input.addEventListener("input", function () {
    if (!onPreview) return;
    clearTimeout(timer);
    timer = setTimeout(function () { onPreview(input.value); }, 250);
  });
  input.addEventListener("keydown", function (event) { if (event.key === "Enter") input.blur(); });
  input.addEventListener("change", function () { clearTimeout(timer); onCommit(input.value); });
  return input;
}

function numberInput(key, value, onCommit) {
  const input = el("input", { type: "number", step: "any", "data-key": key });
  input.value = value == null ? "" : value;
  input.addEventListener("keydown", function (event) { if (event.key === "Enter") input.blur(); });
  input.addEventListener("change", function () {
    const number = Number(input.value);
    if (input.value.trim() !== "" && isFinite(number)) onCommit(number);
  });
  return input;
}

function selectInput(key, options, value, onChange) {
  const select = el("select", { "data-key": key });
  options.forEach(function (option) {
    const item = el("option", { value: option.id, text: option.label });
    if (option.id === value) item.selected = true;
    select.appendChild(item);
  });
  select.addEventListener("change", function () { onChange(select.value); });
  return select;
}

function sliderStep(range) {
  return (range[1] - range[0]) / 1000;
}

function variableControl(name, value, range) {
  const valueInput = numberInput("var:" + name, value, function (v) {
    const change = { variables: {} };
    change.variables[name] = v;
    sendEdit(change, true);
  });
  valueInput.className = "var-value";

  const remove = el("button", { type: "button", class: "icon", title: "Remove variable " + name, text: "×" });
  remove.addEventListener("click", function () { sendEdit({ remove_variable: name }, true); });

  const slider = el("input", { type: "range", "data-var": name });
  slider.min = range[0];
  slider.max = range[1];
  slider.step = sliderStep(range);
  slider.value = value;

  function preview(commit) {
    const v = Number(slider.value);
    valueInput.value = Number(v.toPrecision(6));
    const change = { variables: {} };
    change.variables[name] = v;
    sendEdit(change, commit);
  }
  // The slider stays the same element while it is dragged (see updateEditor), so the
  // drag is never interrupted by replies from Fusion.
  slider.addEventListener("pointerdown", function () { state.draggingVariable = name; });
  slider.addEventListener("input", function () { preview(false); });
  slider.addEventListener("change", function () {
    state.draggingVariable = null;
    preview(true);
  });

  function rangeInput(which) {
    const input = numberInput("range:" + name + ":" + which, range[which], function () {
      const low = Number(minInput.value), high = Number(maxInput.value);
      if (!(low < high)) {
        showStatus("Slider minimum must be smaller than maximum.", true);
        return;
      }
      const change = { variable_ranges: {} };
      change.variable_ranges[name] = [low, high];
      sendEdit(change, true);
    });
    input.className = "range-input";
    return input;
  }
  const minInput = rangeInput(0);
  const maxInput = rangeInput(1);

  return el("div", { class: "var", "data-variable": name }, [
    el("div", { class: "var-head" }, [el("span", { class: "var-name", text: name }), valueInput, remove]),
    slider,
    el("div", { class: "var-range" }, [el("span", { text: "min" }), minInput, el("span", { text: "max" }), maxInput])
  ]);
}

function addVariableRow(curve) {
  const nameInput = el("input", { type: "text", placeholder: "name", spellcheck: "false", class: "new-var-name" });
  const valueInput = el("input", { type: "number", step: "any", placeholder: "value", class: "new-var-value" });
  valueInput.value = 1;
  const add = el("button", { type: "button", text: "+ Variable" });
  function submit() {
    const name = nameInput.value.trim();
    if (!name) {
      nameInput.focus();
      return;
    }
    sendEdit({ add_variable: { name: name, value: Number(valueInput.value) || 0 } }, true);
  }
  add.addEventListener("click", submit);
  nameInput.addEventListener("keydown", function (event) { if (event.key === "Enter") submit(); });
  return el("div", { class: "add-var" }, [nameInput, valueInput, add]);
}

function renderMessages(curve) {
  const box = editorEl.querySelector(".messages");
  if (!box) return;
  box.innerHTML = "";
  curve.errors.forEach(function (text) {
    box.appendChild(el("div", { class: "error", text: text }));
    // "Unknown name 'a'" -> one click to define it as a variable.
    const match = /Unknown name '([A-Za-z_][A-Za-z0-9_]*)'/.exec(text);
    if (match) {
      const quick = el("button", { type: "button", class: "quick", text: "+ Add variable " + match[1] });
      quick.addEventListener("click", function () { sendEdit({ add_variable: { name: match[1], value: 1 } }, true); });
      box.appendChild(quick);
    }
  });
  curve.warnings.forEach(function (text) {
    box.appendChild(el("div", { class: "warning", text: text }));
  });
}

function buildEditor(curve) {
  editorEl.innerHTML = "";

  const deleteButton = el("button", { type: "button", class: "danger", text: "Delete" });
  deleteButton.addEventListener("click", function () {
    if (!state.deleteArmed) {
      state.deleteArmed = true;
      deleteButton.textContent = "Click again to delete";
      setTimeout(function () {
        state.deleteArmed = false;
        deleteButton.textContent = "Delete";
      }, 3000);
      return;
    }
    state.deleteArmed = false;
    send("graphDelete", { index: curve.index });
  });
  const title = el("h3", { text: curve.name });
  title.style.color = colorOf(curve.index);
  editorEl.appendChild(el("div", { class: "editor-head" }, [title, deleteButton]));

  editorEl.appendChild(field("Name", liveText("name", curve.name, null, function (v) { sendEdit({ name: v }, true); })));
  editorEl.appendChild(field("Type", selectInput("type", state.types, curve.type, function (v) { sendEdit({ type: v }, true); })));

  Object.keys(curve.fields).forEach(function (name) {
    function change(commit) {
      return function (v) {
        const c = {};
        c[name] = v;
        sendEdit(c, commit);
      };
    }
    const hint = name === "z_expr" ? "z is drawn along the sketch normal; the graph shows the x-y view." : null;
    editorEl.appendChild(field(FIELD_LABELS[name] || name, liveText("field:" + name, curve.fields[name], change(false), change(true)), hint));
  });

  if (curve.type === "implicit") {
    editorEl.appendChild(field("Sketch step (x)", numberInput("step", curve.step, function (v) { sendEdit({ step: v }, true); }),
      "Distance between points when the curve is created in the sketch."));
  } else {
    editorEl.appendChild(el("div", { class: "row3" }, [
      field("t start", numberInput("t_start", curve.t_start, function (v) { sendEdit({ t_start: v }, true); })),
      field("t end", numberInput("t_end", curve.t_end, function (v) { sendEdit({ t_end: v }, true); })),
      field("t step", numberInput("t_step", curve.t_step, function (v) { sendEdit({ t_step: v }, true); }))
    ]));
    editorEl.appendChild(field("Start / End", selectInput("close_mode", state.closeModes, curve.close_mode,
      function (v) { sendEdit({ close_mode: v }, true); })));
  }

  editorEl.appendChild(el("div", { class: "section-title", text: "Variables" }));
  Object.keys(curve.variables).forEach(function (name) {
    editorEl.appendChild(variableControl(name, curve.variables[name], curve.variable_ranges[name]));
  });
  editorEl.appendChild(addVariableRow(curve));
  if (state.params.length) {
    editorEl.appendChild(el("div", { class: "hint", text: "Fusion parameters you can use: " + state.params.join(", ") }));
  }

  editorEl.appendChild(el("div", { class: "messages" }));
  renderMessages(curve);
}

// Refresh values without replacing elements: keeps focus, caret, and slider drags intact.
function updateEditor(curve) {
  const title = editorEl.querySelector(".editor-head h3");
  if (title) title.textContent = curve.name;
  const values = { name: curve.name, type: curve.type, step: curve.step, t_start: curve.t_start,
    t_end: curve.t_end, t_step: curve.t_step, close_mode: curve.close_mode };
  Object.keys(curve.fields).forEach(function (name) { values["field:" + name] = curve.fields[name]; });
  Object.keys(curve.variables).forEach(function (name) {
    values["var:" + name] = curve.variables[name];
    values["range:" + name + ":0"] = curve.variable_ranges[name][0];
    values["range:" + name + ":1"] = curve.variable_ranges[name][1];
  });
  editorEl.querySelectorAll("[data-key]").forEach(function (input) {
    const key = input.getAttribute("data-key");
    if (!(key in values) || input === document.activeElement) return;
    if (key.indexOf("var:") === 0 && state.draggingVariable === key.slice(4)) return;
    const value = values[key] == null ? "" : String(values[key]);
    if (input.value !== value) input.value = value;
  });
  editorEl.querySelectorAll("input[type=range]").forEach(function (slider) {
    const name = slider.getAttribute("data-var");
    if (name === state.draggingVariable) return;
    const range = curve.variable_ranges[name];
    slider.min = range[0];
    slider.max = range[1];
    slider.step = sliderStep(range);
    slider.value = curve.variables[name];
  });
  renderMessages(curve);
}

function renderEditor() {
  const curve = selectedCurve();
  if (!curve) {
    state.editorKey = null;
    editorEl.innerHTML = '<p class="hint">Select a function to edit it, or add one above.</p>';
    return;
  }
  const key = editorKey(curve);
  if (key === state.editorKey && editorEl.querySelector(".editor-head")) {
    updateEditor(curve);
  } else {
    state.editorKey = key;
    buildEditor(curve);
  }
}

window.addEventListener("pointerup", function () {
  // A drag that ends outside the slider fires no "change"; stop protecting it anyway.
  setTimeout(function () { state.draggingVariable = null; }, 0);
});

// ---------- Sidebar: create in sketch ----------

function sketchSettings() {
  return {
    unit: document.getElementById("unit").value,
    x_start: Number(document.getElementById("xStart").value),
    x_end: Number(document.getElementById("xEnd").value),
    output: document.getElementById("output").value
  };
}

function sketchXRange() {
  const a = Number(document.getElementById("xStart").value);
  const b = Number(document.getElementById("xEnd").value);
  if (!isFinite(a) || !isFinite(b) || a === b) return null;
  return [Math.min(a, b), Math.max(a, b)];
}

function visibleIndices() {
  return state.curves.filter(function (c) { return !state.hidden.has(c.index); }).map(function (c) { return c.index; });
}

function updateCreateButton() {
  const button = document.getElementById("create");
  const count = visibleIndices().length;
  button.textContent = "Create in Sketch (" + count + ")";
  button.disabled = count === 0;
}

function initCreatePanel() {
  const unit = document.getElementById("unit");
  UNITS.forEach(function (u) { unit.appendChild(el("option", { value: u, text: "1 = 1 " + u })); });
  const saved = storageGet("sketch", { unit: "mm", x_start: 0, x_end: 10, output: "light" });
  unit.value = UNITS.indexOf(saved.unit) >= 0 ? saved.unit : "mm";
  document.getElementById("xStart").value = saved.x_start;
  document.getElementById("xEnd").value = saved.x_end;
  document.getElementById("output").value = saved.output === "editable" ? "editable" : "light";
  ["unit", "xStart", "xEnd", "output"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", function () {
      storageSet("sketch", sketchSettings());
      draw();
    });
  });
  document.getElementById("create").addEventListener("click", function () {
    const settings = sketchSettings();
    if (!(isFinite(settings.x_start) && isFinite(settings.x_end) && settings.x_start !== settings.x_end)) {
      showStatus("Set different x from / to values.", true);
      return;
    }
    send("graphCreate", Object.assign({ curves: visibleIndices() }, settings));
  });
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

// Parametric curves count fully. y = f(x) curves count only inside the sketch x range, and
// their y values without the top / bottom 2%: near poles (tan, 1/x) they grow without bound
// and would zoom the view out to nothing useful.
function fitView() {
  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  const range = sketchXRange();
  const implicitY = [];
  state.curves.forEach(function (curve) {
    if (state.hidden.has(curve.index)) return;
    curve.pieces.forEach(function (piece) {
      piece.forEach(function (p) {
        if (curve.type === "implicit") {
          if (range && (p[0] < range[0] || p[0] > range[1])) return;
          implicitY.push(p[1]);
          xmin = Math.min(xmin, p[0]); xmax = Math.max(xmax, p[0]);
          return;
        }
        xmin = Math.min(xmin, p[0]); xmax = Math.max(xmax, p[0]);
        ymin = Math.min(ymin, p[1]); ymax = Math.max(ymax, p[1]);
      });
    });
  });
  if (implicitY.length) {
    implicitY.sort(function (a, b) { return a - b; });
    const pick = function (q) { return implicitY[Math.min(implicitY.length - 1, Math.floor(q * (implicitY.length - 1)))]; };
    ymin = Math.min(ymin, pick(0.02));
    ymax = Math.max(ymax, pick(0.98));
    if (range) {
      xmin = Math.min(xmin, range[0]);
      xmax = Math.max(xmax, range[1]);
    }
  }
  if (!isFinite(xmin) || !isFinite(ymin)) return;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const spanX = Math.max(xmax - xmin, 1e-6), spanY = Math.max(ymax - ymin, 1e-6);
  state.scale = 0.85 * Math.min(w / spanX, h / spanY);
  state.cx = (xmin + xmax) / 2;
  state.cy = (ymin + ymax) / 2;
  draw();
  requestData();
}


function zoomBy(factor) {
  state.scale = Math.min(Math.max(state.scale * factor, 1e-4), 1e7);
  draw();
  if (viewNeedsData()) requestData();
}

document.getElementById("fit").addEventListener("click", fitView);
document.getElementById("zoomIn").addEventListener("click", function () { zoomBy(1.5); });
document.getElementById("zoomOut").addEventListener("click", function () { zoomBy(1 / 1.5); });
document.getElementById("home").addEventListener("click", function () {
  state.cx = 0;
  state.cy = 0;
  draw();
  requestData();
});
document.getElementById("refresh").addEventListener("click", requestData);
document.getElementById("addMenu").addEventListener("change", function (event) {
  const value = event.target.value;
  event.target.value = "";
  if (value.indexOf("kind:") === 0) send("graphAdd", { kind: value.slice(5) });
  if (value.indexOf("preset:") === 0) send("graphAdd", { preset: Number(value.slice(7)) });
});

let resizeTimer = null;
window.addEventListener("resize", function () {
  draw();
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(requestData, 200);
});

// ---------- Start ----------

function start() {
  initCreatePanel();
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
