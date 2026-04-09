"""
RenderDoc Extension Installer
Copies the extension to RenderDoc's extension directory.
Supports killing stale MCP server processes and running uv sync.

Usage:
    python install_extension.py              # Install extension only
    python install_extension.py uninstall    # Uninstall extension
    python install_extension.py sync         # Kill old processes + uv sync + install extension
    python install_extension.py kill         # Kill MCP server processes only
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Process names to look for when cleaning up stale MCP server instances
MCP_PROCESS_NAMES = ["renderdoc_toolset"]


def get_extension_dirs():
    """Get possible RenderDoc extension directories.

    Windows has two layouts in the wild:
    - %APPDATA%\\qrenderdoc\\extensions   (newer/common)
    - %APPDATA%\\renderdoc\\extensions    (legacy)
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("Cannot determine APPDATA directory")

        qrenderdoc_dir = Path(appdata) / "qrenderdoc" / "extensions"
        legacy_dir = Path(appdata) / "renderdoc" / "extensions"

        # Always install to both paths to avoid version skew across RenderDoc builds.
        return [qrenderdoc_dir, legacy_dir]

    home = Path.home()
    return [home / ".local" / "share" / "qrenderdoc" / "extensions"]




def _get_process_list_powershell():
    """Get process list using PowerShell Get-CimInstance (modern Windows)."""
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ExecutablePath | "
            "ForEach-Object { \"$($_.ProcessId),$($_.ExecutablePath)\" }",
        ],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        return None

    processes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: PID,ExecutablePath
        idx = line.find(",")
        if idx < 0:
            continue
        pid_str = line[:idx].strip()
        exe_path = line[idx + 1:].strip()
        if pid_str.isdigit() and exe_path:
            processes.append((int(pid_str), exe_path))
    return processes


def _get_process_list_wmic():
    """Get process list using wmic (legacy Windows, may not be available)."""
    result = subprocess.run(
        ["wmic", "process", "get", "ProcessId,ExecutablePath", "/format:csv"],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        return None

    processes = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # CSV format: Node,ExecutablePath,ProcessId
        parts = line.split(",")
        if len(parts) < 3:
            continue
        exe_path = parts[1].strip()
        pid_str = parts[2].strip()
        if pid_str.isdigit() and exe_path:
            processes.append((int(pid_str), exe_path))
    return processes


def kill_mcp_processes():
    """Kill any running MCP server processes that belong to this project.

    On Windows, uses PowerShell Get-CimInstance (preferred) or wmic (fallback)
    to enumerate processes, then taskkill to terminate them.
    Only kills processes whose executable path is under PROJECT_ROOT.
    """
    if sys.platform != "win32":
        print("Process cleanup is currently only supported on Windows.")
        return False

    killed_any = False
    venv_scripts = PROJECT_ROOT / ".venv" / "Scripts"
    venv_python = str(venv_scripts / "python.exe").lower()

    try:
        # Try PowerShell first (works on modern Windows), fall back to wmic
        processes = None
        for getter, name in [
            (_get_process_list_powershell, "PowerShell"),
            (_get_process_list_wmic, "wmic"),
        ]:
            try:
                processes = getter()
                if processes is not None:
                    break
            except FileNotFoundError:
                continue
            except Exception:
                continue

        if processes is None:
            print("Warning: Could not enumerate processes (neither PowerShell nor wmic available).")
            return False

        pids_to_kill = []
        project_lower = str(PROJECT_ROOT).lower()

        for pid, exe_path in processes:
            exe_lower = exe_path.lower()
            # Match MCP exe or the venv python serving it
            is_mcp_exe = any(name in exe_lower for name in MCP_PROCESS_NAMES) and project_lower in exe_lower
            is_venv_python = exe_lower == venv_python

            if is_mcp_exe or is_venv_python:
                pids_to_kill.append((pid, exe_path))

        if not pids_to_kill:
            print("No running MCP server processes found.")
            return False

        for pid, exe in pids_to_kill:
            print("  Killing PID %d  (%s)" % (pid, exe))
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                )
                killed_any = True
            except Exception as e:
                print("  Warning: Failed to kill PID %d: %s" % (pid, e))

        if killed_any:
            print("Stale MCP processes terminated.")
    except Exception as e:
        print("Warning: Process cleanup failed: %s" % e)

    return killed_any


def uv_sync():
    """Run `uv sync` in the project root to reinstall the package."""
    print("\nRunning uv sync ...")
    try:
        result = subprocess.run(
            ["uv", "sync"],
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        if result.returncode == 0:
            print("uv sync completed successfully.")
        else:
            print("Warning: uv sync exited with code %d" % result.returncode)
            return False
    except FileNotFoundError:
        print("Error: 'uv' command not found. Please install uv first.")
        return False
    except Exception as e:
        print("Error running uv sync: %s" % e)
        return False
    return True


def install():
    """Install the extension"""
    # Source directory
    extension_src = PROJECT_ROOT / "renderdoc_extension"

    if not extension_src.exists():
        print("Error: Extension source not found at %s" % extension_src)
        sys.exit(1)

    # Destination directory(s)
    ext_dirs = get_extension_dirs()

    installed = []
    for ext_dir in ext_dirs:
        ext_dir.mkdir(parents=True, exist_ok=True)
        dest = ext_dir / "renderdoc_toolset_bridge"

        # Remove existing installation
        if dest.exists():
            print("Removing existing installation at %s" % dest)
            shutil.rmtree(dest)

        # Copy extension (excluding __pycache__)
        shutil.copytree(
            extension_src,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        installed.append(dest)

    for d in installed:
        print("Extension installed to %s" % d)
    print("  (__pycache__ directories excluded)")
    print("")

    print("Please restart RenderDoc and enable the extension in:")
    print("  Tools > Manage Extensions > RenderDoc renderdoc_toolset_bridge")


def uninstall():
    """Uninstall the extension"""
    ext_dirs = get_extension_dirs()
    found = False

    for ext_dir in ext_dirs:
        dest = ext_dir / "renderdoc_toolset_bridge"
        if dest.exists():
            shutil.rmtree(dest)
            print("Extension uninstalled from %s" % dest)
            found = True
        else:
            print("Extension not found at %s" % dest)

    if not found:
        print("No installed extension directory was found.")



def sync():
    """Full sync: kill stale processes -> uv sync -> install extension"""
    print("=== RenderDoc MCP Full Sync ===\n")

    print("[1/3] Killing stale MCP server processes ...")
    kill_mcp_processes()

    print("\n[2/3] Syncing Python environment ...")
    if not uv_sync():
        print("\nuv sync failed. Aborting.")
        sys.exit(1)

    print("\n[3/3] Installing RenderDoc extension ...")
    install()

    print("\n=== Done! ===")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"

    if cmd == "uninstall":
        uninstall()
    elif cmd == "sync":
        sync()
    elif cmd == "kill":
        kill_mcp_processes()
    else:
        install()
