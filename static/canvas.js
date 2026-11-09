"use strict";
// 화이트보드: box 를 놓고 · 옮기고 · 포트(bullet)끼리 선을 잇는다. 선을 이으면 IP 를 알아서 매긴다.
// box 위치·포트·선은 S.lab 에 바로 고치고 save() 로 저장한다. 그리는 것은 매번 처음부터 (box 가 수십 개라 충분히 빠르다).
const KIND = {
  router: { ic: "R", ifs: ["eth0", "eth1"], name: "R" },
  switch: { ic: "SW", ifs: ["eth0", "eth1", "eth2", "eth3"], name: "SW" },
  pc: { ic: "PC", ifs: ["eth0"], name: "PC" },
  server: { ic: "SV", ifs: ["eth0"], name: "SRV", image: "nginx:alpine" },
  host: { ic: "⌂", ifs: ["ch0"] },
  whale: { ic: "🐳", ifs: ["ch0"] },
  vm: { ic: "VM", ifs: [] },
  aws: { ic: "AWS", ifs: [] },
  note: { ic: "✎", ifs: [] },
};
const WIRED = new Set(["router", "switch", "pc", "server", "host", "whale"]);
const BOX_W = 176;
// Cisco(Dynamips) 라우터: 이미지 이름이 chamber/ios-<플랫폼>:… , 포트 이름은 cobweb 목록(S.cob.platforms)에서
const isIOS = (img) => (img || "").startsWith("chamber/ios-");
const iosPlat = (img) => isIOS(img) ? img.slice(12).split(":")[0] : "";
// L3 스위치(Cisco + NM-16ESW): 스위치 포트 Fa1/0~15 가 먼저, 라우티드 포트 Fa0/0 · 0/1 이 뒤
const isL3sw = (n) => n.kind === "switch" && isIOS(n.image);
const isSwPort = (n, i) => isL3sw(n) && i < 16;
const iosPortsOf = (n) => (isL3sw(n) ? S.cob?.switch_platforms : S.cob?.platforms)?.[iosPlat(n.image)] || [];
const iosPorts = (img) => S.cob?.platforms?.[iosPlat(img)] || [];
const shortIf = (s) => s.replace("FastEthernet", "Fa").replace("GigabitEthernet", "Gi");
function portLabel(n, i) { return isIOS(n.image) && iosPortsOf(n)[i] ? shortIf(iosPortsOf(n)[i]) : n.ifaces[i].name; }
function maxPorts(n) { return isIOS(n.image) ? iosPortsOf(n).length || 2 : n.kind === "host" ? 1 : 16; }
// box 에 보이는 포트 값: IP, L3 스위치의 스위치 포트는 VLAN
function portText(n, i) {
  const f = n.ifaces[i];
  if (isSwPort(n, i)) return f.vlan === "trunk" ? "trunk" : `vlan ${f.vlan || 1}`;
  return n.kind === "switch" && !isL3sw(n) ? "" : f.ip || "–";
}
const byNode = (id) => S.lab.nodes.find(n => n.id === id);
const linkAt = (nid, ifc) => S.lab.links.find(l => (l.a.node === nid && l.a.ifc === ifc) || (l.b.node === nid && l.b.ifc === ifc));
const peerOf = (l, nid, ifc) => (l.a.node === nid && l.a.ifc === ifc) ? l.b : l.a;
const uid = (p) => p + Math.random().toString(36).slice(2, 7);

