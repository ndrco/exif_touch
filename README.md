# exif-touch

`exif-touch` — небольшая CLI-утилита на Python, которая выставляет время файла по дате съёмки из метаданных через `exiftool`.

Подходит для фото и видеоархивов, когда файловая дата сбилась после копирования, выгрузки из мессенджеров или переноса между устройствами.

## Что умеет

- ищет дату съёмки в EXIF/QuickTime-метаданных через `exiftool`
- обновляет timestamps файлов в каталоге
- умеет обходить вложенные папки рекурсивно
- поддерживает режим проверки без записи через `--dry-run`
- на Windows меняет `creation time`, `atime` и `mtime`
- на Linux/macOS переносимо меняет `atime` и `mtime`

## Поддерживаемые расширения

По умолчанию обрабатываются:

- `jpg`, `jpeg`
- `tif`, `tiff`
- `png`
- `webp`
- `heic`, `heif`
- `mov`

Для попытки обработки любых файлов используйте флаг `--all-files`.

## Требования

- Python 3.10+
- `exiftool` в `PATH`

Установка `exiftool` на Debian/Ubuntu:

```bash
sudo apt install -y libimage-exiftool-perl
```

## Быстрый старт

Запуск напрямую:

```bash
python3 exif_touch.py /path/to/media
```

Рекурсивный обход:

```bash
python3 exif_touch.py -r /path/to/media
```

Предпросмотр без записи:

```bash
python3 exif_touch.py -r --dry-run /path/to/media
```

Установка как утилиты из локального репозитория:

```bash
python3 -m pip install .
```

После публикации на GitHub можно будет ставить и так:

```bash
python3 -m pip install "git+https://github.com/<user>/<repo>.git"
```

## Публикация на GitHub

1. Создайте пустой репозиторий на GitHub без `README`, `.gitignore` и лицензии.
2. Привяжите локальный репозиторий:

```bash
git remote add origin git@github.com:<user>/<repo>.git
```

Или через HTTPS:

```bash
git remote add origin https://github.com/<user>/<repo>.git
```

3. Отправьте текущую ветку:

```bash
git push -u origin main
```

После первого `push` workflow из `.github/workflows/ci.yml` начнет автоматически проверять проект на `push` и `pull request`.

## Использование

```text
usage: exif_touch.py [-h] [-r] [--dry-run] [--all-files] [directory]
```

Аргументы:

- `directory` — каталог с файлами, по умолчанию текущий
- `-r`, `--recursive` — обходить подкаталоги рекурсивно
- `--dry-run` — только показать изменения без записи
- `--all-files` — пробовать читать дату у всех файлов, а не только у известных расширений

## Откуда берётся дата

Утилита по очереди проверяет несколько стандартных тегов, включая:

- `DateTimeOriginal`
- `SubSecDateTimeOriginal`
- `CreateDate`
- `SubSecCreateDate`
- `CreationDate`
- `MediaCreateDate`
- `TrackCreateDate`
- `ModifyDate`
- `FileModifyDate`

## Ограничения

- если `exiftool` не установлен, утилита только сообщит об этом и завершится
- на Unix-подобных системах переносимо меняются только `atime` и `mtime`
- не у всех файлов есть корректная дата съёмки в метаданных, такие файлы будут пропущены

## Лицензия

Проект распространяется по лицензии MIT. См. файл `LICENSE`.
