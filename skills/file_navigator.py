"""
file_navigator.py - File system access skill for CHOTU AI assistant.

Provides safe, user-friendly file-system operations including listing,
searching, reading, copying, deleting (via recycle bin), and opening files.
All methods handle permission errors and other OS errors gracefully.
"""

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: send2trash (safe delete to recycle bin)
# ---------------------------------------------------------------------------
try:
    from send2trash import send2trash as _send2trash  # type: ignore[import]
    _SEND2TRASH_AVAILABLE = True
except ImportError:
    _SEND2TRASH_AVAILABLE = False
    logger.warning(
        "file_navigator: send2trash not installed – delete_file will use permanent deletion."
    )

# ---------------------------------------------------------------------------
# Directories to skip during recursive searches (speed + safety)
# ---------------------------------------------------------------------------
_SKIP_DIRS = frozenset(
    {
        "Windows",
        "System32",
        "SysWOW64",
        "$Recycle.Bin",
        "$WINDOWS.~BT",
        "ProgramData",
        "AppData",
        "node_modules",
        ".git",
        "__pycache__",
        "venv",
        ".venv",
    }
)

# 1 MiB read limit to prevent memory issues with large files
_MAX_READ_BYTES = 1 * 1024 * 1024


class FileNavigator:
    """
    File-system skill for CHOTU AI.

    Provides directory listing, recursive search, file reading, metadata
    retrieval, and common file operations, all with graceful error handling.
    """

    def __init__(self) -> None:
        """Initialise FileNavigator; detects the user's home directory."""
        self._home = Path.home()
        logger.debug("FileNavigator: home directory is %s", self._home)

    # ------------------------------------------------------------------
    # Directory listing
    # ------------------------------------------------------------------

    def list_directory(self, path: str) -> List[Dict[str, Any]]:
        """
        List the contents of *path*.

        Args:
            path: Absolute or relative directory path.

        Returns:
            List of dicts, each with keys:
            ``name``, ``size`` (bytes, -1 for dirs), ``type`` (``'file'``
            or ``'directory'``), ``modified`` (ISO string).
            Returns an empty list on error.
        """
        target = Path(path)
        entries: List[Dict[str, Any]] = []
        try:
            for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                try:
                    stat = item.stat()
                    entries.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "size": stat.st_size if item.is_file() else -1,
                            "type": "file" if item.is_file() else "directory",
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        }
                    )
                except (PermissionError, OSError):
                    # Skip individual items that cannot be stat'd.
                    pass
        except PermissionError:
            logger.warning("list_directory: permission denied for %s", path)
        except FileNotFoundError:
            logger.warning("list_directory: path not found: %s", path)
        except OSError as exc:
            logger.exception("list_directory error for %s: %s", path, exc)
        return entries

    # ------------------------------------------------------------------
    # File search
    # ------------------------------------------------------------------

    def search_files(
        self,
        query: str,
        root_path: str = "C:\\",
        extensions: Optional[List[str]] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Recursively search for files whose name contains *query*.

        Args:
            query:       Substring to match against file names (case-insensitive).
            root_path:   Directory to start the search from.
            extensions:  Optional list of extensions to restrict matches,
                         e.g. ``['.pdf', '.docx']``.
            max_results: Maximum number of results to return.

        Returns:
            List of file-info dicts (same structure as :meth:`list_directory`).
        """
        root = Path(root_path)
        query_lower = query.lower()
        results: List[Dict[str, Any]] = []

        if extensions:
            ext_set = {e.lower().lstrip(".") for e in extensions}
        else:
            ext_set = None

        def _should_skip(directory: Path) -> bool:
            return directory.name in _SKIP_DIRS

        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=None):
                # Prune skip dirs in-place so os.walk won't recurse into them.
                dirnames[:] = [
                    d for d in dirnames if d not in _SKIP_DIRS
                ]

                for fname in filenames:
                    if len(results) >= max_results:
                        return results

                    if query_lower not in fname.lower():
                        continue

                    fpath = Path(dirpath) / fname

                    if ext_set and fpath.suffix.lower().lstrip(".") not in ext_set:
                        continue

                    info = self.get_file_info(str(fpath))
                    if info:
                        results.append(info)
        except (PermissionError, OSError) as exc:
            logger.warning("search_files: error during walk from %s: %s", root_path, exc)

        return results

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def read_file(self, path: str) -> str:
        """
        Read and return the text content of a file (up to 1 MiB).

        Args:
            path: Path to the file.

        Returns:
            File content as a string, or an error message string starting
            with ``'[Error:'`` if reading fails.
        """
        fpath = Path(path)
        try:
            size = fpath.stat().st_size
            if size > _MAX_READ_BYTES:
                return (
                    f"[Error: file is {size:,} bytes — exceeds the 1 MiB read limit. "
                    "Open it with a dedicated application instead.]"
                )
            # Attempt UTF-8, fall back to Latin-1 for binary-ish files.
            try:
                return fpath.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return fpath.read_text(encoding="latin-1")
        except PermissionError:
            msg = f"[Error: permission denied reading '{path}'.]"
            logger.warning(msg)
            return msg
        except FileNotFoundError:
            msg = f"[Error: file not found: '{path}'.]"
            logger.warning(msg)
            return msg
        except OSError as exc:
            msg = f"[Error: could not read '{path}': {exc}]"
            logger.exception(msg)
            return msg

    # ------------------------------------------------------------------
    # File metadata
    # ------------------------------------------------------------------

    def get_file_info(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Return metadata for a single file or directory.

        Args:
            path: Path to inspect.

        Returns:
            Dict with keys ``name``, ``path``, ``size``, ``type``,
            ``modified``, ``created``, ``extension``, or ``None`` on error.
        """
        fpath = Path(path)
        try:
            stat = fpath.stat()
            return {
                "name":      fpath.name,
                "path":      str(fpath),
                "size":      stat.st_size,
                "type":      "file" if fpath.is_file() else "directory",
                "modified":  datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created":   datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "extension": fpath.suffix.lower(),
            }
        except (PermissionError, FileNotFoundError, OSError):
            return None

    # ------------------------------------------------------------------
    # Recent files
    # ------------------------------------------------------------------

    def find_recent_files(
        self,
        days: int = 7,
        root_path: Optional[str] = None,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Find files modified within the last *days* days.

        Args:
            days:        Look-back window in days (default 7).
            root_path:   Directory to search; defaults to the user's home dir.
            max_results: Cap on results returned.

        Returns:
            List of file-info dicts sorted by modification time (newest first).
        """
        root = Path(root_path) if root_path else self._home
        cutoff = datetime.now() - timedelta(days=days)
        results: List[Dict[str, Any]] = []

        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

                for fname in filenames:
                    if len(results) >= max_results:
                        break
                    fpath = Path(dirpath) / fname
                    try:
                        mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
                        if mtime >= cutoff:
                            info = self.get_file_info(str(fpath))
                            if info:
                                results.append(info)
                    except (PermissionError, OSError):
                        pass
        except OSError as exc:
            logger.warning("find_recent_files error: %s", exc)

        results.sort(key=lambda x: x.get("modified", ""), reverse=True)
        return results[:max_results]

    # ------------------------------------------------------------------
    # Common user folder shortcuts
    # ------------------------------------------------------------------

    def get_downloads(self) -> List[Dict[str, Any]]:
        """
        List files in the current user's Downloads folder.

        Returns:
            List of file-info dicts, newest-modified first.
        """
        downloads = self._home / "Downloads"
        return self._list_sorted_by_modified(downloads)

    def get_desktop_files(self) -> List[Dict[str, Any]]:
        """
        List files on the current user's Desktop.

        Returns:
            List of file-info dicts.
        """
        desktop = self._home / "Desktop"
        return self._list_sorted_by_modified(desktop)

    def get_documents(self) -> List[Dict[str, Any]]:
        """
        List files in the current user's Documents folder (non-recursive).

        Returns:
            List of file-info dicts.
        """
        documents = self._home / "Documents"
        return self._list_sorted_by_modified(documents)

    def _list_sorted_by_modified(self, folder: Path) -> List[Dict[str, Any]]:
        """Helper: list *folder* sorted by modification time descending."""
        entries = self.list_directory(str(folder))
        entries.sort(key=lambda x: x.get("modified", ""), reverse=True)
        return entries

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def open_file(self, path: str) -> bool:
        """
        Open a file with its default Windows application.

        Args:
            path: Path to the file to open.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            logger.info("open_file: opened '%s'", path)
            return True
        except AttributeError:
            # os.startfile is Windows-only; fall back to subprocess.
            try:
                subprocess.Popen(["xdg-open", path])
                return True
            except OSError as exc:
                logger.error("open_file fallback failed: %s", exc)
                return False
        except FileNotFoundError:
            logger.warning("open_file: file not found: '%s'", path)
            return False
        except OSError as exc:
            logger.exception("open_file error for '%s': %s", path, exc)
            return False

    def copy_file(self, src: str, dst: str) -> bool:
        """
        Copy a file from *src* to *dst*.  Destination directories are created
        automatically.

        Args:
            src: Source file path.
            dst: Destination file path.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            dst_path = Path(dst)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            logger.info("copy_file: '%s' → '%s'", src, dst)
            return True
        except PermissionError:
            logger.error("copy_file: permission denied copying '%s' → '%s'", src, dst)
            return False
        except FileNotFoundError:
            logger.error("copy_file: source not found: '%s'", src)
            return False
        except OSError as exc:
            logger.exception("copy_file error: %s", exc)
            return False

    def delete_file(self, path: str) -> bool:
        """
        Move a file to the recycle bin (preferred) or delete it permanently.

        Uses ``send2trash`` when available; otherwise falls back to
        ``os.remove`` / ``shutil.rmtree``.

        Args:
            path: Path to the file or directory to delete.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        fpath = Path(path)
        if not fpath.exists():
            logger.warning("delete_file: path does not exist: '%s'", path)
            return False

        if _SEND2TRASH_AVAILABLE:
            try:
                _send2trash(str(fpath))
                logger.info("delete_file: moved to recycle bin: '%s'", path)
                return True
            except Exception as exc:  # send2trash raises generic Exception subtypes
                logger.warning("delete_file: send2trash failed (%s); falling back.", exc)

        # Permanent deletion fallback.
        try:
            if fpath.is_dir():
                shutil.rmtree(fpath)
            else:
                fpath.unlink()
            logger.info("delete_file: permanently deleted '%s'", path)
            return True
        except PermissionError:
            logger.error("delete_file: permission denied for '%s'", path)
            return False
        except OSError as exc:
            logger.exception("delete_file error for '%s': %s", path, exc)
            return False

    def create_folder(self, path: str) -> bool:
        """
        Create a directory (and any necessary parents).

        Args:
            path: Absolute path of the directory to create.

        Returns:
            ``True`` if the directory now exists, ``False`` on error.
        """
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            logger.info("create_folder: created '%s'", path)
            return True
        except PermissionError:
            logger.error("create_folder: permission denied for '%s'", path)
            return False
        except OSError as exc:
            logger.exception("create_folder error for '%s': %s", path, exc)
            return False

    # ------------------------------------------------------------------
    # Drive detection
    # ------------------------------------------------------------------

    def get_drives(self) -> List[str]:
        """
        Return a list of available drive-letter root paths on Windows.

        Returns:
            List of strings like ``['C:\\\\', 'D:\\\\']``.
        """
        drives: List[str] = []
        try:
            # Try Windows-specific method first.
            import ctypes  # noqa: PLC0415
            bitmask: int = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
            for i, letter in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                if bitmask & (1 << i):
                    drives.append(f"{letter}:\\")
        except (AttributeError, OSError):
            # Fallback: probe each drive letter.
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                if Path(drive).exists():
                    drives.append(drive)
        logger.debug("get_drives: found %s", drives)
        return drives

    # ------------------------------------------------------------------
    # Natural language formatting for TTS
    # ------------------------------------------------------------------

    def format_file_list(self, files: List[Dict[str, Any]]) -> str:
        """
        Convert a list of file-info dicts to a human-readable string for TTS.

        Args:
            files: List of dicts as returned by :meth:`list_directory` et al.

        Returns:
            A natural-language sentence listing the files/folders.
        """
        if not files:
            return "No files found."

        items = []
        for f in files[:10]:  # Speak at most 10 items to avoid a wall of text
            name = f.get("name", "unknown")
            ftype = f.get("type", "file")
            size = f.get("size", -1)

            if ftype == "directory":
                items.append(f"folder named {name}")
            else:
                if size >= 0:
                    size_str = self._human_size(size)
                    items.append(f"{name} ({size_str})")
                else:
                    items.append(name)

        total = len(files)
        listed = len(items)
        noun = "item" if total == 1 else "items"

        if total > listed:
            suffix = f" (showing {listed} of {total} {noun})"
        else:
            suffix = f" — {total} {noun} total"

        return "I found: " + ", ".join(items) + suffix + "."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """Return *size_bytes* as a human-readable string."""
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes //= 1024
        return f"{size_bytes:.1f} PB"
