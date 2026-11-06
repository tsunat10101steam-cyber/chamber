"""Boom 연동: Boom(AWS 정리 앱)이 켜져 있고 AWS 에 연결돼 있으면, 그 AWS 구성(VPC · 서브넷 · 리소스)을 box 로 가져온다.

Boom 의 로컬 API(127.0.0.1:8765)를 서버끼리 부른다. AWS 자격 증명은 Boom 안에만 있고 Chamber 는 보지 않는다.
가져온 AWS box 는 보기 전용이다 (실제 선은 꽂지 않는다).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from dock import ChamberError

BOOM = "http://127.0.0.1:8765"
WHALE = "http://127.0.0.1:8766"


def _call(base, path, body=None, timeout=5):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def app_status(base):
    try:
        return {"running": True, "version": _call(base, "/api/version", timeout=1.5).get("version", "")}
    except (OSError, ValueError):
        return {"running": False}


def boom_status():
    # 연결 여부는 가져올 때 Boom 이 알려 준다 (need_connect)
    return app_status(BOOM)


def boom_import():
    """Boom 에서 지역별 VPC 구성을 받아 화면에 필요한 것만 추린다."""
    try:
        d = _call(BOOM, "/api/topology", {}, timeout=120)
    except urllib.error.HTTPError as e:
        try:
            code = json.loads(e.read().decode("utf-8")).get("error", "")
        except ValueError:
            code = ""
        raise ChamberError("boom_not_connected" if code == "need_connect" else "boom_failed",
                           detail=code or str(e))
    except (OSError, ValueError) as e:
        raise ChamberError("boom_off", detail=str(e))
    vpcs = []
    for reg in d.get("regions") or []:
        for v in reg.get("vpcs") or []:
            subs = []
            for s in v.get("subnets") or []:
                subs.append({"id": s.get("id"), "name": s.get("name") or "", "cidr": s.get("cidr"), "az": s.get("az"),
                             "public": bool(s.get("public")),
                             "res": [{"type": r.get("type"), "id": r.get("id"), "name": r.get("name") or "", "state": r.get("state") or ""}
                                     for r in (s.get("resources") or [])][:100]})
            vpcs.append({"region": reg.get("region"), "id": v.get("id"), "name": v.get("name") or "", "cidr": v.get("cidr"),
                         "default": bool(v.get("default")), "igw": v.get("igw") or "", "subnets": subs})
    return {"vpcs": vpcs}
