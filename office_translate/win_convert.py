"""Windows 平台上的 .xls → .xlsx 自动转换（PowerShell COM）。

策略：
- 在 Windows 上运行 init 且输入为 .xls 时，若检测到 Excel 可用，
  调用 PowerShell 的 Excel COM 对象自动转换为 .xlsx（保真度最高）。
- 若 Windows 上无 Excel，或非 Windows 平台，不自动转换，
  由调用方提示用户手动转换（见 README「手动转换」一节）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _excel_powershell_script(src: str, dst: str) -> str:
    """生成调用 Excel COM 转换的 PowerShell 脚本。"""
    return (
        "$ErrorActionPreference = 'Stop';"
        "try {"
        f"$excel = New-Object -ComObject Excel.Application;"
        "$excel.DisplayAlerts = $false;"
        f"$wb = $excel.Workbooks.Open('{src}');"
        f"$wb.SaveAs('{dst}', 51);"  # 51 = xlOpenXMLWorkbook (.xlsx)
        "$wb.Close($false);"
        "$excel.Quit();"
        "Write-Output 'OK';"
        "} catch {"
        "if ($excel) { $excel.Quit() };"
        "Write-Error $_;"
        "}"
    )


def _run_powershell(script: str) -> tuple[int, str]:
    """在 Windows 上执行 PowerShell 脚本，返回 (退出码, 输出)。"""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def can_convert() -> bool:
    """判断当前平台是否具备自动转换能力（Windows + 有 PowerShell）。"""
    if not _is_windows():
        return False
    return shutil.which("powershell") is not None


def convert_xls_to_xlsx(src: str, dst: str) -> None:
    """把 .xls 转换为 .xlsx（调用 Excel COM）。失败抛 OSError。"""
    if not _is_windows():
        raise OSError("自动转换仅在 Windows 上可用。")
    if not os.path.isfile(src):
        raise OSError(f"源文件不存在: {src}")
    script = _excel_powershell_script(src, dst)
    code, out = _run_powershell(script)
    if code != 0 or not os.path.isfile(dst):
        raise OSError(f"Excel 自动转换失败（{code}）: {out}")


def manual_convert_instructions() -> str:
    """返回给用户的「手动转换」操作步骤文案。"""
    return (
        "\n当前环境无法自动把 .xls 转换为 .xlsx，请手动转换后重试：\n"
        "  1. 用 Excel（或 WPS）打开该 .xls 文件\n"
        "  2. 菜单「文件 → 另存为」，格式选择「Excel 工作簿 (*.xlsx)」\n"
        "  3. 保存后，把转换出的 .xlsx 路径重新作为输入传给 init\n"
    )


def maybe_convert(src_path: str) -> Optional[str]:
    """init 的辅助入口：若输入是 .xls 且可自动转换，则转换并返回 xlsx 路径；
    否则返回 None（调用方据此提示手动转换）。"""
    ext = os.path.splitext(src_path)[1].lower()
    if ext != ".xls":
        return None
    if can_convert():
        dst = src_path[:-4] + ".xlsx"  # 同目录同名 .xlsx
        convert_xls_to_xlsx(src_path, dst)
        return dst
    return None
