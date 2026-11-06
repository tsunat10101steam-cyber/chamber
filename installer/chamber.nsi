; Chamber 설치 프로그램 (NSIS)
;   makensis /DVERSION=0.1.0 installer\chamber.nsi   →  dist\Chamber-Setup-0.1.0.exe
; dist\Chamber (PyInstaller 결과)을 사용자 폴더(%LOCALAPPDATA%\Programs\Chamber)에 설치한다.
; 관리자 권한이 필요 없어서(UAC 창 없음) 앱 안의 자동 업데이트가 /S 로 조용히 다시 설치할 수 있다.

Unicode true
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!define APP "Chamber"
!define PUBLISHER "tsunat10101steam-cyber"
!define URL "https://github.com/tsunat10101steam-cyber/chamber"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chamber"

Name "${APP}"
OutFile "..\dist\Chamber-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\Chamber"
RequestExecutionLevel user
BrandingText "${APP} ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=0 "ProductName" "${APP}"
VIAddVersionKey /LANG=0 "CompanyName" "${PUBLISHER}"
VIAddVersionKey /LANG=0 "FileDescription" "${APP} Setup"
VIAddVersionKey /LANG=0 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=0 "LegalCopyright" "${PUBLISHER}"

!include "MUI2.nsh"
!define MUI_ICON "..\app.ico"
!define MUI_UNICON "..\app.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Chamber.exe"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Windows 표시 언어에 맞춰 자동으로 고른다 (설치 화면 언어)
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "TradChinese"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Spanish"

Section "Chamber"
  ; 실행 중인 Chamber 은 닫고 설치 (업데이트할 때 파일이 잠겨 있지 않게)
  nsExec::Exec 'taskkill /im Chamber.exe /f'
  Sleep 500
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\_internal"
  File /r "..\dist\Chamber\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateShortcut "$SMPROGRAMS\Chamber.lnk" "$INSTDIR\Chamber.exe"
  CreateShortcut "$DESKTOP\Chamber.lnk" "$INSTDIR\Chamber.exe"

  ; 설정 → 앱 목록에 표시 (제거 가능)
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "${UNINST_KEY}" "URLInfoAbout" "${URL}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\Chamber.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  nsExec::Exec 'taskkill /im Chamber.exe /f'
  Sleep 500
  Delete "$SMPROGRAMS\Chamber.lnk"
  Delete "$DESKTOP\Chamber.lnk"
  ; 설치 폴더를 사용자가 바꿨을 수 있으니 통째로 지우지 않고 Chamber 파일만 지운다
  Delete "$INSTDIR\Chamber.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR\_internal"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
  ; 앱 창 프로필(%LOCALAPPDATA%\Chamber)은 지우지 않는다 (다시 설치하면 설정을 그대로 이어서 사용)
SectionEnd
