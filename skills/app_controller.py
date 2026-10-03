"""
app_controller.py - Application Controller Skill for CHOTU AI Assistant
========================================================================
Provides system-level controls: launching/closing apps, screenshots,
clipboard management, volume control, wallpaper setting, and more.
All operations target Windows; graceful fallbacks are included.
"""

import ctypes
import logging
import os
import pathlib
import subprocess
import sys
import time
import webbrowser
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not installed. Some features will be limited.")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not installed. Screenshot feature will be unavailable.")

try:
    import win32clipboard
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("pywin32 not installed. Clipboard features will use subprocess fallback.")

# ---------------------------------------------------------------------------
# Application name → executable mappings
# ---------------------------------------------------------------------------
APP_MAP = {
    # Browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "browser": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    # Editors / IDEs
    "notepad": "notepad.exe",
    "notepad++": "notepad++.exe",
    "vscode": "code.exe",
    "vs code": "code.exe",
    "visual studio code": "code.exe",
    # Office
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    # System utilities
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "registry": "regedit.exe",
    "snipping tool": "SnippingTool.exe",
    # Terminals
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "cmd.exe",
    "powershell": "powershell.exe",
    "windows terminal": "wt.exe",
    # Media
    "vlc": "vlc.exe",
    "media player": "wmplayer.exe",
    "windows media player": "wmplayer.exe",
    "spotify": "Spotify.exe",
    # Productivity
    "teams": "Teams.exe",
    "microsoft teams": "Teams.exe",
    "zoom": "Zoom.exe",
    "discord": "Discord.exe",
    "slack": "slack.exe",
    # Other
    "steam": "steam.exe",
    "obs": "obs64.exe",
    "7zip": "7zFM.exe",
}

# Common installation directories to search for executables
SEARCH_DIRS: List[str] = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    os.path.expandvars(r"%LOCALAPPDATA%"),
    os.path.expandvars(r"%APPDATA%"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
    r"C:\Windows",
    r"C:\Windows\System32",
]


