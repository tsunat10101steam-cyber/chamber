"""Chamber — Docker 위에서 실제로 동작하는 네트워크 실습실 (Windows 앱)

Flask 서버(127.0.0.1:8767) + Edge 앱 창. 구조는 Boom · Whale 과 같다.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from docker.errors import APIError, DockerException, NotFound
from flask import Flask, jsonify, request, send_from_directory

import boomlink
import cobweb
import dock
import engine
import ios
import updater
import vcom
import winroute
from dock import ChamberError
from version import REPO, __version__

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_VER = str(int(time.time()))
if sys.stdout is None:
    sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
else:
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(errors="replace")
app = Flask(__name__, static_folder=str(ROOT / "static"))
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

STATE = {"client": None, "host": None, "engine": None, "last_beat": None}
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()
LAB_LOCKS: dict[str, threading.Lock] = {}


def fail(code, status=400, **params):
    return jsonify(error=code, params=params), status


def client():
    with LOCK:
        c = STATE["client"]
        if c:
            try:
                c.ping()
                return c
            except (DockerException, OSError):
                STATE.update(client=None, engine=None)
        c, host = dock.connect()
        STATE.update(client=c, host=host, engine=dock.engine(c, host))
        return c


def call(fn, need_docker=True):
    """오류를 코드로 돌려주는 공통 처리."""
    try:
        return fn(client() if need_docker else None)
    except ChamberError as e:
        return fail(e.code, **e.params)
    except NotFound as e:
        return fail("not_found", 404, detail=dock._err(e))
    except (APIError, DockerException, OSError) as e:
        return fail("docker", detail=dock._err(e))


def job(fn):
    """오래 걸리는 일 (이미지 받기 · chamber 시작). 진행은 /api/jobs/<id> 로 본다."""
    jid = uuid.uuid4().hex[:8]
    j = {"status": "running", "logs": [], "results": {}}
    JOBS[jid] = j

    def log(k, **p):
        j["logs"].append({"k": k, "p": p})

    def run():
        try:
            j["results"] = fn(log) or {}
            j["status"] = "done"
        except ChamberError as e:
            log("error", code=e.code, params=e.params)
            j["status"] = "error"
        except (APIError, DockerException, OSError) as e:
            log("error", code="docker", params={"detail": dock._err(e)})
            j["status"] = "error"
        except Exception as e:  # noqa: BLE001 — 화면에 그대로 보여 준다
            log("error", code="docker", params={"detail": f"{type(e).__name__}: {e}"})
            j["status"] = "error"
    threading.Thread(target=run, daemon=True).start()
    return jsonify(job_id=jid)


LOCAL_HOSTS = {"127.0.0.1", "localhost"}


@app.before_request
def _same_origin_only():
    """다른 웹사이트가 사용자 브라우저를 통해 Chamber API 를 부르지 못하게 막는다 (CSRF · DNS 리바인딩)."""
    if not request.path.startswith("/api/"):
        return None
    if request.host.rsplit(":", 1)[0] not in LOCAL_HOSTS:
        return fail("forbidden_origin", 403)
    origin = request.headers.get("Origin")
    if origin is not None and origin != f"http://{request.host}":
        return fail("forbidden_origin", 403)
    if request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return fail("forbidden_origin", 403)
    if request.method == "POST" and request.mimetype != "application/json" and request.get_data(cache=True):
        return fail("forbidden_origin", 415)
    return None


@app.get("/")
def index():
    html = (Path(app.static_folder) / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "canvas.js", "side.js", "term.js", "style.css", "i18n.js"):
        html = html.replace(f'/static/{name}"', f'/static/{name}?v={STATIC_VER}"')
    resp = app.response_class(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(ROOT, "app.ico")


@app.get("/manifest.json")
def manifest():
    return jsonify(name="Chamber", short_name="Chamber", start_url="/", display="standalone",
                   background_color="#ffffff", theme_color="#0b7a5c",
                   icons=[{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                          {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}])


# ---------------------------------------------------------------- chamber
@app.get("/api/overview")
def overview():
    def run(c):
        return jsonify(engine=STATE["engine"], labs=engine.list_labs())
    return call(run)


@app.post("/api/labs")
def lab_new():
    name = str(request.get_json(force=True).get("name") or "")
    return call(lambda c: jsonify(engine.new_lab(name)), need_docker=False)


@app.get("/api/lab/<lab_id>")
def lab_get(lab_id):
    return call(lambda c: jsonify(engine.load(lab_id)), need_docker=False)


@app.post("/api/lab/<lab_id>/save")
def lab_save(lab_id):
    b = request.get_json(force=True)
    b["id"] = lab_id

    def run(c):
        engine.load(lab_id)  # 있는 chamber 만
        lab = engine.save(b)
        return jsonify(lab=lab, plan=engine.plan(lab))
    return call(run, need_docker=False)


@app.post("/api/lab/<lab_id>/delete")
def lab_delete(lab_id):
    return call(lambda c: (engine.delete_lab(c, lab_id), jsonify(ok=True))[1])


@app.get("/api/lab/<lab_id>/status")
def lab_status(lab_id):
    return call(lambda c: jsonify(engine.status(c, engine.load(lab_id))))


def _lab_lock(lab_id):
    return LAB_LOCKS.setdefault(lab_id, threading.Lock())


@app.post("/api/lab/<lab_id>/start")
def lab_start(lab_id):
    try:
        lab = engine.load(lab_id)
        c = client()
    except ChamberError as e:
        return fail(e.code, **e.params)
    lk = _lab_lock(lab_id)
    if not lk.acquire(blocking=False):
        return fail("busy", 409)

    def run(log):
        try:
            r = engine.start(c, lab, log)
            out = {"wsl_ip": r["wsl_ip"], "routes": "none"}
            if r["wsl_ip"] and r["plan"]["host"]:
                need = winroute.missing(r["plan"]["subnets"], r["wsl_ip"])
                if need:
                    log("uac", n=len(need))
                    ok = winroute.apply(need, r["wsl_ip"])
                    still = winroute.missing(r["plan"]["subnets"], r["wsl_ip"])
                    out["routes"] = "added" if ok and not still else "declined"
                    log("routes_added" if out["routes"] == "added" else "routes_declined", n=len(need))
                else:
                    out["routes"] = "ok"
            return out
        finally:
            lk.release()
    return job(run)


@app.post("/api/lab/<lab_id>/stop")
def lab_stop(lab_id):
    try:
        lab = engine.load(lab_id)
        c = client()
    except ChamberError as e:
        return fail(e.code, **e.params)
    lk = _lab_lock(lab_id)
    if not lk.acquire(blocking=False):
        return fail("busy", 409)

    def run(log):
        try:
            engine.stop(c, lab)
            log("stopped")
        finally:
            lk.release()
    return job(run)


@app.post("/api/lab/<lab_id>/box_remove")
def box_remove(lab_id):
    """box 를 지울 때 그 컨테이너도 (FRR 설정 등 안에 있던 것과 함께)."""
    nid = str(request.get_json(force=True).get("node") or "")
    if not engine.ID_RE.fullmatch(nid):
        return fail("missing", field="node")
    return call(lambda c: (dock.remove_box(c, engine.load(lab_id)["id"], nid), jsonify(ok=True))[1])


@app.post("/api/lab/<lab_id>/ios_reset")
def lab_ios_reset(lab_id):
    """Cisco 라우터에 bullet 설정을 다시 넣고 다시 켠 뒤 선을 다시 꽂는다."""
    nid = str(request.get_json(force=True).get("node") or "")
    try:
        lab = engine.load(lab_id)
        c = client()
    except ChamberError as e:
        return fail(e.code, **e.params)
    lk = _lab_lock(lab_id)
    if not lk.acquire(blocking=False):
        return fail("busy", 409)

    def run(log):
        try:
            engine.ios_reset(c, lab, nid)
            log("ios_reset")
            engine.start(c, lab, log)
        finally:
            lk.release()
    return job(run)


@app.post("/api/winping")
def winping():
    ip = str(request.get_json(force=True).get("ip") or "")
    try:
        return jsonify(winroute.ping(ip))
    except ValueError:
        return fail("bad_field", field="ip")


# ---------------------------------------------------------------- cobweb · VcoM · Whale · Boom
@app.get("/api/cobweb")
def cobweb_list():
    return call(lambda c: jsonify(cobweb.listing(c)))


@app.post("/api/cobweb/pull")
def cobweb_pull():
    try:
        image = cobweb.check_image(request.get_json(force=True).get("image"))
        c = client()
    except ChamberError as e:
        return fail(e.code, **e.params)
    return job(lambda log: (dock.pull(c, image, log), {"image": image})[1])


PICKER = threading.Lock()  # 파일 선택 창은 하나만


@app.post("/api/cobweb/ios_pick")
def ios_pick():
    """IOS 파일 고르기: 이 PC 의 파일 선택 창 (서버가 이 PC 에서 돌기 때문에 올릴 필요 없이 경로만 받는다)."""
    # 선택 창이 앱 창 뒤에 숨지 않게: 보이지 않는 '맨 위' 창을 실제로 띄우고 그 위에 연다
    ps = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; Add-Type -AssemblyName System.Windows.Forms;"
          "$f = New-Object System.Windows.Forms.OpenFileDialog; $f.Filter = 'Cisco IOS (*.bin;*.image)|*.bin;*.image|*.*|*.*';"
          "$f.InitialDirectory = Join-Path $env:USERPROFILE 'Downloads'; $f.Title = 'Chamber - Cisco IOS';"
          "$o = New-Object System.Windows.Forms.Form; $o.TopMost = $true; $o.ShowInTaskbar = $false; $o.Opacity = 0;"
          "$o.FormBorderStyle = 'None'; $o.StartPosition = 'CenterScreen'; $o.Width = 1; $o.Height = 1;"
          "$o.Show(); $o.Activate(); $r = $f.ShowDialog($o); $o.Close(); if ($r -eq 'OK') { $f.FileName }")
    if not PICKER.acquire(blocking=False):
        return fail("picker_open", 409)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, timeout=600,
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        PICKER.release()
    path = r.stdout.decode("utf-8", "replace").strip()
    if not path:
        return jsonify(path="")
    try:
        return jsonify(path=path, platform=ios.detect(path), tag=ios.image_tag(path))
    except ChamberError as e:
        return fail(e.code, **e.params)


@app.post("/api/cobweb/ios_import")
def ios_import():
    path = str(request.get_json(force=True).get("path") or "")
    try:
        ios.detect(path)
        c = client()
    except ChamberError as e:
        return fail(e.code, **e.params)
    return job(lambda log: {"image": ios.build_ios(c, path, log)})


@app.post("/api/cobweb/remove")
def cobweb_remove():
    b = request.get_json(force=True)
    return call(lambda c: (cobweb.remove(c, b.get("image"), bool(b.get("with_boxes"))), jsonify(ok=True))[1])


@app.get("/api/vcom")
def vcom_list():
    return call(lambda c: jsonify(vcom.listing()), need_docker=False)


@app.post("/api/vcom/act")
def vcom_act():
    b = request.get_json(force=True)
    return call(lambda c: jsonify(vcom.act(str(b.get("hv") or ""), str(b.get("id") or ""), str(b.get("action") or ""))),
                need_docker=False)


@app.get("/api/whale")
def whale_list():
    """Whale 이 다루는 Docker 컨테이너 중 chamber 가 만든 것이 아닌 것 → 'Whale 컨테이너' box 로 놓을 수 있다."""
    def run(c):
        ctrs = []
        for x in c.containers(all=True):
            lb = x.get("Labels") or {}
            if dock.LAB_LABEL in lb or dock.NETD_LABEL in lb:
                continue
            nets = list((x.get("NetworkSettings") or {}).get("Networks") or {})
            ctrs.append({"name": (x.get("Names") or ["/?"])[0].lstrip("/"), "image": x.get("Image", ""), "state": x.get("State"),
                         "group": lb.get("com.docker.compose.project") or lb.get(dock.WHALE_GROUP, ""), "networks": nets})
        return jsonify(app=boomlink.app_status(boomlink.WHALE), containers=ctrs)
    return call(run)


@app.get("/api/boom")
def boom_status():
    return jsonify(boomlink.boom_status())


@app.post("/api/boom/import")
def boom_import():
    return call(lambda c: jsonify(boomlink.boom_import()), need_docker=False)


# ---------------------------------------------------------------- 앱 안 터미널 (box 콘솔)
TERMS: dict[str, dict] = {}
SID_RE = re.compile(r"[0-9a-f]{32}")


def _term_size(b):
    try:
        return max(10, min(int(b.get("cols") or 80), 500)), max(4, min(int(b.get("rows") or 24), 300))
    except (TypeError, ValueError):
        return 80, 24


def _term_reader(sid, T):
    while True:
        try:
            d = T["sock"].recv(65536)
        except Exception:  # Windows 파이프는 OSError 가 아닌 pywintypes.error(109) 를 낸다
            d = b""
        with T["cond"]:
            if d:
                T["out"].append(d)
            else:
                T["done"] = True
            T["cond"].notify_all()
        if not d:
            return


def _term_close(sid):
    T = TERMS.pop(sid, None)
    if not T:
        return

    def end():
        if not T["done"]:
            try:
                dock.hangup_shell(client(), T["ctr"], sid)
            except Exception:
                pass
        try:
            T["sock"].close()
        except Exception:
            pass
    threading.Thread(target=end, daemon=True).start()


@app.post("/api/term")
def term_open():
    b = request.get_json(force=True)
    cols, rows = _term_size(b)
    mode = b.get("mode") or "sh"

    def run(c):
        ctr, node = engine.box_ctr(c, engine.load(str(b.get("lab") or "")), str(b.get("node") or ""))
        cmd = None
        if mode == "vtysh" and node["kind"] == "router" and not node.get("image"):
            cmd = ["vtysh"]
        elif mode == "ios" and ios.is_ios(node.get("image")):
            # 라우터 콘솔 (dynamips). IOS 가 아직 켜지는 중이면 열릴 때까지 기다린다
            cmd = ["sh", "-c", "printf 'Waiting for the IOS console (the router may still be booting)'; "
                   "until python3 -c 'import socket; socket.create_connection((\"127.0.0.1\", 2000), 1)' 2>/dev/null; "
                   "do printf .; sleep 1; done; echo; exec telnet 127.0.0.1 2000"]
        sid = uuid.uuid4().hex
        eid, sock = dock.exec_shell(c, ctr, cols, rows, sid, cmd)
        T = {"sock": sock, "exec": eid, "ctr": ctr, "out": [], "done": False, "cond": threading.Condition()}
        TERMS[sid] = T
        threading.Thread(target=_term_reader, args=(sid, T), daemon=True).start()
        return jsonify(sid=sid)
    return call(run)


@app.get("/api/term/<sid>/out")
def term_out(sid):
    T = TERMS.get(sid) if SID_RE.fullmatch(sid) else None
    if not T:
        return fail("not_found", 404, detail="terminal")

    def gen():
        try:
            yield "retry: 100000\n\n"
            while True:
                with T["cond"]:
                    if not T["out"] and not T["done"]:
                        T["cond"].wait(15)
                    chunks, T["out"] = T["out"], []
                    done = T["done"]
                if chunks:
                    yield "data: " + base64.b64encode(b"".join(chunks)).decode() + "\n\n"
                if done:
                    code = None
                    try:
                        code = client().exec_inspect(T["exec"]).get("ExitCode")
                    except (APIError, DockerException, OSError):
                        pass
                    yield f"event: exit\ndata: {'' if code is None else code}\n\n"
                    return
                if not chunks:
                    yield ": ping\n\n"
        finally:
            _term_close(sid)

    resp = app.response_class(gen(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.post("/api/term/<sid>/<op>")
def term_op(sid, op):
    T = TERMS.get(sid) if SID_RE.fullmatch(sid) else None
    if not T:
        return fail("not_found", 404, detail="terminal")
    b = request.get_json(force=True)
    try:
        if op == "in":
            T["sock"].sendall(str(b.get("d") or "").encode("utf-8"))
        elif op == "size":
            cols, rows = _term_size(b)
            client().exec_resize(T["exec"], height=rows, width=cols)
        elif op == "close":
            _term_close(sid)
        else:
            return fail("missing", field="op")
    except Exception as e:
        return fail("docker", detail=dock._err(e))
    return jsonify(ok=True)


@app.get("/api/jobs/<job_id>")
def job_status(job_id):
    j = JOBS.get(job_id)
    if not j:
        return fail("no_job", 404)
    since = int(request.args.get("since", 0))
    return jsonify(status=j["status"], logs=j["logs"][since:], next=len(j["logs"]), results=j["results"])


# ---------------------------------------------------------------- 버전 / 업데이트
@app.get("/api/version")
def version():
    return jsonify(version=__version__, repo=f"https://github.com/{REPO}")


@app.get("/api/diag/tls")
def diag_tls():
    return jsonify(updater.tls_diag())


@app.get("/api/update")
def update_check():
    return jsonify(updater.check(force=bool(request.args.get("force"))))


@app.post("/api/update")
def update_apply():
    info = updater.check()
    if not info.get("available") or not info.get("asset"):
        return fail("no_update")
    dest = updater.install_dir()
    if not dest:
        return fail("dev_mode", url=info["url"])
    if _busy():
        return fail("busy", 409)
    labels = (request.get_json(silent=True) or {}).get("labels") or {}
    try:
        updater.launch_update_window(info["asset"], info.get("kind", "setup"), str(dest), os.getpid(), labels)
    except OSError as e:
        return fail("download_failed", detail=str(e))
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return jsonify(ok=True, version=info["latest"])


@app.post("/api/heartbeat")
def heartbeat():
    STATE["last_beat"] = time.time()
    return jsonify(ok=True)


@app.post("/api/bye")
def bye():
    t = time.time()

    def later():
        time.sleep(15)
        if (STATE["last_beat"] or 0) < t and not _busy():
            os._exit(0)
    if APP_MODE:
        threading.Thread(target=later, daemon=True).start()
    return "", 204


# ---------------------------------------------------------------- launcher
PORT = int(os.environ.get("CHAMBER_PORT", 8767))
URL = f"http://127.0.0.1:{PORT}"
APP_MODE = False
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def _open_app_window():
    exe = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not exe:
        return False
    profile = Path(os.environ.get("LOCALAPPDATA", ROOT)) / "Chamber" / "browser"
    subprocess.Popen([exe, f"--app={URL}", f"--user-data-dir={profile}", "--window-size=1480,940",
                      "--no-first-run", "--no-default-browser-check"])
    return True


def _busy():
    return any(j["status"] == "running" for j in JOBS.values())


def _watchdog():
    while True:
        time.sleep(15)
        beat = STATE["last_beat"]
        if beat and time.time() - beat > 180 and not _busy():
            os._exit(0)


def _already_running():
    import urllib.request
    try:
        urllib.request.urlopen(URL + "/api/version", timeout=1)
        return True
    except OSError:
        return False


if __name__ == "__main__":
    use_browser = "--browser" in sys.argv
    if _already_running():
        if use_browser or not _open_app_window():
            webbrowser.open(URL)
        sys.exit(0)
    if not use_browser:
        APP_MODE = True
        threading.Thread(target=_watchdog, daemon=True).start()
        threading.Timer(0.8, lambda: _open_app_window() or webbrowser.open(URL)).start()
    else:
        threading.Timer(0.8, lambda: webbrowser.open(URL)).start()
    print(f"Chamber: {URL}")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
