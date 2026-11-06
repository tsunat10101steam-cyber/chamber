# 변경 내역

릴리스 노트는 이 파일의 해당 버전 항목에서 자동으로 가져온다. 새 버전을 낼 때 맨 위에 `## vX.Y.Z` 항목을 추가하고 같은 이름으로 태그를 푸시한다.

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
