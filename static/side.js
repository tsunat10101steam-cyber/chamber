"use strict";
// 오른쪽 패널: 고른 box 의 bullet(포트 · IP · 게이트웨이 · 경로 · 이미지)과 할 일. 아무것도 안 고르면 chamber 요약.
// 아래쪽에 cobweb(이미지 저장소) · VcoM(가상 머신) 탭 화면도 그린다.
const side = $("#side");
const typing = () => side.contains(document.activeElement) && document.activeElement.matches("input, textarea, select");

function renderSide() {
  if (!S.lab) { side.innerHTML = ""; return; }
  const sel = S.sel;
  if (sel?.t === "box" && byNode(sel.id)) side.innerHTML = boxPanel(byNode(sel.id));
  else if (sel?.t === "link" && S.lab.links.some(l => l.id === sel.id)) side.innerHTML = linkPanel(S.lab.links.find(l => l.id === sel.id));
  else { S.sel = null; side.innerHTML = labPanel(); }
}
function paintPlan() { if (!typing()) renderSide(); }
function paintSideStatus() { if (!typing()) renderSide(); }

const kv = (rows) => `<div class="kv2">${rows.filter(Boolean).map(([k, v]) => `<span>${esc(k)}</span><span>${v}</span>`).join("")}</div>`;
const head = (n, sub) => `<div class="sd-h k-${n.kind}"><span class="ki k-${n.kind}" style="grid-row:span 2">${esc(KIND[n.kind].ic)}</span>
  <input type="text" data-f="name" value="${esc(n.name)}" aria-label="name"><span class="s">${esc(sub)}</span></div>`;
const running = () => S.status?.state === "running";

// ---- chamber 요약 (아무것도 안 골랐을 때)
function labPanel() {
  const st = S.status, p = S.plan, lab = S.lab;
  const host = lab.nodes.find(n => n.kind === "host");
  let h = `<div class="sd-h"><span class="ki" style="grid-row:span 2;background:var(--accent)">CH</span>
    <input type="text" data-lab="name" value="${esc(lab.name)}" aria-label="name">
    <span class="s">${esc(t("lab_counts", { b: lab.nodes.length, l: lab.links.length }))}</span></div>`;
  h += `<h4>${esc(t("h_state"))}</h4>` + kv([
    [t("h_state"), esc(t("st_" + (st?.state || "stopped"), { n: st?.running || 0, m: st?.total || 0 }))],
    host && [t("wsl_ip"), st?.wsl_ip ? `<span class="mono">${esc(st.wsl_ip)}</span>` : "–"],
    [t("subnets"), (p?.subnets || []).map(s => `<span class="mono">${esc(s)}</span>`).join("<br>") || "–"],
  ]);
  h += `<h4>${esc(t("h_options"))}</h4>
    <label class="chk field"><span><input type="checkbox" data-lab="auto_ospf" ${lab.auto_ospf ? "checked" : ""}> ${esc(t("opt_ospf"))}</span></label>
    <p class="muted small">${esc(t("opt_ospf_s"))}</p>
    <label class="chk field"><span><input type="checkbox" data-lab="internet" ${lab.internet ? "checked" : ""}> ${esc(t("opt_internet"))}</span></label>
    <p class="muted small">${esc(t("opt_internet_s"))}</p>`;
  for (const i of p?.issues || []) h += `<div class="issue">${esc(t("issue." + i.code, i))}</div>`;
  h += pingBlock(firstIP());
  h += `<h4>${esc(t("h_howto"))}</h4><ol class="small muted" style="margin:0 16px;padding-left:18px">
    <li>${esc(t("howto1"))}</li><li>${esc(t("howto2"))}</li><li>${esc(t("howto3"))}</li><li>${esc(t("howto4"))}</li></ol>`;
  return h;
}
function firstIP() {
  for (const n of S.lab.nodes) if (n.kind !== "host") for (const f of n.ifaces) if (f.ip) return f.ip.split("/")[0];
  return "";
}
function pingBlock(ip) {
  return `<h4>${esc(t("h_ping"))}</h4><p class="muted small">${esc(t("ping_s"))}</p>
    <div class="ping-row"><input type="text" class="mono" id="pingIp" value="${esc(ip)}" placeholder="10.77.1.10"><button id="pingGo" data-act="ping">${esc(t("ping_go"))}</button></div>
    <pre class="out hidden" id="pingOut"></pre>`;
}

