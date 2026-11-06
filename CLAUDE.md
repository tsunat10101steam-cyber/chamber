# Chamber — 작업 규칙

Docker 위의 네트워크 실습실 Windows 앱. 같은 사람이 만든 Boom(AWS) · Whale(Docker) 과 구조가 같다.

## 이름 (화면과 코드에서 그대로 쓴다)
- chamber = 실습 네트워크 하나 (코드에서는 lab), box = 그 안의 장비 (node), bullet = box 의 포트 · IP · 경로 같은 구성 요소
- cobweb = 장비 이미지 저장소, VcoM = 가상 머신(VMware · VirtualBox) 감지

## 구조
- Flask 서버(127.0.0.1:8767, `CHAMBER_PORT` 로 바꿈) + Edge 앱 창. Boom 8765, Whale 8766.
- `engine.py`: chamber 저장(`%LOCALAPPDATA%\Chamber\chambers`) · 검사(`clean`) · 계획(`plan`) · 시작/중지. 선 꽂기는 sh 스크립트 하나로 만든다.
- `dock.py`: Docker 연결, Chamber 기본 이미지(`chamber/box:1`, 처음에 이 PC 에서 build), 도우미 `chamber-netd`, box 컨테이너, 콘솔.
- `winroute.py`: Windows 경로 (UAC 한 번). `vcom.py`, `cobweb.py`, `boomlink.py`(Boom · Whale 로컬 API).
- 화면: `static/app.js`(공통 · chamber 불러오기/저장/시작), `canvas.js`(화이트보드), `side.js`(오른쪽 패널 · cobweb · VcoM), `term.js`(콘솔).
- 모든 `/api/` 요청은 같은 출처 · JSON 만 받는다 (`_same_origin_only`). 지우지 않는다.

## 네트워크가 실제로 동작하는 방법 (바꿀 때 주의)
- box 는 `--network none` 컨테이너. 선은 veth 쌍.
- 선 꽂기는 `wsl -d docker-desktop -u root sh -s` 로 WSL 루트 네트워크에서 실행한다. 도우미(`--pid host --privileged`)의
  마운트 공간만 빌려 iproute2 를 쓰고(`nsenter -t <도우미> -m`), 그 안의 `/proc` 은 엔진 pid 공간이라 `docker inspect` 의 Pid 를 그대로 쓴다.
  도우미의 배포판 pid 는 `/proc/*/status` 의 `NSpid` 로 찾는다.
- docker-desktop 배포판의 `ip` 는 busybox 라 veth 이름 · netns 문법이 깨진다. 반드시 도우미의 iproute2 로.
- FRR(zebra)은 `SYS_ADMIN` 이 필요하다 (라우터 box 에만 준다).
- Windows 의 파이프 오류는 OSError 가 아닌 `pywintypes.error` 다. 소켓 읽기는 `except Exception`.

## 규칙
- 화면 문구는 전부 `static/i18n.js` 키로 넣고 ko · en 을 모두 채운다.
- 코드 주석은 한국어. 주변 코드의 밀도와 이름 짓는 방식을 따른다.
- 디자인: 흰 바탕, 1px 선 격자, 각진 모서리, 강조색은 Chamber 초록 하나. box 종류 색은 아이콘 칸에만.
- 라이선스가 있는 이미지(Cisco 등)를 받아 주는 기능은 넣지 않는다.

## 시험
- 실제 Docker Desktop(WSL2)으로 시험한다. '이 PC' 가 있는 chamber 를 시작하고 Windows 에서 ping 이 되는지까지 본다.
- 화면은 서버를 다른 포트로 띄우고 헤드리스 Edge(CDP)로 실제 마우스 이벤트를 보내 눌러 본다.

## 릴리스 ("Release vX.Y.Z")
1. `version.py` 의 `__version__` 을 올린다.
2. `CHANGELOG.md` 맨 위(설명 문단 아래)에 `## vX.Y.Z` 항목을 추가한다.
3. 커밋 메시지는 `vX.Y.Z: <요약>`.
4. main 에 커밋하고 태그 `vX.Y.Z` 를 push 한다 → GitHub Actions 가 `Chamber-Setup-X.Y.Z.exe` 와 `Chamber-vX.Y.Z.zip` 을 만든다.
