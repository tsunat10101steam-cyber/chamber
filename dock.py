"""Docker 연결과 box 컨테이너 다루기.

Chamber 의 box(라우터·스위치·PC…)는 네트워크 없이(--network none) 뜬 컨테이너다. 선은 engine.py 가 veth 로 꽂는다.
"""
from __future__ import annotations

import io
import os
import subprocess

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

LAB_LABEL = "chamber.lab"
NODE_LABEL = "chamber.node"
NETD_LABEL = "chamber.netd"
WHALE_GROUP = "whale.group"  # Whale 아키텍처 화면이 이 라벨로 한 묶음으로 그린다
NETD_NAME = "chamber-netd"

# Chamber 기본 이미지: 라우터(FRR) · PC · 스위치(브리지) 를 모두 이것 하나로. 처음 쓸 때 이 PC 에서 만든다.
BOX_IMAGE = "chamber/box:1"
BOX_DOCKERFILE = r"""FROM alpine:3.22
RUN apk add --no-cache iproute2 iptables bridge-utils iputils busybox-extras tcpdump frr frr-openrc bash curl \
      traceroute mtr bind-tools ethtool nmap-ncat \
 && sed -i -E 's/^(zebra|staticd|ospfd|bgpd|ripd)=no/\1=yes/' /etc/frr/daemons \
 && touch /etc/frr/vtysh.conf \
 && echo 'export PS1="\h:\w# "' > /etc/profile.d/chamber.sh
LABEL chamber.image="box"
# 라우터면 FRR 을 켠다 (vtysh 로 설정). 그 외에는 가만히 기다린다
CMD ["sh", "-c", "if [ \"$CHAMBER_ROLE\" = router ]; then /usr/lib/frr/frrinit.sh start >/dev/null 2>&1; fi; exec tail -f /dev/null"]
"""

if os.name == "nt":
    CANDIDATES = ["npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine"]
