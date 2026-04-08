#!/usr/bin/env python3
"""
CraftBot Service Manager

Run CraftBot as a background process that survives terminal closure,
and optionally register it to auto-start when your system boots.

Commands:
    python service.py start [options]    Start CraftBot in background
    python service.py stop               Stop CraftBot
    python service.py restart [options]  Stop then start
    python service.py status             Show if CraftBot is running
    python service.py logs [-n N]        Show last N log lines (default: 50)
    python service.py install [options]  Register for auto-start on boot/login
    python service.py uninstall          Remove auto-start registration

Options passed to 'start' / 'install':
    --tui                   Run in TUI mode instead of browser
    --cli                   Run in CLI mode
    --no-open-browser       Don't open browser automatically (default for service)
    --frontend-port PORT    Frontend port (default: 7925)
    --backend-port PORT     Backend port (default: 7926)
    --conda                 Use conda environment
    --no-conda              Don't use conda

Examples:
    python service.py start                   # Start in background (browser mode)
    python service.py start --tui             # Start in background (TUI mode)
    python service.py install                 # Auto-start on login (browser mode)
    python service.py install --no-open-browser  # Auto-start without opening browser
    python service.py stop
    python service.py logs -n 100
"""
import os
import sys
import signal
import subprocess
import time
from typing import List, Optional

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_SCRIPT = os.path.join(BASE_DIR, "run.py")
PID_FILE = os.path.join(BASE_DIR, "craftbot.pid")
LOG_FILE = os.path.join(BASE_DIR, "craftbot.log")

TASK_NAME = "CraftBot"          # Windows Task Scheduler task name
SYSTEMD_SERVICE = "craftbot"    # Linux systemd service name
LAUNCHD_LABEL = "com.craftbot.agent"  # macOS launchd label
BROWSER_URL = "http://localhost:7925"
SHORTCUT_NAME = "CraftBot.url"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _python_exe() -> str:
    """Return the Python executable to use for the service process."""
    # On Windows prefer pythonw.exe (no console window) when not in TUI/CLI mode
    if sys.platform == "win32":
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.isfile(pythonw):
            return pythonw
    return sys.executable


def _read_pid() -> Optional[int]:
    """Read PID from the PID file. Returns None if file missing or invalid."""
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _write_pid(pid: int) -> None:
    with open(PID_FILE, "w") as f:
        f.write(str(pid))


