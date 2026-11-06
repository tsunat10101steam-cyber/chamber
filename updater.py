"""GitHub 릴리스로 업데이트 확인 / 자동 설치.

릴리스에는 Chamber-Setup-vX.Y.Z.exe(설치 프로그램)와 Chamber-vX.Y.Z.zip 이 붙는다 (.github/workflows/release.yml).
설치: 대시보드 창은 바로 닫히고, 초록 진행 막대가 있는 작은 Windows 창(PowerShell + WinForms)이 떠서
설치 파일을 내려받고 → Chamber 이 꺼지면 조용히(/S) 설치하고 → Chamber 을 다시 실행한다.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from version import REPO, __version__

API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
_cache = {"t": 0.0, "data": None}


def _ver(s):
    parts = (s or "0").lstrip("vV").split("-")[0].split(".")
    nums = [int(p) if p.isdigit() else 0 for p in parts]
    return tuple(nums + [0] * (3 - len(nums)))


def _native_context():
    """Windows 가 직접 인증서를 검증 (truststore). 브라우저·curl 과 같은 방식이라 루트 인증서가 아직 안 받아졌거나
    회사·백신의 HTTPS 검사 인증서가 있어도 통과한다."""
    import truststore
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _bundled_context():
    """파이썬 TLS + Windows 저장소 + certifi CA 묶음. 체인 중간 인증서만 믿어도 되게 (Python 3.13+ 기본값과 같게)."""
    ctx = ssl.create_default_context()
    try:
        from certifi import where
        ctx.load_verify_locations(where())
    except (ImportError, OSError, ssl.SSLError):
        pass
    ctx.verify_flags |= getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    return ctx


# Chamber v1.2.0 에서 GitHub Actions(Python 3.12)로 만든 exe 가 일부 PC 에서 CERTIFICATE_VERIFY_FAILED 로
# 업데이트 확인을 못 했다. 그래서 여러 방식을 차례로 시도하고, 처음 성공한 방식을 계속 쓴다.
CONTEXTS = [("native", _native_context), ("bundled", _bundled_context), ("default", ssl.create_default_context)]
_working = {"name": None}


def _ssl_context():
    for name, make in CONTEXTS:
        if _working["name"] in (None, name):
            try:
                return make()
            except Exception:  # noqa: BLE001 — 다음 방식으로
                continue
    return ssl.create_default_context()


def _get(url, timeout=10, headers=None):
    """HTTPS GET. 인증서 검증이 실패하면 다음 검증 방식으로 다시 시도한다."""
    hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "Chamber", **(headers or {})}
    last = None
    for name, make in CONTEXTS:
        if _working["name"] and _working["name"] != name:
            continue
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=timeout, context=make())
            _working["name"] = name
            return r
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # noqa: BLE001 — SSL 오류 등: 다음 방식으로
            last = e
            if _working["name"] == name:  # 잘 되던 방식이 갑자기 실패하면 처음부터 다시
                _working["name"] = None
                return _get(url, timeout, headers)
    raise last if isinstance(last, (urllib.error.URLError, OSError)) else urllib.error.URLError(str(last))


def tls_diag(url="https://api.github.com/repos/" + REPO + "/releases/latest"):
    """방식별로 GitHub 접속이 되는지 (문제가 생긴 PC 에서 원인 확인용)."""
    import platform
    out = {"python": platform.python_version(), "openssl": ssl.OPENSSL_VERSION, "using": _working["name"], "tries": {}}
    for name, make in CONTEXTS:
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Chamber"}), timeout=8,
                                   context=make()).close()
            out["tries"][name] = "ok"
        except Exception as e:  # noqa: BLE001
            out["tries"][name] = f"{type(e).__name__}: {e}"[:200]
    return out


def check(force=False):
    """최신 릴리스 확인 (10분 캐시). GitHub API 비로그인 한도는 시간당 60회."""
    if not force and _cache["data"] and time.time() - _cache["t"] < 600:
        return _cache["data"]
    data = {"current": __version__, "available": False, "url": RELEASES_URL}
    try:
        with _get(API) as r:
            rel = json.load(r)
        # 설치 프로그램(Chamber-Setup-x.exe)을 우선, 없으면 zip
        assets = rel.get("assets", [])
        setup = next((a for a in assets
                      if a["name"].lower().startswith("chamber-setup") and a["name"].lower().endswith(".exe")), None)
        zipped = next((a for a in assets if a["name"].lower().endswith(".zip")), None)
        asset = setup or zipped
        latest = rel.get("tag_name", "").lstrip("vV")
        data.update(latest=latest, notes=rel.get("body") or "", url=rel.get("html_url") or RELEASES_URL,
                    published=rel.get("published_at"), asset=asset["browser_download_url"] if asset else None,
                    kind="setup" if setup else "zip",
                    available=bool(asset) and _ver(latest) > _ver(__version__))
    except urllib.error.HTTPError as e:
        data["error"], data["error_params"] = ("no_release", {}) if e.code == 404 else ("gh_status", {"code": e.code})
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        data["error"], data["error_params"] = "check_failed", {"detail": str(e)}
    _cache.update(t=time.time(), data=data)
    return data


def install_dir():
    """지금 실행 중인 Chamber.exe 폴더. 개발 모드(python app.py)면 None."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return None
    d = Path(sys.executable).resolve().parent
    # 엉뚱한 폴더를 덮어쓰지 않도록, Chamber 설치 폴더 모양일 때만
    return d if (d / "Chamber.exe").exists() and (d / "_internal").is_dir() else None


