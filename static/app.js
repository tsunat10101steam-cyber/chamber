"use strict";
// Chamber 화면 공통: chamber(실습 네트워크) 불러오기 · 저장 · 시작/중지, 탭, 설정.
// 화이트보드는 canvas.js, 오른쪽 자세히(bullet)와 cobweb · VcoM 화면은 side.js, box 콘솔은 term.js.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* 저장 못 해도 동작은 그대로 */ } },
};
const S = {
  tab: store.get("tab") || "lab", engine: null, labs: [], lab: null, plan: null, status: null, sel: null,
  job: null, cob: null, vcom: null, whale: null, boom: null, saveErr: null,
};

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(errText(j) || r.statusText); e.data = j; throw e; }
  return j;
}
const errText = (j) => j && j.error ? t("err." + j.error, j.params || {}) : "";
const fmtBytes = (n) => {
  if (!n || n < 0) return "–";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return `${n >= 100 || i === 0 ? Math.round(n) : n.toFixed(1)} ${u[i]}`;
};
function toast(text) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}
// 확인 · 이름 묻기 상자. → Promise(true/false 또는 입력값)
function ask(title, body, ok, opt = {}) {
  const d = $("#ask");
  $("#askTitle").textContent = title;
  $("#askBody").textContent = body || "";
  $("#askBody").classList.toggle("hidden", !body);
  const inp = $("#askInput");
  inp.classList.toggle("hidden", opt.input === undefined);
  inp.value = opt.input ?? "";
  $("#askYes").textContent = ok;
  $("#askYes").className = opt.danger ? "danger" : "primary";
  d.showModal();
  if (opt.input !== undefined) setTimeout(() => { inp.focus(); inp.select(); }, 30);
  return new Promise((res) => {
    const done = (v) => { d.close(); $("#askYes").onclick = $("#askNo").onclick = null; inp.onkeydown = null; res(v); };
    $("#askYes").onclick = () => done(opt.input !== undefined ? inp.value.trim() : true);
    $("#askNo").onclick = () => done(false);
    inp.onkeydown = (e) => { if (e.key === "Enter") done(inp.value.trim()); };
    d.oncancel = () => done(false);
  });
}

// ---------------------------------------------------------------- chamber 불러오기 · 저장
async function loadOverview() {
  try {
    const o = await api("/api/overview");
    S.engine = o.engine; S.labs = o.labs;
    $("#over").classList.add("hidden");
  } catch (e) {
    showOver(e);
    return false;
  }
  paintEngine();
  if (!S.labs.length) S.labs = [await api("/api/labs", { name: t("first_lab") })].map(l => ({ id: l.id, name: l.name }));
  const want = store.get("lab");
  await openLab(S.labs.some(l => l.id === want) ? want : S.labs[0].id);
  return true;
}
function showOver(e) {
  const o = $("#over");
  o.classList.remove("hidden");
  const noDocker = e?.data?.error === "no_docker";
  o.innerHTML = `<div class="msg"><h2>${esc(t(noDocker ? "no_docker_title" : "load_failed"))}</h2>
    <p>${esc(noDocker ? t("no_docker_body") : e.message)}</p><button class="primary" id="overRetry">${esc(t("retry"))}</button></div>`;
  $("#overRetry").onclick = () => loadOverview();
}
function paintEngine() {
  const e = S.engine, el = $("#engine");
  if (!e) { el.className = "engine off"; el.innerHTML = `<i></i>${esc(t("disconnected"))}`; return; }
  el.className = "engine";
  el.innerHTML = `<i></i>Docker ${esc(e.version)} · ${esc(e.wsl ? t("wsl_ok") : t("wsl_no"))}`;
  el.title = e.os;
}
function paintLabSel() {
  $("#labSel").innerHTML = S.labs.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join("") +
    `<option value="__rename">${esc(t("lab_rename"))}</option><option value="__delete">${esc(t("lab_delete"))}</option>`;
  if (S.lab) $("#labSel").value = S.lab.id;
}
async function openLab(id) {
  try {
    S.lab = await api(`/api/lab/${id}`);
  } catch (e) { toast(e.message); return; }
  store.set("lab", id);
  S.sel = null; S.status = null; S.plan = null;
  paintLabSel();
  renderBoard(); renderSide();
  save(true);  // 계획(plan)만 받아 온다
  pollStatus();
}
$("#labSel").onchange = async () => {
  const v = $("#labSel").value;
  if (v === "__rename") {
    $("#labSel").value = S.lab.id;
    const name = await ask(t("lab_rename"), "", t("ok"), { input: S.lab.name });
    if (name) { S.lab.name = name; S.labs.find(l => l.id === S.lab.id).name = name; paintLabSel(); save(); }
    return;
  }
  if (v === "__delete") {
    $("#labSel").value = S.lab.id;
    const ok = await ask(t("lab_delete_q", { n: S.lab.name }), t("lab_delete_body"), t("lab_delete"), { danger: true });
    if (!ok) return;
    try { await api(`/api/lab/${S.lab.id}/delete`, {}); } catch (e) { return toast(e.message); }
    S.labs = S.labs.filter(l => l.id !== S.lab.id);
    if (!S.labs.length) S.labs = [await api("/api/labs", { name: t("first_lab") })];
    return openLab(S.labs[0].id);
  }
  openLab(v);
};
$("#labNew").onclick = async () => {
  const name = await ask(t("lab_new"), t("lab_new_body"), t("lab_create"), { input: t("lab_default", { n: S.labs.length + 1 }) });
  if (!name) return;
  const l = await api("/api/labs", { name });
  S.labs.unshift({ id: l.id, name: l.name });
  openLab(l.id);
};