def _remove_pid() -> None:
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def _is_running(pid: int) -> bool:
    """Return True if a process with the given PID is currently alive."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def _build_run_args(extra: List[str], service_mode: bool = True) -> List[str]:
    """Build the argument list for run.py.

    Adds --no-open-browser by default in service mode (auto-start at boot
    should not pop open a browser without the user asking).
    """
    args = list(extra)
    # TUI/CLI modes don't use the browser flag
    if service_mode and "--tui" not in args and "--cli" not in args:
        if "--no-open-browser" not in args:
            args.append("--no-open-browser")
    return args


# ─── Core operations ──────────────────────────────────────────────────────────

def cmd_start(extra_args: List[str]) -> None:
    """Start CraftBot as a detached background process."""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"CraftBot is already running (PID {pid}).")
        print(f"Use 'python service.py stop' to stop it first.")
        return

    run_args = _build_run_args(extra_args)
    python = _python_exe()

    # Use plain python.exe for TUI/CLI because pythonw has no console
    if "--tui" in run_args or "--cli" in run_args:
        python = sys.executable

    cmd = [python, RUN_SCRIPT] + run_args

    log_fh = open(LOG_FILE, "a")
    log_fh.write(f"\n{'='*60}\n")
    log_fh.write(f"CraftBot service started at {_timestamp()}\n")
    log_fh.write(f"Command: {' '.join(cmd)}\n")
    log_fh.write(f"{'='*60}\n")
    log_fh.flush()

    kwargs = dict(
        cwd=BASE_DIR,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )

    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        CREATE_NO_WINDOW = 0x08000000
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError as e:
        print(f"Error: Could not launch CraftBot — {e}")
        return

    _write_pid(proc.pid)
    print(f"CraftBot started in background (PID {proc.pid}).")
    print(f"Logs: {LOG_FILE}")
    if "--tui" not in run_args and "--cli" not in run_args:
        print(f"\nBrowser interface: {BROWSER_URL}")
        print(f"  Tip: Bookmark {BROWSER_URL} so you never have to remember it!")
        if "--no-open-browser" in run_args:
            print("  (Browser will NOT open automatically — open it manually)")


def cmd_stop() -> None:
    """Stop the running CraftBot service."""
    pid = _read_pid()
    if pid is None:
        print("CraftBot does not appear to be running (no PID file found).")
        return

    if not _is_running(pid):
        print(f"CraftBot (PID {pid}) is not running. Cleaning up stale PID file.")
        _remove_pid()
        return

    print(f"Stopping CraftBot (PID {pid})...")

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True, timeout=15,
            )
        except Exception as e:
            print(f"Warning: taskkill failed — {e}")
    else:
        try:
            # Kill the entire process group so child processes also die
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            # Give it a moment to exit gracefully
            for _ in range(10):
                time.sleep(0.5)
                if not _is_running(pid):
                    break
            else:
                os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            print(f"Warning: {e}")

    _remove_pid()
    print("CraftBot stopped.")


def cmd_status() -> None:
    """Print whether CraftBot is currently running."""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"CraftBot is RUNNING (PID {pid}).")
        print(f"Logs: {LOG_FILE}")
    else:
        if pid:
            _remove_pid()
        print("CraftBot is NOT running.")


def cmd_logs(n: int = 50) -> None:
    """Print the last N lines of the CraftBot log."""
    if not os.path.isfile(LOG_FILE):
        print(f"No log file found at {LOG_FILE}")
        return
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        print(f"--- Last {len(tail)} lines of {LOG_FILE} ---")
        print("".join(tail), end="")
    except Exception as e:
        print(f"Error reading log: {e}")


def cmd_restart(extra_args: List[str]) -> None:
    cmd_stop()
    time.sleep(1)
    cmd_start(extra_args)


# ─── Desktop shortcut ─────────────────────────────────────────────────────────

def _find_desktop() -> Optional[str]:
    """Return the path to the user's Desktop folder, or None if not found."""
    for candidate in [
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return None


def _create_desktop_shortcut_windows() -> None:
    """Create a .url shortcut on the Windows Desktop."""
    desktop = _find_desktop()
    if not desktop:
        return
    shortcut_path = os.path.join(desktop, SHORTCUT_NAME)
    try:
        with open(shortcut_path, "w") as f:
            f.write(f"[InternetShortcut]\nURL={BROWSER_URL}\n")
        print(f"  Desktop shortcut created: {shortcut_path}")
        print(f"  Double-click it anytime to open CraftBot in your browser.")
    except Exception as e:
        print(f"  (Could not create desktop shortcut: {e})")


def _create_desktop_shortcut_unix() -> None:
    """Create a .desktop shortcut on Linux/macOS Desktop."""
    desktop = _find_desktop()
    if not desktop:
        return
    shortcut_path = os.path.join(desktop, "CraftBot.desktop")
    try:
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=CraftBot\n"
            f"Exec=xdg-open {BROWSER_URL}\n"
            "Icon=web-browser\n"
            "Terminal=false\n"
        )
        with open(shortcut_path, "w") as f:
            f.write(content)
        os.chmod(shortcut_path, 0o755)
        print(f"  Desktop shortcut created: {shortcut_path}")
        print(f"  Double-click it anytime to open CraftBot in your browser.")
    except Exception as e:
        print(f"  (Could not create desktop shortcut: {e})")


# ─── Auto-start: Windows Task Scheduler ───────────────────────────────────────

def _install_windows(run_args: List[str]) -> None:
    python = _python_exe()
    # Build the task action string
    # Wrap paths in quotes to handle spaces
    action = f'"{python}" "{RUN_SCRIPT}" {" ".join(run_args)}'

    # Create a scheduled task that runs at logon for this user
    cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", action,
        "/sc", "ONLOGON",
        "/ru", os.environ.get("USERNAME", ""),
        "/f",  # overwrite if exists
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"Auto-start registered in Windows Task Scheduler (task: '{TASK_NAME}').")
            print("CraftBot will start automatically the next time you log in.")
            print(f"\nOpen CraftBot: {BROWSER_URL}")
            print(f"  Tip: Bookmark {BROWSER_URL} so you never have to remember it!")
            _create_desktop_shortcut_windows()
        else:
            print(f"Failed to register task:\n{result.stderr.strip()}")
            print("\nTry running this command manually as Administrator:")
            print(f"  schtasks /create /tn \"{TASK_NAME}\" /tr \"{action}\" /sc ONLOGON /f")
    except FileNotFoundError:
        print("Error: schtasks not found. Are you on Windows?")
    except subprocess.TimeoutExpired:
        print("Error: schtasks timed out.")


def _uninstall_windows() -> None:
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            print(f"Auto-start removed (task '{TASK_NAME}' deleted).")
        else:
            # Task may not exist
            print(f"Could not remove task (it may not be registered): {result.stderr.strip()}")
    except Exception as e:
        print(f"Error: {e}")


# ─── Auto-start: Linux systemd (user service) ─────────────────────────────────

