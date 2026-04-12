#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg",
    ".tif", ".tiff",
    ".png", ".webp",
    ".heic", ".heif",
    ".mov",
}

# The order in which we try date fields from exiftool.
# Native capture timestamps come first, then more generic/container-level fields.
EXIFTOOL_DATE_TAGS = [
    "DateTimeOriginal",
    "SubSecDateTimeOriginal",
    "CreateDate",
    "SubSecCreateDate",
    "CreationDate",
    "MediaCreateDate",
    "TrackCreateDate",
    "ModifyDate",
    "FileModifyDate",
]


def parse_dt(value: str) -> datetime | None:
    """
    Try to parse dates from formats commonly returned by exiftool.
    Supported examples:
      2024:03:17 12:34:56
      2024:03:17 12:34:56+03:00
      2024:03:17 12:34:56.12+03:00
      2024-03-17T12:34:56Z
      2024-03-17 12:34:56
    """
    if not value:
        return None

    s = str(value).strip()

    # exiftool sometimes returns a timezone without a colon: +0300
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-5] + s[-5:-2] + ":" + s[-2:]

    # Z -> +00:00
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Common EXIF and QuickTime formats
    formats = (
        "%Y:%m:%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S%z",
        "%Y:%m:%d %H:%M:%S.%f",
        "%Y:%m:%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    )

    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass

    # Last chance: fromisoformat
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def find_key_case_insensitive(data: dict, wanted_key: str) -> str | None:
    wanted = wanted_key.lower()
    for key, value in data.items():
        if str(key).lower() == wanted and value:
            return str(value)
    return None


def get_datetime_from_exiftool(file_path: Path) -> tuple[datetime | None, str]:
    """
    Return (datetime, source_tag).
    Read metadata via exiftool -j.
    """
    if shutil.which("exiftool") is None:
        return None, "exiftool not found"

    cmd = [
        "exiftool",
        "-j",
        "-d",
        "%Y:%m:%d %H:%M:%S%z",
        str(file_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        data = json.loads(result.stdout)
        if not data:
            return None, "no metadata"
        meta = data[0]
    except Exception as e:
        return None, f"exiftool error: {e}"

    for tag in EXIFTOOL_DATE_TAGS:
        value = find_key_case_insensitive(meta, tag)
        if not value:
            continue

        dt = parse_dt(value)
        if dt is not None:
            return dt, tag

    return None, "no date tags"


# ---------- File timestamp handling ----------

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    FILE_WRITE_ATTRIBUTES = 0x0100
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    FILE_SHARE_DELETE = 0x00000004
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x00000080
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    SetFileTime = kernel32.SetFileTime
    SetFileTime.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    SetFileTime.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL


def timestamp_to_filetime(timestamp: float):
    intervals = int(timestamp * 10_000_000) + 116444736000000000
    return FILETIME(
        intervals & 0xFFFFFFFF,
        (intervals >> 32) & 0xFFFFFFFF,
    )


def set_windows_all_times(file_path: Path, dt: datetime) -> None:
    ts = dt.timestamp()
    ft = timestamp_to_filetime(ts)

    handle = CreateFileW(
        str(file_path),
        FILE_WRITE_ATTRIBUTES,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )

    if handle == INVALID_HANDLE_VALUE:
        raise OSError(f"Failed to open file for timestamp update: {file_path}")

    try:
        ok = SetFileTime(
            handle,
            ctypes.byref(ft),  # creation
            ctypes.byref(ft),  # access
            ctypes.byref(ft),  # modified
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        CloseHandle(handle)


def format_exiftool_datetime(dt: datetime) -> str:
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.strftime("%Y:%m:%d %H:%M:%S")

    offset = dt.strftime("%z")
    offset = offset[:3] + ":" + offset[3:]
    return dt.strftime("%Y:%m:%d %H:%M:%S") + offset


def has_macos_setfile() -> bool:
    return shutil.which("setfile") is not None


def set_macos_creation_time(file_path: Path, dt: datetime) -> None:
    cmd = [
        "exiftool",
        "-overwrite_original",
        f"-FileCreateDate={format_exiftool_datetime(dt)}",
        str(file_path),
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as e:
        details = (e.stderr or e.stdout or "").strip()
        if details:
            raise OSError(f"exiftool failed to set FileCreateDate: {details}") from e
        raise OSError("exiftool failed to set FileCreateDate") from e


def set_file_times(file_path: Path, dt: datetime, dry_run: bool = False) -> str:
    if dry_run:
        if os.name == "nt":
            return f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} (creation/atime/mtime)"
        if sys.platform == "darwin":
            if has_macos_setfile():
                return (
                    f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} "
                    "(creation via exiftool + atime/mtime)"
                )
            return (
                f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} "
                "(atime/mtime only; install setfile for macOS creation time)"
            )
        return f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} (atime/mtime only)"

    if os.name == "nt":
        set_windows_all_times(file_path, dt)
        return f"[OK] {file_path} -> {dt.isoformat(sep=' ')} (creation/atime/mtime)"

    creation_note = ""
    if sys.platform == "darwin":
        if has_macos_setfile():
            try:
                set_macos_creation_time(file_path, dt)
                creation_note = "creation via exiftool + "
            except Exception as e:
                creation_note = f"creation skipped ({e}); "
        else:
            creation_note = "creation skipped (setfile not found); "

    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))

    if sys.platform == "darwin":
        return (
            f"[OK] {file_path} -> {dt.isoformat(sep=' ')} "
            f"({creation_note}atime/mtime)"
        )

    return f"[OK] {file_path} -> {dt.isoformat(sep=' ')} (atime/mtime only)"


