@echo off
rem Builds Chamber.exe (and Chamber-Setup-x.exe if NSIS is installed),
rem installs Chamber to %LOCALAPPDATA%\Programs\Chamber and creates Desktop + Start menu shortcuts.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller || exit /b 1
.venv\Scripts\python tools\version_info.py || exit /b 1

.venv\Scripts\python -m PyInstaller --noconfirm --clean --windowed --name Chamber ^
  --icon app.ico --version-file build\version_info.txt --add-data "static;static" --add-data "app.ico;." app.py || exit /b 1

rem Setup (optional): needs NSIS (https://nsis.sourceforge.io)
set "MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if exist "%MAKENSIS%" (
  for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" version.py') do set "VER=%%~v"
  setlocal enabledelayedexpansion
  set "VER=!VER: =!"
  set "VER=!VER:"=!"
  "%MAKENSIS%" /V2 /DVERSION=!VER! installer\chamber.nsi && echo Setup: dist\Chamber-Setup-!VER!.exe
  endlocal
)

set "DEST=%LOCALAPPDATA%\Programs\Chamber"
taskkill /im Chamber.exe /f >nul 2>&1
robocopy dist\Chamber "%DEST%" /mir /xf Uninstall.exe /njh /njs /nfl /ndl >nul
if errorlevel 8 exit /b 1

powershell -NoProfile -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'))) {" ^
  "  $l = $s.CreateShortcut((Join-Path $d 'Chamber.lnk'));" ^
  "  $l.TargetPath = '%DEST%\Chamber.exe'; $l.WorkingDirectory = '%DEST%';" ^
  "  $l.IconLocation = '%DEST%\Chamber.exe,0'; $l.Description = 'Network lab on Docker'; $l.Save();" ^
  "  Write-Host ('shortcut: ' + $d + '\Chamber.lnk') }"

echo Installed: %DEST%\Chamber.exe