// ---------------------------------------------------------------- 팔레트 (왼쪽)
function renderPalette() {
  const el = $("#palette");
  if (!el) return;
  const hasHost = S.lab?.nodes.some(n => n.kind === "host");
  const item = (kind, title, sub, extra, dis) =>
    `<div class="pal-item k-${kind}${dis ? " dim" : ""}" draggable="${dis ? "false" : "true"}" data-pal='${esc(JSON.stringify({ kind, ...extra }))}'
      title="${esc(dis || t("pal_drag"))}"><span class="ki">${esc(KIND[kind].ic)}</span><b>${esc(title)}</b><span class="s">${esc(sub)}</span></div>`;
  let h = `<div class="pal-h">${esc(t("pal_devices"))}</div>`;
  h += item("router", t("k_router"), t("k_router_s"), {});
  h += item("switch", t("k_switch"), t("k_switch_s"), {});
  h += item("pc", t("k_pc"), t("k_pc_s"), {});
  h += item("server", t("k_server"), t("k_server_s"), {});
  for (const im of S.cob?.ios || []) h += item("router", `Cisco ${im.platform}`, im.file, { image: im.image });
  for (const im of S.cob?.ios || []) if (im.switch_ports?.length) h += item("switch", t("k_l3sw", { p: im.platform }), im.file, { image: im.image });
  h += item("host", t("k_host"), t("k_host_s"), {},
    hasHost ? t("host_one") : S.engine && !S.engine.wsl ? t("host_no_wsl") : "");
  h += item("note", t("k_note"), t("k_note_s"), {});
  // Whale: 이미 있는 Docker 컨테이너
  h += `<div class="pal-h">Whale<button class="ghost mini" id="palWhale" title="${esc(t("refresh"))}">↻</button></div>`;
  if (!S.whale) h += `<div class="pal-note">${esc(t("loading"))}</div>`;
  else if (!S.whale.containers.length) h += `<div class="pal-note">${esc(t("whale_none"))}</div>`;
  else h += S.whale.containers.slice(0, 30).map(c => item("whale", c.name, `${c.image}${c.state !== "running" ? " · " + c.state : ""}`, { ctr: c.name })).join("");
  if (S.whale?.app.running) h += `<div class="pal-note"><a href="http://127.0.0.1:8766/" target="_blank" rel="noopener">${esc(t("whale_open"))} ↗</a></div>`;
  // VcoM: 가상 머신
  h += `<div class="pal-h">VcoM<button class="ghost mini" id="palVcom" title="${esc(t("refresh"))}">↻</button></div>`;
  if (!S.vcom) h += `<div class="pal-note">${esc(t("loading"))}</div>`;
  else if (!S.vcom.vms.length) h += `<div class="pal-note">${esc(S.vcom.hypervisors.length ? t("vm_none") : t("hv_none"))}</div>`;
  else h += S.vcom.vms.map(v => item("vm", v.name, `${v.hv === "vmware" ? "VMware" : "VirtualBox"} · ${v.running ? t("running") : t("stopped")}`,
    { ref: { hv: v.hv, id: v.id } })).join("");
  // AWS (Boom)
  h += `<div class="pal-h">AWS · Boom</div>`;
  if (!S.boomVpcs?.length) h += `<div class="pal-note">${esc(S.boom?.running ? t("boom_on") : t("boom_off"))}</div>`;
  for (const v of S.boomVpcs || []) {
    const placed = S.lab?.nodes.some(n => n.kind === "aws" && n.ref?.vpc === v.id);
    h += item("aws", v.name || v.id, `${v.region} · ${v.cidr}`, { vpc: v.id }, placed ? t("aws_placed") : "");
  }
  h += `<div class="pal-note"><button class="mini" id="palBoom" ${S.boom?.running ? "" : "disabled"}>${esc(t("boom_import"))}</button></div>`;
  el.innerHTML = h;
  el.querySelectorAll("[data-pal]").forEach(p => {
    p.ondragstart = (e) => { e.dataTransfer.setData("text/chamber", p.dataset.pal); e.dataTransfer.effectAllowed = "copy"; };
    p.ondblclick = () => { if (p.getAttribute("draggable") === "true") dropItem(JSON.parse(p.dataset.pal)); };
  });
  $("#palWhale").onclick = () => loadWhale(true);
  $("#palVcom").onclick = () => loadVcom(true);
  $("#palBoom").onclick = importBoom;
  if (!S.whale) loadWhale();
  if (!S.vcom) loadVcom();
  if (!S.boom) api("/api/boom").then(b => { S.boom = b; renderPalette(); }, () => { S.boom = { running: false }; });
}
async function loadWhale(force) {
  try { S.whale = await api("/api/whale"); } catch { S.whale = { app: {}, containers: [] }; }
  renderPalette();
}
async function loadVcom(force) {
  try { S.vcom = await api("/api/vcom"); } catch { S.vcom = { hypervisors: [], vms: [], host_nets: [] }; }
  renderPalette();
  if (S.tab === "vcom") renderVcom();
}

