"""Cisco IOS (Dynamips) 라우터 box.

사용자가 가진 IOS 이미지(.bin, 예: c3725-adventerprisek9-mz.124-15.T5.bin)를 받아 이 PC 에서 box 이미지를 만든다.
Chamber 는 IOS 이미지를 받아 주지 않는다 (라이선스). dynamips 는 GNS3 가 관리하는 오픈소스(GPL) 에뮬레이터.

컨테이너 안에서 드라이버(DRIVER)가 dynamips 를 하이퍼바이저 모드로 띄우고:
  포트(eth0 …)가 꽂히길 기다림 → 라우터 만들기 · 포트 모듈 · linux_eth NIO → (처음이면) 시작 설정 넣기 → 시작
  → idle-pc 를 모르면 계산해 저장 (안 하면 라우터 하나가 CPU 한 코어를 100% 씀) → 선이 다시 꽂히면 NIO 를 다시 붙인다.
"""
from __future__ import annotations

import io
import ipaddress
import re
import tarfile
from pathlib import Path

from dock import ChamberError

DYN_IMAGE = "chamber/dynamips:1"
IOS_PREFIX = "chamber/ios-"
LABEL_PLATFORM = "chamber.ios.platform"
LABEL_FILE = "chamber.ios.file"

# 플랫폼별 포트: (dynamips 이름, RAM MB, [(슬롯, 모듈 또는 None=내장, 포트 수)])
# eth0, eth1 … 를 차례로 아래 포트에 붙인다. 모듈은 FastEthernet 하나짜리로 단순하게
PLATFORMS = {
    "c3725": {"ram": 160, "slots": [(0, None, 2), (1, "NM-1FE-TX", 1), (2, "NM-1FE-TX", 1)]},
    "c3745": {"ram": 192, "slots": [(0, None, 2), (1, "NM-1FE-TX", 1), (2, "NM-1FE-TX", 1), (3, "NM-1FE-TX", 1), (4, "NM-1FE-TX", 1)]},
    "c2691": {"ram": 160, "slots": [(0, None, 2), (1, "NM-1FE-TX", 1)]},
    "c3640": {"ram": 160, "slots": [(0, "NM-1FE-TX", 1), (1, "NM-1FE-TX", 1), (2, "NM-1FE-TX", 1), (3, "NM-1FE-TX", 1)]},
    "c7200": {"ram": 256, "slots": [(0, "C7200-IO-FE", 1), (1, "PA-FE-TX", 1), (2, "PA-FE-TX", 1), (3, "PA-FE-TX", 1),
                                     (4, "PA-FE-TX", 1), (5, "PA-FE-TX", 1), (6, "PA-FE-TX", 1)]},
}


def ports(platform):
    """[(슬롯, 포트, 'FastEthernet1/0')] — eth 번호 순서."""
    out = []
    for slot, _mod, n in PLATFORMS[platform]["slots"]:
        for p in range(n):
            out.append((slot, p, f"FastEthernet{slot}/{p}"))
    return out


def detect(filename):
    """파일 이름에서 플랫폼 (c3725-adventerprisek9-mz.124-15.T5.bin → c3725)."""
    m = re.match(r"(c\d{4})[-_]", Path(filename).name.lower())
    plat = m.group(1) if m else ""
    if plat == "c3620":
        plat = "c3640"
    if plat not in PLATFORMS:
        raise ChamberError("ios_platform", name=Path(filename).name, list=", ".join(PLATFORMS))
    return plat


def image_tag(filename):
    plat = detect(filename)
    stem = re.sub(r"[^a-z0-9._-]", "-", Path(filename).stem.lower())[:100].strip(".-") or "ios"
    return f"{IOS_PREFIX}{plat}:{stem}"


def is_ios(image):
    return (image or "").startswith(IOS_PREFIX)


def platform_of(image):
    return image[len(IOS_PREFIX):].split(":")[0] if is_ios(image) else ""


# ---------------------------------------------------------------- 이미지 만들기
DYN_DOCKERFILE = """FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git cmake make gcc libc6-dev libelf-dev libpcap0.8-dev \\
 && git clone --depth 1 --branch v0.2.25 https://github.com/GNS3/dynamips /src \\
 && cmake -S /src -B /b -DDYNAMIPS_CODE=stable -DCMAKE_BUILD_TYPE=Release && make -C /b -j4 && make -C /b install
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libelf1 libpcap0.8 python3-minimal telnet iproute2 iputils-ping \\
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/dynamips /usr/local/bin/nvram_export /usr/local/bin/
COPY chamber-ios.py /usr/local/bin/chamber-ios.py
LABEL chamber.image="dynamips"
WORKDIR /data
CMD ["python3", "/usr/local/bin/chamber-ios.py"]
"""