def explain_update_error(file_path: Path, error: Exception) -> str:
    path_str = str(file_path)

    if isinstance(error, OSError):
        if error.errno == errno.EROFS:
            return f"{error} (filesystem is mounted read-only)"

        if error.errno == errno.EACCES:
            return f"{error} (permission denied while updating file times)"

        if error.errno == errno.EOPNOTSUPP:
            if "/gvfs/" in path_str:
                return (
                    f"{error} (GVFS/network mounts such as AFP/SMB may not support "
                    "updating timestamps via os.utime; copy files locally or use a "
                    "mount method that supports utime)"
                )
            return f"{error} (filesystem does not support updating timestamps)"

    return str(error)


def iter_files(directory: Path, recursive: bool):
    if recursive:
        files = (p for p in directory.rglob("*") if p.is_file())
    else:
        files = (p for p in directory.iterdir() if p.is_file())

    yield from sorted(files, key=lambda p: p.name.lower())


def is_supported_file(file_path: Path, all_files: bool) -> bool:
    if all_files:
        return True
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set file timestamps from metadata via exiftool (JPG/HEIC/MOV and more)."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=Path.cwd(),
        type=Path,
        help="Directory with files (defaults to the current directory)",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Scan subdirectories recursively",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing anything",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Try every file, not only known extensions",
    )

    args = parser.parse_args()
    directory = args.directory

    if not directory.exists():
        print(f"Directory not found: {directory}")
        return

    if not directory.is_dir():
        print(f"Not a directory: {directory}")
        return

    if shutil.which("exiftool") is None:
        print("Error: exiftool was not found in PATH.")
        print("Install it, for example:")
        if sys.platform == "darwin":
            print("  Install the ExifTool MacOS package from https://exiftool.org/")
        else:
            print("  sudo apt install -y libimage-exiftool-perl")
        return

    print(f"Working directory: {directory.resolve()}")

    if "/gvfs/" in str(directory):
        print("[INFO] The target directory is inside a GVFS mount.")
        print("[INFO] Some network mounts, including AFP shares opened via file managers,")
        print("[INFO] do not support changing file timestamps with os.utime().")

    if sys.platform == "darwin":
        print("[INFO] On macOS, atime/mtime are updated with os.utime().")
        if has_macos_setfile():
            print("[INFO] macOS creation time will also be updated via exiftool/setfile.")
        else:
            print("[INFO] macOS creation time requires Apple's setfile utility.")
            print("[INFO] Install it with: xcode-select --install")
    elif os.name != "nt":
        print("[INFO] Only atime/mtime can be updated portably on this platform.")
        print("[INFO] Real creation time is only updated by the script on Windows.")

    processed = 0
    updated = 0
    skipped = 0

    for file_path in iter_files(directory, args.recursive):
        if not is_supported_file(file_path, args.all_files):
            continue

        processed += 1
        dt, source = get_datetime_from_exiftool(file_path)

        if dt is None:
            print(f"[SKIP] {file_path} -> no usable date found ({source})")
            skipped += 1
            continue

        try:
            msg = set_file_times(file_path, dt, dry_run=args.dry_run)
            print(f"{msg} [source: {source}]")
            updated += 1
        except Exception as e:
            print(
                f"[SKIP] {file_path} -> failed to update timestamps: "
                f"{explain_update_error(file_path, e)}"
            )
            skipped += 1

    print("\nDone:")
    print(f"  Processed: {processed}")
    print(f"  Updated:   {updated}")
    print(f"  Skipped:   {skipped}")


if __name__ == "__main__":
    main()