// ---------------------------------------------------------------- box 만들기
function nextName(prefix) {
  const used = new Set(S.lab.nodes.map(n => n.name));
  for (let i = 1; ; i++) if (!used.has(prefix + i)) return prefix + i;
}
function addNode(spec, x, y) {
  const k = KIND[spec.kind];
  const n = { id: uid("n"), kind: spec.kind, x: Math.max(0, Math.round(x / 8) * 8), y: Math.max(0, Math.round(y / 8) * 8),
    ifaces: k.ifs.map(name => ({ name, ip: "" })), gw: "", routes: [], note: "" };
  if (spec.kind === "host") n.name = t("k_host");
  else if (spec.kind === "whale") { n.name = spec.ctr; n.ctr = spec.ctr; }
  else if (spec.kind === "vm") {
    const v = S.vcom?.vms.find(v => v.hv === spec.ref.hv && v.id === spec.ref.id);
    n.name = v?.name || "VM"; n.ref = spec.ref;
    n.info = v ? { os: v.os, cpus: v.cpus, mem: v.mem, nics: v.nics } : null;
  } else if (spec.kind === "aws") { n.name = spec.name; n.ref = spec.ref; n.info = spec.info; }
  else if (spec.kind === "note") { n.name = t("k_note"); n.note = t("note_default"); }
  else { n.name = nextName(k.name); n.image = spec.image || k.image || ""; }
  S.lab.nodes.push(n);
  return n;
}
function dropItem(spec, x, y) {
  if (spec.kind === "aws") {  // 옆 메뉴의 Boom VPC → box
    const v = S.boomVpcs?.find(v => v.id === spec.vpc);
    if (!v || S.lab.nodes.some(n => n.kind === "aws" && n.ref?.vpc === v.id)) return;
    spec = { kind: "aws", name: v.name || v.id, ref: { vpc: v.id, region: v.region }, info: vpcInfo(v) };
  }
  if (x === undefined) [x, y] = freeSpot();  // 더블클릭: 보이는 곳에서 비어 있는 자리
  const n = addNode(spec, x, y);
  S.sel = { t: "box", id: n.id };
  renderBoard(); renderSide(); renderPalette(); save();
}
// 보이는 영역 왼쪽 위부터 격자로 훑어 다른 box 와 겹치지 않는 첫 자리
function freeSpot() {
  const w = $("#boardWrap"), GX = BOX_W + 64, GY = 150;
  const rects = [...board.querySelectorAll(".box")].map(b => {
    const n = byNode(b.dataset.node);
    return { x: n.x, y: n.y, w: BOX_W, h: b.offsetHeight };
  });
  const x0 = w.scrollLeft + 40, y0 = w.scrollTop + 40;
  const cols = Math.max(1, Math.floor((w.clientWidth - 80) / GX));
  for (let i = 0; i < 400; i++) {
    const x = x0 + (i % cols) * GX, y = y0 + Math.floor(i / cols) * GY;
    if (!rects.some(r => x < r.x + r.w + 24 && x + BOX_W + 24 > r.x && y < r.y + r.h + 24 && y + 130 > r.y)) return [x, y];
  }
  return [x0, y0];
}
const board = $("#board");
board.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/chamber")) { e.preventDefault(); board.classList.add("drop"); } });
board.addEventListener("dragleave", () => board.classList.remove("drop"));
board.addEventListener("drop", (e) => {
  board.classList.remove("drop");
  const raw = e.dataTransfer.getData("text/chamber");
  if (!raw) return;
  e.preventDefault();
  const r = board.getBoundingClientRect();
  dropItem(JSON.parse(raw), e.clientX - r.left - 30, e.clientY - r.top - 16);
});

const vpcInfo = (v) => ({ region: v.region, cidr: v.cidr, igw: v.igw, default: v.default, subnets: v.subnets });
async function importBoom() {
  const b = $("#palBoom");
  b.disabled = true; b.textContent = t("boom_importing");
  try {
    const r = await api("/api/boom/import", {});
    // 화이트보드에 바로 그리지 않고 옆 메뉴에 둔다. 이미 놓인 AWS box 는 내용만 새로
    S.boomVpcs = r.vpcs;
    let changed = false;
    for (const v of r.vpcs) {
      const old = S.lab?.nodes.find(n => n.kind === "aws" && n.ref?.vpc === v.id);
      if (old) { old.info = vpcInfo(v); changed = true; }
    }
    if (changed) { renderBoard(); save(); }
    toast(r.vpcs.length ? t("boom_done", { n: r.vpcs.length }) : t("boom_empty"));
  } catch (e) { toast(e.message); }
  renderPalette();
}