DRIVER = r'''#!/usr/bin/env python3
# Chamber IOS 드라이버: dynamips 하이퍼바이저를 띄우고 라우터 하나를 관리한다.
import os, socket, subprocess, sys, time, signal

PLAT = os.environ["CHAMBER_PLATFORM"]
RAM = os.environ.get("CHAMBER_RAM", "160")
SLOTS = [s.split(":") for s in os.environ.get("CHAMBER_SLOTS", "").split()]          # "1:NM-1FE-TX"
PORTS = [p.split("=") for p in os.environ.get("CHAMBER_PORTS", "").split()]           # "eth0=0/0"
DATA = "/data"
IDLE = os.path.join(DATA, "idlepc")
PUSH = "/chamber/push"        # 처음 만든 라우터
PUSH2 = "/data/push"          # '설정 다시 넣기' (볼륨에 남아서 컨테이너를 새로 만들어도 지켜진다)
CFG = "/chamber/startup.cfg"
NAME = "R"

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

hv = subprocess.Popen(["dynamips", "-H", "127.0.0.1:7200", "-l", os.path.join(DATA, "dynamips.log")], cwd=DATA)
sock = None
for _ in range(100):
    try:
        sock = socket.create_connection(("127.0.0.1", 7200), timeout=120)
        break
    except OSError:
        time.sleep(0.1)
f = sock.makefile("rwb", buffering=0)

def cmd(line, ok_fail=False):
    f.write(line.encode() + b"\r\n")
    out = []
    while True:
        r = f.readline().decode("latin-1").rstrip("\r\n")
        if not r:
            raise SystemExit("hypervisor closed")
        out.append(r)
        if r[:3].isdigit() and r[3:4] == "-" and r[0] in "12":
            if r.startswith("2") and not ok_fail:
                log("ERR", line, "->", r)
            if r.startswith("100") or r.startswith("2"):
                return out

def ifindex(dev):
    try:
        return open(f"/sys/class/net/{dev}/ifindex").read().strip()
    except OSError:
        return None

def stop(*_):
    log("stopping")
    try:
        cmd("vm stop " + NAME, True)
        cmd("hypervisor stop", True)
    except Exception:
        pass
    hv.terminate()
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)

# 1) Chamber 가 포트(eth…)를 꽂을 때까지 잠깐 기다린다 (선이 없는 포트는 dummy 로 꽂힌다).
#    20초가 지나도 없는 포트는 두고 시작하고, 나중에 생기면 아래 4) 에서 붙인다
log("waiting for ports", [p[0] for p in PORTS])
t0 = time.time()
while not all(ifindex(d) for d, _ in PORTS) and time.time() - t0 < 20:
    time.sleep(0.5)

def prep(dev):
    subprocess.run(["ip", "link", "set", dev, "up"])
    subprocess.run(["sh", "-c", f"echo 1 > /proc/sys/net/ipv6/conf/{dev}/disable_ipv6"], stderr=subprocess.DEVNULL)
for d, _ in PORTS:
    if ifindex(d):
        prep(d)
seen = {d: ifindex(d) for d, _ in PORTS}

# 2) 라우터
cmd("hypervisor working_dir " + DATA)
cmd(f"vm create {NAME} 1 {PLAT}")
cmd(f"vm set_ios {NAME} /ios/image.bin")
cmd(f"vm set_ram {NAME} {RAM}")
cmd(f"vm set_con_tcp_port {NAME} 2000")
if PLAT != "c7200":
    cmd(f"vm set_disk0 {NAME} 0", True)
for slot, mod in SLOTS:
    cmd(f"vm slot_add_binding {NAME} {slot} 0 {mod}")
def bind(dev, sp):
    s, p = sp.split("/")
    cmd(f"nio create_linux_eth nio_{dev} {dev}")
    cmd(f"vm slot_add_nio_binding {NAME} {s} {p} nio_{dev}")
for d, sp in PORTS:
    if seen[d]:
        bind(d, sp)
    else:
        log("port missing, will bind later", d)
if not os.path.exists(IDLE) and os.path.exists("/chamber/idlepc"):
    open(IDLE, "w").write(open("/chamber/idlepc").read().strip())
if os.path.exists(IDLE):
    cmd(f"vm set_idle_pc {NAME} {open(IDLE).read().strip()}")
# bullet 설정을 넣을지: 처음이거나(PUSH) 사용자가 '설정 다시 넣기' 를 눌렀을 때.
# 또는 bullet 이 바뀌었는데 라우터에서 저장(wr mem)한 적이 없을 때 — NVRAM 이 Chamber 가 마지막에 넣은 그대로면 덮어써도 된다
PUSHED = os.path.join(DATA, "pushed.cfg")
norm = lambda t: [l.rstrip() for l in t.replace("\r", "").split("\n") if l.strip()]
push = os.path.exists(PUSH) or os.path.exists(PUSH2)
if not push and os.path.exists(CFG) and not os.path.exists(PUSHED):
    # 예전 드라이버로 만든 라우터(기록 없음): NVRAM 이 비었거나 Chamber 가 넣은 모양(hostname 으로 시작)이면 넣는다.
    # IOS 가 wr mem 으로 저장한 설정은 '!' · 'version 12.4' 머리말로 시작하므로 그대로 둔다
    try:
        import base64
        q = cmd(f"vm extract_config {NAME}", True)[-1].split("'")
        cur = norm(base64.b64decode(q[3]).decode("latin-1")) if len(q) > 3 else []
        if not cur or cur[0].startswith("hostname"):
            push = True
            log("no push record, router config is Chamber-made: pushing")
    except Exception as e:
        log("extract_config failed", e)
if not push and os.path.exists(CFG) and os.path.exists(PUSHED) and norm(open(CFG).read()) != norm(open(PUSHED).read()):
    try:
        import base64
        r = cmd(f"vm extract_config {NAME}", True)[-1]  # 100-conf 'R' '<startup b64>' '<private b64>'
        q = r.split("'")
        cur = base64.b64decode(q[3]).decode("latin-1") if len(q) > 3 else ""
        if norm(cur) == norm(open(PUSHED).read()):
            push = True
            log("bullets changed and router config was not saved by hand: pushing")
        else:
            log("bullets changed but router has its own saved config: keeping it")
    except Exception as e:
        log("extract_config failed", e)
if push and os.path.exists(CFG):
    cmd(f"vm set_config {NAME} {CFG}")
    open(PUSHED, "w").write(open(CFG).read())
    log("startup-config pushed")
cmd(f"vm start {NAME}")
for p in (PUSH, PUSH2):
    if os.path.exists(p):
        os.remove(p)  # 다음 부팅부터는 라우터에 저장된 설정(wr mem)을 쓴다
log("started")
started = time.time()

# 3) idle-pc 계산 (IOS 가 다 뜬 뒤 한 번)
idle_done = os.path.exists(IDLE)
while True:
    time.sleep(1)
    if hv.poll() is not None:
        log("dynamips exited", hv.returncode)
        sys.exit(1)
    if not idle_done and time.time() - started > 75:
        idle_done = True
        try:
            props = []
            for r in cmd(f"vm get_idle_pc_prop {NAME} 0"):
                parts = r.split()
                if r.startswith("101") and len(parts) >= 3 and parts[1].startswith("0x"):
                    props.append((parts[1], int(parts[2].strip("[]"))))
            if props:
                # GNS3 처럼 50~60 사이(별표)에 가장 가까운 것
                pc = min(props, key=lambda x: abs(x[1] - 55))[0]
                cmd(f"vm set_idle_pc_online {NAME} 0 {pc}")
                open(IDLE, "w").write(pc)
                log("idle-pc", pc, props)
        except Exception as e:
            log("idle-pc failed", e)
    # 4) 선을 다시 꽂았으면 (ifindex 가 바뀜) NIO 를 다시 붙인다
    for d, sp in PORTS:
        now = ifindex(d)
        if now and now != seen[d]:
            s, p = sp.split("/")
            log("rebind", d)
            prep(d)
            cmd(f"vm slot_disable_nio {NAME} {s} {p}", True)
            cmd(f"vm slot_remove_nio_binding {NAME} {s} {p}", True)
            cmd(f"nio delete nio_{d}", True)
            bind(d, sp)
            cmd(f"vm slot_enable_nio {NAME} {s} {p}", True)
            seen[d] = now
'''


