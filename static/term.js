// ---------------------------------------------------------------- 앱 안 터미널
// box 콘솔(docker exec -it, 라우터는 vtysh 도)을 화면 아래 패널에 띄운다. 탭으로 여러 개를 연다.
// 출력은 SSE(/api/term/<sid>/out) 로 받고, 입력·크기는 POST 로 보낸다. 화면 그리기는 xterm.js (static/vendor).
const TM = { list: [], cur: null, h: 320, min: false };
const TERM_THEME = {
  background: "#0b1b33", foreground: "#e5ecf7", cursor: "#4c86ff", cursorAccent: "#0b1b33",
  selectionBackground: "#2c4f8f", black: "#0b1b33", brightBlack: "#5a6b85", blue: "#4c86ff", brightBlue: "#7aa5ff",
};
{ const h = +store.get("termH"); if (h >= 120) TM.h = h; }

const b64bytes = (s) => Uint8Array.from(atob(s), (ch) => ch.charCodeAt(0));

function termLayout() {
  const on = TM.list.length > 0;
  $("#term").classList.toggle("hidden", !on);
  document.body.classList.toggle("term-open", on);
  document.body.classList.toggle("term-min", on && TM.min);
  // 아래 패널 높이만큼 본문·오른쪽 패널을 비켜 준다 (style.css 의 --term-h)
  const h = !on ? 0 : TM.min ? $(".term-h").offsetHeight + 1 : Math.min(TM.h, innerHeight - 140);
  document.body.style.setProperty("--term-h", h + "px");
  $("#termMin").textContent = TM.min ? "▴" : "▾";
  $("#termMin").title = t(TM.min ? "term_max" : "term_min");
  if (TM.cur && !TM.min) requestAnimationFrame(() => { try { TM.cur.fit.fit(); } catch { /* 숨겨진 동안은 크기를 못 잰다 */ } });
}

function termTabs() {
  $("#termTabs").innerHTML = TM.list.map((T, i) =>
    `<button class="term-tab${T === TM.cur ? " on" : ""}${T.ended ? " ended" : ""}" data-tsel="${i}" title="${esc(T.name)}">` +
    `<span class="dot ${T.ended ? "exited" : "running"}"></span>${esc(T.name)}` +
    `<span class="x" data-tclose="${i}" title="${esc(t("close"))}">×</span></button>`).join("");
}

function termShow(T) {
  TM.cur = T;
  TM.list.forEach((x) => x.box.classList.toggle("hidden", x !== T));
  TM.min = false;
  termTabs();
  termLayout();
  requestAnimationFrame(() => T.term.focus());
}