// ---- box
function boxPanel(n) {
  const st = S.status?.boxes?.[n.id];
  const kindLabel = isIOS(n.image) ? `Cisco ${iosPlat(n.image)}` : t("k_" + n.kind);
  let h = head(n, kindLabel + (st ? ` · ${t("box_" + (["running", "exited", "created", "missing", "none"].includes(st) ? st : "other"))}` : ""));
  const acts = [];
  if (WIRED.has(n.kind) && n.kind !== "host") {
    acts.push(`<button class="primary" data-act="${isIOS(n.image) ? "ios" : "console"}">${esc(t(isIOS(n.image) ? "a_ios_console" : "a_console"))}</button>`);
    if (n.kind === "router" && !n.image) acts.push(`<button data-act="vtysh">vtysh</button>`);
    if (isIOS(n.image)) acts.push(`<button data-act="iosreset" title="${esc(t("ios_reset_s"))}">${esc(t("ios_reset"))}</button>`);
  }
  if (n.kind === "vm") {
    const v = S.vcom?.vms.find(v => v.hv === n.ref?.hv && v.id === n.ref?.id);
    acts.push(v?.running ? `<button data-vm="stop">${esc(t("a_stop"))}</button>` : `<button class="primary" data-vm="start">${esc(t("a_start"))}</button>`);
    acts.push(`<button data-vm="gui">${esc(t(n.ref?.hv === "vbox" ? "a_vbox" : "a_vmware"))}</button><button data-vm="ip">${esc(t("a_vm_ip"))}</button>`);
  }
  acts.push(`<button class="danger" data-act="remove">${esc(t("remove"))}</button>`);
  h += `<div class="sd-acts">${acts.join("")}</div>`;

  if (n.kind === "host") {
    h += `<p class="small">${esc(t("host_about"))}</p>`;
    if (S.status?.wsl_ip) h += kv([[t("wsl_ip"), `<span class="mono">${esc(S.status.wsl_ip)}</span>`]]);
  }
  if (n.kind === "whale") h += `<p class="small">${esc(t("whale_about", { n: n.ctr }))}</p>`;
  if (WIRED.has(n.kind)) {
    h += `<h4>${esc(t("h_ports"))}${n.kind !== "host" ? `<button class="mini" data-act="addif">${esc(t("add_port"))}</button>` : ""}</h4><div class="bul">`;
    for (const [i, f] of n.ifaces.entries()) {
      const l = linkAt(n.id, f.name), pe = l && peerOf(l, n.id, f.name), pn = pe && byNode(pe.node);
      h += `<div class="bul-row"><b class="mono" title="${esc(f.name)}">${esc(portLabel(n, i))}</b>
        ${n.kind === "switch" ? `<span class="muted small">${esc(t("l2_port"))}</span>` :
          `<input type="text" class="mono" data-if="${i}" value="${esc(f.ip)}" placeholder="10.77.1.1/24">`}
        ${l ? `<button class="x" data-unlink="${esc(l.id)}" title="${esc(t("unlink"))}">⨯</button>` :
          n.ifaces.length > 1 ? `<button class="x" data-rmif="${i}" title="${esc(t("rm_port"))}">−</button>` : "<span></span>"}
        <span class="peer">${pn ? `→ ${esc(pn.name)} · ${esc(pe.ifc)}` : esc(t("no_peer"))}</span></div>`;
    }
    h += `</div>`;
  }
  if (["pc", "server", "router", "whale"].includes(n.kind)) {
    const auto = S.plan?.gw?.[n.id];
    h += `<label class="field"><span>${esc(t("gateway"))}</span><input type="text" class="mono" data-f="gw" value="${esc(n.gw)}"
      placeholder="${esc(auto ? t("gw_auto", { ip: auto }) : n.kind === "whale" ? t("gw_whale") : t("gw_none"))}"></label>`;
    h += `<h4>${esc(t("h_routes"))}<button class="mini" data-act="addroute">${esc(t("add_route"))}</button></h4>`;
    if (n.routes.length) {
      h += `<div class="bul">${n.routes.map((r, i) => `<div class="bul-row" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto">
        <input type="text" class="mono" data-rt="${i}" data-k="dst" value="${esc(r.dst)}" placeholder="10.77.9.0/24">
        <input type="text" class="mono" data-rt="${i}" data-k="via" value="${esc(r.via)}" placeholder="via 10.77.1.1">
        <button class="x" data-rmrt="${i}">−</button></div>`).join("")}</div>`;
    } else h += `<p class="muted small">${esc(t(n.kind === "router" && S.lab.auto_ospf && !n.image ? "routes_ospf" : "routes_none"))}</p>`;
  }
  if (["router", "pc", "server", "switch"].includes(n.kind)) {
    const opts = imageOptions(n.kind);
    h += `<label class="field"><span>${esc(t("image"))}</span><select data-f="image">${opts.map(o =>
      `<option value="${esc(o.v)}" ${o.v === (n.image || "") ? "selected" : ""}>${esc(o.l)}</option>`).join("")}</select></label>`;
    if (isIOS(n.image)) h += `<p class="muted small">${esc(t("ios_note", { n: maxPorts(n) }))}</p>`;
    else if (n.kind === "router" && n.image) h += `<p class="muted small">${esc(t("image_router_note"))}</p>`;
    if (n.kind === "switch" && n.image) h += `<p class="muted small">${esc(t("image_switch_note"))}</p>`;
  }
  if (n.kind === "vm") h += vmInfo(n);
  if (n.kind === "aws") h += awsInfo(n);
  if (n.kind === "note") h += `<label class="field"><span>${esc(t("k_note"))}</span><textarea data-f="note" rows="6" style="width:100%">${esc(n.note)}</textarea></label>`;
  const ip = n.ifaces.find(f => f.ip)?.ip?.split("/")[0];
  if (ip && n.kind !== "host") h += pingBlock(ip);
  return h;
}
function imageOptions(kind) {
  const o = [{ v: "", l: t("image_default") }];
  const cat = S.cob?.catalog || [];
  for (const c of cat) if (!c.builtin && c.kinds.includes(kind)) o.push({ v: c.image, l: `${t("cw." + c.id)} · ${c.image}${c.have ? "" : " " + t("image_will_pull")}` });
  if (kind === "router") for (const im of S.cob?.ios || []) o.push({ v: im.image, l: `Cisco ${im.platform} · ${im.file}` });
  for (const m of S.cob?.mine || []) o.push({ v: m.image, l: m.image });
  const cur = byNode(S.sel?.id)?.image;
  if (cur && !o.some(x => x.v === cur)) o.push({ v: cur, l: cur });
  return o;
}
function vmInfo(n) {
  const v = S.vcom?.vms.find(v => v.hv === n.ref?.hv && v.id === n.ref?.id);
  const i = n.info || {};
  let h = `<h4>${esc(t("h_vm"))}</h4>` + kv([
    [t("state"), v ? esc(v.running ? t("running") : t("stopped")) : esc(t("vm_gone"))],
    [t("vm_os"), esc(i.os || "–")], [t("vm_cpu"), esc(`${i.cpus || "?"} vCPU · ${i.mem ? i.mem + " MB" : "?"}`)],
    ...(i.nics || []).map(c => [`nic${c.n}`, esc(c.label)]),
    n.ref?.ip && [t("vm_ip"), `<span class="mono">${esc(n.ref.ip)}</span>`],
  ]);
  h += `<p class="muted small">${esc(t("vm_note"))}</p>`;
  return h;
}
function awsInfo(n) {
  const i = n.info || {};
  let h = `<h4>VPC</h4>` + kv([[t("region"), esc(i.region || "")], ["CIDR", `<span class="mono">${esc(i.cidr || "")}</span>`],
    ["ID", `<span class="mono">${esc(n.ref?.vpc || "")}</span>`], [t("igw"), esc(i.igw || "–")]]);
  for (const s of i.subnets || []) {
    h += `<h4 class="mono" style="text-transform:none;letter-spacing:0">${esc(s.name || s.id)} · ${esc(s.cidr)} · ${esc(s.public ? t("public") : t("private"))}</h4>`;
    h += s.res.length ? `<div class="res-list">${s.res.map(r => `<div><span class="t">${esc(r.type)}</span><span class="mono">${esc(r.name || r.id)}</span>
      <span class="sp"></span><span class="muted">${esc(r.state)}</span></div>`).join("")}</div>` : `<p class="muted small">${esc(t("no_res"))}</p>`;
  }
  h += `<p class="muted small">${esc(t("aws_note"))}</p>`;
  return h;
}

