"""VcoM: 이 PC 의 가상 머신(VMware Workstation · VirtualBox)을 찾아 chamber 에서 쓰게 한다.

VMware: %APPDATA%\\VMware\\inventory.vmls 의 목록 + .vmx 설정 + vmrun(실행 중 · 시작 · 중지 · 게스트 IP).
VirtualBox: VBoxManage. 둘 다 없으면 빈 목록.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from dock import ChamberError

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PF = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", r"C:\Program Files")]
VMWARE_DIRS = [Path(p) / "VMware" / "VMware Workstation" for p in PF] + [Path(p) / "VMware" / "VMware Player" for p in PF]
VBOX = [Path(p) / "Oracle" / "VirtualBox" / "VBoxManage.exe" for p in PF]


def _run(args, timeout=20):
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _vmware():
    d = next((d for d in VMWARE_DIRS if (d / "vmrun.exe").exists()), None)
    return d


def _kv(path):
    out = {}
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r'\s*([\w.:]+)\s*=\s*"(.*)"\s*$', line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    except OSError:
        pass
    return out


NET_NAMES = {"nat": "NAT (VMnet8)", "hostonly": "Host-only (VMnet1)", "bridged": "Bridged (VMnet0)"}


def _vmx_info(vmx):
    k = _kv(vmx)
    nics = []
    for i in range(10):
        p = f"ethernet{i}."
        if k.get(p + "present", "").upper() != "TRUE":
            continue
        t = k.get(p + "connectiontype", "bridged").lower()
        nics.append({"n": i, "type": t, "vnet": k.get(p + "vnet", ""),
                     "label": NET_NAMES.get(t) or (k.get(p + "vnet") or t), "mac": k.get(p + "generatedaddress", "")})
    return {"name": k.get("displayname", Path(vmx).stem), "os": k.get("guestos", ""), "mem": int(k.get("memsize", "0") or 0),
            "cpus": int(k.get("numvcpus", "1") or 1), "nics": nics}


def listing():
    hv, vms = [], []
    d = _vmware()
    if d:
        hv.append({"id": "vmware", "name": "VMware Workstation", "path": str(d)})
        code, out = _run([str(d / "vmrun.exe"), "-T", "ws", "list"])
        running = {os.path.normcase(l.strip()) for l in out.splitlines()[1:] if l.strip().lower().endswith(".vmx")}
        inv = _kv(Path(os.environ.get("APPDATA", "")) / "VMware" / "inventory.vmls")
        paths = {v for k, v in inv.items() if k.endswith(".config") and v.lower().endswith(".vmx")}
        paths |= {l.strip() for l in out.splitlines()[1:] if l.strip().lower().endswith(".vmx")}
        for vmx in sorted(paths):
            if not Path(vmx).exists():
                continue
            info = _vmx_info(vmx)
            vms.append({"hv": "vmware", "id": vmx, **info, "running": os.path.normcase(vmx) in running})
    vb = next((p for p in VBOX if p.exists()), None)
    if vb:
        hv.append({"id": "vbox", "name": "VirtualBox", "path": str(vb.parent)})
        _, out = _run([str(vb), "list", "vms"])
        _, run = _run([str(vb), "list", "runningvms"])
        on = set(re.findall(r"\{([0-9a-f-]+)\}", run))
        for name, uid in re.findall(r'"(.+)" \{([0-9a-f-]+)\}', out):
            vms.append({"hv": "vbox", "id": uid, "name": name, "os": "", "mem": 0, "cpus": 0, "nics": [], "running": uid in on})
    return {"hypervisors": hv, "vms": vms, "host_nets": host_nets()}


_hn = {}


def host_nets():
    """VMware 가 Windows 에 만든 가상 어댑터(VMnet1 · VMnet8)의 주소. 이 PC 에서 그 VM 들로 가는 길."""
    if "v" in _hn or os.name != "nt":
        return _hn.get("v", [])
    ps = ("Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object InterfaceAlias -like '*VMnet*' "
          "| Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json -Compress")
    code, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=20)
    try:
        d = json.loads(out.strip() or "[]")
        d = [d] if isinstance(d, dict) else d
        _hn["v"] = [{"name": x["InterfaceAlias"], "ip": f'{x["IPAddress"]}/{x["PrefixLength"]}'} for x in d]
    except (ValueError, KeyError, TypeError):
        _hn["v"] = []
    return _hn["v"]


def _known(hv, vm_id):
    for v in listing()["vms"]:
        if v["hv"] == hv and v["id"] == vm_id:
            return v
    raise ChamberError("not_found", detail="vm")


def act(hv, vm_id, action):
    v = _known(hv, vm_id)  # 목록에 있는 VM 만 (아무 경로나 실행하지 않게)
    if hv == "vmware":
        d = _vmware()
        vmrun = str(d / "vmrun.exe")
        if action == "start":
            code, out = _run([vmrun, "-T", "ws", "start", v["id"], "nogui"], timeout=180)
        elif action == "stop":
            code, out = _run([vmrun, "-T", "ws", "stop", v["id"], "soft"], timeout=180)
        elif action == "gui":
            subprocess.Popen([str(d / "vmware.exe"), v["id"]], creationflags=NO_WINDOW, close_fds=True)
            return {"ok": True}
        elif action == "ip":
            code, out = _run([vmrun, "-T", "ws", "getGuestIPAddress", v["id"]], timeout=20)
            ip = out.strip().splitlines()[-1] if out.strip() else ""
            return {"ok": code == 0 and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip) is not None, "ip": ip if code == 0 else "",
                    "detail": "" if code == 0 else ip}
        else:
            raise ChamberError("bad_field", field="action")
    elif hv == "vbox":
        vb = str(next(p for p in VBOX if p.exists()))
        if action == "start":
            code, out = _run([vb, "startvm", v["id"], "--type", "headless"], timeout=120)
        elif action == "stop":
            code, out = _run([vb, "controlvm", v["id"], "acpipowerbutton"], timeout=60)
        elif action == "gui":
            code, out = _run([vb, "startvm", v["id"], "--type", "gui"], timeout=120)
        elif action == "ip":
            code, out = _run([vb, "guestproperty", "get", v["id"], "/VirtualBox/GuestInfo/Net/0/V4/IP"])
            m = re.search(r"Value: (\S+)", out)
            return {"ok": bool(m), "ip": m.group(1) if m else "", "detail": "" if m else out.strip()[:200]}
        else:
            raise ChamberError("bad_field", field="action")
    else:
        raise ChamberError("bad_field", field="hv")
    if code != 0:
        raise ChamberError("vm_failed", detail=out.strip()[-300:])
    return {"ok": True}