else:
    CANDIDATES = ["unix:///var/run/docker.sock", f"unix://{os.path.expanduser('~/.docker/run/docker.sock')}"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ChamberError(Exception):
    """화면에 보여줄 오류. 문장 대신 코드(code)와 값(params)을 넘기고 화면(i18n.js)이 번역한다."""

    def __init__(self, code, **params):
        super().__init__(code)
        self.code, self.params = code, params


def _err(e):
    if isinstance(e, APIError):
        return (e.explanation or str(e)).strip()
    return str(e)


# ---------------------------------------------------------------- 연결
def connect():
    hosts = [os.environ["DOCKER_HOST"]] if os.environ.get("DOCKER_HOST") else CANDIDATES
    last = None
    for host in hosts:
        try:
            c = docker.APIClient(base_url=host, version="auto", timeout=30)
            c.ping()
            return c, host
        except (DockerException, OSError) as e:
            last = e
    raise ChamberError("no_docker", detail=_err(last) if last else "")


def engine(c, host):
    i, v = c.info(), c.version()
    return {"host": host, "version": v.get("Version", ""), "os": i.get("OperatingSystem", ""),
            "desktop": "Docker Desktop" in i.get("OperatingSystem", ""), "cpus": i.get("NCPU", 0), "mem": i.get("MemTotal", 0),
            "wsl": wsl_ready()}


_wsl = {}


def wsl_ready():
    """Docker Desktop 의 WSL2 배포판(docker-desktop)이 있는가. '이 PC' 연결(Windows 에서 ping)은 여기서만 된다."""
    if "v" not in _wsl:
        ok = False
        if os.name == "nt":
            try:
                r = subprocess.run(["wsl", "-d", "docker-desktop", "-u", "root", "true"], capture_output=True, timeout=20,
                                   creationflags=NO_WINDOW)
                ok = r.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                ok = False
        _wsl["v"] = ok
    return _wsl["v"]


# ---------------------------------------------------------------- 이미지
def has_image(c, image):
    try:
        c.inspect_image(image)
        return True
    except ImageNotFound:
        return False


def pull(c, image, log):
    """이미지가 없으면 받는다. 진행률은 레이어별 받은 양을 합쳐 log('pull', pct=…) 로."""
    if has_image(c, image):
        return
    if image == BOX_IMAGE:
        return build_box(c, log)
    if image.startswith("chamber/ios-"):
        raise ChamberError("ios_missing", image=image)  # 사용자의 IOS 파일로만 만든다 (cobweb)
    repo, tag = image, None
    if "@" not in image and ":" in image.rsplit("/", 1)[-1]:
        repo, tag = image.rsplit(":", 1)
    log("pulling", image=image)
    layers, last = {}, -10
    for ev in c.pull(repo, tag=tag or "latest", stream=True, decode=True):
        if ev.get("error"):
            raise ChamberError("docker", detail=ev["error"])
        d = ev.get("progressDetail") or {}
        if ev.get("status") == "Downloading" and d.get("total"):
            layers[ev["id"]] = (d.get("current", 0), d["total"])
        elif ev.get("status") in ("Download complete", "Pull complete", "Already exists") and ev.get("id") in layers:
            layers[ev["id"]] = (layers[ev["id"]][1], layers[ev["id"]][1])
        if layers:
            done, total = sum(a for a, _ in layers.values()), sum(b for _, b in layers.values())
            pct = int(done / total * 100) if total else 0
            if pct - last >= 2:
                last = pct
                log("pull", image=image, pct=pct)
    log("pulled", image=image)


def build_box(c, log):
    """Chamber 기본 이미지를 이 PC 에서 만든다 (Alpine 패키지를 받으므로 처음 한 번 1~2분)."""
    log("building", image=BOX_IMAGE)
    tail = []
    for ev in c.build(fileobj=io.BytesIO(BOX_DOCKERFILE.encode()), tag=BOX_IMAGE, rm=True, forcerm=True, decode=True):
        if ev.get("error"):
            raise ChamberError("build_failed", detail=ev["error"].strip() + " " + " ".join(tail[-3:]))
        s = (ev.get("stream") or "").strip()
        if s:
            tail.append(s[:160])
            if s.startswith("Step "):
                log("build_step", step=s.split(":")[0].replace("Step ", ""))
    log("built", image=BOX_IMAGE)


# ---------------------------------------------------------------- 도우미 (chamber-netd)
def ensure_netd(c, log):
    """선을 꽂는 도우미 컨테이너. 엔진의 모든 프로세스를 보고(--pid host) 네트워크 장치를 만들 수 있어야(privileged) 한다."""
    try:
        i = c.inspect_container(NETD_NAME)
        if i["Config"]["Image"] != BOX_IMAGE:
            c.remove_container(NETD_NAME, force=True)
            raise NotFound("old netd")
        if not i["State"]["Running"]:
            c.start(NETD_NAME)
        return
    except NotFound:
        pass
    pull(c, BOX_IMAGE, log)
    hc = c.create_host_config(privileged=True, pid_mode="host", network_mode="none", init=True,
                              restart_policy={"Name": "unless-stopped"})
    c.create_container(BOX_IMAGE, name=NETD_NAME, host_config=hc, labels={NETD_LABEL: "1", WHALE_GROUP: "chamber"})
    c.start(NETD_NAME)
    log("netd_started")


def run_in(c, ctr, cmd, stdin_script=None, timeout=None):
    """컨테이너 안에서 명령을 실행하고 (종료 코드, 출력). 스크립트는 sh -c 로 넘긴다."""
    if stdin_script is not None:
        cmd = ["sh", "-c", stdin_script]
    ex = c.exec_create(ctr, cmd)
    out = c.exec_start(ex["Id"]).decode("utf-8", "replace")
    code = c.exec_inspect(ex["Id"]).get("ExitCode")
    return code, out


def wsl_run(script, timeout=90):
    """docker-desktop 배포판(WSL 루트 네트워크 = Windows 가 닿는 곳)에서 sh 스크립트를 실행."""
    r = subprocess.run(["wsl", "-d", "docker-desktop", "-u", "root", "sh", "-s"], input=script.encode(), capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


# ---------------------------------------------------------------- box 컨테이너
def box_name(lab_id, node_id):
    return f"chamber-{lab_id}-{node_id}"


def data_volume(lab_id, node_id):
    """Cisco box 의 NVRAM(wr mem) · idle-pc 를 지키는 볼륨. 컨테이너를 새로 만들어도 남는다."""
    return f"chamber-{lab_id}-{node_id}-data"


def ensure_box(c, lab, node, log, ios=None):
    """box 컨테이너가 있고 실행 중이게. 이미지·역할이 바뀌었으면 새로 만든다. → 컨테이너 id
    ios: Cisco(Dynamips) box 면 (환경 변수, 시작 설정 글, 알고 있는 idle-pc) 를 돌려주는 함수."""
    name = box_name(lab["id"], node["id"])
    image = node.get("image") or BOX_IMAGE
    role = node["kind"]
    want_env = ios()[0] if ios else {}
    try:
        i = c.inspect_container(name)
        env = dict(e.split("=", 1) for e in i["Config"].get("Env") or [] if "=" in e)
        caps = set(i["HostConfig"].get("CapAdd") or [])
        changed = i["Config"]["Image"] != image or env.get("CHAMBER_ROLE") != role
        if ios:
            changed |= any(env.get(k) != v for k, v in want_env.items())  # 포트 수가 바뀌면 새로 (설정은 볼륨에 남는다)
        elif role == "router" and not caps & {"SYS_ADMIN", "CAP_SYS_ADMIN"}:
            changed = True
        if changed:
            c.remove_container(name, force=True)
            raise NotFound("changed")
        if i["Config"].get("Hostname") != _hostname(node["name"]):
            pass  # 이름만 바뀐 것은 다음에 새로 만들 때 반영 (FRR 설정을 지키려고 지우지 않는다)
        if not i["State"]["Running"]:
            if ios:
                from ios import config_archive
                c.put_archive(name, "/", config_archive(ios()[1], push=False))
            c.start(name)
        return i["Id"]
    except NotFound:
        pass
    pull(c, image, log)
    labels = {LAB_LABEL: lab["id"], NODE_LABEL: node["id"], WHALE_GROUP: f"chamber · {lab['name']}"}
    if ios:
        env, cfg, idle = ios()
        vol = data_volume(lab["id"], node["id"])
        fresh = not any(v["Name"] == vol for v in (c.volumes(filters={"name": vol}).get("Volumes") or []))
        if fresh:
            c.create_volume(vol, labels={LAB_LABEL: lab["id"], NODE_LABEL: node["id"]})
        hc = c.create_host_config(network_mode="none", init=True, cap_add=["NET_ADMIN", "NET_RAW"], binds={vol: {"bind": "/data", "mode": "rw"}})
        r = c.create_container(image, name=name, hostname=_hostname(node["name"]), host_config=hc, labels=labels,
                               environment={"CHAMBER_ROLE": role, **env})
        # 처음 만든 라우터에만 bullet 설정을 넣는다 (그 뒤로는 라우터에 저장한 설정이 우선)
        from ios import config_archive
        c.put_archive(r["Id"], "/", config_archive(cfg, push=fresh, idle=idle))
        c.start(r["Id"])
        log("box_created", name=node["name"])
        return r["Id"]
    caps = ["NET_ADMIN", "NET_RAW"] + (["SYS_ADMIN"] if role == "router" else [])  # FRR(zebra) 이 SYS_ADMIN 을 요구한다
    hc = c.create_host_config(network_mode="none", init=True, cap_add=caps,
                              dns=["1.1.1.1", "8.8.8.8"], sysctls={"net.ipv4.ip_forward": "1" if role == "router" else "0"})
    cmd = None if image == BOX_IMAGE else _keepalive_cmd(c, image)
    r = c.create_container(image, name=name, hostname=_hostname(node["name"]), host_config=hc, labels=labels,
                           environment={"CHAMBER_ROLE": role}, command=cmd, tty=cmd is not None, stdin_open=cmd is not None)
    c.start(r["Id"])
    log("box_created", name=node["name"])
    return r["Id"]


def _keepalive_cmd(c, image):
    """다른 이미지(nginx 등)는 원래 명령을 쓰되, 명령이 없거나 셸이면 멈추지 않게 붙잡아 둔다."""
    cfg = c.inspect_image(image).get("Config") or {}
    cmd = (cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or [])
    if not cmd or cmd[-1] in ("sh", "bash", "/bin/sh", "/bin/bash", "ash"):
        return ["sh", "-c", "exec tail -f /dev/null"]
    return None


def _hostname(name):
    import re
    h = re.sub(r"[^A-Za-z0-9-]", "-", name).strip("-")[:63]
    return h or "box"


def lab_containers(c, lab_id=None):
    flt = {"label": f"{LAB_LABEL}={lab_id}" if lab_id else LAB_LABEL}
    return c.containers(all=True, filters=flt)


def remove_box(c, lab_id, node_id):
    try:
        c.remove_container(box_name(lab_id, node_id), force=True)
    except NotFound:
        pass
    try:
        c.remove_volume(data_volume(lab_id, node_id))  # Cisco box 의 NVRAM
    except (NotFound, APIError):
        pass


# ---------------------------------------------------------------- 앱 안 터미널 (Whale 과 같은 방식)
def exec_shell(c, ctr, cols, rows, tag, cmd=None):
    cmd = cmd or ["sh", "-c", "command -v bash >/dev/null && exec bash -l || exec sh -l"]
    ex = c.exec_create(ctr, cmd, stdin=True, tty=True, environment={"TERM": "xterm-256color", "CHAMBER_TERM": tag})
    sock = c.exec_start(ex["Id"], tty=True, socket=True)
    raw = getattr(sock, "_sock", sock)
    if hasattr(raw, "settimeout"):
        raw.settimeout(None)
    try:
        c.exec_resize(ex["Id"], height=rows, width=cols)
    except APIError:
        pass
    return ex["Id"], raw


def hangup_shell(c, ctr, tag):
    import re
    if not re.fullmatch(r"[0-9a-f]{32}", tag):
        return
    script = (f'for p in /proc/[0-9]*; do tr "\\0" "\\n" < $p/environ 2>/dev/null | grep -qx CHAMBER_TERM={tag} '
              f'&& kill -HUP ${{p#/proc/}} 2>/dev/null; done; true')
    ex = c.exec_create(ctr, ["sh", "-c", script])
    c.exec_start(ex["Id"])