class AppController:
    """
    System-level application controller for the CHOTU AI assistant.

    Supports launching/closing applications, screenshots, clipboard I/O,
    volume control, URL opening, screen locking, shutdown scheduling,
    wallpaper changes, and screen resolution queries on Windows.
    """

    def __init__(self) -> None:
        """Initialise the AppController."""
        logger.info("AppController skill initialised.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_exe(app_name: str) -> Optional[str]:
        """
        Resolve a human-readable app name to an executable path.

        Checks:
        1. Direct mapping via :data:`APP_MAP`.
        2. If the name itself ends with ``.exe``, treat it as the executable.
        3. Search common installation directories for a matching ``.exe``.

        Args:
            app_name: Lowercase application name or path.

        Returns:
            Resolved executable name/path, or ``None`` if not found.
        """
        normalised = app_name.strip().lower()

        # 1. Exact mapping
        if normalised in APP_MAP:
            return APP_MAP[normalised]

        # 2. Treat as raw executable
        if normalised.endswith(".exe"):
            return app_name.strip()

        # 3. Fuzzy-match the map
        for key, exe in APP_MAP.items():
            if normalised in key or key in normalised:
                return exe

        # 4. Search common directories
        exe_candidate = app_name.strip()
        if not exe_candidate.endswith(".exe"):
            exe_candidate += ".exe"
        for directory in SEARCH_DIRS:
            for root, _dirs, files in os.walk(directory):
                for fname in files:
                    if fname.lower() == exe_candidate.lower():
                        return os.path.join(root, fname)

        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def launch_app(self, app_name: str) -> bool:
        """
        Launch an application by its common name or executable path.

        Args:
            app_name: Application name (e.g. ``"chrome"``) or full path.

        Returns:
            ``True`` if the process was started successfully, ``False`` otherwise.
        """
        if not app_name.strip():
            logger.warning("launch_app called with empty app_name.")
            return False

        exe = self._resolve_exe(app_name)
        if exe is None:
            logger.error("Could not resolve executable for: %s", app_name)
            return False

        try:
            logger.info("Launching: %s", exe)
            subprocess.Popen(  # noqa: S603
                exe,
                shell=True,  # noqa: S602
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)  # brief wait so caller can check state
            return True
        except (FileNotFoundError, PermissionError, OSError) as exc:
            logger.error("Failed to launch '%s': %s", exe, exc)
            return False

    def close_app(self, app_name: str) -> bool:
        """
        Terminate all processes whose name matches ``app_name``.

        Args:
            app_name: Application name or executable name (with or without
                      ``.exe`` suffix).

        Returns:
            ``True`` if at least one process was terminated, ``False`` otherwise.
        """
        if not PSUTIL_AVAILABLE:
            # Fallback: use taskkill
            exe = self._resolve_exe(app_name) or app_name
            exe_name = pathlib.Path(exe).name
            try:
                result = subprocess.run(  # noqa: S603
                    ["taskkill", "/F", "/IM", exe_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.returncode == 0
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("taskkill failed: %s", exc)
                return False

        exe = self._resolve_exe(app_name) or app_name
        exe_name = pathlib.Path(exe).name.lower()
        killed = False
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == exe_name:
                    proc.kill()
                    logger.info("Killed process: %s (PID %s)", proc.info["name"], proc.pid)
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return killed

    def list_open_apps(self) -> List[str]:
        """
        List currently running applications that have a visible window.

        Returns:
            Sorted list of process names (deduplicated).
        """
        apps: List[str] = []

        if not PSUTIL_AVAILABLE:
            logger.warning("psutil not available. Returning empty app list.")
            return apps

        try:
            seen = set()
            for proc in psutil.process_iter(["name", "status"]):
                try:
                    name = proc.info.get("name", "")
                    status = proc.info.get("status", "")
                    if name and status == psutil.STATUS_RUNNING and name not in seen:
                        seen.add(name)
                        apps.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("list_open_apps error: %s", exc)

        return sorted(apps)

    def take_screenshot(self, save_path: Optional[str] = None) -> str:
        """
        Capture a full-screen screenshot and save it to disk.

        Args:
            save_path: Absolute path to save the screenshot. Defaults to
                       ``~/Pictures/chotu_screenshot_<timestamp>.png``.

        Returns:
            Absolute path of the saved screenshot, or an error message.
        """
        if not PYAUTOGUI_AVAILABLE:
            return "pyautogui is not installed. Cannot take a screenshot."

        if save_path is None:
            pictures = pathlib.Path.home() / "Pictures"
            pictures.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            save_path = str(pictures / f"chotu_screenshot_{timestamp}.png")

        try:
            screenshot = pyautogui.screenshot()
            screenshot.save(save_path)
            logger.info("Screenshot saved to: %s", save_path)
            return save_path
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Screenshot failed: %s", exc)
            return f"Screenshot failed: {exc}"

    def get_clipboard(self) -> str:
        """
        Read text from the system clipboard.

        Returns:
            Clipboard text content, or an error message.
        """
        if WIN32_AVAILABLE:
            try:
                win32clipboard.OpenClipboard()
                try:
                    data = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    return str(data)
                finally:
                    win32clipboard.CloseClipboard()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("get_clipboard (win32) error: %s", exc)

        # PowerShell fallback
        try:
            result = subprocess.run(  # noqa: S603
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_clipboard (PowerShell) error: %s", exc)
            return ""

    def set_clipboard(self, text: str) -> bool:
        """
        Write text to the system clipboard.

        Args:
            text: Text to place on the clipboard.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if WIN32_AVAILABLE:
            try:
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
                    return True
                finally:
                    win32clipboard.CloseClipboard()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("set_clipboard (win32) error: %s", exc)

        # PowerShell fallback
        try:
            escaped = text.replace('"', '`"')
            subprocess.run(  # noqa: S603
                ["powershell", "-command", f'Set-Clipboard -Value "{escaped}"'],
                capture_output=True,
                timeout=10,
            )
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("set_clipboard (PowerShell) error: %s", exc)
            return False

    def control_volume(self, action: str) -> str:
        """
        Control system volume using Windows multimedia keys via ctypes.

        Args:
            action: One of ``'up'``, ``'down'``, ``'mute'``, ``'unmute'``.

        Returns:
            Human-readable confirmation string.
        """
        VK_VOLUME_UP = 0xAF
        VK_VOLUME_DOWN = 0xAE
        VK_VOLUME_MUTE = 0xAD
        KEYEVENTF_KEYUP = 0x0002

        def _press(vk: int) -> None:
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        action = action.strip().lower()
        try:
            if action == "up":
                for _ in range(5):
                    _press(VK_VOLUME_UP)
                return "Volume increased."
            elif action == "down":
                for _ in range(5):
                    _press(VK_VOLUME_DOWN)
                return "Volume decreased."
            elif action in ("mute", "toggle"):
                _press(VK_VOLUME_MUTE)
                return "Volume muted."
            elif action == "unmute":
                _press(VK_VOLUME_MUTE)
                return "Volume unmuted."
            else:
                return (
                    f"Unknown volume action '{action}'. "
                    "Use 'up', 'down', 'mute', or 'unmute'."
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("control_volume error: %s", exc)
            return f"Volume control failed: {exc}"

    def open_url(self, url: str) -> bool:
        """
        Open a URL in the default web browser.

        Args:
            url: URL to open (will be prefixed with ``https://`` if no
                 scheme is present).

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        if not url.strip():
            return False
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            logger.info("Opened URL: %s", url)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("open_url error: %s", exc)
            return False

    def lock_screen(self) -> bool:
        """
        Lock the Windows workstation immediately.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        try:
            ctypes.windll.user32.LockWorkStation()
            logger.info("Screen locked.")
            return True
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("lock_screen error: %s", exc)
            return False

    def shutdown(self, delay: int = 60) -> bool:
        """
        Schedule a system shutdown after ``delay`` seconds.

        Args:
            delay: Seconds before shutdown (default 60).

        Returns:
            ``True`` if the shutdown was scheduled, ``False`` otherwise.
        """
        try:
            subprocess.run(  # noqa: S603
                ["shutdown", "/s", "/t", str(delay)],
                check=True,
                capture_output=True,
            )
            logger.info("Shutdown scheduled in %s seconds.", delay)
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("Shutdown scheduling failed: %s", exc)
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Shutdown error: %s", exc)
            return False

    def cancel_shutdown(self) -> bool:
        """
        Cancel a previously scheduled shutdown.

        Returns:
            ``True`` if cancellation succeeded, ``False`` otherwise.
        """
        try:
            subprocess.run(  # noqa: S603
                ["shutdown", "/a"],
                check=True,
                capture_output=True,
            )
            logger.info("Shutdown cancelled.")
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("cancel_shutdown failed: %s", exc)
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("cancel_shutdown error: %s", exc)
            return False

    def set_wallpaper(self, path: str) -> bool:
        """
        Change the Windows desktop wallpaper.

        Args:
            path: Absolute path to the image file (JPEG or PNG recommended).

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
        abs_path = str(pathlib.Path(path).resolve())
        if not os.path.isfile(abs_path):
            logger.error("Wallpaper file not found: %s", abs_path)
            return False

        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02

        try:
            result = ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER,
                0,
                abs_path,
                SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
            )
            if result:
                logger.info("Wallpaper set to: %s", abs_path)
                return True
            logger.error("SystemParametersInfoW returned 0 for wallpaper change.")
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("set_wallpaper error: %s", exc)
            return False

    def get_screen_resolution(self) -> Tuple[int, int]:
        """
        Query the primary monitor's screen resolution.

        Returns:
            Tuple ``(width, height)`` in pixels. Returns ``(0, 0)`` on failure.
        """
        try:
            width = ctypes.windll.user32.GetSystemMetrics(0)   # SM_CXSCREEN
            height = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
            logger.info("Screen resolution: %dx%d", width, height)
            return (width, height)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("get_screen_resolution error: %s", exc)
            return (0, 0)
