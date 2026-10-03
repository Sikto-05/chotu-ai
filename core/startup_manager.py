"""
startup_manager.py - Windows startup integration manager for CHOTU AI assistant.

Manages automatic launch of CHOTU at Windows login via:
  1. HKCU registry Run key  (primary)
  2. Startup folder shortcut (secondary)
  3. Task Scheduler task     (fallback / admin scenarios)
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Guard: winreg is Windows-only.
try:
    import winreg  # type: ignore[import]
    _WINREG_AVAILABLE = True
except ImportError:
    _WINREG_AVAILABLE = False
    logger.warning("startup_manager: winreg not available – registry features disabled.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTRY_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REGISTRY_VALUE_NAME = "CHOTU_AI"
TASK_NAME = "CHOTU_AI_Startup"


class StartupManager:
    """
    Manages Windows auto-start entries for the CHOTU AI assistant.

    Supports three complementary mechanisms:
    * Windows Registry ``HKCU\\...\\Run`` key (no admin required)
    * Startup folder shortcut  (no admin required)
    * Task Scheduler task      (most reliable; may need elevation)
    """

    def __init__(self, project_root: Optional[str] = None) -> None:
        """
        Initialise the manager.

        Args:
            project_root: Absolute path to the chotu-ai project directory.
                          Defaults to the grandparent of this file.
        """
        if project_root:
            self._root = Path(project_root).resolve()
        else:
            # core/startup_manager.py  →  grandparent is project root
            self._root = Path(__file__).resolve().parent.parent

        self._bat_launcher = self._root / "launch_chotu.bat"
        self._main_py = self._root / "main.py"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_app_path(self) -> str:
        """
        Return the full path used as the startup command target.

        Prefers a compiled ``chotu.exe`` if present next to ``main.py``,
        otherwise falls back to ``pythonw.exe main.py`` via the .bat launcher.

        Returns:
            Absolute path string to the exe or bat launcher.
        """
        exe_path = self._root / "chotu.exe"
        if exe_path.exists():
            logger.debug("startup_manager: using compiled exe %s", exe_path)
            return str(exe_path)

        # Ensure the .bat launcher exists before returning its path.
        self._ensure_bat_launcher()
        return str(self._bat_launcher)

    def enable_startup(self) -> bool:
        """
        Add CHOTU to the Windows HKCU registry Run key.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        if not _WINREG_AVAILABLE:
            logger.error("enable_startup: winreg unavailable.")
            return False

        app_path = self.get_app_path()
        command = f'"{app_path}"'

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            )
            with key:
                winreg.SetValueEx(key, REGISTRY_VALUE_NAME, 0, winreg.REG_SZ, command)
            logger.info("startup_manager: registry Run entry set → %s", command)
            return True
        except PermissionError:
            logger.error("startup_manager: permission denied writing to registry.")
            return False
        except OSError as exc:
            logger.exception("startup_manager.enable_startup OS error: %s", exc)
            return False

    def disable_startup(self) -> bool:
        """
        Remove the CHOTU registry Run entry.

        Returns:
            ``True`` if the entry was removed (or did not exist), ``False`` on error.
        """
        if not _WINREG_AVAILABLE:
            logger.error("disable_startup: winreg unavailable.")
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            )
            with key:
                winreg.DeleteValue(key, REGISTRY_VALUE_NAME)
            logger.info("startup_manager: registry Run entry removed.")
            return True
        except FileNotFoundError:
            logger.info("startup_manager: registry Run entry did not exist.")
            return True
        except PermissionError:
            logger.error("startup_manager: permission denied removing registry entry.")
            return False
        except OSError as exc:
            logger.exception("startup_manager.disable_startup OS error: %s", exc)
            return False

    def is_startup_enabled(self) -> bool:
        """
        Check whether the HKCU registry Run entry exists for CHOTU.

        Returns:
            ``True`` if the entry is present, ``False`` otherwise.
        """
        if not _WINREG_AVAILABLE:
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_KEY_PATH,
                0,
                winreg.KEY_READ,
            )
            with key:
                winreg.QueryValueEx(key, REGISTRY_VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            logger.exception("startup_manager.is_startup_enabled OS error: %s", exc)
            return False

    def create_startup_shortcut(self) -> bool:
        """
        Create a ``.bat`` shortcut in the Windows user Startup folder.

        The Startup folder is ``%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup``.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            startup_folder = Path(os.environ.get("APPDATA", "")) / (
                r"Microsoft\Windows\Start Menu\Programs\Startup"
            )
            if not startup_folder.exists():
                logger.warning(
                    "startup_manager: Startup folder not found at %s", startup_folder
                )
                return False

            shortcut_bat = startup_folder / "CHOTU_AI.bat"
            self._ensure_bat_launcher()

            bat_content = (
                f'@echo off\n'
                f'start "" "{self.get_app_path()}"\n'
            )
            shortcut_bat.write_text(bat_content, encoding="utf-8")
            logger.info("startup_manager: startup folder shortcut created at %s", shortcut_bat)
            return True
        except PermissionError:
            logger.error("startup_manager: permission denied creating startup shortcut.")
            return False
        except OSError as exc:
            logger.exception("startup_manager.create_startup_shortcut OS error: %s", exc)
            return False

    def add_to_task_scheduler(self) -> bool:
        """
        Register a Task Scheduler task as a reliable fallback launch mechanism.

        Uses ``schtasks.exe`` to create an ``ONLOGON`` trigger task.
        May require elevated privileges on some systems.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        self._ensure_bat_launcher()
        app_path = self.get_app_path()

        cmd = [
            "schtasks",
            "/Create",
            "/F",                          # Force overwrite if exists
            "/SC", "ONLOGON",
            "/TN", TASK_NAME,
            "/TR", f'"{app_path}"',
            "/RL", "HIGHEST",
            "/DELAY", "0001:00",           # 1-minute delay after logon
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("startup_manager: Task Scheduler task '%s' created.", TASK_NAME)
                return True
            else:
                logger.error(
                    "startup_manager: schtasks returned %d: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
        except FileNotFoundError:
            logger.error("startup_manager: schtasks.exe not found.")
            return False
        except subprocess.TimeoutExpired:
            logger.error("startup_manager: schtasks timed out.")
            return False
        except OSError as exc:
            logger.exception("startup_manager.add_to_task_scheduler OS error: %s", exc)
            return False

    def remove_from_task_scheduler(self) -> bool:
        """
        Delete the Task Scheduler task for CHOTU if it exists.

        Returns:
            ``True`` on success or if task did not exist, ``False`` on error.
        """
        cmd = ["schtasks", "/Delete", "/F", "/TN", TASK_NAME]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                logger.info("startup_manager: Task Scheduler task '%s' removed.", TASK_NAME)
                return True
            # schtasks returns 1 if the task does not exist – treat as success.
            if "does not exist" in result.stderr.lower() or result.returncode == 1:
                return True
            logger.error(
                "startup_manager: schtasks /Delete returned %d: %s",
                result.returncode,
                result.stderr.strip(),
            )
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            logger.exception("startup_manager.remove_from_task_scheduler error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_bat_launcher(self) -> None:
        """
        Write (or overwrite) the ``launch_chotu.bat`` launcher in the project root.

        The launcher runs ``main.py`` via ``pythonw.exe`` (no console window),
        from the project root directory, and redirects stdout/stderr to a log file.
        """
        pythonw = self._find_pythonw()
        log_file = self._root / "data" / "chotu_launch.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        bat_lines = [
            "@echo off",
            f'cd /d "{self._root}"',
            f'start "" "{pythonw}" "{self._main_py}" >> "{log_file}" 2>&1',
        ]
        bat_content = "\r\n".join(bat_lines) + "\r\n"

        try:
            self._bat_launcher.write_text(bat_content, encoding="utf-8")
            logger.debug("startup_manager: .bat launcher written to %s", self._bat_launcher)
        except OSError as exc:
            logger.exception("startup_manager: could not write .bat launcher: %s", exc)

    @staticmethod
    def _find_pythonw() -> str:
        """
        Locate ``pythonw.exe`` next to the running Python interpreter.

        Returns:
            Full path to ``pythonw.exe``, or the bare ``'pythonw'`` string
            as a fallback (must be on PATH).
        """
        python_dir = Path(sys.executable).parent
        pythonw = python_dir / "pythonw.exe"
        if pythonw.exists():
            return str(pythonw)
        # Virtual-env layouts sometimes have it one level up.
        pythonw_up = python_dir.parent / "pythonw.exe"
        if pythonw_up.exists():
            return str(pythonw_up)
        logger.warning("startup_manager: pythonw.exe not found; falling back to 'pythonw'.")
        return "pythonw"


# ---------------------------------------------------------------------------
# Quick self-test (run this file directly: python startup_manager.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    mgr = StartupManager()
    print("App path    :", mgr.get_app_path())
    print("Is enabled  :", mgr.is_startup_enabled())
    print("Enable      :", mgr.enable_startup())
    print("Is enabled  :", mgr.is_startup_enabled())
    print("Disable     :", mgr.disable_startup())
    print("Is enabled  :", mgr.is_startup_enabled())
