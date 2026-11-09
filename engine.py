"""chamber(실습 네트워크) 의 저장 · 검사 · 실행.

box 마다 컨테이너 하나(--network none). 선은 veth 쌍: 도우미 chamber-netd 의 iproute2 로 두 컨테이너의 네트워크 공간에 한쪽씩 꽂는다.
'이 PC' box 는 veth 한쪽을 docker-desktop WSL 배포판(= Windows 가 vEthernet(WSL) 로 닿는 곳)에 두고, Windows 에 경로를 넣는다.
그래서 cmd 에서 ping 10.x.x.x 가 실제로 그 컨테이너까지 간다.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import time
from pathlib import Path

from docker.errors import APIError, NotFound

import dock
import ios
from dock import ChamberError

DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Chamber"
LABS = DATA / "chambers"

WIRED = {"router", "switch", "pc", "server", "host", "whale"}  # 실제 선이 꽂히는 box
KINDS = WIRED | {"vm", "aws", "note"}
NAME_RE = re.compile(r"[^\x00-\x1f<>]{1,40}")
IF_RE = re.compile(r"[a-z][a-z0-9]{0,9}")
ID_RE = re.compile(r"[a-z0-9]{1,12}")
LAB_ID_RE = re.compile(r"[0-9a-f]{8}")
IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:@-]{0,200}")
CTR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
WIRE_FILE = DATA / "wired.json"
IDLE_FILE = DATA / "ios_idlepc.json"  # IOS 이미지마다 한 번 계산한 idle-pc (다음 라우터는 바로 씀)


def _load_wired():
    try:
        return json.loads(WIRE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# lab id → {"ctrs": {컨테이너 id: StartedAt}, "wsl_ip": ..., "subnets": [...]}. 앱을 다시 켜도 '꽂힌 그대로' 를 알 수 있게 파일에도
WIRE_STATE: dict[str, dict] = _load_wired()


def _save_wired():
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        WIRE_FILE.write_text(json.dumps(WIRE_STATE), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- 저장
def _path(lab_id):
    if not LAB_ID_RE.fullmatch(lab_id or ""):
        raise ChamberError("not_found", detail="chamber")
    return LABS / f"{lab_id}.json"


def list_labs():
    LABS.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(LABS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"id": d["id"], "name": d["name"], "boxes": len(d.get("nodes", [])), "updated": d.get("updated", 0)})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda x: -x["updated"])


def load(lab_id):
    p = _path(lab_id)
    if not p.exists():
        raise ChamberError("not_found", detail="chamber")
    return json.loads(p.read_text(encoding="utf-8"))


def new_lab(name):
    lab = {"id": secrets.token_hex(4), "name": (name or "chamber").strip()[:40] or "chamber", "created": time.time(),
           "auto_ospf": True, "internet": True, "nodes": [], "links": []}
    return save(lab)


def delete_lab(c, lab_id):
    lab = load(lab_id)
    if c is not None:
        stop(c, lab, remove=True)
    _path(lab_id).unlink(missing_ok=True)


def save(lab):
    lab = clean(lab)
    lab["updated"] = time.time()
    LABS.mkdir(parents=True, exist_ok=True)
    p = _path(lab["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(lab, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return lab


# ---------------------------------------------------------------- 검사 (화면이 보낸 값은 그대로 믿지 않는다)
def _bad(field):
    raise ChamberError("bad_field", field=field)


def _iface(ip):
    if not ip:
        return ""
    try:
        i = ipaddress.ip_interface(ip)
    except ValueError:
        _bad(f"ip {ip}")
    if i.version != 4 or i.network.prefixlen > 30 and i.network.prefixlen != 32 or i.network.prefixlen < 8:
        _bad(f"ip {ip}")
    return str(i)


def _addr(ip, field):
    if not ip:
        return ""
    try:
        return str(ipaddress.IPv4Address(ip))
    except ValueError:
        _bad(f"{field} {ip}")


def clean(lab):
    if not LAB_ID_RE.fullmatch(str(lab.get("id", ""))):
        _bad("id")
    out = {k: lab.get(k) for k in ("id", "created")}
    out["name"] = str(lab.get("name") or "chamber").strip()[:40] or "chamber"
    out["auto_ospf"] = bool(lab.get("auto_ospf", True))
    out["internet"] = bool(lab.get("internet", True))
    nodes, seen = [], set()
    for n in lab.get("nodes") or []:
        nid, kind = str(n.get("id", "")), n.get("kind")
        if not ID_RE.fullmatch(nid) or nid in seen or kind not in KINDS:
            _bad("box")
        seen.add(nid)
        name = str(n.get("name") or nid).strip()
        if not NAME_RE.fullmatch(name):
            _bad("name")
        node = {"id": nid, "kind": kind, "name": name,
                "x": max(0, min(int(n.get("x") or 0), 5000)), "y": max(0, min(int(n.get("y") or 0), 4000))}
        if kind in ("router", "pc", "server", "switch"):
            img = str(n.get("image") or "").strip()
            if img and not IMAGE_RE.fullmatch(img) or ios.is_ios(img) and kind != "router":
                _bad("image")
            node["image"] = img
        if kind == "whale":
            ctr = str(n.get("ctr") or "")
            if not CTR_RE.fullmatch(ctr):
                _bad("container")
            node["ctr"] = ctr
        if kind in ("vm", "aws", "note"):
            node["ref"] = {k: str(v)[:300] for k, v in (n.get("ref") or {}).items() if isinstance(v, (str, int, float))}
            node["info"] = n.get("info") if isinstance(n.get("info"), (dict, list)) and len(json.dumps(n.get("info"))) < 200000 else None
        ifs, names = [], set()
        for f in (n.get("ifaces") or [])[:32]:
            fname = str(f.get("name", ""))
            if not IF_RE.fullmatch(fname) or fname in names or fname in ("lo", "br0"):
                _bad(f"iface {fname}")
            if kind == "whale" and fname.startswith("eth"):
                _bad(f"iface {fname}")  # Docker 가 붙인 eth0 과 부딪치지 않게 ch0 처럼
            names.add(fname)
            ifs.append({"name": fname, "ip": "" if kind == "switch" else _iface(str(f.get("ip") or "").strip())})
        node["ifaces"] = ifs
        node["gw"] = _addr(str(n.get("gw") or "").strip(), "gateway") if kind in ("pc", "server", "router", "whale") else ""
        routes = []
        for r in (n.get("routes") or [])[:64]:
            try:
                dst = str(ipaddress.IPv4Network(str(r.get("dst", "")).strip(), strict=False))
            except ValueError:
                _bad(f"route {r.get('dst')}")
            routes.append({"dst": dst, "via": _addr(str(r.get("via") or "").strip(), "via")})
        node["routes"] = routes if kind in ("router", "pc", "server", "whale") else []
        node["note"] = str(n.get("note") or "")[:2000]
        if kind == "router" and ios.is_ios(node.get("image")):
            node["ios_sync"] = str(n.get("ios_sync") or "")[:16]  # wr mem 한 설정을 bullet 으로 가져온 것의 지문
        nodes.append(node)
    out["nodes"] = nodes
    by = {n["id"]: n for n in nodes}
    links, used = [], set()
    for l in lab.get("links") or []:
        a, b = l.get("a") or {}, l.get("b") or {}
        ends = []
        for e in (a, b):
            n = by.get(e.get("node"))
            if not n or n["kind"] not in WIRED or e.get("ifc") not in {f["name"] for f in n["ifaces"]}:
                _bad("link")
            key = (n["id"], e["ifc"])
            if key in used:
                _bad(f"link {n['name']} {e['ifc']}")  # 포트 하나에는 선 하나
            used.add(key)
            ends.append({"node": n["id"], "ifc": e["ifc"]})
        if ends[0]["node"] == ends[1]["node"] or by[ends[0]["node"]]["kind"] == by[ends[1]["node"]]["kind"] == "host":
            _bad("link")
        links.append({"id": str(l.get("id") or secrets.token_hex(3))[:12], "a": ends[0], "b": ends[1]})
    out["links"] = links
    hosts = [n for n in nodes if n["kind"] == "host"]
    if len(hosts) > 1:
        _bad("host")  # '이 PC' 는 chamber 하나에 하나
    return out


# ---------------------------------------------------------------- 실행 계획
def _peer(lab, nid, ifc):
    for l in lab["links"]:
        for x, y in ((l["a"], l["b"]), (l["b"], l["a"])):
            if x["node"] == nid and x["ifc"] == ifc:
                return y
    return None


def plan(lab):
    """실제로 꽂을 것과 자동으로 채울 값 (PC 의 게이트웨이, 이 PC 로 가는 길 …)."""
    by = {n["id"]: n for n in lab["nodes"]}
    wired = [n for n in lab["nodes"] if n["kind"] in WIRED]
    addrs = []  # (node, iface, ip_interface)
    for n in wired:
        for f in n["ifaces"]:
            if f["ip"]:
                addrs.append((n, f["name"], ipaddress.ip_interface(f["ip"])))
    subnets = sorted({a[2].network for a in addrs}, key=lambda x: (int(x.network_address), x.prefixlen))
    host = next((n for n in wired if n["kind"] == "host"), None)
    host_ips = [a[2] for a in addrs if a[0] is host]
    gw, issues, whale_routes = {}, [], {}
    # 같은 IP 두 번
    seen = {}
    for n, f, i in addrs:
        k = str(i.ip)
        if k in seen:
            issues.append({"code": "dup_ip", "ip": k, "a": seen[k], "b": n["name"]})
        seen[k] = n["name"]
    for n in wired:
        if n["kind"] in ("pc", "server", "whale") and not n["gw"]:
            mine = [a[2] for a in addrs if a[0] is n]
            cand = [a for a in addrs if a[0]["kind"] in ("router", "host") and a[0] is not n
                    and any(a[2].network == m.network for m in mine)]
            cand.sort(key=lambda a: a[0]["kind"] != "router")
            if cand and n["kind"] != "whale":
                gw[n["id"]] = str(cand[0][2].ip)
            elif cand and n["kind"] == "whale":
                via = str(cand[0][2].ip)
                whale_routes[n["id"]] = [(str(s), via) for s in subnets if not any(s == m.network for m in mine)]
        if n["kind"] == "router" and not n["gw"] and host_ips:
            mine = [a[2] for a in addrs if a[0] is n]
            h = next((h for h in host_ips if any(h.network == m.network for m in mine)), None)
            if h:
                gw[n["id"]] = str(h.ip)  # 이 PC 바로 옆 라우터는 기본 경로를 이 PC 로 (OSPF 로 나머지에 퍼뜨린다)
    host_route = None
    if host and host_ips:
        hi = host_ips[0]
        # 이 PC 에서 chamber 안쪽으로 가는 다음 장비: 이 PC 와 같은 구간의 라우터(없으면 아무 장비)
        nxt = [a for a in addrs if a[0] is not host and a[2].network == hi.network]
        nxt.sort(key=lambda a: a[0]["kind"] != "router")
        host_route = {"ip": str(hi), "via": str(nxt[0][2].ip) if nxt else "",
                      "nets": [str(s) for s in subnets if s != hi.network]}
    for n in wired:
        if n["kind"] != "note" and n["ifaces"] and not any(_peer(lab, n["id"], f["name"]) for f in n["ifaces"]):
            issues.append({"code": "no_links", "box": n["name"]})
    # 선 하나의 양 끝이 서로 다른 서브넷이면 그 선으로는 아무것도 오가지 않는다 (예: 이 PC 10.77.1.254/24 ↔ 라우터 192.168.100.1/24)
    for l in lab["links"]:
        a, b = by[l["a"]["node"]], by[l["b"]["node"]]
        fa = next((f for f in a["ifaces"] if f["name"] == l["a"]["ifc"]), None)
        fb = next((f for f in b["ifaces"] if f["name"] == l["b"]["ifc"]), None)
        if fa and fb and fa["ip"] and fb["ip"]:
            ia, ib = ipaddress.ip_interface(fa["ip"]), ipaddress.ip_interface(fb["ip"])
            if ia.network != ib.network:
                issues.append({"code": "subnet_mismatch", "a": a["name"], "ai": str(ia), "b": b["name"], "bi": str(ib),
                               "nodes": [a["id"], b["id"]]})
    return {"subnets": [str(s) for s in subnets], "gw": gw, "host": host_route, "issues": issues,
            "whale_routes": whale_routes, "sig": wire_sig(lab)}


def wire_sig(lab):
    """실제로 꽂는 것에 영향을 주는 것만의 지문 (위치 · 이름 · 메모는 빼고)."""
    import hashlib
    keep = [{k: n.get(k) for k in ("id", "kind", "image", "ctr", "ifaces", "gw", "routes")} for n in lab["nodes"] if n["kind"] in WIRED]
    links = sorted((l["a"]["node"], l["a"]["ifc"], l["b"]["node"], l["b"]["ifc"]) for l in lab["links"])
    return hashlib.sha1(json.dumps([keep, links], sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- 시작 · 중지
def _sq(s):
    """sh 작은따옴표 안에 넣을 값 (검사를 통과한 값만 오지만 한 번 더)."""
    if not re.fullmatch(r"[A-Za-z0-9._:/@-]*", s):
        raise ChamberError("bad_field", field=s)
    return s


def _root_if(lab_id, i):
    return f"c{lab_id[:6]}h{i}"


def _netd_pid(c):
    return c.inspect_container(dock.NETD_NAME)["State"]["Pid"]


def start(c, lab, log):
    """box 컨테이너를 띄우고 선을 꽂고 주소·경로를 넣는다. 다시 불러도 처음부터 다시 꽂는다(멱등)."""
    lab = clean(lab)
    p = plan(lab)
    wired = [n for n in lab["nodes"] if n["kind"] in WIRED]
    host = next((n for n in wired if n["kind"] == "host"), None)
    use_wsl = dock.wsl_ready()
    if host and not use_wsl:
        raise ChamberError("no_wsl")
    dock.ensure_netd(c, log)
    pids, ctrs = {}, {}
    by0 = {n["id"]: n for n in lab["nodes"]}

    def peer_kind(nid, ifc):
        pe = _peer(lab, nid, ifc)
        return by0[pe["node"]]["kind"] if pe else ""
    for n in wired:
        if n["kind"] == "host":
            continue
        if n["kind"] == "whale":
            try:
                i = c.inspect_container(n["ctr"])
            except NotFound:
                raise ChamberError("whale_missing", name=n["ctr"])
            if not i["State"]["Running"]:
                c.start(i["Id"])
                i = c.inspect_container(i["Id"])
            cid = i["Id"]
        else:
            spec = None
            if ios.is_ios(n.get("image")):
                spec = (lambda n=n: (ios.env_for(n["image"], n), ios.startup_config(lab, n, p, peer_kind),
                                     _idle_cache().get(n["image"], "")))
            cid = dock.ensure_box(c, lab, n, log, ios=spec)
            i = c.inspect_container(cid)
        pids[n["id"]], ctrs[cid] = i["State"]["Pid"], i["State"]["StartedAt"]
    by = {n["id"]: n for n in lab["nodes"]}
    S = ["set -u", "fail=0"]
    S.append(f"HP={_netd_pid(c)}")
    if use_wsl:
        # 도우미의 파일 시스템(iproute2)만 빌리고 네트워크는 WSL 루트 그대로. 도우미 안의 /proc 은 엔진 pid 공간이다
        S += ['H=""; for s in /proc/[0-9]*/status; do set -- $(grep "^NSpid:" $s 2>/dev/null); '
              'if [ "$#" -ge 3 ] && [ "$3" = "$HP" ]; then H=$2; break; fi; done',
              '[ -n "$H" ] || { echo "ERR netd_not_found"; exit 3; }', 'X="nsenter -t $H -m --"']
    else:
        S.append('X=""')
    S += ['ns() { p=$1; shift; $X nsenter --net=/proc/$p/ns/net "$@"; }',
          'run() { "$@" || { echo "ERR $*"; fail=1; }; }']
    # 1) 예전에 꽂은 것 치우기 (컨테이너를 다시 시작했으면 이미 없다)
    for n in wired:
        if n["kind"] == "host":
            for k in range(4):
                S.append(f"$X ip link del {_root_if(lab['id'], k)} 2>/dev/null")
            continue
        for f in n["ifaces"]:
            S.append(f"ns {pids[n['id']]} ip link del {_sq(f['name'])} 2>/dev/null")
        if n["kind"] == "switch":
            S.append(f"ns {pids[n['id']]} ip link del br0 2>/dev/null")
    # 2) 선 (veth 쌍)
    host_ifs = {}
    for k, l in enumerate(lab["links"]):
        a, b = l["a"], l["b"]
        if by[b["node"]]["kind"] == "host":
            a, b = b, a
        tb = f"t{lab['id'][:5]}{k:03d}b"
        if by[a["node"]]["kind"] == "host":
            root = _root_if(lab["id"], len(host_ifs))
            host_ifs[a["ifc"]] = root
            S.append(f"run $X ip link add {root} type veth peer name {tb} netns /proc/{pids[b['node']]}/ns/net")
        else:
            ta = f"t{lab['id'][:5]}{k:03d}a"
            pa, pb = pids[a["node"]], pids[b["node"]]
            S.append(f"run $X ip link add {ta} netns /proc/{pa}/ns/net type veth peer name {tb} netns /proc/{pb}/ns/net")
            S.append(f"run ns {pa} ip link set {ta} name {_sq(a['ifc'])}")
        S.append(f"run ns {pids[b['node']]} ip link set {tb} name {_sq(b['ifc'])}")
    # 3) 주소 · 브리지 · 경로
    for n in wired:
        if n["kind"] == "host":
            continue
        P = pids[n["id"]]
        S.append(f"run ns {P} ip link set lo up")
        linked = [f for f in n["ifaces"] if _peer(lab, n["id"], f["name"])]
        if n["kind"] == "switch":
            S += [f"run ns {P} ip link add br0 type bridge", f"run ns {P} ip link set br0 up"]
            for f in linked:
                S += [f"run ns {P} ip link set {_sq(f['name'])} master br0", f"run ns {P} ip link set {_sq(f['name'])} up"]
            continue
        if ios.is_ios(n.get("image")):  # Cisco: 리눅스 쪽은 선만 올리고 주소 · 경로는 IOS 가 (시작 설정)
            for f in linked:
                S.append(f"run ns {P} ip link set {_sq(f['name'])} up")
            # 선이 없는 포트는 빈 장치(dummy)로: dynamips 가 붙을 곳이 있어야 라우터가 켜진다. 나중에 선을 이으면 veth 로 바뀐다
            for f in n["ifaces"]:
                if f not in linked:
                    S += [f"run ns {P} ip link add {_sq(f['name'])} type dummy", f"run ns {P} ip link set {_sq(f['name'])} up"]
            continue
        for f in linked:
            if f["ip"]:
                S.append(f"run ns {P} ip addr add {_sq(f['ip'])} dev {_sq(f['name'])}")
            S.append(f"run ns {P} ip link set {_sq(f['name'])} up")
        if n["kind"] == "router":
            S.append(f"ns {P} sysctl -qw net.ipv4.ip_forward=1")
        gw = n["gw"] or p["gw"].get(n["id"])
        if gw and n["kind"] != "whale":
            S.append(f"run ns {P} ip route replace default via {_sq(gw)}")
        for net, via in p["whale_routes"].get(n["id"], []):
            S.append(f"run ns {P} ip route replace {_sq(net)} via {_sq(via)}")
        for r in n["routes"]:
            if r["via"]:
                S.append(f"run ns {P} ip route replace {_sq(r['dst'])} via {_sq(r['via'])}")
    # 4) 이 PC (WSL 루트): 주소, chamber 안쪽으로 가는 길, 인터넷(NAT)
    if host and p["host"] and host_ifs:
        h = p["host"]
        root = next(iter(host_ifs.values()))
        S += [f"run $X ip addr add {_sq(h['ip'])} dev {root}", f"run $X ip link set {root} up",
              "echo 1 > /proc/sys/net/ipv4/ip_forward"]
        for net in h["nets"]:
            via = f"via {_sq(h['via'])}" if h["via"] else ""
            S.append(f"run $X ip route replace {_sq(net)} {via} dev {root}")
        # Windows 에서 들어가는 것은 출발지를 이 PC box 주소로 바꾼다(NAT). 그래야 게이트웨이가 없는 장비
        # (예: wr mem 한 Cisco 설정에 ip route 가 없을 때)도 바로 옆 주소로 답할 수 있다
        rule = f"POSTROUTING -o {root} -j MASQUERADE"
        S.append(f"$X iptables -t nat -C {rule} 2>/dev/null || run $X iptables -t nat -A {rule}")
        if lab["internet"]:
            for net in p["subnets"]:
                rule = f"POSTROUTING -s {_sq(net)} -o eth0 -j MASQUERADE"
                S.append(f"$X iptables -t nat -C {rule} 2>/dev/null || run $X iptables -t nat -A {rule}")
        S.append('echo "WSLIP $(ip -4 -o addr show eth0 | awk \'{print $4}\' | cut -d/ -f1)"')
    S.append('echo "DONE $fail"')
    script = "\n".join(S) + "\n"
    log("wiring", links=len(lab["links"]))
    if use_wsl:
        code, out = dock.wsl_run(script)
    else:
        code, out = dock.run_in(c, dock.NETD_NAME, None, stdin_script=script)
    errs = [x[4:] for x in out.splitlines() if x.startswith("ERR ")]
    if code not in (0, None) and not errs:
        errs = [out.strip()[-400:]]
    if errs:
        raise ChamberError("wire_failed", detail="; ".join(errs)[:600])
    wsl_ip = next((x.split()[1] for x in out.splitlines() if x.startswith("WSLIP ") and len(x.split()) > 1), "")
    # 5) 자동 라우팅: Chamber 이미지 라우터끼리 OSPF (설정은 Chamber 가 맡는다)
    if lab["auto_ospf"]:
        _ospf(c, lab, p, log)
    WIRE_STATE[lab["id"]] = {"ctrs": ctrs, "wsl_ip": wsl_ip, "subnets": p["subnets"], "sig": p["sig"],
                             "host_nets": (p["host"] or {}).get("nets", []) if host else [], "at": time.time()}
    _save_wired()
    log("wired")
    return {"wsl_ip": wsl_ip, "plan": p}


def _ospf(c, lab, p, log):
    routers = [n for n in lab["nodes"] if n["kind"] == "router" and not n.get("image")]
    if len(routers) < 1:
        return
    for n in routers:
        nets = sorted({str(ipaddress.ip_interface(f["ip"]).network) for f in n["ifaces"]
                       if f["ip"] and _peer(lab, n["id"], f["name"])})
        if not nets:
            continue
        cmd = ["vtysh", "-c", "configure terminal"]
        # 실습용으로 빨리 붙게: hello 2초 · dead 8초. 라우터끼리 바로 이은 선은 point-to-point (DR 뽑느라 40초 기다리지 않게)
        by = {x["id"]: x for x in lab["nodes"]}
        for f in n["ifaces"]:
            pe = _peer(lab, n["id"], f["name"])
            if not f["ip"] or not pe:
                continue
            cmd += ["-c", f"interface {f['name']}", "-c", "ip ospf hello-interval 2", "-c", "ip ospf dead-interval 8"]
            cmd += ["-c", "ip ospf network point-to-point" if by[pe["node"]]["kind"] == "router" else "no ip ospf network"]
            cmd += ["-c", "exit"]
        cmd += ["-c", "router ospf", "-c", "redistribute connected", "-c", "redistribute static"]
        for net in nets:
            cmd += ["-c", f"network {net} area 0"]
        if p["gw"].get(n["id"]) and p["host"]:
            cmd += ["-c", "default-information originate always"]
        name = dock.box_name(lab["id"], n["id"])
        for _ in range(30):  # 컨테이너가 막 떴으면 FRR(ospfd) 이 뜰 때까지 잠깐
            # 예전 설정은 지우고 새로 (없을 때 지우면 실패 코드가 나오므로 따로)
            dock.run_in(c, name, ["vtysh", "-c", "configure terminal", "-c", "no router ospf"])
            code, out = dock.run_in(c, name, cmd)
            if code == 0:
                break
            time.sleep(0.5)
        else:
            log("ospf_failed", name=n["name"], detail=out.strip()[:200])
    log("ospf", n=len(routers))


def stop(c, lab, remove=False):
    """box 컨테이너를 멈춘다(remove 면 지운다). Whale 컨테이너는 그대로 두고 꽂았던 선만 뺀다."""
    st = WIRE_STATE.pop(lab["id"], None)
    _save_wired()
    for n in lab["nodes"]:
        if n["kind"] == "whale":
            names = [f["name"] for f in n["ifaces"]]
            try:
                script = "; ".join(f"ip link del {_sq(x)} 2>/dev/null" for x in names) + "; true"
                dock.run_in(c, dock.NETD_NAME, None,
                            stdin_script=f"nsenter --net=/proc/{c.inspect_container(n['ctr'])['State']['Pid']}/ns/net sh -c '{script}'")
            except (NotFound, APIError):
                pass
    for x in dock.lab_containers(c, lab["id"]):
        try:
            if remove:
                c.remove_container(x["Id"], force=True)
            elif x["State"] == "running":
                c.stop(x["Id"], timeout=3)
        except NotFound:
            pass
    if remove:
        for v in c.volumes(filters={"label": f"{dock.LAB_LABEL}={lab['id']}"}).get("Volumes") or []:
            try:
                c.remove_volume(v["Name"])
            except (NotFound, APIError):
                pass
    if dock.wsl_ready() and any(n["kind"] == "host" for n in lab["nodes"]):
        nets = (st or {}).get("subnets") or plan(clean(lab))["subnets"]
        S = [f"ip link del {_root_if(lab['id'], k)} 2>/dev/null" for k in range(4)]
        try:
            S = [f'HP={_netd_pid(c)}',
                 'H=""; for s in /proc/[0-9]*/status; do set -- $(grep "^NSpid:" $s 2>/dev/null); '
                 'if [ "$#" -ge 3 ] && [ "$3" = "$HP" ]; then H=$2; break; fi; done',
                 'X="nsenter -t $H -m --"'] + [f"$X {x}" for x in S]
            S += [f"$X iptables -t nat -D POSTROUTING -s {_sq(net)} -o eth0 -j MASQUERADE 2>/dev/null" for net in nets]
            S += [f"$X iptables -t nat -D POSTROUTING -o {_root_if(lab['id'], k)} -j MASQUERADE 2>/dev/null" for k in range(4)]
            dock.wsl_run("\n".join(S) + "\ntrue\n")
        except (NotFound, APIError, OSError):
            pass


def status(c, lab):
    """box 마다 컨테이너 상태와, chamber 전체가 '꽂힌 그대로' 인지."""
    ctrs = {x["Labels"].get(dock.NODE_LABEL): x for x in dock.lab_containers(c, lab["id"])}
    st = WIRE_STATE.get(lab["id"])
    boxes, running, total = {}, 0, 0
    for n in lab["nodes"]:
        if n["kind"] not in WIRED or n["kind"] == "host":
            continue
        total += 1
        if n["kind"] == "whale":
            try:
                i = c.inspect_container(n["ctr"])
                s = i["State"]["Status"]
            except NotFound:
                s = "missing"
        else:
            x = ctrs.get(n["id"])
            s = x["State"] if x else "none"
        boxes[n["id"]] = s
        running += s == "running"
        if s == "running" and ios.is_ios(n.get("image")) and n["image"] not in _idle_cache():
            _learn_idle(c, lab, n)
    wired = False
    if st and running == total and total:
        try:
            now = {}
            for cid in st["ctrs"]:
                now[cid] = c.inspect_container(cid)["State"]["StartedAt"]
            # 컨테이너를 다시 켰거나, 꽂은 뒤 box · 선 · IP 를 고쳤으면 '다시 연결 필요'
            wired = now == st["ctrs"] and st.get("sig") == wire_sig(clean(lab))
        except NotFound:
            wired = False
    state = "running" if wired else "stale" if running else "stopped"
    synced = ios_sync(c, lab, boxes)
    return {"state": state, "boxes": boxes, "running": running, "total": total,
            "wsl_ip": (st or {}).get("wsl_ip", ""), "subnets": (st or {}).get("subnets", []),
            "host_nets": (st or {}).get("host_nets", []), "synced": synced}


def box_ctr(c, lab, nid):
    n = next((n for n in lab["nodes"] if n["id"] == nid), None)
    if not n or n["kind"] not in WIRED or n["kind"] == "host":
        raise ChamberError("not_found", detail="box")
    return n["ctr"] if n["kind"] == "whale" else dock.box_name(lab["id"], nid), n


# ---------------------------------------------------------------- Cisco (Dynamips)
def _idle_cache():
    try:
        return json.loads(IDLE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _learn_idle(c, lab, n):
    """라우터 안에서 계산된 idle-pc 를 이미지별로 기억한다 (같은 이미지의 다음 라우터는 처음부터 CPU 를 덜 쓴다)."""
    try:
        code, out = dock.run_in(c, dock.box_name(lab["id"], n["id"]), ["cat", "/data/idlepc"])
    except (NotFound, APIError):
        return
    pc = out.strip()
    if code == 0 and re.fullmatch(r"0x[0-9a-f]{6,16}", pc):
        d = _idle_cache()
        d[n["image"]] = pc
        DATA.mkdir(parents=True, exist_ok=True)
        IDLE_FILE.write_text(json.dumps(d), encoding="utf-8")


def ios_reset(c, lab, nid):
    """bullet 설정을 라우터에 다시 넣고 다시 켠다 (라우터에 저장한 설정은 덮어쓴다)."""
    lab = clean(lab)
    n = next((x for x in lab["nodes"] if x["id"] == nid), None)
    if not n or not ios.is_ios(n.get("image")):
        raise ChamberError("not_found", detail="box")
    by0 = {x["id"]: x for x in lab["nodes"]}

    def peer_kind(a, ifc):
        pe = _peer(lab, a, ifc)
        return by0[pe["node"]]["kind"] if pe else ""
    name = dock.box_name(lab["id"], nid)
    cfg = ios.startup_config(lab, n, plan(lab), peer_kind)
    # 넣으라는 표시는 볼륨(/data/push)에: 이어지는 시작에서 컨테이너를 새로 만들어도 남는다
    c.put_archive(name, "/", ios.config_archive(cfg, push="volume"))
    c.restart(name, timeout=5)


SYNC_AT: dict[str, float] = {}  # "lab/node" → 마지막으로 읽은 때


def ios_sync(c, lab, boxes, every=8):
    """실행 중인 Cisco 라우터의 NVRAM 설정(wr mem)이 바뀌었으면 그 포트 IP · 게이트웨이 · 경로 · 이름을 bullet 으로.
    → 바뀐 box 들 (화면이 받아서 고친다). 파일에도 바로 저장한다."""
    import hashlib
    out = []
    for n in lab["nodes"]:
        if n["kind"] != "router" or not ios.is_ios(n.get("image")) or boxes.get(n["id"]) != "running":
            continue
        key = f"{lab['id']}/{n['id']}"
        if time.time() - SYNC_AT.get(key, 0) < every:
            continue
        SYNC_AT[key] = time.time()
        try:
            code, text = dock.run_in(c, dock.box_name(lab["id"], n["id"]), ["python3", "-c", ios.EXTRACT])
        except (NotFound, APIError):
            continue
        if code != 0 or not ios.user_saved(text):
            continue  # 아직 wr mem 하지 않았다 (Chamber 가 넣은 설정 그대로)
        h = hashlib.sha1(text.encode("latin-1", "replace")).hexdigest()[:16]
        if n.get("ios_sync") == h:
            continue
        host, ifs, gw, routes = ios.parse_config(text, ios.platform_of(n["image"]))
        for i, f in enumerate(n["ifaces"]):
            if i in ifs:
                f["ip"] = ifs[i]
        n["gw"], n["routes"], n["ios_sync"] = gw, routes, h
        if host and NAME_RE.fullmatch(host):
            n["name"] = host
        out.append({k: n[k] for k in ("id", "name", "ifaces", "gw", "routes", "ios_sync")})
    if out:
        try:
            cur = load(lab["id"])
            by = {x["id"]: x for x in out}
            for n in cur["nodes"]:
                if n["id"] in by:
                    n.update(by[n["id"]])
            save(cur)
        except ChamberError:
            pass
    return out
