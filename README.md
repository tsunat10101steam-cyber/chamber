# Chamber

Docker 위에서 **실제로 동작하는** 네트워크 실습실을 화이트보드처럼 그리는 Windows 앱.
라우터 · 스위치 · PC 를 끌어다 놓고 포트끼리 이으면, Windows `cmd` 에서 `ping` 이 정말로 그 라우터와 스위치를 거쳐 갑니다.

같은 사람이 만든 [Boom](https://github.com/tsunat10101steam-cyber/boom)(AWS) · [Whale](https://github.com/tsunat10101steam-cyber/whale)(Docker) 과 함께 씁니다.

## 이름
- **chamber** — 직접 만드는 네트워크 하나. 여러 개를 만들어 두고 골라 씁니다.
- **box** — chamber 안의 장비 하나 (라우터, 스위치, PC, 서버, 이 PC, Whale 컨테이너, 가상 머신, AWS VPC, 메모).
- **bullet** — box 안의 구성 요소: 포트(인터페이스) · IP · 게이트웨이 · 정적 경로 · 이미지.
- **cobweb** — box 로 쓸 장비 이미지 저장소. 자유 라이선스 이미지를 받아 둡니다.
- **VcoM** — 이 PC 의 가상 머신(VMware Workstation · VirtualBox)을 찾아 켜고 끄고 chamber 에 놓습니다.

## 기능
- 화이트보드: box 끌어다 놓기 · 옮기기, 포트 핀을 다른 box 로 끌어 선 잇기, 선을 이으면 IP 자동(스위치 너머 같은 구간은 같은 서브넷)
- 시작하면 box 마다 컨테이너가 뜨고 선(veth)이 꽂히고 주소 · 경로가 들어감. 다시 누르면 처음부터 다시 꽂음
- 자동 라우팅: Chamber 기본 이미지 라우터끼리 OSPF (실습용으로 빠르게: hello 2초 · dead 8초)
- **이 PC** box: Windows 에서 chamber 안으로 들어오는 길. 시작할 때 Windows 경로를 넣고(관리자 확인 한 번) chamber 는 이 PC 를 통해 인터넷에도 나감(NAT)
- 콘솔: box 를 두 번 누르면 아래 패널에 셸, 라우터는 `vtysh` 도
- 오른쪽 패널의 "cmd 에서 ping" 버튼: 이 PC 에서 바로 ping
- Whale 연동: 이미 있는 Docker 컨테이너를 box 로 놓으면 포트(`ch0` …)를 더 꽂아 chamber 에 잇는다 (원래 네트워크는 그대로). Chamber 가 만든 컨테이너는 Whale 에서 `chamber · 이름` 묶음으로 보임
- Boom 연동: Boom 이 켜져 있고 AWS 에 연결돼 있으면 VPC · 서브넷 · 리소스를 AWS box 로 가져오기 (보기 전용)
- 한국어 · English, 밝게 · 어둡게, 자동 업데이트

## 동작 방식
```
Windows cmd ── route 10.77.x.0/24 → WSL(docker-desktop) ── veth ── R1 ── veth ── SW1 ── veth ── PC1
                                       └ NAT → 인터넷          (box = --network none 컨테이너)
```
- box 는 자기 네트워크가 없는(`--network none`) 컨테이너입니다.
- 선은 veth 쌍입니다. 도우미 컨테이너 `chamber-netd`(privileged, `--pid host`)의 iproute2 로 두 box 의 네트워크 공간에 한쪽씩 꽂습니다.
- '이 PC' 는 veth 한쪽을 Docker Desktop 의 WSL2 배포판(`docker-desktop`)에 둡니다. 그곳은 Windows 가 `vEthernet (WSL)` 로 바로 닿는 곳이라, Windows 경로 하나로 ping 이 들어갑니다.

## 필요한 것
- Windows 10/11, **Docker Desktop (WSL2 백엔드)** — '이 PC' 연결에 WSL2 가 필요합니다
- 처음 시작할 때 Chamber 기본 이미지를 이 PC 에서 만듭니다 (Alpine 패키지를 받으므로 1~2분)
- VcoM: VMware Workstation 또는 VirtualBox (없으면 그 탭만 비어 있음)
- Boom 연동: Boom 실행 + AWS 연결

## 라이선스가 있는 이미지
Cisco IOS · IOU, Juniper 같은 이미지는 Chamber 가 받아 주지 않습니다. 가진 이미지를 `docker load` 로 넣고 cobweb 의 "이름으로 받기" 나 box 이미지 칸에 이름을 쓰면 됩니다.

## 실행 (개발)
```
run.bat            :: 처음엔 .venv 를 만들고 패키지를 설치
build.bat          :: Chamber.exe (+ NSIS 가 있으면 Chamber-Setup) 를 만들어 설치
```

## 데이터
- chamber 설정: `%LOCALAPPDATA%\Chamber\chambers\*.json`
- box 컨테이너 이름: `chamber-<chamber id>-<box id>` (라벨 `chamber.lab`, `chamber.node`)
- Windows 경로는 재부팅하면 사라지는 임시 경로입니다. chamber 를 시작할 때마다 맞춥니다.

## 아직 안 되는 것
- VM 네트워크 카드를 chamber 선에 꽂기 (지금은 VcoM 으로 켜고 끄고 정보만)
- QEMU 이미지(VyOS, OpenWrt …) 장비
