"""
CHOTU AI — Tool Executor
Bridges the AI brain to actual system capabilities (file system, apps, web, monitoring).
"""

import os
import sys
import logging
import json
import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("CHOTU.ToolExecutor")


class ToolExecutor:
    """
    Unified executor for all CHOTU tool calls.
    Routes Gemini function call requests to the appropriate skill module.
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._file_nav = None
        self._sys_monitor = None
        self._app_ctrl = None
        self._web_intel = None
        self._memory_bank = None
        self._load_skills()

    def _load_skills(self):
        """Lazy-load skill modules."""
        try:
            from skills.file_navigator import FileNavigator
            self._file_nav = FileNavigator()
            logger.debug("FileNavigator loaded.")
        except ImportError as e:
            logger.warning(f"FileNavigator unavailable: {e}")

        try:
            from skills.system_monitor import SystemMonitor
            self._sys_monitor = SystemMonitor()
            logger.debug("SystemMonitor loaded.")
        except ImportError as e:
            logger.warning(f"SystemMonitor unavailable: {e}")

        try:
            from skills.app_controller import AppController
            self._app_ctrl = AppController()
            logger.debug("AppController loaded.")
        except ImportError as e:
            logger.warning(f"AppController unavailable: {e}")

        try:
            from skills.web_intel import WebIntel
            self._web_intel = WebIntel()
            logger.debug("WebIntel loaded.")
        except ImportError as e:
            logger.warning(f"WebIntel unavailable: {e}")

    def set_memory_bank(self, memory_bank):
        """Attach the memory bank for fact storage/recall tools."""
        self._memory_bank = memory_bank

    def execute(self, tool_name: str, tool_args: dict) -> Any:
        """
        Main dispatch method. Routes tool_name to the appropriate handler.
        Returns a string result for all tools.
        """
        handlers = {
            # File system
            "list_directory": self._list_directory,
            "search_files": self._search_files,
            "read_file": self._read_file,
            "open_file": self._open_file,
            # System monitoring
            "get_system_info": self._get_system_info,
            "get_running_processes": self._get_running_processes,
            "get_battery_info": self._get_battery_info,
            "check_internet": self._check_internet,
            # App control
            "launch_app": self._launch_app,
            "close_app": self._close_app,
            "take_screenshot": self._take_screenshot,
            "control_volume": self._control_volume,
            "lock_screen": self._lock_screen,
            "shutdown_system": self._shutdown_system,
            "get_clipboard": self._get_clipboard,
            "set_clipboard": self._set_clipboard,
            # Web
            "search_web": self._search_web,
            "get_weather": self._get_weather,
            "get_news": self._get_news,
            "open_url": self._open_url,
            # Memory
            "remember_fact": self._remember_fact,
            "recall_fact": self._recall_fact,
        }

        handler = handlers.get(tool_name)
        if handler:
            try:
                return handler(**tool_args)
            except TypeError as e:
                logger.error(f"Tool argument error for {tool_name}: {e}")
                return f"Error: Invalid arguments for {tool_name}. {e}"
            except Exception as e:
                logger.error(f"Tool execution error for {tool_name}: {e}")
                return f"Tool '{tool_name}' encountered an error: {str(e)}"
        else:
            logger.warning(f"Unknown tool: {tool_name}")
            return f"Tool '{tool_name}' is not registered in the executor."

    # ─── File System Tools ────────────────────────────────────────────────────

    def _list_directory(self, path: str) -> str:
        if self._file_nav:
            items = self._file_nav.list_directory(path)
            return self._file_nav.format_file_list(items)
        return self._fallback_list_dir(path)

    def _fallback_list_dir(self, path: str) -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"Directory '{path}' does not exist."
            items = list(p.iterdir())[:50]
            result = [f"Contents of {path}: {len(items)} items."]
            for item in items:
                t = "folder" if item.is_dir() else "file"
                result.append(f"  {item.name} ({t})")
            return "\n".join(result)
        except PermissionError:
            return f"Access denied to '{path}'."
        except Exception as e:
            return f"Error listing directory: {e}"

    def _search_files(self, query: str, root_path: str = "C:\\Users", extensions: list = None) -> str:
        if self._file_nav:
            results = self._file_nav.search_files(query, root_path, extensions)
            if not results:
                return f"No files matching '{query}' found in {root_path}."
            summary = f"Found {len(results)} file(s) matching '{query}':\n"
            for r in results[:10]:
                summary += f"  {r.get('name', '')} — {r.get('path', '')}\n"
            return summary
        return self._fallback_search(query, root_path)

    def _fallback_search(self, query: str, root_path: str) -> str:
        results = []
        try:
            for root, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if d not in {"Windows", "System32", "$Recycle.Bin", "node_modules"}]
                for f in files:
                    if query.lower() in f.lower():
                        results.append(os.path.join(root, f))
                    if len(results) >= 10:
                        break
                if len(results) >= 10:
                    break
        except PermissionError:
            pass
        if not results:
            return f"No files found matching '{query}'."
        return "Found files:\n" + "\n".join(f"  {r}" for r in results)

    def _read_file(self, path: str) -> str:
        if self._file_nav:
            return self._file_nav.read_file(path)
        try:
            p = Path(path)
            if not p.exists():
                return f"File '{path}' not found."
            if p.stat().st_size > 1_000_000:
                return f"File is too large to read in full ({p.stat().st_size // 1024} KB). Showing first 2000 characters."
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read(2000)
        except PermissionError:
            return f"Access denied to '{path}'."
        except Exception as e:
            return f"Error reading file: {e}"

    def _open_file(self, path: str) -> str:
        try:
            os.startfile(path)
            return f"Opened '{Path(path).name}' with its default application."
        except FileNotFoundError:
            return f"File '{path}' not found."
        except Exception as e:
            return f"Could not open file: {e}"

    # ─── System Monitor Tools ─────────────────────────────────────────────────

    def _get_system_info(self) -> str:
        if self._sys_monitor:
            return self._sys_monitor.format_system_report()
        return self._fallback_system_info()

    def _fallback_system_info(self) -> str:
        import platform
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            return (
                f"System: {platform.system()} {platform.release()}, "
                f"CPU: {cpu}%, "
                f"RAM: {mem.percent}% used ({mem.used // 1024**3}GB of {mem.total // 1024**3}GB)."
            )
        except Exception:
            return f"System: {platform.system()} {platform.release()}, {platform.machine()}."

    def _get_running_processes(self) -> str:
        if self._sys_monitor:
            procs = self._sys_monitor.get_running_processes()
            if procs:
                lines = ["Top running processes by CPU usage:"]
                for p in procs[:10]:
                    lines.append(f"  {p.get('name', 'Unknown')} — CPU: {p.get('cpu', 0):.1f}%, RAM: {p.get('memory', 0):.1f}%")
                return "\n".join(lines)
        try:
            import psutil
            procs = sorted(psutil.process_iter(["name", "cpu_percent"]), key=lambda x: x.info.get("cpu_percent", 0), reverse=True)
            lines = ["Top processes: " + ", ".join(p.info["name"] for p in procs[:5] if p.info.get("name"))]
            return "\n".join(lines)
        except Exception as e:
            return f"Could not retrieve processes: {e}"

    def _get_battery_info(self) -> str:
        if self._sys_monitor:
            info = self._sys_monitor.get_battery_info()
            return json.dumps(info)
        try:
            import psutil
            bat = psutil.sensors_battery()
            if bat:
                status = "charging" if bat.power_plugged else "on battery"
                return f"Battery at {bat.percent:.0f}%, {status}."
            return "No battery detected — desktop system."
        except Exception:
            return "Battery information unavailable."

    def _check_internet(self) -> str:
        if self._sys_monitor:
            connected = self._sys_monitor.check_internet()
            return "Internet connectivity confirmed." if connected else "No internet connection detected."
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return "Internet connectivity confirmed."
        except Exception:
            return "No internet connection detected."

    # ─── App Controller Tools ─────────────────────────────────────────────────

    def _launch_app(self, app_name: str) -> str:
        if self._app_ctrl:
            success = self._app_ctrl.launch_app(app_name)
            return f"Launched {app_name}." if success else f"Could not launch {app_name}."
        try:
            apps = {
                "chrome": "chrome.exe", "browser": "chrome.exe",
                "notepad": "notepad.exe", "calculator": "calc.exe",
                "explorer": "explorer.exe", "cmd": "cmd.exe",
                "terminal": "cmd.exe", "powershell": "powershell.exe",
                "paint": "mspaint.exe", "wordpad": "wordpad.exe",
            }
            exe = apps.get(app_name.lower(), f"{app_name}.exe")
            import subprocess
            subprocess.Popen(exe, shell=True)
            return f"Launching {app_name}."
        except Exception as e:
            return f"Failed to launch {app_name}: {e}"

    def _close_app(self, app_name: str) -> str:
        if self._app_ctrl:
            success = self._app_ctrl.close_app(app_name)
            return f"Closed {app_name}." if success else f"Could not close {app_name}."
        try:
            import subprocess
            subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"], capture_output=True)
            return f"Termination signal sent to {app_name}."
        except Exception as e:
            return f"Error closing {app_name}: {e}"

    def _take_screenshot(self, save_path: str = None) -> str:
        if self._app_ctrl:
            path = self._app_ctrl.take_screenshot(save_path)
            return f"Screenshot saved to {path}." if path else "Screenshot failed."
        try:
            import pyautogui
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = save_path or str(Path.home() / "Pictures" / f"chotu_screenshot_{ts}.png")
            pyautogui.screenshot(path)
            return f"Screenshot captured and saved to {path}."
        except Exception as e:
            return f"Screenshot failed: {e}"

    def _control_volume(self, action: str) -> str:
        if self._app_ctrl:
            return self._app_ctrl.control_volume(action)
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            if action == "mute":
                volume.SetMute(1, None)
                return "System muted."
            elif action == "unmute":
                volume.SetMute(0, None)
                return "System unmuted."
            elif action == "up":
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(min(1.0, current + 0.1), None)
                return "Volume increased."
            elif action == "down":
                current = volume.GetMasterVolumeLevelScalar()
                volume.SetMasterVolumeLevelScalar(max(0.0, current - 0.1), None)
                return "Volume decreased."
            return f"Volume action '{action}' executed."
        except Exception as e:
            return f"Volume control error: {e}"

    def _lock_screen(self) -> str:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "Screen locked."
        except Exception as e:
            return f"Could not lock screen: {e}"

    def _shutdown_system(self, delay_minutes: int = 1, cancel: bool = False) -> str:
        import subprocess
        if cancel:
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "Scheduled shutdown cancelled."
        delay_secs = delay_minutes * 60
        subprocess.run(["shutdown", "/s", "/t", str(delay_secs)], capture_output=True)
        return f"System shutdown scheduled in {delay_minutes} minute(s)."

    def _get_clipboard(self) -> str:
        if self._app_ctrl:
            return self._app_ctrl.get_clipboard()
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True
            )
            text = result.stdout.strip()
            return text if text else "Clipboard is empty."
        except Exception as e:
            return f"Could not read clipboard: {e}"

    def _set_clipboard(self, text: str) -> str:
        if self._app_ctrl:
            success = self._app_ctrl.set_clipboard(text)
            return "Text copied to clipboard." if success else "Clipboard operation failed."
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-command", f"Set-Clipboard '{text}'"],
                capture_output=True
            )
            return "Text copied to clipboard."
        except Exception as e:
            return f"Clipboard error: {e}"

    # ─── Web Tools ────────────────────────────────────────────────────────────

    def _search_web(self, query: str, num_results: int = 5) -> str:
        if self._web_intel:
            results = self._web_intel.search_web(query, num_results)
            return self._web_intel.format_search_results(results)
        return f"Web search for '{query}' — web module not loaded."

    def _get_weather(self, city: str) -> str:
        if self._web_intel:
            return self._web_intel.get_weather(city)
        try:
            import requests
            resp = requests.get(f"https://wttr.in/{city}?format=3", timeout=8)
            return resp.text.strip()
        except Exception as e:
            return f"Weather service unavailable: {e}"

    def _get_news(self, topic: str = "") -> str:
        if self._web_intel:
            results = self._web_intel.get_news(topic)
            if isinstance(results, list):
                return "Latest headlines: " + ". ".join(r.get("title", "") for r in results[:5])
            return str(results)
        return "News module not loaded."

    def _open_url(self, url: str) -> str:
        import webbrowser
        webbrowser.open(url)
        return f"Opening {url} in your browser."

    # ─── Memory Tools ─────────────────────────────────────────────────────────

    def _remember_fact(self, key: str, value: str) -> str:
        if self._memory_bank:
            self._memory_bank.store_fact(key, value)
            return f"Committed to memory: '{key}' = '{value}'."
        return "Memory bank not available."

    def _recall_fact(self, key: str) -> str:
        if self._memory_bank:
            value = self._memory_bank.get_fact(key)
            if value:
                return f"Memory recall: '{key}' — {value}"
            return f"No memory found for '{key}'."
        return "Memory bank not available."
