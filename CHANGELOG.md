# 변경 내역

릴리스 노트는 이 파일의 해당 버전 항목에서 자동으로 가져온다. 새 버전을 낼 때 맨 위에 `## vX.Y.Z` 항목을 추가하고 같은 이름으로 태그를 푸시한다.

## v0.1.0

- 첫 버전
- 화이트보드: 라우터 · 스위치 · PC · 서버 · 이 PC · 메모 box 를 놓고 포트끼리 선 잇기, IP 자동
- 시작하면 실제로 동작: box 는 컨테이너, 선은 veth, 라우터는 FRR (자동 OSPF)
- 이 PC box 로 Windows cmd 에서 chamber 안쪽까지 ping, chamber 에서 인터넷 (NAT)
- box 콘솔 (셸 · vtysh) 과 "cmd 에서 ping" 버튼
- cobweb: 자유 라이선스 장비 이미지 받기 · 이름으로 받기 · 이 PC 의 이미지
- VcoM: VMware Workstation · VirtualBox 가상 머신 찾기 · 켜기 · 끄기 · chamber 에 놓기
- Whale 연동 (기존 컨테이너를 box 로), Boom 연동 (AWS VPC 가져오기)