def _install_linux(run_args: List[str]) -> None:
    service_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(service_dir, exist_ok=True)

    service_file = os.path.join(service_dir, f"{SYSTEMD_SERVICE}.service")
    python = sys.executable
    exec_start = f"{python} {RUN_SCRIPT} {' '.join(run_args)}"

    content = f"""[Unit]
Description=CraftBot AI Agent
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
WorkingDirectory={BASE_DIR}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    with open(service_file, "w") as f:
        f.write(content)

    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, timeout=10)
        subprocess.run(["systemctl", "--user", "enable", SYSTEMD_SERVICE], check=True, timeout=10)
        print(f"Auto-start registered as systemd user service '{SYSTEMD_SERVICE}'.")
        print("CraftBot will start automatically when you log in.")
        print(f"\nOpen CraftBot: {BROWSER_URL}")
        print(f"  Tip: Bookmark {BROWSER_URL} so you never have to remember it!")
        _create_desktop_shortcut_unix()
        print(f"\nTo start it now: systemctl --user start {SYSTEMD_SERVICE}")
        print(f"To view logs:    journalctl --user -u {SYSTEMD_SERVICE} -f")
    except subprocess.CalledProcessError as e:
        print(f"Error enabling systemd service: {e}")
        print(f"Service file written to: {service_file}")
        print("Try manually: systemctl --user daemon-reload && systemctl --user enable craftbot")
    except FileNotFoundError:
        print("systemctl not found. Is systemd running on this system?")


def _uninstall_linux() -> None:
    service_file = os.path.expanduser(f"~/.config/systemd/user/{SYSTEMD_SERVICE}.service")
    try:
        subprocess.run(["systemctl", "--user", "disable", SYSTEMD_SERVICE], capture_output=True, timeout=10)
        subprocess.run(["systemctl", "--user", "stop", SYSTEMD_SERVICE], capture_output=True, timeout=10)
    except Exception:
        pass
    if os.path.isfile(service_file):
        os.remove(service_file)
        print(f"Auto-start removed (service file deleted).")
    else:
        print("No systemd service file found.")
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=10)
    except Exception:
        pass


# ─── Auto-start: macOS launchd ────────────────────────────────────────────────

def _install_macos(run_args: List[str]) -> None:
    agents_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(agents_dir, exist_ok=True)

    plist_file = os.path.join(agents_dir, f"{LAUNCHD_LABEL}.plist")
    python = sys.executable
    program_args = [python, RUN_SCRIPT] + run_args
    program_args_xml = "\n".join(f"        <string>{a}</string>" for a in program_args)

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{program_args_xml}
    </array>
    <key>WorkingDirectory</key>
    <string>{BASE_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
</dict>
</plist>
"""
    with open(plist_file, "w") as f:
        f.write(content)

    try:
        subprocess.run(["launchctl", "load", plist_file], check=True, timeout=10)
        print(f"Auto-start registered as launchd agent '{LAUNCHD_LABEL}'.")
        print("CraftBot will start automatically when you log in.")
        print(f"\nOpen CraftBot: {BROWSER_URL}")
        print(f"  Tip: Bookmark {BROWSER_URL} so you never have to remember it!")
        _create_desktop_shortcut_unix()
        print(f"\nPlist file: {plist_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error loading launchd agent: {e}")
        print(f"Plist written to: {plist_file}")
        print(f"Try manually: launchctl load {plist_file}")


def _uninstall_macos() -> None:
    plist_file = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist")
    if os.path.isfile(plist_file):
        try:
            subprocess.run(["launchctl", "unload", plist_file], capture_output=True, timeout=10)
        except Exception:
            pass
        os.remove(plist_file)
        print("Auto-start removed.")
    else:
        print("No launchd agent found.")


# ─── Install / Uninstall dispatch ─────────────────────────────────────────────

def cmd_install(extra_args: List[str]) -> None:
    """Register CraftBot to auto-start when the system boots / user logs in."""
    run_args = _build_run_args(extra_args, service_mode=True)
    plat = sys.platform
    if plat == "win32":
        _install_windows(run_args)
    elif plat == "darwin":
        _install_macos(run_args)
    else:
        _install_linux(run_args)


def cmd_uninstall() -> None:
    """Remove auto-start registration."""
    plat = sys.platform
    if plat == "win32":
        _uninstall_windows()
    elif plat == "darwin":
        _uninstall_macos()
    else:
        _uninstall_linux()


# ─── Utility ──────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _usage() -> None:
    print(__doc__)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        _usage()
        return

    command = args[0]
    rest = args[1:]

    if command == "start":
        cmd_start(rest)

    elif command == "stop":
        cmd_stop()

    elif command == "restart":
        cmd_restart(rest)

    elif command == "status":
        cmd_status()

    elif command == "logs":
        n = 50
        if "-n" in rest:
            idx = rest.index("-n")
            try:
                n = int(rest[idx + 1])
            except (IndexError, ValueError):
                print("Warning: invalid -n value, using 50")
        cmd_logs(n)

    elif command == "install":
        cmd_install(rest)

    elif command == "uninstall":
        cmd_uninstall()

    else:
        print(f"Unknown command: '{command}'")
        print("Run 'python service.py --help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