// ---------------------------------------------------------------- 그리기
function boxSub(n) {
  if (isIOS(n.image)) return `Cisco ${iosPlat(n.image)} · IOS`;
  if (n.kind === "whale") return t("k_whale");
  if (n.kind === "vm") return n.info?.os || "VM";
  if (n.kind === "aws") return `${n.info?.region || ""} · ${n.info?.cidr || ""}`;
  if (n.kind === "note") return "";
  if (n.kind === "host") return S.status?.wsl_ip ? `WSL ${S.status.wsl_ip}` : t("k_host_s");
  return n.image ? n.image.replace(/:latest$/, "") : t("k_" + n.kind);
}
function renderBoard() {
  if (!S.lab) return;
  board.querySelectorAll(".box").forEach(b => b.remove());
  for (const n of S.lab.nodes) {
    const el = document.createElement("div");
    el.className = `box k-${n.kind}${S.sel?.t === "box" && S.sel.id === n.id ? " sel" : ""}`;
    el.dataset.node = n.id;
    el.style.left = n.x + "px"; el.style.top = n.y + "px";
    let ports = "";
    if (WIRED.has(n.kind)) {
      ports = `<div class="ports">${n.ifaces.map((f, i) => {
        const l = linkAt(n.id, f.name);
        return `<div class="port" data-ifc="${esc(f.name)}" title="${esc(f.name)}"><b>${esc(portLabel(n, i))}</b><span class="ip">${esc(portText(n, i))}</span>
          <i class="pin${l ? " on" : ""}" data-pin="${esc(f.name)}" title="${esc(t("pin_hint"))}"></i></div>`;
      }).join("")}</div>`;
    } else if (n.kind === "vm") {
      ports = `<div class="ports">${(n.info?.nics || []).map(c => `<div class="port"><b>nic${c.n}</b><span class="ip">${esc(c.label)}</span></div>`).join("")}</div>`;
    } else if (n.kind === "aws") {
      const subs = n.info?.subnets || [];
      ports = `<div class="ports">${subs.slice(0, 6).map(s => `<div class="port"><b>${esc(s.public ? "pub" : "prv")}</b><span class="ip">${esc(s.cidr)}</span></div>`).join("")}
        ${subs.length > 6 ? `<div class="port"><span class="ip">+${subs.length - 6}</span></div>` : ""}</div>`;
    } else if (n.kind === "note") {
      ports = `<div class="box-note">${esc(n.note)}</div>`;
    }
    el.innerHTML = `<div class="box-h"><span class="ki k-${n.kind}">${esc(KIND[n.kind].ic)}</span><b>${esc(n.name)}</b>
      <span class="s"><i class="dot" data-dot="${n.id}"></i><span>${esc(boxSub(n))}</span></span></div>${ports}`;
    board.append(el);
  }
  $("#boardEmpty").classList.toggle("hidden", S.lab.nodes.length > 0);
  $("#boardEmpty").innerHTML = `<b>${esc(t("empty_title"))}</b>${esc(t("empty_body"))}`;
  paintBoxStates();
  drawWires();
}
function pinXY(nid, ifc, side) {
  const box = board.querySelector(`.box[data-node="${nid}"]`);
  const port = box?.querySelector(`.port[data-ifc="${CSS.escape(ifc)}"]`);
  if (!box || !port) return null;
  const n = byNode(nid);
  return { x: n.x + (side === "l" ? 0 : BOX_W), y: n.y + port.offsetTop + port.offsetHeight / 2 };
}
// 선이 어느 쪽 옆구리로 나갈지: 상대가 왼쪽에 있으면 왼쪽
function sideOf(n, other) { return other.x + BOX_W / 2 < n.x ? "l" : "r"; }
function curve(a, b, sa, sb) {
  const dx = Math.max(40, Math.abs(b.x - a.x) / 2);
  const c1 = a.x + (sa === "l" ? -dx : dx), c2 = b.x + (sb === "l" ? -dx : dx);
  return `M${a.x},${a.y} C${c1},${a.y} ${c2},${b.y} ${b.x},${b.y}`;
}
function drawWires(temp) {
  const svg = $("#wires");
  let h = "";
  const up = S.status?.state === "running";
  for (const l of S.lab.links) {
    const na = byNode(l.a.node), nb = byNode(l.b.node);
    if (!na || !nb) continue;
    const sa = sideOf(na, nb), sb = sideOf(nb, na);
    const a = pinXY(l.a.node, l.a.ifc, sa), b = pinXY(l.b.node, l.b.ifc, sb);
    if (!a || !b) continue;
    const d = curve(a, b, sa, sb);
    const sel = S.sel?.t === "link" && S.sel.id === l.id;
    const on = up && S.status.boxes[na.id] !== "exited" && S.status.boxes[nb.id] !== "exited";
    h += `<path class="w${on ? " up" : ""}${sel ? " sel" : ""}" d="${d}"/><path class="w-hit" data-link="${esc(l.id)}" d="${d}"/>`;
    // 핀을 실제 선이 나가는 쪽으로
    movePin(l.a.node, l.a.ifc, sa); movePin(l.b.node, l.b.ifc, sb);
  }
  if (temp) h += `<path class="w temp" d="${curve(temp.a, temp.b, temp.sa, temp.b.x < temp.a.x ? "r" : "l")}"/>`;
  svg.innerHTML = h;
}
function movePin(nid, ifc, side) {
  const pin = board.querySelector(`.box[data-node="${nid}"] .port[data-ifc="${CSS.escape(ifc)}"] .pin`);
  if (pin) { pin.style.left = side === "l" ? "-6px" : ""; pin.style.right = side === "l" ? "auto" : ""; }
}
function paintBoxStates() {
  const st = S.status;
  board.querySelectorAll("[data-dot]").forEach(d => {
    const s = st?.boxes?.[d.dataset.dot];
    d.className = "dot" + (s === "running" ? (st.state === "running" ? " running" : " stale") : "");
    d.title = s ? t("box_" + (["running", "exited", "created", "missing", "none"].includes(s) ? s : "other")) : "";
  });
  if (S.lab) drawWires();
}

