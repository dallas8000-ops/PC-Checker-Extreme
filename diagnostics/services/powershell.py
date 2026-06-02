"""Run PowerShell scripts reliably on Windows (full path to powershell.exe)."""
import os
import shutil
import subprocess
import sys

_POWERSHELL_EXE: str | None = None


def get_powershell_executable() -> str:
    """Resolve powershell.exe — avoids WinError 2 when PATH omits System32."""
    global _POWERSHELL_EXE
    if _POWERSHELL_EXE and os.path.isfile(_POWERSHELL_EXE):
        return _POWERSHELL_EXE

    if sys.platform != "win32":
        _POWERSHELL_EXE = "powershell"
        return _POWERSHELL_EXE

    system_root = os.environ.get("SystemRoot") or r"C:\Windows"
    candidates = [
        os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"),
        os.path.join(system_root, "Sysnative", "WindowsPowerShell", "v1.0", "powershell.exe"),
        shutil.which("powershell.exe"),
        shutil.which("powershell"),
        shutil.which("pwsh.exe"),
        shutil.which("pwsh"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            _POWERSHELL_EXE = os.path.normpath(path)
            return _POWERSHELL_EXE

    _POWERSHELL_EXE = "powershell.exe"
    return _POWERSHELL_EXE


def run_powershell(script: str, timeout: int = 90) -> tuple[str, str, int]:
    """Run a PowerShell script; returns (stdout, stderr, returncode). -1 on timeout."""
    exe = get_powershell_executable()
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        return result.stdout or "", result.stderr or "", result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timed out after {timeout}s", -1
    except FileNotFoundError as exc:
        return "", str(exc), -1


def run_powershell_stdout(script: str, timeout: int = 90) -> str:
    """Run script and return stdout only (empty string on failure)."""
    stdout, stderr, code = run_powershell(script, timeout=timeout)
    if code == -1 and not stdout.strip():
        return ""
    if code != 0 and not stdout.strip():
        return ""
    return stdout.strip()