// ---- 선
function linkPanel(l) {
  const a = byNode(l.a.node), b = byNode(l.b.node);
  const fa = a.ifaces.find(f => f.name === l.a.ifc), fb = b.ifaces.find(f => f.name === l.b.ifc);
  return `<div class="sd-h"><span class="ki" style="grid-row:span 2;background:var(--wire)">⎯</span><b>${esc(t("link"))}</b>
    <span class="s">${esc(a.name)} ↔ ${esc(b.name)}</span></div>
    <div class="sd-acts"><button class="danger" data-act="remove">${esc(t("unlink"))}</button></div>` +
    kv([[a.name, `<span class="mono">${esc(l.a.ifc)} ${esc(fa?.ip || "")}</span>`], [b.name, `<span class="mono">${esc(l.b.ifc)} ${esc(fb?.ip || "")}</span>`]]) +
    `<p class="muted small">${esc(t("link_about"))}</p>`;
}

// ---- 패널에서 고치기
side.addEventListener("input", (e) => {
  const el = e.target, lab = S.lab;
  if (el.dataset.lab === "name") { lab.name = el.value; const l = S.labs.find(x => x.id === lab.id); if (l) l.name = el.value; paintLabSel(); return save(); }
  const n = S.sel?.t === "box" && byNode(S.sel.id);
  if (!n) return;
  if (el.dataset.f) n[el.dataset.f] = el.value;
  if (el.dataset.if !== undefined) {
    n.ifaces[+el.dataset.if].ip = el.value.trim();
    el.classList.toggle("bad", !!el.value.trim() && !parseIf(el.value.trim()));
  }
  if (el.dataset.rt !== undefined) n.routes[+el.dataset.rt][el.dataset.k] = el.value.trim();
  if (el.dataset.f === "gw") el.classList.toggle("bad", !!el.value.trim() && !/^\d+\.\d+\.\d+\.\d+$/.test(el.value.trim()));
  renderBoard();
  save();
});
side.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.lab === "auto_ospf" || el.dataset.lab === "internet") { S.lab[el.dataset.lab] = el.checked; save(); }
  if (el.dataset.f === "image") renderSide();
});
side.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const n = S.sel?.t === "box" && byNode(S.sel.id);
  const act = b.dataset.act;
  if (act === "remove") return removeSel();
  if (act === "ping") return winPing();
  if (act === "console" || act === "vtysh" || act === "ios") return openConsole(n, act === "console" ? "sh" : act);
  if (act === "iosreset") return iosReset(n);
  if (act === "addif") return addPort(n);
  if (act === "addroute") { n.routes.push({ dst: "", via: "" }); renderSide(); return; }
  if (b.dataset.unlink) { S.lab.links = S.lab.links.filter(l => l.id !== b.dataset.unlink); renderBoard(); renderSide(); return save(); }
  if (b.dataset.rmif !== undefined) { n.ifaces.splice(+b.dataset.rmif, 1); renderBoard(); renderSide(); return save(); }
  if (b.dataset.rmrt !== undefined) { n.routes.splice(+b.dataset.rmrt, 1); renderSide(); return save(); }
  if (b.dataset.vm) return vmAct(n, b.dataset.vm, b);
});
async function iosReset(n) {
  if (!(await ask(t("ios_reset_q", { n: n.name }), t("ios_reset_body"), t("ios_reset"), { danger: true }))) return;
  await doSave();
  runJob(`/api/lab/${S.lab.id}/ios_reset`, t("ios_reset_job", { n: n.name }), { node: n.id });
}
function addPort(n) {
  if (n.ifaces.length >= maxPorts(n)) return toast(t("no_free_port", { n: n.name }));
  const base = n.kind === "whale" ? "ch" : "eth";
  let i = 0;
  while (n.ifaces.some(f => f.name === base + i)) i++;
  n.ifaces.push({ name: base + i, ip: "" });
  renderBoard(); renderSide(); save();
}
async function winPing() {
  const ip = $("#pingIp").value.trim(), out = $("#pingOut"), btn = $("#pingGo");
  btn.disabled = true; out.classList.remove("hidden"); out.textContent = `C:\\> ping ${ip}\n…`;
  try {
    const r = await api("/api/winping", { ip });
    out.textContent = `C:\\> ping ${ip}\n\n${r.out}`;
    out.style.borderLeft = `4px solid ${r.ok ? "var(--run)" : "var(--bad)"}`;
  } catch (e) { out.textContent = e.message; }
  btn.disabled = false;
}
async function vmAct(n, action, btn) {
  btn.disabled = true;
  try {
    const r = await api("/api/vcom/act", { hv: n.ref.hv, id: n.ref.id, action });
    if (action === "ip") { if (r.ip) { n.ref.ip = r.ip; save(); } else toast(t("vm_no_ip")); }
    if (action === "start" || action === "stop") await loadVcom(true);
  } catch (e) { toast(e.message); }
  btn.disabled = false;
  renderSide();
}
function openConsole(n, mode) {
  if (!S.status?.boxes?.[n.id] || S.status.boxes[n.id] !== "running") return toast(t("start_first"));
  openTerm({ lab: S.lab.id, node: n.id, name: n.name + (mode === "vtysh" ? " · vtysh" : mode === "ios" ? " · IOS" : ""), mode });
}