def build_runtime(c, log):
    """dynamips 실행 이미지 (GNS3 소스에서 빌드, 처음 한 번 2~4분)."""
    log("building", image=DYN_IMAGE)
    ctx = _tar({"Dockerfile": DYN_DOCKERFILE.encode(), "chamber-ios.py": DRIVER.encode()})
    _build(c, ctx, DYN_IMAGE, log)


def build_ios(c, path, log):
    """사용자의 IOS 파일로 box 이미지. → 태그"""
    p = Path(path)
    if not p.is_file() or p.stat().st_size < 1_000_000 or p.stat().st_size > 600_000_000:
        raise ChamberError("ios_file", name=str(p))
    plat = detect(p.name)
    with p.open("rb") as fh:
        head = fh.read(4)
    if head != b"\x7fELF":  # IOS 이미지는 ELF. 다른 것(zip 등)은 dynamips 가 못 읽는다
        raise ChamberError("ios_not_elf", name=p.name)
    from dock import has_image
    if not has_image(c, DYN_IMAGE):
        build_runtime(c, log)
    tag = image_tag(p.name)
    df = (f"FROM {DYN_IMAGE}\nCOPY image.bin /ios/image.bin\n"
          f'LABEL {LABEL_PLATFORM}="{plat}" {LABEL_FILE}="{p.name}"\n')
    log("ios_copy", name=p.name)
    ctx = _tar({"Dockerfile": df.encode()}, files={"image.bin": p})
    _build(c, ctx, tag, log)
    return tag


