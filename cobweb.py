"""cobweb: box 로 쓸 장비 이미지 저장소.

자유 라이선스로 공개된 Docker 이미지만 바로 받는다. Cisco IOS 같은 라이선스 이미지는 받아 주지 않는다
(사용자가 가진 Docker 이미지는 '이미지 이름으로 받기' 또는 docker load 로 넣고 이름으로 쓰면 된다).
"""
from __future__ import annotations

import re

import dock

# kind: 이 이미지로 만들 수 있는 box 종류. license 는 화면에 그대로 보여 준다.
CATALOG = [
    {"id": "box", "image": dock.BOX_IMAGE, "kinds": ["router", "switch", "pc"], "license": "GPL-2.0 (FRR) · MIT",
     "builtin": True, "size": 60_000_000},
    {"id": "netshoot", "image": "nicolaka/netshoot:latest", "kinds": ["pc", "server"], "license": "Apache-2.0",
     "size": 220_000_000},
    {"id": "alpine", "image": "alpine:3.22", "kinds": ["pc", "server"], "license": "MIT", "size": 4_000_000},
    {"id": "nginx", "image": "nginx:alpine", "kinds": ["server"], "license": "BSD-2-Clause", "size": 22_000_000},
    {"id": "httpd", "image": "httpd:alpine", "kinds": ["server"], "license": "Apache-2.0", "size": 25_000_000},
    {"id": "frr", "image": "quay.io/frrouting/frr:10.2.1", "kinds": ["router"], "license": "GPL-2.0", "size": 130_000_000},
    {"id": "dnsmasq", "image": "dockurr/dnsmasq:latest", "kinds": ["server"], "license": "GPL-2.0 · MIT", "size": 5_000_000},
]
IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:@-]{0,200}")


def listing(c):
    """카탈로그 + 이 PC 에 받아 둔 다른 이미지 (내가 가져온 것)."""
    local = {}
    for im in c.images():
        for tag in im.get("RepoTags") or []:
            if tag != "<none>:<none>":
                local[tag] = im.get("Size", 0)
    items = []
    known = set()
    for x in CATALOG:
        items.append({**x, "have": x["image"] in local, "local_size": local.get(x["image"], 0)})
        known.add(x["image"])
    mine = [{"id": "", "image": t, "kinds": ["pc", "server", "router"], "license": "", "have": True, "local_size": s, "mine": True}
            for t, s in sorted(local.items()) if t not in known and not t.startswith("chamber/")]
    return {"catalog": items, "mine": mine}


def check_image(name):
    name = (name or "").strip().lower()
    if not IMAGE_RE.fullmatch(name):
        raise dock.ChamberError("bad_field", field="image")
    return name if ":" in name.rsplit("/", 1)[-1] or "@" in name else name + ":latest"


def remove(c, image):
    image = check_image(image)
    if image == dock.BOX_IMAGE:
        # 기본 이미지는 도우미(chamber-netd)도 쓴다
        raise dock.ChamberError("in_use", name=image)
    c.remove_image(image)
