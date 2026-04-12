# exif-touch

[![CI](https://github.com/ndrco/exif_touch/actions/workflows/ci.yml/badge.svg)](https://github.com/ndrco/exif_touch/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/ndrco/exif_touch)](https://github.com/ndrco/exif_touch/releases)

`exif-touch` is a small Python CLI utility that sets file timestamps from capture dates stored in metadata via `exiftool`.

It is useful for photo and video archives when file dates were changed by copying, exporting from messaging apps, or moving files between devices.

## Features

- reads capture dates from EXIF and QuickTime metadata via `exiftool`
- updates file timestamps in a directory
- supports recursive directory traversal
- includes a `--dry-run` mode for previewing changes without writing
- updates `creation time`, `atime`, and `mtime` on Windows
- updates `atime` and `mtime` portably on Linux and macOS
- on macOS, can also update filesystem creation time when Apple's `setfile` utility is available

## Supported extensions

Processed by default:

- `jpg`, `jpeg`
- `tif`, `tiff`
- `png`
- `webp`
- `heic`, `heif`
- `mov`

Use `--all-files` if you want to try processing every file type.

## Requirements

- Python 3.10+
- `exiftool` available in `PATH`
- on macOS, `setfile` is needed if you also want to update the filesystem creation time

Install `exiftool` on Debian or Ubuntu:

```bash
sudo apt install -y libimage-exiftool-perl
```

Install Apple's Command Line Tools on macOS to get `setfile`:

```bash
xcode-select --install
```

## Compatibility

### Linux

`exif-touch` is intended to run on Linux with:

- Python `3.10+`
- `exiftool` available in `PATH`
- a local filesystem that supports updating timestamps via `os.utime()`

On Linux, the script updates `atime` and `mtime`.
Filesystem creation time is not updated on Linux by this project.

### macOS

`exif-touch` is intended to run on macOS Sierra `10.12` and later.

Recommended setup on macOS:

- Python `3.10+`
- the ExifTool MacOS package from `https://exiftool.org/`
- Apple's `setfile` utility if you also want to update filesystem creation time

On macOS, the script always updates `atime` and `mtime`.
If `setfile` is available, it also attempts to update the filesystem creation time.

### macOS Sierra 10.12

On Sierra, install your own Python 3 because the system Python is too old for this project.

Recommended setup:

- install Python `3.10.11` from python.org
- install the ExifTool MacOS package from `https://exiftool.org/`
- run `xcode-select --install` so `setfile` is available for updating creation time

Without `setfile`, the script still updates `atime` and `mtime` on macOS, but it will skip the filesystem creation time.

## Quick start

Run directly:

```bash
python3 exif_touch.py /path/to/media
```

Scan recursively:

```bash
python3 exif_touch.py -r /path/to/media
```

Preview without writing:

```bash
python3 exif_touch.py -r --dry-run /path/to/media
```

Install from the local repository:

```bash
python3 -m pip install .
```

Install directly from GitHub:

```bash
python3 -m pip install "git+https://github.com/<user>/<repo>.git"
```

## Usage

```text
usage: exif_touch.py [-h] [-r] [--dry-run] [--all-files] [directory]
```

Arguments:

- `directory` — directory with media files, defaults to the current directory
- `-r`, `--recursive` — scan subdirectories recursively
- `--dry-run` — show planned changes without modifying files
- `--all-files` — try every file, not only known media extensions

## Date source

The utility checks several standard tags in order, including:

- `DateTimeOriginal`
- `SubSecDateTimeOriginal`
- `CreateDate`
- `SubSecCreateDate`
- `CreationDate`
- `MediaCreateDate`
- `TrackCreateDate`
- `ModifyDate`
- `FileModifyDate`

## Limitations

- if `exiftool` is not installed, the utility reports the problem and exits
- on Linux and other Unix-like systems, only `atime` and `mtime` are changed portably
- on macOS, filesystem creation time updates require Apple's `setfile` utility
- some network-mounted filesystems exposed through GVFS/FUSE, such as AFP shares mounted by a desktop file manager, may not support timestamp updates via `os.utime()`
- some files do not contain a valid capture date in metadata and will be skipped

## License

This project is distributed under the MIT License. See `LICENSE`.
