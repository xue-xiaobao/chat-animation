#!/usr/bin/env python3
"""Resolve the caption font without making the Skill bundle carry font binaries."""

from __future__ import annotations

import os
import platform
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common import SkillError, iso_now, sha256_bytes, sha256_file, write_json


FONT_ID = "smiley-sans"
FONT_FAMILY = "Smiley Sans"
FONT_DISPLAY_NAME = "得意黑"
FONT_VERSION = "2.0.1"
FONT_FILENAME = "SmileySans-Oblique.ttf"
FONT_ARCHIVE_MEMBER = FONT_FILENAME
FONT_ARCHIVE_URL = (
    "https://github.com/atelier-anchor/smiley-sans/releases/download/"
    "v2.0.1/smiley-sans-v2.0.1.zip"
)
FONT_ARCHIVE_SHA256 = (
    "299c0be6c960ae37361762eca76f7d0cd516615435bb96c0d4b98a1e70178a07"
)
FONT_FILE_SHA256 = (
    "b447d7e781f08bc95c4c9f23ba71ed2b8ebb639aa7184485c71c4ca5afcd25c4"
)
FONT_SELECTION_RELATIVE = Path("state/font-selection.json")


def font_cache_root() -> Path:
    override = os.environ.get("CHAT_ANIMATION_FONT_CACHE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "chat-animation" / "fonts"
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "chat-animation" / "fonts"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".cache") / "chat-animation" / "fonts"


def cached_font_path() -> Path:
    return font_cache_root() / FONT_ID / FONT_VERSION / FONT_FILENAME


def valid_smiley_font(path: Path) -> bool:
    return path.is_file() and sha256_file(path) == FONT_FILE_SHA256


def download_smiley_font(target: Path, timeout: float = 30.0) -> None:
    request = urllib.request.Request(
        FONT_ARCHIVE_URL,
        headers={"User-Agent": "chat-animation-font-bootstrap/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            archive = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SkillError(f"得意黑下载失败: {exc}") from exc
    if sha256_bytes(archive) != FONT_ARCHIVE_SHA256:
        raise SkillError("得意黑压缩包 SHA-256 校验失败")
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip") as handle:
            handle.write(archive)
            handle.flush()
            with zipfile.ZipFile(handle.name) as bundle:
                font_data = bundle.read(FONT_ARCHIVE_MEMBER)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise SkillError(f"得意黑压缩包无法读取: {exc}") from exc
    if sha256_bytes(font_data) != FONT_FILE_SHA256:
        raise SkillError("得意黑字体文件 SHA-256 校验失败")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp", delete=False
    ) as handle:
        handle.write(font_data)
        temporary = Path(handle.name)
    os.replace(temporary, target)


def fallback_candidates() -> Tuple[str, List[Tuple[str, Path]]]:
    system = platform.system()
    if system == "Darwin":
        return (
            "PingFang SC",
            [
                ("PingFang SC", Path("/System/Library/Fonts/PingFang.ttc")),
                ("Heiti SC", Path("/System/Library/Fonts/STHeiti Medium.ttc")),
                ("Heiti SC", Path("/System/Library/Fonts/STHeiti Light.ttc")),
                (
                    "Arial Unicode MS",
                    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                ),
            ],
        )
    if system == "Windows":
        windows = Path(os.environ.get("WINDIR", "C:/Windows"))
        fonts = windows / "Fonts"
        return (
            "Microsoft YaHei",
            [
                ("Microsoft YaHei", fonts / "msyh.ttc"),
                ("Microsoft YaHei", fonts / "msyhbd.ttc"),
                ("SimHei", fonts / "simhei.ttf"),
                ("SimSun", fonts / "simsun.ttc"),
            ],
        )
    return "sans-serif", []


def system_fallback(reason: str = "") -> Dict[str, Any]:
    generic_family, candidates = fallback_candidates()
    for family, path in candidates:
        if path.is_file():
            return {
                "id": "system-fallback",
                "display_name": family,
                "family": family,
                "version": platform.platform(),
                "source": "system-fallback",
                "file": str(path.resolve()),
                "sha256": sha256_file(path),
                "fallback_reason": reason,
            }
    return {
        "id": "system-fallback",
        "display_name": generic_family,
        "family": generic_family,
        "version": platform.platform(),
        "source": "system-fallback-family",
        "file": None,
        "sha256": None,
        "fallback_reason": reason or "No known platform font file was found.",
    }


def resolve_font(*, allow_download: bool = True) -> Dict[str, Any]:
    target = cached_font_path()
    if valid_smiley_font(target):
        source = "cached"
    elif allow_download and os.environ.get("CHAT_ANIMATION_DISABLE_FONT_DOWNLOAD") != "1":
        try:
            download_smiley_font(target)
            source = "downloaded-cache"
        except SkillError as exc:
            return system_fallback(str(exc))
    else:
        reason = (
            "Font download was disabled."
            if os.environ.get("CHAT_ANIMATION_DISABLE_FONT_DOWNLOAD") == "1"
            else "Smiley Sans is not cached yet."
        )
        return system_fallback(reason)
    return {
        "id": FONT_ID,
        "display_name": FONT_DISPLAY_NAME,
        "family": FONT_FAMILY,
        "version": FONT_VERSION,
        "source": source,
        "file": str(target.resolve()),
        "sha256": FONT_FILE_SHA256,
        "license": "SIL Open Font License 1.1",
        "download_url": FONT_ARCHIVE_URL,
        "archive_sha256": FONT_ARCHIVE_SHA256,
    }


def font_status() -> Dict[str, Any]:
    selection = resolve_font(allow_download=False)
    return {
        "default": FONT_DISPLAY_NAME,
        "version": FONT_VERSION,
        "cached": selection.get("id") == FONT_ID,
        "cache_path": str(cached_font_path()),
        "available_now": selection,
    }


def initialize_project_font(project: Path) -> Dict[str, Any]:
    selection = resolve_font(allow_download=True)
    selection = {
        "schema_version": "1.0",
        "requested": FONT_ID,
        **selection,
        "initialized_at": iso_now(),
    }
    write_json(project / FONT_SELECTION_RELATIVE, selection)
    return selection


def load_project_font(project: Path, *, retry_download: bool = True) -> Dict[str, Any]:
    path = project / FONT_SELECTION_RELATIVE
    if path.is_file():
        import json

        value = json.loads(path.read_text(encoding="utf-8"))
        source = Path(str(value.get("file") or ""))
        expected = str(value.get("sha256") or "")
        if source.is_file() and (not expected or sha256_file(source) == expected):
            return value
        if not value.get("file") and value.get("family"):
            return value
    selection = resolve_font(allow_download=retry_download)
    selection = {
        "schema_version": "1.0",
        "requested": FONT_ID,
        **selection,
        "initialized_at": iso_now(),
    }
    write_json(path, selection)
    return selection