// 고칠 때마다 잠깐 기다렸다가 저장 (끌기 중에는 마지막에 한 번)
let saveTimer = null, saving = false, again = false;
function save(now) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, now ? 0 : 450);
}
async function doSave() {
  if (!S.lab) return;
  if (saving) { again = true; return; }
  saving = true;
  const lab = S.lab;
  try {
    const r = await api(`/api/lab/${lab.id}/save`, lab);
    if (S.lab === lab) { S.plan = r.plan; S.saveErr = null; }
  } catch (e) {
    S.saveErr = e.message;
    toast(t("save_failed", { e: e.message }));
  }
  saving = false;
  if (S.lab === lab) { paintPlan(); }
  if (again) { again = false; doSave(); }
}

// ---------------------------------------------------------------- 상태 · 시작 · 중지
let statusTimer = null;
async function pollStatus() {
  clearTimeout(statusTimer);
  const lab = S.lab;
  if (lab && S.tab === "lab" && !document.hidden) {
    try {
      const st = await api(`/api/lab/${lab.id}/status`);
      if (S.lab === lab) { S.status = st; paintStatus(); }
    } catch { /* Docker 가 잠깐 끊겼을 때 */ }
  }
  statusTimer = setTimeout(pollStatus, 4000);
}
function paintStatus() {
  const st = S.status, busy = !!S.job;
  const el = $("#labState");
  const k = busy ? "busy" : st?.state || "stopped";
  el.className = "state " + k;
  el.innerHTML = `<i></i>${esc(t("st_" + k, { n: st?.running || 0, m: st?.total || 0 }))}`;
  $("#labStart").disabled = busy;
  $("#labStop").disabled = busy || !st || st.running === 0;
  $("#labStart").textContent = t(st?.state === "running" ? "lab_rewire" : "lab_start");
  paintBoxStates();
  if (S.sel === null || S.sel?.t === "box") paintSideStatus();
}
async function runJob(path, title, body = {}) {
  if (S.job) return;
  await doSave();
  if (S.saveErr) return toast(S.saveErr);
  const box = $("#jobBox"), list = $("#jobLog");
  $("#jobTitle").textContent = title;
  list.innerHTML = "";
  box.classList.remove("hidden");
  let r;
  try { r = await api(path, body); } catch (e) { list.innerHTML = `<li class="err">${esc(e.message)}</li>`; return; }
  S.job = r.job_id;
  paintStatus();
  let since = 0, last = null, status = "running";
  while (status === "running") {
    await new Promise(res => setTimeout(res, 600));
    let j;
    try { j = await api(`/api/jobs/${S.job}?since=${since}`); } catch { continue; }
    since = j.next; status = j.status;
    for (const l of j.logs) {
      if (l.k === "pull" || l.k === "build_step") {  // 같은 줄을 고쳐 쓴다
        if (last?.k === l.k) { last.el.textContent = logText(l); continue; }
      }
      const li = document.createElement("li");
      li.textContent = logText(l);
      if (l.k === "error" || l.k === "routes_declined" || l.k === "ospf_failed") li.className = "err";
      list.append(li);
      last = { k: l.k, el: li };
    }
    box.scrollTop = box.scrollHeight;
  }
  const li = document.createElement("li");
  li.className = status === "done" ? "ok" : "err";
  li.textContent = t(status === "done" ? "job_done" : "job_failed");
  list.append(li);
  S.job = null;
  await pollStatus();
  if (status === "done") setTimeout(() => { if (!S.job) box.classList.add("hidden"); }, 4000);
}
function logText(l) {
  if (l.k === "error") return t("err." + l.p.code, l.p.params || {});
  return t("log." + l.k, l.p);
}
$("#jobClose").onclick = () => $("#jobBox").classList.add("hidden");
$("#labStart").onclick = () => runJob(`/api/lab/${S.lab.id}/start`, t("job_start", { n: S.lab.name }));
$("#labStop").onclick = () => runJob(`/api/lab/${S.lab.id}/stop`, t("job_stop", { n: S.lab.name }));