def _tar(blobs, files=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, data in blobs.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
        for name, path in (files or {}).items():
            t.add(str(path), arcname=name)
    buf.seek(0)
    return buf


def _build(c, ctx, tag, log):
    tail = []
    for ev in c.build(fileobj=ctx, custom_context=True, tag=tag, rm=True, forcerm=True, decode=True):
        if ev.get("error"):
            raise ChamberError("build_failed", detail=ev["error"].strip() + " " + " ".join(tail[-3:]))
        s = (ev.get("stream") or "").strip()
        if s:
            tail.append(s[:160])
            if s.startswith("Step "):
                log("build_step", step=s.split(":")[0].replace("Step ", ""))
    log("built", image=tag)


def list_images(c):
    out = []
    for im in c.images(filters={"label": LABEL_PLATFORM}):
        lb = im.get("Labels") or {}
        for tag in im.get("RepoTags") or []:
            if tag.startswith(IOS_PREFIX):
                plat = lb.get(LABEL_PLATFORM, "")
                out.append({"image": tag, "platform": plat, "file": lb.get(LABEL_FILE, ""), "size": im.get("Size", 0),
                            "ports": [x[2] for x in ports(plat)] if plat in PLATFORMS else []})
    return out


# ---------------------------------------------------------------- box 설정
DRIVER_VER = __import__("hashlib").sha1(DRIVER.encode()).hexdigest()[:10]


def env_for(image, node):
    plat = platform_of(image)
    spec = PLATFORMS[plat]
    pl = ports(plat)
    if len(node["ifaces"]) > len(pl):
        raise ChamberError("ios_ports", name=node["name"], n=len(pl))
    slots = " ".join(f"{s}:{m}" for s, m, _ in spec["slots"] if m)
    pm = " ".join(f"{f['name']}={pl[i][0]}/{pl[i][1]}" for i, f in enumerate(node["ifaces"]))
    return {"CHAMBER_PLATFORM": plat, "CHAMBER_RAM": str(spec["ram"]), "CHAMBER_SLOTS": slots, "CHAMBER_PORTS": pm,
            "CHAMBER_DRIVER": DRIVER_VER}


def startup_config(lab, node, plan, peer_kind):
    """bullet(포트 IP · 게이트웨이 · 정적 경로) + 자동 OSPF → IOS 설정."""
    plat = platform_of(node.get("image"))
    pl = ports(plat)
    L = [f"hostname {re.sub(r'[^A-Za-z0-9-]', '-', node['name'])[:60] or 'R'}", "no ip domain-lookup", "ip routing", "!"]
    nets = []
    for i, f in enumerate(node["ifaces"]):
        L.append(f"interface {pl[i][2]}")
        if f["ip"]:
            ii = ipaddress.ip_interface(f["ip"])
            L.append(f" ip address {ii.ip} {ii.netmask}")
            nets.append(ii.network)
            if lab.get("auto_ospf"):
                L += [" ip ospf hello-interval 2", " ip ospf dead-interval 8"]
                if peer_kind(node["id"], f["name"]) == "router":
                    L.append(" ip ospf network point-to-point")
        L += [" no shutdown", "!"]
    gw = node.get("gw") or plan["gw"].get(node["id"])
    if gw:
        L.append(f"ip route 0.0.0.0 0.0.0.0 {gw}")
    for r in node.get("routes") or []:
        if r["via"]:
            n = ipaddress.IPv4Network(r["dst"])
            L.append(f"ip route {n.network_address} {n.netmask} {r['via']}")
    if lab.get("auto_ospf") and nets:
        L += ["!", "router ospf 1", " redistribute connected subnets", " redistribute static subnets"]
        for n in sorted(set(nets), key=lambda x: int(x.network_address)):
            L.append(f" network {n.network_address} {n.hostmask} area 0")
        if plan["gw"].get(node["id"]) and plan.get("host"):
            L.append(" default-information originate always")
    L += ["!", "line con 0", " exec-timeout 0 0", " privilege level 15", " logging synchronous", "!", "end", ""]
    return "\n".join(L)


def config_archive(text, push, idle=""):
    files = {"chamber/startup.cfg": text.encode(), "usr/local/bin/chamber-ios.py": DRIVER.encode()}
    if push == "volume":
        files = {"chamber/startup.cfg": text.encode(), "data/push": b"1"}
        return _tar(files).getvalue()
    if push:
        files["chamber/push"] = b"1"
    if idle:
        files["chamber/idlepc"] = idle.encode()  # 같은 IOS 이미지로 이미 계산한 값
    return _tar(files).getvalue()