# 업데이트 진행 창 (PowerShell + WinForms). __이름__ 자리는 launch_update_window() 가 채운다.
# 내려받기는 Timer 가 UI 스레드에서 60ms 씩 나눠 읽어서, 스레드 없이도 창이 멈추지 않는다.
UPDATE_WINDOW = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -Namespace ChamberUpd -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[ChamberUpd.Dpi]::SetProcessDPIAware() | Out-Null
[Windows.Forms.Application]::EnableVisualStyles()
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Url = '__URL__'; $Kind = '__KIND__'; $Dest = '__DEST__'; $WaitPid = __PID__; $Relaunch = $__RELAUNCH__
$L = @{ Title = '__TITLE__'; Downloading = '__DOWNLOADING__'; Installing = '__INSTALLING__'; Failed = '__FAILED__'; Close = '__CLOSE__' }
$Tmp = Join-Path $env:TEMP ('chamber-update-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Tmp | Out-Null
if ($Kind -eq 'zip') { $File = Join-Path $Tmp 'Chamber.zip' } else { $File = Join-Path $Tmp 'Chamber-Setup.exe' }

$g = [Drawing.Graphics]::FromHwnd([IntPtr]::Zero); $k = $g.DpiX / 96; $g.Dispose()
function S([double]$v) { [int]($v * $k) }

$form = New-Object Windows.Forms.Form
$form.Text = $L.Title
$form.Font = New-Object Drawing.Font('Segoe UI', 9)
$form.ClientSize = New-Object Drawing.Size((S 440), (S 132))
$form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false; $form.MinimizeBox = $false
$form.StartPosition = 'CenterScreen'; $form.TopMost = $true
try { $form.Icon = [Drawing.Icon]::ExtractAssociatedIcon((Join-Path $Dest 'Chamber.exe')) } catch {}
$label = New-Object Windows.Forms.Label; $label.SetBounds((S 18), (S 16), (S 404), (S 22)); $label.Text = $L.Downloading
$bar = New-Object Windows.Forms.ProgressBar; $bar.SetBounds((S 18), (S 44), (S 404), (S 24)); $bar.Maximum = 1000; $bar.Style = 'Continuous'
$info = New-Object Windows.Forms.Label; $info.SetBounds((S 18), (S 78), (S 310), (S 44)); $info.ForeColor = [Drawing.Color]::DimGray
$btn = New-Object Windows.Forms.Button; $btn.SetBounds((S 338), (S 92), (S 84), (S 28)); $btn.Text = $L.Close; $btn.Visible = $false
$btn.Add_Click({ $form.Close() })
$form.Controls.AddRange(@($label, $bar, $info, $btn))

$st = @{ Phase = 'connect'; Resp = $null; In = $null; Out = $null; Total = 0; Done = 0; Proc = $null }
$buf = New-Object byte[] 262144
$timer = New-Object Windows.Forms.Timer; $timer.Interval = 30

function Close-Streams { foreach ($x in 'Out', 'In', 'Resp') { if ($st[$x]) { try { $st[$x].Close() } catch {} ; $st[$x] = $null } } }
function Fail([string]$msg) {
  $timer.Stop(); Close-Streams
  $label.Text = $L.Failed; $info.Text = $msg; $bar.Style = 'Continuous'; $bar.Value = 0; $btn.Visible = $true
  Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}

$timer.Add_Tick({
  try {
    switch ($st.Phase) {
      'connect' {
        $req = [Net.HttpWebRequest]::Create($Url); $req.UserAgent = 'Chamber'
        $st.Resp = $req.GetResponse(); $st.Total = $st.Resp.ContentLength
        $st.In = $st.Resp.GetResponseStream(); $st.Out = [IO.File]::Create($File); $st.Phase = 'download'
      }
      'download' {
        $sw = [Diagnostics.Stopwatch]::StartNew()
        while ($sw.ElapsedMilliseconds -lt 60) {
          $n = $st.In.Read($buf, 0, $buf.Length)
          if ($n -le 0) {
            Close-Streams
            $bar.Value = 1000; $label.Text = $L.Installing; $info.Text = ''; $bar.Style = 'Marquee'
            $st.Phase = 'wait'; return
          }
          $st.Out.Write($buf, 0, $n); $st.Done += $n
        }
        if ($st.Total -gt 0) { $bar.Value = [Math]::Min(1000, [int](1000 * $st.Done / $st.Total)) }
        $info.Text = '{0:N1} MB / {1:N1} MB' -f ($st.Done / 1MB), ($st.Total / 1MB)
      }
      'wait' {
        # 대시보드(Chamber)가 완전히 꺼진 뒤에 설치
        if (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { return }
        if ($Kind -eq 'zip') {
          $x = Join-Path $Tmp 'x'; Expand-Archive -Path $File -DestinationPath $x -Force
          $exe = Get-ChildItem -Path $x -Recurse -Filter 'Chamber.exe' | Select-Object -First 1
          if (-not $exe) { throw 'Chamber.exe not found in the update' }
          robocopy $exe.DirectoryName $Dest /mir /njh /njs /nfl /ndl /r:10 /w:1 | Out-Null
          if ($LASTEXITCODE -ge 8) { throw "robocopy $LASTEXITCODE" }
          $st.Phase = 'launch'
        } else {
          # NSIS: /D 는 따옴표 없이 맨 마지막
          $st.Proc = Start-Process -FilePath $File -ArgumentList '/S', "/D=$Dest" -PassThru
          $st.Phase = 'install'
        }
      }
      'install' {
        if (-not $st.Proc.HasExited) { return }
        if ($st.Proc.ExitCode -ne 0) { throw "setup exit code $($st.Proc.ExitCode)" }
        $st.Phase = 'launch'
      }
      'launch' {
        $timer.Stop()
        if ($Relaunch) { Start-Process -FilePath (Join-Path $Dest 'Chamber.exe') }
        Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
        $form.Close()
      }
    }
  } catch { Fail $_.Exception.Message }
})
$form.Add_Shown({ $timer.Start() })
[Windows.Forms.Application]::Run($form)
"""


def _ps_str(v):
    return str(v).replace("'", "''")


def launch_update_window(asset_url, kind, dest, pid, labels, relaunch=True):
    """초록 진행 막대 창을 띄운다. pid(지금 Chamber)가 꺼지면 설치하고 다시 실행한다."""
    script = UPDATE_WINDOW
    values = {"URL": asset_url, "KIND": kind, "DEST": dest, "TITLE": labels.get("title", "Chamber"),
              "DOWNLOADING": labels.get("downloading", "Downloading..."),
              "INSTALLING": labels.get("installing", "Installing..."),
              "FAILED": labels.get("failed", "Update failed"), "CLOSE": labels.get("close", "Close")}
    for key, v in values.items():
        script = script.replace(f"__{key}__", _ps_str(v))
    script = script.replace("__PID__", str(int(pid))).replace("__RELAUNCH__", "true" if relaunch else "false")
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    # 콘솔 창은 숨기고(CREATE_NO_WINDOW) 진행 창만 보이게. Chamber 이 꺼져도 계속 살아 있도록 별도 프로세스 그룹
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", enc],
                            creationflags=flags, close_fds=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
