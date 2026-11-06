"""version.py → build/version_info.txt (PyInstaller --version-file 용).

Chamber.exe 속성 → 자세히 탭에 제품 이름·버전·게시자(CompanyName)가 보이게 한다.
"작성자를 알 수 없음" 경고는 코드 서명이 있어야 없어지고, 이 정보만으로는 사라지지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from version import REPO, __version__  # noqa: E402

nums = [int(x) for x in __version__.split(".")] + [0]
nums = (nums + [0, 0, 0, 0])[:4]
publisher = REPO.split("/")[0]
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(nums)}, prodvers={tuple(nums)}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{publisher}'),
      StringStruct('FileDescription', 'Chamber - Network lab on Docker'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'Chamber'),
      StringStruct('LegalCopyright', '{publisher}'),
      StringStruct('OriginalFilename', 'Chamber.exe'),
      StringStruct('ProductName', 'Chamber'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(text, encoding="utf-8")
print(out)
