"""Windows 경로 표: chamber 안쪽 구간(10.x …) 을 WSL(docker-desktop) 쪽으로 보낸다.

경로를 넣고 빼는 것은 관리자 권한이 필요하다. 필요한 것만 모아서 UAC 확인 창 한 번으로 처리한다.
경로는 재부팅하면 사라지는 임시 경로(-p 없음)다. WSL 주소는 재부팅마다 바뀌므로 chamber 를 시작할 때마다 맞춘다.
"""
from __future__ import annotations

import ipaddress
import os
import re
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def current():
    """{(망, 마스크): 게이트웨이} — route print 의 IPv4 활성 경로."""
    if os.name != "nt":
        return {}
    out = subprocess.run(["route", "print", "-4"], capture_output=True, creationflags=NO_WINDOW).stdout.decode("mbcs", "replace")
    routes = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+\d+\.\d+\.\d+\.\d+\s+\d+", line)
        if m:
            routes[(m.group(1), m.group(2))] = m.group(3)
    return routes


def missing(nets, gw):
    """넣어야 할 경로 [(망, 마스크)] 와 다른 곳을 가리키는 예전 경로."""
    have = current()
    # 이미 WSL 을 가리키는 더 넓은 경로(예: 직접 넣은 10.77.0.0/16)가 감싸면 따로 넣지 않는다
    cover = [ipaddress.IPv4Network(f"{a}/{m}") for (a, m), g in have.items() if g == gw and m != "255.255.255.255"]
    need = []
    for n in nets:
        net = ipaddress.IPv4Network(n)
        key = (str(net.network_address), str(net.netmask))
        if have.get(key) != gw and not any(net.subnet_of(c) for c in cover if c.prefixlen >= 8):
            need.append(key)
    return need


def apply(adds, gw, deletes=()):
    """관리자 cmd 하나로 route delete/add. 사용자가 UAC 를 거절하면 False."""
    cmds = []
    for net, mask in list(deletes) + list(adds):
        _check(net), _check(mask)
        cmds.append(f"route delete {net} mask {mask}")
    for net, mask in adds:
        cmds.append(f"route add {net} mask {mask} {_check(gw)}")
    if not cmds:
        return True
    line = " & ".join(cmds)
    ps = ("try { $p = Start-Process -FilePath cmd.exe -ArgumentList '/c " + line + "' -Verb RunAs -WindowStyle Hidden "
          "-Wait -PassThru; exit $p.ExitCode } catch { exit 1223 }")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       creationflags=NO_WINDOW, timeout=180)
    return r.returncode != 1223


def _check(ip):
    ipaddress.IPv4Address(ip)
    return ip


def ping(ip, count=2):
    """Windows 에서 ping (화면의 'cmd 에서 ping' 버튼). 출력은 그대로 보여 준다."""
    _check(ip)
    r = subprocess.run(["ping", "-n", str(count), "-w", "1000", ip], capture_output=True, creationflags=NO_WINDOW, timeout=30)
    text = r.stdout.decode("mbcs" if os.name == "nt" else "utf-8", "replace")
    return {"ok": r.returncode == 0 and "TTL=" in text.upper(), "out": text.strip()}
