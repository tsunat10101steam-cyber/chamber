# 변경 내역

릴리스 노트는 이 파일의 해당 버전 항목에서 자동으로 가져온다. 새 버전을 낼 때 맨 위에 `## vX.Y.Z` 항목을 추가하고 같은 이름으로 태그를 푸시한다.

## v0.3.3

- 창이 열려 있는데 서버가 꺼져 'Failed to fetch' 만 뜨던 문제 고침: PC 가 절전에서 깨거나 창이 오래 가려져 있어도 서버가 꺼지지 않고, Chamber 창이 실제로 닫힐 때만 꺼짐
- 서버가 꺼졌으면 위에 안내 막대를 한 번만 띄움 (같은 오류 알림을 되풀이하지 않음)

## v0.3.2

- Boom 에서 가져온 VPC 를 화이트보드에 바로 그리지 않고 왼쪽 'AWS · Boom' 목록에 둠. 필요한 것만 끌어다 놓거나 두 번 눌러 AWS box 로 놓기
- 이미 놓은 VPC 는 목록에서 흐리게 표시, 다시 가져오면 놓인 box 의 내용만 새로

## v0.3.1

- Cisco L3 스위치: PC · 이 PC · 라우터가 꽂힌 access 포트에 spanning-tree portfast 를 넣어, 켜거나 선을 꽂은 뒤 STP 대기(약 30초) 없이 바로 통함

## v0.3.0

- Cisco L3 스위치 box: c3725 · c3745 · c2691 IOS 에 NM-16ESW(16포트 EtherSwitch)를 꽂아 VLAN · 트렁크 · SVI(interface VlanN) 로 VLAN 사이 라우팅
- 팔레트에 'Cisco c3725 L3 스위치', 포트는 Fa1/0~15 (스위치) + Fa0/0 · 0/1 (라우티드)
- bullet: 포트마다 VLAN 번호 또는 trunk, SVI 목록 (VLAN · IP). 포트를 이으면 그 VLAN 의 SVI 와 PC 주소를 자동으로
- 콘솔에서 wr mem 한 VLAN · 트렁크 · SVI 도 bullet 으로 가져옴. VLAN 은 플래시(vlan.dat)에 저장
- PC 가 꽂힌 포트 VLAN 의 SVI 와 서브넷이 다르면 경고
- 라우터 안에서만 바뀌고 서브넷이 그대로면 '다시 연결 필요' 를 띄우지 않음

## v0.2.7

- 위 막대의 Docker 표시를 짧게: "WSL2" / "WSL2 아님"

## v0.2.6

- Whale 컨테이너 box: Docker 기본 게이트웨이는 그대로 두고, chamber 의 다른 구간(이 PC 구간 포함)으로 가는 길을 같은 구간의 라우터로 넣음 → Windows 에서 라우터 너머의 Whale 컨테이너까지 ping
- 시작한 뒤 box · 선 · IP 를 고치면 '다시 연결 필요' 로 표시 (전에는 '실행 중' 으로 남아 새 선이 안 꽂힌 것을 알 수 없었음)

## v0.2.5

- Windows cmd 에서 chamber 로 가는 ping 의 출발지를 '이 PC' box 주소로 바꿔 보냄 (NAT). 게이트웨이가 없는 장비(예: wr mem 한 Cisco 설정에 ip route 가 없을 때)도 응답함

## v0.2.4

- 선 하나의 양쪽 IP 가 서로 다른 서브넷이면 경고 (chamber 요약과 그 box 의 패널에). 예: 이 PC 10.77.1.254/24 ↔ 라우터 192.168.100.1/24 면 ping 이 통하지 않음

## v0.2.3

- Cisco 라우터 IOS → bullet: IOS 콘솔에서 wr mem 으로 저장하면 몇 초 안에 포트 IP · 기본 게이트웨이 · 정적 경로 · hostname 이 화이트보드의 bullet 에 들어옴
- 저장된 설정(NVRAM)을 하이퍼바이저로 읽으므로 열려 있는 IOS 콘솔에는 끼어들지 않음

## v0.2.2

- 선이 없는 Cisco 라우터도 켜짐 (빈 포트를 꽂아 두고, 나중에 선을 이으면 재부팅 없이 바꿔 붙임). 전에는 IOS 콘솔이 'Connection refused'
- IOS 콘솔: 라우터가 아직 켜지는 중이면 열릴 때까지 기다렸다가 붙음
- bullet(IP · 게이트웨이 · 경로)을 바꾸면 라우터를 다시 켤 때 들어감. 라우터에서 wr mem 으로 직접 저장한 설정은 지킴
- '설정 다시 넣기' 가 이어지는 시작에서 사라지던 문제 고침
- 라우터 드라이버를 이미지에 굳히지 않고 box 를 만들 때 넣음 (IOS 파일을 다시 가져올 필요 없음)

## v0.2.1

- IOS 파일 가져오기: 파일 선택 창이 앱 창 뒤에 숨어 버튼이 안 눌린 것처럼 보이던 문제 고침 (맨 앞에 띄움, 열려 있는 동안 표시)
- IOS 파일 경로를 붙여 넣어 가져오는 칸 추가
- 이미지 지우기: 쓰는 box 가 있으면 어느 chamber 의 어느 box 인지 알려 주고, box 컨테이너와 함께 지울 수 있음

## v0.2.0

- Cisco 라우터 box (Dynamips): 가진 IOS 이미지(.bin)를 cobweb 에서 가져오면 팔레트에 'Cisco c3725' 같은 라우터가 생김
- IOS 포트 이름(Fa0/0 …)으로 표시, 플랫폼별 포트 수 제한, IOS 콘솔, 설정 다시 넣기
- bullet → IOS 시작 설정 (자동 OSPF 포함), FRR 라우터와 OSPF 로 붙음
- idle-pc 자동 계산 · 이미지별 기억, 선을 다시 꽂아도 라우터를 다시 켜지 않음

## v0.1.0

- 첫 버전
- 화이트보드: 라우터 · 스위치 · PC · 서버 · 이 PC · 메모 box 를 놓고 포트끼리 선 잇기, IP 자동
- 시작하면 실제로 동작: box 는 컨테이너, 선은 veth, 라우터는 FRR (자동 OSPF)
- 이 PC box 로 Windows cmd 에서 chamber 안쪽까지 ping, chamber 에서 인터넷 (NAT)
- box 콘솔 (셸 · vtysh) 과 "cmd 에서 ping" 버튼
- cobweb: 자유 라이선스 장비 이미지 받기 · 이름으로 받기 · 이 PC 의 이미지
- VcoM: VMware Workstation · VirtualBox 가상 머신 찾기 · 켜기 · 끄기 · chamber 에 놓기
- Whale 연동 (기존 컨테이너를 box 로), Boom 연동 (AWS VPC 가져오기)
