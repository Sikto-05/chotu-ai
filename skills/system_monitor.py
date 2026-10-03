"""
system_monitor.py - System monitoring skill for CHOTU AI assistant.

Provides real-time hardware and OS metrics including CPU, memory, disk, network,
battery, processes, and internet connectivity.  All methods degrade gracefully
when a metric is unavailable or psutil is not installed.
"""

import datetime
import logging
import platform
import socket
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: psutil
# ---------------------------------------------------------------------------
try:
    import psutil  # type: ignore[import]
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    logger.warning(
        "system_monitor: psutil not installed – hardware metrics will be unavailable. "
        "Install with: pip install psutil"
    )

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
_InfoDict = Dict[str, Any]


class SystemMonitor:
    """
    System monitoring skill for CHOTU AI.

    All public methods return plain dicts or primitive types so they can be
    serialised to JSON for tool-use or spoken via TTS.
    """

    # ------------------------------------------------------------------
    # Comprehensive system information
    # ------------------------------------------------------------------

    def get_system_info(self) -> _InfoDict:
        """
        Return a consolidated snapshot of the host system.

        Returns:
            Dict with keys: ``os``, ``os_version``, ``hostname``,
            ``architecture``, ``cpu_cores_logical``, ``cpu_cores_physical``,
            ``cpu_freq_mhz``, ``ram_total_gb``, ``uptime``.
        """
        info: _InfoDict = {
            "os":               platform.system(),
            "os_version":       platform.version(),
            "os_release":       platform.release(),
            "hostname":         socket.gethostname(),
            "architecture":     platform.machine(),
            "processor":        platform.processor(),
        }

        if _PSUTIL_AVAILABLE:
            try:
                info["cpu_cores_logical"]  = psutil.cpu_count(logical=True)
                info["cpu_cores_physical"] = psutil.cpu_count(logical=False)
                freq = psutil.cpu_freq()
                info["cpu_freq_mhz"] = round(freq.current, 1) if freq else "N/A"
                mem = psutil.virtual_memory()
                info["ram_total_gb"] = round(mem.total / 1024 ** 3, 2)
                info["ram_used_gb"]  = round(mem.used  / 1024 ** 3, 2)
                info["uptime"]       = self.get_startup_time()
            except Exception as exc:
                logger.warning("get_system_info partial failure: %s", exc)

        return info

    # ------------------------------------------------------------------
    # CPU
    # ------------------------------------------------------------------

    def get_cpu_usage(self) -> float:
        """
        Return the system-wide CPU utilisation percentage (1-second interval).

        Returns:
            Float 0–100, or -1.0 if unavailable.
        """
        if not _PSUTIL_AVAILABLE:
            return -1.0
        try:
            return psutil.cpu_percent(interval=1)
        except Exception as exc:
            logger.warning("get_cpu_usage error: %s", exc)
            return -1.0

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def get_memory_info(self) -> _InfoDict:
        """
        Return virtual memory statistics.

        Returns:
            Dict with keys ``total``, ``available``, ``used``, ``percent``
            (values in bytes, percent as float 0–100).
        """
        if not _PSUTIL_AVAILABLE:
            return {"error": "psutil not available"}
        try:
            mem = psutil.virtual_memory()
            return {
                "total":     mem.total,
                "available": mem.available,
                "used":      mem.used,
                "percent":   mem.percent,
                "total_gb":  round(mem.total     / 1024 ** 3, 2),
                "used_gb":   round(mem.used      / 1024 ** 3, 2),
                "free_gb":   round(mem.available / 1024 ** 3, 2),
            }
        except Exception as exc:
            logger.warning("get_memory_info error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Disk
    # ------------------------------------------------------------------

    def get_disk_info(self) -> List[_InfoDict]:
        """
        Return usage statistics for every mounted disk partition.

        Returns:
            List of dicts with keys ``device``, ``mountpoint``, ``fstype``,
            ``total_gb``, ``used_gb``, ``free_gb``, ``percent``.
        """
        if not _PSUTIL_AVAILABLE:
            return [{"error": "psutil not available"}]

        results: List[_InfoDict] = []
        try:
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    results.append(
                        {
                            "device":     part.device,
                            "mountpoint": part.mountpoint,
                            "fstype":     part.fstype,
                            "total_gb":   round(usage.total / 1024 ** 3, 2),
                            "used_gb":    round(usage.used  / 1024 ** 3, 2),
                            "free_gb":    round(usage.free  / 1024 ** 3, 2),
                            "percent":    usage.percent,
                        }
                    )
                except (PermissionError, OSError):
                    # Optical drives or unmounted paths raise this.
                    pass
        except Exception as exc:
            logger.warning("get_disk_info error: %s", exc)
        return results

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    def get_network_info(self) -> _InfoDict:
        """
        Return network interface addresses and I/O counters.

        Returns:
            Dict with keys ``interfaces`` (list of dicts) and ``io``
            (bytes_sent, bytes_recv as ints).
        """
        if not _PSUTIL_AVAILABLE:
            return {"error": "psutil not available"}

        info: _InfoDict = {"interfaces": [], "io": {}}

        try:
            addrs = psutil.net_if_addrs()
            for iface, addr_list in addrs.items():
                iface_info: _InfoDict = {"name": iface, "addresses": []}
                for addr in addr_list:
                    iface_info["addresses"].append(
                        {
                            "family":  str(addr.family),
                            "address": addr.address,
                            "netmask": addr.netmask,
                        }
                    )
                info["interfaces"].append(iface_info)
        except Exception as exc:
            logger.warning("get_network_info (interfaces) error: %s", exc)

        try:
            counters = psutil.net_io_counters()
            info["io"] = {
                "bytes_sent":   counters.bytes_sent,
                "bytes_recv":   counters.bytes_recv,
                "packets_sent": counters.packets_sent,
                "packets_recv": counters.packets_recv,
            }
        except Exception as exc:
            logger.warning("get_network_info (io) error: %s", exc)

        return info

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    def get_battery_info(self) -> _InfoDict:
        """
        Return battery status information.

        Returns:
            Dict with keys ``percent``, ``plugged``, ``time_remaining``
            (human-readable string), or ``{"error": ...}`` if no battery.
        """
        if not _PSUTIL_AVAILABLE:
            return {"error": "psutil not available"}
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return {"error": "No battery detected"}

            secs_left = battery.secsleft
            if secs_left == psutil.POWER_TIME_UNLIMITED:
                time_str = "charging / plugged in"
            elif secs_left == psutil.POWER_TIME_UNKNOWN:
                time_str = "unknown"
            else:
                hours, rem = divmod(int(secs_left), 3600)
                minutes = rem // 60
                time_str = f"{hours}h {minutes}m remaining"

            return {
                "percent":        round(battery.percent, 1),
                "plugged":        battery.power_plugged,
                "time_remaining": time_str,
            }
        except Exception as exc:
            logger.warning("get_battery_info error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Processes
    # ------------------------------------------------------------------

    def get_running_processes(self, top_n: int = 20) -> List[_InfoDict]:
        """
        Return the top *top_n* processes sorted by CPU usage.

        Args:
            top_n: Number of processes to return (default 20).

        Returns:
            List of dicts with keys ``pid``, ``name``, ``cpu_percent``,
            ``memory_mb``, ``status``.
        """
        if not _PSUTIL_AVAILABLE:
            return [{"error": "psutil not available"}]

        procs: List[_InfoDict] = []
        try:
            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_info", "status"]
            ):
                try:
                    mem_bytes = (
                        proc.info["memory_info"].rss
                        if proc.info.get("memory_info")
                        else 0
                    )
                    procs.append(
                        {
                            "pid":         proc.info["pid"],
                            "name":        proc.info.get("name", "unknown"),
                            "cpu_percent": proc.info.get("cpu_percent") or 0.0,
                            "memory_mb":   round(mem_bytes / 1024 ** 2, 1),
                            "status":      proc.info.get("status", "unknown"),
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as exc:
            logger.warning("get_running_processes error: %s", exc)

        # Sort by CPU descending.
        procs.sort(key=lambda p: p.get("cpu_percent", 0), reverse=True)
        return procs[:top_n]

    def get_top_apps(self, top_n: int = 5) -> List[_InfoDict]:
        """
        Return the top *top_n* CPU-consuming applications (named processes).

        Args:
            top_n: Number of apps to return (default 5).

        Returns:
            List of dicts (subset of :meth:`get_running_processes`).
        """
        all_procs = self.get_running_processes(top_n=50)
        # Filter out system/nameless processes for a user-friendly list.
        named = [p for p in all_procs if p.get("name") and p["name"] not in ("System", "Idle")]
        return named[:top_n]

    # ------------------------------------------------------------------
    # Temperature
    # ------------------------------------------------------------------

    def get_temperature(self) -> _InfoDict:
        """
        Return available hardware temperature readings.

        Returns:
            Dict mapping sensor name → list of temperature dicts
            (``label``, ``current``, ``high``, ``critical`` in °C).
            Returns ``{"error": ...}`` if not supported.
        """
        if not _PSUTIL_AVAILABLE:
            return {"error": "psutil not available"}

        if not hasattr(psutil, "sensors_temperatures"):
            return {"error": "Temperature sensors not supported on this platform."}

        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return {"error": "No temperature sensors found."}

            result: _InfoDict = {}
            for sensor_name, entries in temps.items():
                result[sensor_name] = [
                    {
                        "label":    e.label or sensor_name,
                        "current":  e.current,
                        "high":     e.high,
                        "critical": e.critical,
                    }
                    for e in entries
                ]
            return result
        except Exception as exc:
            logger.warning("get_temperature error: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    def get_startup_time(self) -> str:
        """
        Return a human-readable string of how long the system has been running.

        Returns:
            String like ``'2 days, 4 hours, 31 minutes'``, or ``'unknown'``.
        """
        if not _PSUTIL_AVAILABLE:
            return "unknown"
        try:
            boot_ts = psutil.boot_time()
            boot_dt = datetime.datetime.fromtimestamp(boot_ts)
            delta   = datetime.datetime.now() - boot_dt

            days    = delta.days
            hours   = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60

            parts = []
            if days:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            return ", ".join(parts)
        except Exception as exc:
            logger.warning("get_startup_time error: %s", exc)
            return "unknown"

    # ------------------------------------------------------------------
    # Internet connectivity
    # ------------------------------------------------------------------

    def check_internet(self) -> bool:
        """
        Check whether the system has an active internet connection.

        Attempts a TCP connection to Google's DNS (8.8.8.8:53).

        Returns:
            ``True`` if connected, ``False`` otherwise.
        """
        try:
            sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
            sock.close()
            return True
        except OSError:
            return False

    def get_ip_info(self) -> _InfoDict:
        """
        Return the host's local and (best-effort) public IP addresses.

        Returns:
            Dict with keys ``local_ip``, ``hostname``, and optionally
            ``public_ip`` (requires internet access).
        """
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except OSError:
            local_ip = "unavailable"

        info: _InfoDict = {
            "hostname": hostname,
            "local_ip": local_ip,
        }

        # Attempt to retrieve public IP via a lightweight DNS socket trick.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(3)
            s.connect(("8.8.8.8", 80))
            info["local_ip_outbound"] = s.getsockname()[0]
            s.close()
        except OSError:
            pass

        # Try curl/Invoke-WebRequest as fallback for public IP (non-blocking).
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "4", "https://api.ipify.org"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                info["public_ip"] = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        return info

    # ------------------------------------------------------------------
    # Natural language system report for TTS
    # ------------------------------------------------------------------

    def format_system_report(self) -> str:
        """
        Generate a natural-language system status report suitable for TTS.

        Returns:
            Multi-sentence string summarising CPU, RAM, disk, battery,
            and network status.
        """
        lines: List[str] = []

        # --- CPU ---
        cpu = self.get_cpu_usage()
        if cpu >= 0:
            lines.append(f"CPU usage is at {cpu:.0f} percent.")
        else:
            lines.append("CPU usage information is unavailable.")

        # --- RAM ---
        mem = self.get_memory_info()
        if "error" not in mem:
            lines.append(
                f"RAM: {mem.get('used_gb', '?')} GB used out of "
                f"{mem.get('total_gb', '?')} GB "
                f"({mem.get('percent', '?')}% in use)."
            )
        else:
            lines.append("Memory information is unavailable.")

        # --- Disk ---
        disks = self.get_disk_info()
        for disk in disks[:3]:  # Limit to first 3 drives
            if "error" not in disk:
                lines.append(
                    f"Drive {disk.get('device', '?')}: "
                    f"{disk.get('free_gb', '?')} GB free of "
                    f"{disk.get('total_gb', '?')} GB "
                    f"({disk.get('percent', '?')}% used)."
                )

        # --- Battery ---
        batt = self.get_battery_info()
        if "error" not in batt:
            plugged_str = "plugged in" if batt.get("plugged") else "on battery"
            lines.append(
                f"Battery is at {batt.get('percent', '?')}%, {plugged_str}. "
                f"{batt.get('time_remaining', '')}".strip()
            )

        # --- Internet ---
        if self.check_internet():
            lines.append("Internet connection is active.")
        else:
            lines.append("No internet connection detected.")

        # --- Uptime ---
        uptime = self.get_startup_time()
        if uptime != "unknown":
            lines.append(f"System has been running for {uptime}.")

        return " ".join(lines)