// ---------------------------------------------------------------- cobweb (이미지 저장소)
const PULLS = {};
async function renderCobweb(reload) {
  const el = $("#cobwebView");
  if (reload || !S.cob) {
    try { S.cob = await api("/api/cobweb"); } catch (e) { el.innerHTML = `<div class="msg"><p>${esc(e.message)}</p></div>`; return; }
  }
  const card = (c) => {
    const p = PULLS[c.image];
    return `<div class="card"><div class="t"><span class="ki k-${c.kinds[0]}" style="grid-row:auto">${esc(KIND[c.kinds[0]].ic)}</span>
      <b>${esc(c.mine ? c.image.split("/").pop() : t("cw." + c.id))}</b><span class="sp"></span>
      ${c.have ? `<span class="badge have">${esc(t("cw_have"))}</span>` : ""}</div>
      <div class="img">${esc(c.image)}</div>
      ${c.mine ? "" : `<div class="d">${esc(t("cw." + c.id + "_d"))}</div>`}
      ${p && p.status === "running" ? `<div class="bar"><i style="width:${p.pct || 2}%"></i></div><div class="d">${esc(p.text || "")}</div>` : ""}
      <div class="f">${c.kinds.map(k => `<span class="badge">${esc(t("k_" + k))}</span>`).join("")}
        ${c.license ? `<span>${esc(c.license)}</span>` : ""}<span class="sp"></span>
        <span>${esc(fmtBytes(c.have ? c.local_size : c.size))}</span>
        ${c.have ? (c.builtin ? "" : `<button class="mini ghost" data-cwrm="${esc(c.image)}">${esc(t("remove"))}</button>`) :
          `<button class="mini primary" data-cwpull="${esc(c.image)}" ${p?.status === "running" ? "disabled" : ""}>${esc(t(c.builtin ? "cw_build" : "cw_pull"))}</button>`}</div></div>`;
  };
  el.innerHTML = `<div><div class="pg-h"><h2>cobweb</h2><p>${esc(t("cw_about"))}</p></div>
    <div class="ping-row" style="margin:0 0 16px"><input type="text" class="mono" id="cwName" placeholder="${esc(t("cw_name_ph"))}">
      <button class="primary" id="cwPull">${esc(t("cw_pull_name"))}</button></div>
    <p class="muted small">${esc(t("cw_license"))}</p>
    <div class="cards">${S.cob.catalog.map(card).join("")}</div>
    <div class="sec"><div class="sec-h"><b>${esc(t("cw_ios"))}</b><span class="muted small">${esc(t("cw_ios_s"))}</span><span class="sp"></span>
      <button class="primary" id="iosPick" ${PULLS.__ios ? "disabled" : ""}>${esc(t("cw_ios_pick"))}</button></div>
      ${PULLS.__ios ? `<div style="padding:10px 14px"><div class="bar"><i style="width:${PULLS.__ios.pct || 3}%"></i></div><div class="muted small">${esc(PULLS.__ios.text || "")}</div></div>` : ""}
      ${S.cob.ios.length ? `<table><thead><tr><th>${esc(t("name"))}</th><th>${esc(t("cw_ios_plat"))}</th><th>${esc(t("cw_ios_ports"))}</th><th></th></tr></thead><tbody>
        ${S.cob.ios.map(im => `<tr><td><b>${esc(im.file)}</b><span class="sub mono">${esc(im.image)}</span></td><td>Cisco ${esc(im.platform)}</td>
          <td class="mono small">${esc(im.ports.map(shortIf).join(" · "))}</td>
          <td><div class="acts"><button class="mini ghost" data-cwrm="${esc(im.image)}">${esc(t("remove"))}</button></div></td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">${esc(t("cw_ios_none"))}</div>`}
      <p class="muted small" style="margin:10px 14px">${esc(t("cw_ios_about", { list: Object.keys(S.cob.platforms || {}).join(", ") }))}</p></div>
    <div class="sec"><div class="sec-h"><b>${esc(t("cw_mine"))}</b><span class="muted small">${esc(t("cw_mine_s"))}</span></div>
      ${S.cob.mine.length ? `<div class="cards" style="border:0">${S.cob.mine.map(card).join("")}</div>` : `<div class="empty">${esc(t("cw_mine_none"))}</div>`}</div></div>`;
  $("#cwPull").onclick = () => { const v = $("#cwName").value.trim(); if (v) pullImage(v); };
  $("#iosPick").onclick = importIOS;
  $("#cwName").onkeydown = (e) => { if (e.key === "Enter") $("#cwPull").click(); };
  el.querySelectorAll("[data-cwpull]").forEach(b => b.onclick = () => pullImage(b.dataset.cwpull));
  el.querySelectorAll("[data-cwrm]").forEach(b => b.onclick = async () => {
    try { await api("/api/cobweb/remove", { image: b.dataset.cwrm }); } catch (e) { toast(e.message); }
    renderCobweb(true);
  });
}
async function pullImage(image) {
  let r;
  try { r = await api("/api/cobweb/pull", { image }); } catch (e) { return toast(e.message); }
  const p = PULLS[image] = { status: "running", pct: 0, text: t("cw_pulling") };
  renderCobweb();
  let since = 0;
  while (p.status === "running") {
    await new Promise(res => setTimeout(res, 700));
    let j;
    try { j = await api(`/api/jobs/${r.job_id}?since=${since}`); } catch { continue; }
    since = j.next; p.status = j.status;
    for (const l of j.logs) {
      if (l.k === "pull") p.pct = l.p.pct;
      p.text = logText(l);
      if (l.k === "error") toast(p.text);
    }
    if (S.tab === "cobweb") renderCobweb();
  }
  if (p.status === "done") toast(t("cw_done", { n: image }));
  delete PULLS[image];
  if (S.tab === "cobweb") renderCobweb(true); else S.cob = null;
}

// Cisco IOS 가져오기: 이 PC 의 파일 선택 창 → box 이미지 만들기 (처음엔 dynamips 도 빌드)
async function importIOS() {
  let pick;
  try { pick = await api("/api/cobweb/ios_pick", {}); } catch (e) { return toast(e.message); }
  if (!pick.path) return;
  if (!(await ask(t("cw_ios_q"), t("cw_ios_q_body", { f: pick.path, p: pick.platform }), t("cw_ios_go")))) return;
  let r;
  try { r = await api("/api/cobweb/ios_import", { path: pick.path }); } catch (e) { return toast(e.message); }
  const p = PULLS.__ios = { status: "running", pct: 3, text: t("cw_pulling") };
  renderCobweb();
  let since = 0, steps = 0;
  while (p.status === "running") {
    await new Promise(res => setTimeout(res, 800));
    let j;
    try { j = await api(`/api/jobs/${r.job_id}?since=${since}`); } catch { continue; }
    since = j.next; p.status = j.status;
    for (const l of j.logs) {
      if (l.k === "build_step") p.pct = Math.min(95, 5 + (++steps) * 8);
      p.text = logText(l);
      if (l.k === "error") toast(p.text);
    }
    if (S.tab === "cobweb") renderCobweb();
  }
  delete PULLS.__ios;
  if (p.status === "done") toast(t("cw_ios_done"));
  S.cob = await api("/api/cobweb").catch(() => S.cob);
  if (S.tab === "cobweb") renderCobweb(); else renderPalette();
}

// ---------------------------------------------------------------- VcoM (가상 머신)
async function renderVcom(reload) {
  const el = $("#vcomView");
  if (reload || !S.vcom) {
    el.innerHTML = `<div class="msg"><div class="spin"></div></div>`;
    await loadVcom(true);
  }
  const v = S.vcom;
  el.innerHTML = `<div><div class="pg-h"><h2>VcoM</h2><p>${esc(t("vc_about"))}</p><span class="sp"></span>
      <button id="vcReload">${esc(t("refresh"))}</button></div>
    <div class="cards">${v.hypervisors.map(h => `<div class="card"><div class="t"><span class="ki k-vm" style="grid-row:auto">VM</span><b>${esc(h.name)}</b>
      <span class="sp"></span><span class="badge have">${esc(t("vc_found"))}</span></div><div class="img">${esc(h.path)}</div></div>`).join("") ||
      `<div class="card"><b>${esc(t("hv_none"))}</b><div class="d">${esc(t("hv_none_s"))}</div></div>`}
      ${v.host_nets.length ? `<div class="card"><div class="t"><b>${esc(t("vc_hostnets"))}</b></div>${v.host_nets.map(n =>
        `<div class="img">${esc(n.name)} · ${esc(n.ip)}</div>`).join("")}<div class="d">${esc(t("vc_hostnets_s"))}</div></div>` : ""}</div>
    <div class="sec"><div class="sec-h"><b>${esc(t("vc_vms"))}</b><span class="muted small">${esc(t("vc_vms_s"))}</span></div>
    ${v.vms.length ? `<table><thead><tr><th>${esc(t("name"))}</th><th>${esc(t("vm_cpu"))}</th><th>${esc(t("vc_net"))}</th><th>${esc(t("state"))}</th><th></th></tr></thead><tbody>
      ${v.vms.map((m, i) => `<tr><td><b>${esc(m.name)}</b><span class="sub mono">${esc(m.os)}</span></td>
        <td>${esc(m.cpus ? `${m.cpus} vCPU · ${m.mem} MB` : "–")}</td>
        <td>${m.nics.map(c => `<span class="badge">${esc(c.label)}</span>`).join(" ") || "–"}</td>
        <td><span class="dot ${m.running ? "running" : ""}"></span> ${esc(m.running ? t("running") : t("stopped"))}</td>
        <td><div class="acts">${m.running ? `<button class="mini" data-vc="stop:${i}">${esc(t("a_stop"))}</button>` : `<button class="mini" data-vc="start:${i}">${esc(t("a_start"))}</button>`}
          <button class="mini" data-vc="gui:${i}">${esc(t(m.hv === "vbox" ? "a_vbox" : "a_vmware"))}</button>
          <button class="mini primary" data-vc="place:${i}">${esc(t("vc_place"))}</button></div></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty">${esc(t("vm_none"))}</div>`}</div></div>`;
  $("#vcReload").onclick = () => renderVcom(true);
  el.querySelectorAll("[data-vc]").forEach(b => b.onclick = async () => {
    const [a, i] = b.dataset.vc.split(":"), m = v.vms[+i];
    if (a === "place") { setTab("lab"); return dropItem({ kind: "vm", ref: { hv: m.hv, id: m.id } }); }
    b.disabled = true;
    try { await api("/api/vcom/act", { hv: m.hv, id: m.id, action: a }); } catch (e) { toast(e.message); }
    renderVcom(true);
  });
}
// box 이미지 고르기에 cobweb 목록이 필요하다
api("/api/cobweb").then(c => { S.cob = c; renderPalette(); if (S.lab) renderBoard(); }, () => {});