// ---------------------------------------------------------------- 탭
function setTab(tab) {
  S.tab = tab;
  store.set("tab", tab);
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  $("#labView").classList.toggle("hidden", tab !== "lab");
  $("#cobwebView").classList.toggle("hidden", tab !== "cobweb");
  $("#vcomView").classList.toggle("hidden", tab !== "vcom");
  if (tab === "cobweb") renderCobweb(true);
  if (tab === "vcom") renderVcom(true);
  if (tab === "lab") { renderPalette(); pollStatus(); }
}
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));
document.addEventListener("visibilitychange", () => { if (!document.hidden) pollStatus(); });

// ---------------------------------------------------------------- 설정 / 테마 / 언어 / 업데이트
const darkMQ = matchMedia("(prefers-color-scheme: dark)");
function applyTheme() {
  const v = store.get("theme") || "system";
  document.documentElement.dataset.theme = v === "system" ? (darkMQ.matches ? "dark" : "light") : v;
  document.querySelectorAll("#themeSeg button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
}
darkMQ.addEventListener("change", applyTheme);
document.querySelectorAll("#themeSeg button").forEach(b => b.onclick = () => { store.set("theme", b.dataset.v); applyTheme(); });
$("#btnSettings").onclick = () => $("#settings").showModal();
$("#setClose").onclick = () => $("#settings").close();
$("#langSel").innerHTML = LANGS.map(([k, n]) => `<option value="${k}">${n}</option>`).join("");
$("#langSel").onchange = () => { setLang($("#langSel").value); applyStatic(); paintLabSel(); paintEngine(); renderPalette(); renderBoard(); renderSide(); paintStatus(); if (S.tab !== "lab") setTab(S.tab); };
$("#autoUpd").checked = store.get("autoUpdate") !== "off";
$("#autoUpd").onchange = () => { store.set("autoUpdate", $("#autoUpd").checked ? "on" : "off"); if ($("#autoUpd").checked) checkUpdate(true); };

function applyStatic() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(el => el.textContent = t(el.dataset.i18n));
  document.querySelectorAll("[data-i18n-title]").forEach(el => el.title = t(el.dataset.i18nTitle));
  document.querySelectorAll("[data-i18n-ph]").forEach(el => el.placeholder = t(el.dataset.i18nPh));
  $("#langSel").value = LANG;
}

let upd = null;
async function checkUpdate(force) {
  try { upd = await api("/api/update" + (force ? "?force=1" : "")); } catch { return; }
  const bar = $("#updateBar");
  if (!upd.available) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  bar.innerHTML = `<b>${esc(t("new_ver", { v: upd.latest }))}</b><span class="muted">${esc(t("current_ver", { v: upd.current }))}</span>
    <a href="${esc(upd.url)}" target="_blank" rel="noopener">${esc(t("release_notes"))}</a><span class="sp"></span>
    <button class="ghost" id="updLater">${esc(t("later"))}</button><button class="primary" id="updNow">${esc(t("update_now"))}</button>`;
  $("#updLater").onclick = () => bar.classList.add("hidden");
  $("#updNow").onclick = async () => {
    $("#updNow").disabled = true; $("#updNow").textContent = t("downloading");
    try {
      await api("/api/update", { labels: { title: t("upd_title"), downloading: t("upd_downloading", { v: upd.latest }),
        installing: t("installing"), failed: t("upd_failed"), close: t("close") } });
      bar.innerHTML = `<span>${esc(t("installing"))}</span>`;
      setTimeout(() => window.close(), 400);
    } catch (e) { toast(e.message); $("#updNow").disabled = false; $("#updNow").textContent = t("update_now"); }
  };
}

const beat = () => fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
beat(); setInterval(beat, 30000);
addEventListener("pagehide", () => navigator.sendBeacon("/api/bye"));

// 스크립트(canvas.js · side.js · term.js)가 모두 읽힌 뒤 시작
addEventListener("DOMContentLoaded", async () => {
  applyTheme(); applyStatic();
  api("/api/version").then(v => { $("#ver").textContent = `Chamber v${v.version}`; $("#repo").href = v.repo; }, () => {});
  if (store.get("autoUpdate") !== "off") checkUpdate(false);
  setTab(["lab", "cobweb", "vcom"].includes(S.tab) ? S.tab : "lab");
  if (!(await loadOverview())) {
    // Docker Desktop 이 아직 켜지는 중이면 5초마다 다시
    const tm = setInterval(async () => { if (await loadOverview()) clearInterval(tm); }, 5000);
  }
});