async function openTerm(spec) {
  const key = `${spec.lab}/${spec.node}/${spec.mode}`;
  const old = TM.list.find((x) => x.key === key && !x.ended);
  if (old) return termShow(old);
  const box = document.createElement("div");
  box.className = "term-pane";
  $("#termBody").append(box);
  const term = new Terminal({
    fontFamily: '"Cascadia Mono", Consolas, "D2Coding", monospace', fontSize: 13, lineHeight: 1.15,
    cursorBlink: true, scrollback: 5000, theme: TERM_THEME, allowProposedApi: false,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  const T = { key, name: spec.name, term, fit, box, sid: null, es: null, ended: false, q: "", busy: false };
  TM.list.push(T);
  term.open(box);
  termShow(T);
  try { fit.fit(); } catch { /* 첫 그리기 전 */ }
  // Windows 터미널처럼: 고른 글자가 있으면 Ctrl+C 는 복사, Ctrl+V 는 붙여넣기 (그 외 Ctrl+C 는 셸로 → 중단)
  term.attachCustomKeyEventHandler((e) => {
    if (e.type !== "keydown" || !e.ctrlKey || e.altKey) return true;
    const k = e.key.toLowerCase();
    if (k === "c" && term.hasSelection()) { navigator.clipboard?.writeText(term.getSelection()).catch(() => {}); term.clearSelection(); return false; }
    if (k === "v") return false;  // 브라우저의 paste 이벤트를 xterm 이 받아 보낸다
    return true;
  });
  term.onData((d) => termSend(T, d));
  term.onResize(({ cols, rows }) => { if (T.sid && !T.ended) api(`/api/term/${T.sid}/size`, { cols, rows }).catch(() => {}); });
  term.write(`\x1b[2m${t("term_connecting", { n: T.name })}\x1b[0m`);
  try {
    T.sid = (await api("/api/term", { lab: spec.lab, node: spec.node, mode: spec.mode, cols: term.cols, rows: term.rows })).sid;
  } catch (e) {
    term.write(`\r\x1b[2K\x1b[31m${e.message}\x1b[0m\r\n`);
    T.ended = true;
    return termTabs();
  }
  term.write("\r\x1b[2K");
  const es = new EventSource(`/api/term/${T.sid}/out`);
  T.es = es;
  es.onmessage = (ev) => term.write(b64bytes(ev.data));
  es.addEventListener("exit", (ev) => termEnd(T, t("term_ended", { code: ev.data === "" ? "?" : ev.data })));
  es.onerror = () => termEnd(T, t("term_lost"));
}

function termEnd(T, why) {
  if (T.ended) return;
  T.ended = true;
  T.es?.close();
  T.term.write(`\r\n\x1b[2m── ${why} ──\x1b[0m\r\n`);
  termTabs();
}

// 키 입력은 순서대로 보낸다. 앞 요청이 가는 동안 친 글자는 모아서 한 번에
async function termSend(T, d) {
  if (T.ended || !T.sid) return;
  T.q += d;
  if (T.busy) return;
  T.busy = true;
  while (T.q && !T.ended) {
    const s = T.q;
    T.q = "";
    try { await api(`/api/term/${T.sid}/in`, { d: s }); } catch (e) { termEnd(T, e.message); }
  }
  T.busy = false;
}

function termClose(T) {
  if (T.sid && !T.ended) api(`/api/term/${T.sid}/close`, {}).catch(() => {});
  T.ended = true;
  T.es?.close();
  T.term.dispose();
  T.box.remove();
  const i = TM.list.indexOf(T);
  TM.list.splice(i, 1);
  if (TM.cur === T) TM.cur = TM.list[Math.min(i, TM.list.length - 1)] || null;
  if (TM.cur) termShow(TM.cur); else { termTabs(); termLayout(); }
}

$("#termTabs").addEventListener("click", (e) => {
  const x = e.target.closest("[data-tclose]");
  if (x) { e.stopPropagation(); return termClose(TM.list[+x.dataset.tclose]); }
  const b = e.target.closest("[data-tsel]");
  if (b) termShow(TM.list[+b.dataset.tsel]);
});
// 가운데 버튼으로 탭 닫기
$("#termTabs").addEventListener("auxclick", (e) => {
  const b = e.target.closest("[data-tsel]");
  if (b && e.button === 1) termClose(TM.list[+b.dataset.tsel]);
});
$("#termMin").onclick = () => { TM.min = !TM.min; termLayout(); if (!TM.min) TM.cur?.term.focus(); };
$("#termCloseAll").onclick = () => [...TM.list].forEach(termClose);

// 위쪽 가장자리를 끌어 높이 조절
$("#termGrip").addEventListener("pointerdown", (e) => {
  if (TM.min) return;
  e.preventDefault();
  const grip = e.currentTarget;
  grip.setPointerCapture(e.pointerId);
  const move = (ev) => { TM.h = Math.max(120, Math.min(innerHeight - 140, innerHeight - ev.clientY)); termLayout(); };
  const up = () => { grip.removeEventListener("pointermove", move); store.set("termH", String(Math.round(TM.h))); };
  grip.addEventListener("pointermove", move);
  grip.addEventListener("pointerup", up, { once: true });
});
addEventListener("resize", () => { if (TM.list.length) termLayout(); });
// 창을 닫을 때 셸도 닫는다 (서버는 스트림이 끊기면 어차피 정리한다)
addEventListener("pagehide", () => TM.list.forEach((T) => {
  if (T.sid && !T.ended) fetch(`/api/term/${T.sid}/close`, { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
}));
