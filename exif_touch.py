#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg",
    ".tif", ".tiff",
    ".png", ".webp",
    ".heic", ".heif",
    ".mov",
}

# В каком порядке пробуем брать дату из exiftool.
# Сначала наиболее "родные" поля съёмки, потом более общие/контейнерные.
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
    Пытается распарсить дату из разных форматов, которые часто возвращает exiftool.
    Поддерживает, например:
      2024:03:17 12:34:56
      2024:03:17 12:34:56+03:00
      2024:03:17 12:34:56.12+03:00
      2024-03-17T12:34:56Z
      2024-03-17 12:34:56
    """
    if not value:
        return None

    s = str(value).strip()

    # exiftool иногда возвращает timezone без двоеточия: +0300
    if re.search(r"[+-]\d{4}$", s):
        s = s[:-5] + s[-5:-2] + ":" + s[-2:]

    # Z -> +00:00
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Самые частые форматы EXIF/QuickTime
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

    # Последний шанс: fromisoformat
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
    Возвращает (datetime, source_tag).
    Для чтения использует exiftool -j.
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


# ---------- Работа со временем файла ----------

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
        raise OSError(f"Не удалось открыть файл для изменения времени: {file_path}")

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


def set_file_times(file_path: Path, dt: datetime, dry_run: bool = False) -> str:
    if dry_run:
        if os.name == "nt":
            return f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} (creation/atime/mtime)"
        return f"[DRY-RUN] {file_path} -> {dt.isoformat(sep=' ')} (atime/mtime only)"

    if os.name == "nt":
        set_windows_all_times(file_path, dt)
        return f"[OK] {file_path} -> {dt.isoformat(sep=' ')} (creation/atime/mtime)"

    ts = dt.timestamp()
    os.utime(file_path, (ts, ts))
    return f"[OK] {file_path} -> {dt.isoformat(sep=' ')} (atime/mtime only)"


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
        description="Ставит дату файла по метаданным через exiftool (JPG/HEIC/MOV и др.)."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=Path.cwd(),
        type=Path,
        help="Каталог с файлами (по умолчанию — текущий каталог)",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Обходить подкаталоги рекурсивно",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет изменено, без записи",
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Пробовать все файлы, а не только известные расширения",
    )

    args = parser.parse_args()
    directory = args.directory

    if not directory.exists():
        print(f"Каталог не найден: {directory}")
        return

    if not directory.is_dir():
        print(f"Это не каталог: {directory}")
        return

    if shutil.which("exiftool") is None:
        print("Ошибка: exiftool не найден в PATH.")
        print("Установи его, например, так:")
        print("  sudo apt install -y libimage-exiftool-perl")
        return

    print(f"Рабочий каталог: {directory.resolve()}")

    if os.name != "nt":
        print("[INFO] На этой платформе переносимо меняется только atime/mtime.")
        print("[INFO] Настоящую creation time скрипт меняет только на Windows.")

    processed = 0
    updated = 0
    skipped = 0

    for file_path in iter_files(directory, args.recursive):
        if not is_supported_file(file_path, args.all_files):
            continue

        processed += 1
        dt, source = get_datetime_from_exiftool(file_path)

        if dt is None:
            print(f"[SKIP] {file_path} -> дата не найдена ({source})")
            skipped += 1
            continue

        try:
            msg = set_file_times(file_path, dt, dry_run=args.dry_run)
            print(f"{msg} [source: {source}]")
            updated += 1
        except Exception as e:
            print(f"[SKIP] {file_path} -> ошибка изменения времени: {e}")
            skipped += 1

    print("\nГотово:")
    print(f"  Обработано: {processed}")
    print(f"  Обновлено:  {updated}")
    print(f"  Пропущено:  {skipped}")


if __name__ == "__main__":
    main()