// ---------------------------------------------------------------- 옮기기 · 선 잇기 · 고르기
let drag = null;
board.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  const pin = e.target.closest("[data-pin]");
  const boxEl = e.target.closest(".box");
  if (pin && boxEl) {
    const nid = boxEl.dataset.node, ifc = pin.dataset.pin;
    if (linkAt(nid, ifc)) { toast(t("pin_used")); return; }
    e.preventDefault();
    const n = byNode(nid);
    drag = { kind: "wire", nid, ifc, a: pinXY(nid, ifc, "r"), sa: "r" };
    board.setPointerCapture(e.pointerId);
    return;
  }
  if (boxEl && e.target.closest(".box-h")) {
    const n = byNode(boxEl.dataset.node);
    drag = { kind: "move", n, el: boxEl, dx: e.clientX - n.x, dy: e.clientY - n.y, moved: false };
    board.setPointerCapture(e.pointerId);
    select({ t: "box", id: n.id });
    return;
  }
  if (boxEl) { select({ t: "box", id: boxEl.dataset.node }); return; }
  const w = e.target.closest("[data-link]");
  if (w) { select({ t: "link", id: w.dataset.link }); return; }
  select(null);
});
board.addEventListener("pointermove", (e) => {
  if (!drag) return;
  const r = board.getBoundingClientRect();
  if (drag.kind === "move") {
    const x = Math.max(0, Math.round((e.clientX - drag.dx) / 8) * 8), y = Math.max(0, Math.round((e.clientY - drag.dy) / 8) * 8);
    if (x === drag.n.x && y === drag.n.y) return;
    drag.n.x = x; drag.n.y = y; drag.moved = true;
    drag.el.style.left = x + "px"; drag.el.style.top = y + "px";
    drawWires();
  } else {
    const b = { x: e.clientX - r.left, y: e.clientY - r.top };
    drag.sa = b.x < drag.a.x - 20 ? "l" : "r";
    drag.a = pinXY(drag.nid, drag.ifc, drag.sa);
    board.querySelectorAll(".pin.target").forEach(p => p.classList.remove("target"));
    const over = document.elementFromPoint(e.clientX, e.clientY)?.closest("[data-pin]");
    over?.classList.add("target");
    drawWires({ a: drag.a, b, sa: drag.sa });
  }
});
board.addEventListener("pointerup", (e) => {
  if (!drag) return;
  const d = drag;
  drag = null;
  if (d.kind === "move") { if (d.moved) save(); return; }
  board.querySelectorAll(".pin.target").forEach(p => p.classList.remove("target"));
  const el = document.elementFromPoint(e.clientX, e.clientY);
  const boxEl = el?.closest(".box"), pin = el?.closest("[data-pin]");
  if (boxEl && boxEl.dataset.node !== d.nid) connect(d.nid, d.ifc, boxEl.dataset.node, pin?.dataset.pin);
  drawWires();
});
board.addEventListener("dblclick", (e) => {
  // 끌기 때문에 포인터를 보드가 잡고 있어서 e.target 이 보드가 될 수 있다 → 위치로 찾는다
  const boxEl = document.elementFromPoint(e.clientX, e.clientY)?.closest(".box");
  if (!boxEl) return;
  const n = byNode(boxEl.dataset.node);
  if (WIRED.has(n.kind) && n.kind !== "host") openConsole(n, isIOS(n.image) ? "ios" : "sh");
});
addEventListener("keydown", (e) => {
  if (S.tab !== "lab" || !S.sel || document.querySelector("dialog[open]")) return;
  if (e.target.closest("input, textarea, select, #term")) return;
  if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); removeSel(); }
  if (e.key === "Escape") select(null);
});
function select(sel) {
  S.sel = sel;
  board.querySelectorAll(".box").forEach(b => b.classList.toggle("sel", sel?.t === "box" && b.dataset.node === sel.id));
  drawWires();
  renderSide();
}
async function removeSel() {
  const sel = S.sel;
  if (sel.t === "link") {
    S.lab.links = S.lab.links.filter(l => l.id !== sel.id);
  } else {
    const n = byNode(sel.id);
    if (!n) return;
    const linked = S.lab.links.filter(l => l.a.node === n.id || l.b.node === n.id).length;
    if (S.status?.boxes?.[n.id] && !["none", "missing"].includes(S.status.boxes[n.id]) && n.kind !== "whale") {
      if (!(await ask(t("box_remove_q", { n: n.name }), t("box_remove_body"), t("remove"), { danger: true }))) return;
      api(`/api/lab/${S.lab.id}/box_remove`, { node: n.id }).catch(e => toast(e.message));
    }
    S.lab.links = S.lab.links.filter(l => l.a.node !== n.id && l.b.node !== n.id);
    S.lab.nodes = S.lab.nodes.filter(x => x !== n);
  }
  S.sel = null;
  renderBoard(); renderSide(); renderPalette(); save();
}

// ---------------------------------------------------------------- 선 잇기 + IP 자동
function freeIface(n, want) {
  if (want) return linkAt(n.id, want) ? null : want;
  const f = n.ifaces.find(f => !linkAt(n.id, f.name));
  if (f) return f.name;
  if (n.kind === "host" || n.ifaces.length >= maxPorts(n)) return null;
  const base = n.kind === "whale" ? "ch" : "eth";
  let i = 0;
  while (n.ifaces.some(f => f.name === base + i)) i++;
  n.ifaces.push({ name: base + i, ip: "" });
  return base + i;
}
function connect(aid, aifc, bid, bifc) {
  const a = byNode(aid), b = byNode(bid);
  if (!WIRED.has(b.kind)) return toast(t("no_wire_kind"));
  if (a.kind === "host" && b.kind === "host") return;
  const bi = freeIface(b, bifc);
  if (!bi) return toast(t(bifc ? "pin_used" : "no_free_port", { n: b.name }));
  const l = { id: uid("l"), a: { node: aid, ifc: aifc }, b: { node: bid, ifc: bi } };
  S.lab.links.push(l);
  autoIP(l);
  renderBoard(); renderSide(); save();
}
const ip2n = (s) => s.split(".").reduce((a, x) => a * 256 + +x, 0);
const n2ip = (n) => [24, 16, 8, 0].map(s => (n >>> s) & 255).join(".");
function parseIf(s) {
  const m = /^(\d+\.\d+\.\d+\.\d+)\/(\d+)$/.exec(s || "");
  if (!m) return null;
  const len = +m[2], ip = ip2n(m[1]), mask = len ? (0xffffffff << (32 - len)) >>> 0 : 0;
  return { ip, len, net: (ip & mask) >>> 0, mask };
}
// 스위치를 건너 같은 L2 구간에 있는 (box, 포트) 들
function segment(nid, ifc, seen = new Set()) {
  const out = [];
  const visit = (id, f) => {
    const key = id + "/" + f;
    if (seen.has(key)) return;
    seen.add(key);
    const n = byNode(id);
    const fi = n.ifaces.findIndex(x => x.name === f);
    if (isL3sw(n)) {  // L3 스위치: 스위치 포트는 그 VLAN 의 SVI, 라우티드 포트는 라우터처럼
      out.push({ n, f: n.ifaces[fi], sw: isSwPort(n, fi) });
      return;
    }
    if (n.kind === "switch") {
      for (const p of n.ifaces) {
        if (seen.has(id + "/" + p.name) && p.name !== f) continue;
        seen.add(id + "/" + p.name);
        const l = linkAt(id, p.name);
        if (l) { const pe = peerOf(l, id, p.name); visit(pe.node, pe.ifc); }
      }
    } else {
      out.push({ n, f: n.ifaces.find(x => x.name === f) });
      const l = linkAt(id, f);
      if (l) { const pe = peerOf(l, id, f); visit(pe.node, pe.ifc); }
    }
  };
  visit(nid, ifc);
  return out;
}
function autoIP(l) {
  const seg = segment(l.a.node, l.a.ifc);
  // L3 스위치의 스위치 포트 쪽: 그 포트 VLAN 의 SVI 가 이 구간의 게이트웨이
  const l3 = seg.find(x => x.sw);
  const vlan = l3 ? (l3.f.vlan === "trunk" ? null : +(l3.f.vlan || 1)) : null;
  const svi = l3 && vlan ? (l3.n.svis ||= []).find(s => s.vlan === vlan) : null;
  const need = seg.filter(x => x.f && !x.f.ip && !x.sw && (x.n.kind !== "switch" || isL3sw(x.n)));
  if (!need.length && !(l3 && vlan && !svi?.ip)) return;
  let sub = (svi?.ip && parseIf(svi.ip)) || seg.filter(x => !x.sw).map(x => parseIf(x.f?.ip)).find(Boolean);
  if (!sub) {  // 새 구간: 10.77.N.0/24 중 비어 있는 것
    const used = new Set();
    S.lab.nodes.forEach(n => [...n.ifaces, ...(n.svis || [])].forEach(f => { const p = parseIf(f.ip); if (p) used.add(p.net); }));
    for (let i = 1; i < 255; i++) {
      const net = ip2n(`10.77.${i}.0`);
      if (!used.has(net)) { sub = { net, len: 24, mask: 0xffffff00 }; break; }
    }
    if (!sub) return;
  }
  const taken = new Set();
  S.lab.nodes.forEach(n => [...n.ifaces, ...(n.svis || [])].forEach(f => { const p = parseIf(f.ip); if (p && p.net === sub.net) taken.add(p.ip - sub.net); }));
  const max = 2 ** (32 - sub.len) - 2;
  const pick = (from, down) => {
    for (let h = from; down ? h >= 1 : h <= max; h += down ? -1 : 1) if (!taken.has(h)) { taken.add(h); return h; }
    return null;
  };
  // L3 스위치의 SVI 가 없으면 만든다 (.1)
  if (l3 && vlan && !svi?.ip) {
    const h = pick(1);
    if (h) { if (svi) svi.ip = `${n2ip(sub.net + h)}/${sub.len}`; else l3.n.svis.push({ vlan, ip: `${n2ip(sub.net + h)}/${sub.len}` }); }
  }
  // 라우터는 .1 부터, 이 PC 는 끝(.254), 나머지는 .10 부터
  const rt = (x) => x.n.kind === "router" || isL3sw(x.n);
  need.sort((x, y) => !rt(x) - !rt(y));
  for (const x of need) {
    const h = rt(x) ? pick(1) : x.n.kind === "host" ? pick(max, true) : pick(Math.min(10, max));
    if (h) x.f.ip = `${n2ip(sub.net + h)}/${sub.len}`;
  }
}
