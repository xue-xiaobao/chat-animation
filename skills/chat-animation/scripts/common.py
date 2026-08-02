#!/usr/bin/env python3
"""Shared helpers for the chat-animation skill.

The module intentionally uses only the Python standard library. FFmpeg and
FFprobe are called as external media tools.
"""

from __future__ import annotations

import hashlib
import getpass
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


AGNES_LEGACY_TOKEN_NAMES = (
    "AGNES_API_KEY",
    "AGNES_API_TOKEN",
    "APIHUB_AGNES_API_KEY",
)
AGNES_GLOBAL_TOKEN_NAMES = ("AGNES_GLOBAL_API_KEY",) + AGNES_LEGACY_TOKEN_NAMES
AGNES_CN_TOKEN_NAMES = ("AGNES_CN_API_KEY",)
AGNES_TOKEN_NAMES = AGNES_GLOBAL_TOKEN_NAMES
AGNES_REGIONS = ("global", "cn")
AGNES_BASE_URLS = {
    "global": "https://apihub.agnes-ai.com",
    "cn": "https://api.agnes-ai.cn",
}
MIMO_TOKEN_NAMES = ("MIMO_API_KEY",)
STAGES = ("director", "visual", "motion", "audio", "composition")
STAGE_NUMBERS = {stage: index + 1 for index, stage in enumerate(STAGES)}
SAMPLE_STAGES = ("visual", "motion", "audio")
KEYCHAIN_SERVICES = {
    "AGNES_GLOBAL_API_KEY": "chat-animation/AGNES_GLOBAL_API_KEY",
    "AGNES_CN_API_KEY": "chat-animation/AGNES_CN_API_KEY",
    "AGNES_API_KEY": "chat-animation/AGNES_API_KEY",
    "AGNES_API_TOKEN": "chat-animation/AGNES_API_KEY",
    "APIHUB_AGNES_API_KEY": "chat-animation/AGNES_API_KEY",
    "MIMO_API_KEY": "chat-animation/MIMO_API_KEY",
}


class SkillError(RuntimeError):
    """A user-actionable workflow error."""


class ProviderError(SkillError):
    """A provider HTTP or response-contract error."""

    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillError(f"Required JSON is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SkillError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_name = handle.name
    os.replace(temp_name, path)


def token_value(names: Sequence[str]) -> Tuple[Optional[str], Optional[str]]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return name, value
    if os.environ.get("CHAT_ANIMATION_DISABLE_KEYCHAIN") == "1":
        return None, None
    security = shutil.which("security")
    if not security:
        return None, None
    account = os.environ.get("USER") or getpass.getuser()
    for name in names:
        service = KEYCHAIN_SERVICES.get(name)
        if not service:
            continue
        completed = subprocess.run(
            [
                security,
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        value = (completed.stdout or "").strip()
        if completed.returncode == 0 and value:
            return name, value
    return None, None


def agnes_region(value: Optional[str] = None) -> str:
    selected = str(value or os.environ.get("CHAT_ANIMATION_AGNES_REGION") or "").strip().lower()
    if not selected:
        cn_name, _ = token_value(AGNES_CN_TOKEN_NAMES)
        global_name, _ = token_value(AGNES_GLOBAL_TOKEN_NAMES)
        if cn_name and global_name:
            raise SkillError(
                "Both Agnes Global and CN credentials are configured. Select one via "
                "--agnes-region or CHAT_ANIMATION_AGNES_REGION."
            )
        selected = "cn" if cn_name else "global"
    if selected not in AGNES_REGIONS:
        raise SkillError(
            "Agnes region must be 'global' or 'cn' via --agnes-region or "
            "CHAT_ANIMATION_AGNES_REGION."
        )
    return selected


def agnes_token_names(region: str) -> Sequence[str]:
    if region == "cn":
        return AGNES_CN_TOKEN_NAMES
    if region == "global":
        return AGNES_GLOBAL_TOKEN_NAMES
    raise SkillError(f"Unsupported Agnes region: {region}")


def agnes_base_url(region: str) -> str:
    override = os.environ.get("CHAT_ANIMATION_AGNES_BASE_URL")
    if not override:
        suffix = "CN" if region == "cn" else "GLOBAL"
        override = os.environ.get(f"CHAT_ANIMATION_AGNES_{suffix}_BASE_URL")
    return str(override or AGNES_BASE_URLS[region]).rstrip("/")


def require_token(names: Sequence[str], provider: str) -> str:
    _, value = token_value(names)
    if not value:
        raise SkillError(
            f"{provider} API token is missing. Run project.py preflight for setup guidance."
        )
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def slugify(value: str, fallback: str = "animation") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:64] or fallback


def project_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise SkillError(f"Project directory does not exist: {path}")
    if not (path / "request.json").is_file():
        raise SkillError(f"Not a chat-animation project (request.json missing): {path}")
    return path


def project_approval_mode(project: Path) -> str:
    request = load_json(project / "request.json")
    mode = str(request.get("approval_mode") or "human-gated")
    if mode not in ("human-gated", "full-auto"):
        raise SkillError(f"Unsupported approval_mode in request.json: {mode}")
    return mode


def is_full_auto(project: Path) -> bool:
    return project_approval_mode(project) == "full-auto"


def resolve_project_file(project: Path, relative: str) -> Path:
    candidate = (project / relative).resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError as exc:
        raise SkillError(f"Path escapes project directory: {relative}") from exc
    return candidate


def relative_to_project(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise SkillError(f"Artifact is outside project: {path}") from exc


def file_record(project: Path, path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise SkillError(f"Artifact is missing: {path}")
    return {
        "path": relative_to_project(project, path),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def run(
    command: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def command_path(name: str) -> Optional[str]:
    return shutil.which(name)


def ffprobe(path: Path) -> Dict[str, Any]:
    if not command_path("ffprobe"):
        raise SkillError("ffprobe is required but was not found")
    completed = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SkillError(f"ffprobe returned invalid JSON for {path}") from exc


def media_duration(path: Path) -> float:
    data = ffprobe(path)
    value = data.get("format", {}).get("duration")
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise SkillError(f"Could not determine duration: {path}") from exc
    if duration <= 0:
        raise SkillError(f"Media duration must be positive: {path}")
    return duration


def parse_rate(value: Any) -> float:
    if not isinstance(value, str):
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def image_dimensions(path: Path) -> Tuple[int, int]:
    streams = ffprobe(path).get("streams", [])
    for stream in streams:
        if stream.get("codec_type") == "video":
            return int(stream.get("width") or 0), int(stream.get("height") or 0)
    raise SkillError(f"No image/video stream found: {path}")


def media_summary(path: Path) -> Dict[str, Any]:
    data = ffprobe(path)
    streams = data.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    return {
        "duration": float(data.get("format", {}).get("duration") or 0),
        "video": video,
        "audio": audio,
    }


def decode_check(path: Path) -> None:
    if not command_path("ffmpeg"):
        raise SkillError("ffmpeg is required but was not found")
    completed = run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[-1000:]
        raise SkillError(f"Media decode check failed for {path}: {detail}")


def http_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "chat-animation-skill/1.0",
    }
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        text = raw.decode("utf-8", errors="replace")[:4000]
        raise ProviderError(
            f"Provider HTTP {exc.code} for {method} {url}", exc.code, text
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Provider request failed for {method} {url}: {exc}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        excerpt = raw.decode("utf-8", errors="replace")[:1000]
        raise ProviderError(
            f"Provider returned non-JSON for {method} {url}: {excerpt}"
        ) from exc
    if not isinstance(value, dict):
        raise ProviderError(f"Provider returned a non-object JSON response: {url}")
    return value


def download(url: str, output: Path, timeout: int = 300) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "chat-animation-skill/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with tempfile.NamedTemporaryFile(
                "wb",
                dir=str(output.parent),
                prefix=f".{output.name}.",
                suffix=".part",
                delete=False,
            ) as handle:
                shutil.copyfileobj(response, handle)
                temp_name = handle.name
    except Exception:
        if "temp_name" in locals():
            Path(temp_name).unlink(missing_ok=True)
        raise
    os.replace(temp_name, output)


def read_review(project: Path, stage: str) -> Optional[Dict[str, Any]]:
    number = STAGE_NUMBERS[stage]
    path = project / "reviews" / f"{number:02d}-{stage}.json"
    if not path.is_file():
        return None
    return load_json(path)


def review_path(project: Path, stage: str) -> Path:
    return project / "reviews" / f"{STAGE_NUMBERS[stage]:02d}-{stage}.json"


def sample_review_path(project: Path, stage: str) -> Path:
    if stage not in SAMPLE_STAGES:
        raise SkillError(f"Stage '{stage}' does not have a sample gate")
    return project / "reviews" / f"{STAGE_NUMBERS[stage]:02d}-{stage}-sample.json"


def read_sample_review(project: Path, stage: str) -> Optional[Dict[str, Any]]:
    path = sample_review_path(project, stage)
    return load_json(path) if path.is_file() else None


def stage_manifest_path(project: Path, stage: str) -> Path:
    if stage not in SAMPLE_STAGES:
        raise SkillError(f"Stage '{stage}' does not have a scene manifest")
    return project / stage / f"{stage}-manifest.json"


def manifest_scene_entry(project: Path, stage: str, scene_id: str) -> Dict[str, Any]:
    manifest = load_json(stage_manifest_path(project, stage))
    for item in listify(manifest.get("scenes")):
        if isinstance(item, dict) and item.get("id") == scene_id:
            return item
    if stage == "motion":
        matches = [
            item
            for item in listify(manifest.get("scenes"))
            if isinstance(item, dict)
            and item.get("scene_id") == scene_id
            and item.get("kind") in ("content", "terminal-content")
        ]
        if len(matches) == 1:
            return matches[0]
    raise SkillError(f"Scene {scene_id} is missing from {stage}-manifest.json")


def sample_entry_sha256(project: Path, stage: str, scene_id: str) -> str:
    entry = manifest_scene_entry(project, stage, scene_id)
    canonical = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(canonical)


def require_sample_approved(project: Path, stage: str) -> Dict[str, Any]:
    if is_full_auto(project):
        return {"approval_mode": "full-auto", "stage": stage, "gate": "sample-skipped"}
    review = read_sample_review(project, stage)
    if not review:
        raise SkillError(
            f"Stage '{stage}' sample has not been human-approved. Generate and review "
            "one scene before producing the remaining scenes."
        )
    if review.get("human_review", {}).get("status") != "approved":
        raise SkillError(f"Stage '{stage}' sample approval is not active")
    scene_id = str(review.get("scene_id", ""))
    if not scene_id or sample_entry_sha256(project, stage, scene_id) != review.get(
        "sample_entry_sha256"
    ):
        raise SkillError(
            f"Stage '{stage}' sample approval is stale because its manifest entry changed"
        )
    for item in listify(review.get("approved_artifacts")):
        relative = item.get("path") if isinstance(item, dict) else None
        if not isinstance(relative, str):
            raise SkillError(f"Invalid artifact record in {sample_review_path(project, stage)}")
        path = resolve_project_file(project, relative)
        if not path.is_file() or sha256_file(path) != item.get("sha256"):
            raise SkillError(
                f"Stage '{stage}' sample approval is stale; artifact changed: {relative}"
            )
    return review


def enforce_sample_generation_gate(
    project: Path, stage: str, requested_scene_ids: Sequence[str]
) -> None:
    if is_full_auto(project):
        return
    requested = list(dict.fromkeys(requested_scene_ids))
    if not requested:
        raise SkillError("At least one scene is required")
    try:
        require_sample_approved(project, stage)
        return
    except SkillError as approval_error:
        review = read_sample_review(project, stage)
        manifest_path = stage_manifest_path(project, stage)
        existing: List[str] = []
        if manifest_path.is_file():
            manifest = load_json(manifest_path)
            existing = [
                str(item.get("id"))
                for item in listify(manifest.get("scenes"))
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        sample_scene = (
            str(review.get("scene_id"))
            if review and isinstance(review.get("scene_id"), str)
            else (existing[0] if len(existing) == 1 else "")
        )
        if len(requested) == 1 and (
            not existing or (sample_scene and requested[0] == sample_scene)
        ):
            return
        raise SkillError(
            f"{approval_error} Only one sample scene may be generated or regenerated "
            "before approval; batch generation and additional scenes are blocked."
        ) from approval_error


def review_is_approved(project: Path, stage: str) -> bool:
    review = read_review(project, stage)
    return bool(
        review
        and review.get("self_review", {}).get("status") == "passed"
        and review.get("human_review", {}).get("status") == "approved"
    )


def require_approved(project: Path, stage: str) -> Dict[str, Any]:
    stage_index = STAGES.index(stage)
    if stage_index:
        try:
            require_approved(project, STAGES[stage_index - 1])
        except SkillError as exc:
            raise SkillError(
                f"Stage '{stage}' is stale because its upstream approval is not active: {exc}"
            ) from exc
    review = read_review(project, stage)
    if not review:
        raise SkillError(f"Stage '{stage}' has not been human-approved")
    human_approved = review.get("human_review", {}).get("status") == "approved"
    auto_completed = review.get("automation_review", {}).get("status") == "completed"
    if not human_approved and not auto_completed:
        raise SkillError(f"Stage '{stage}' approval is not active")
    for item in review.get("approved_artifacts", []):
        relative = item.get("path")
        if not isinstance(relative, str):
            raise SkillError(f"Invalid artifact record in {review_path(project, stage)}")
        path = resolve_project_file(project, relative)
        if not path.is_file():
            raise SkillError(
                f"Approved stage '{stage}' is stale; artifact is missing: {relative}"
            )
        if sha256_file(path) != item.get("sha256"):
            raise SkillError(
                f"Approved stage '{stage}' is stale; artifact changed: {relative}"
            )
    return review


def stage_scene_ids(script: Dict[str, Any]) -> List[str]:
    scenes = script.get("scenes")
    if not isinstance(scenes, list):
        raise SkillError("script.json.scenes must be an array")
    values: List[str] = []
    for scene in scenes:
        if not isinstance(scene, dict) or not isinstance(scene.get("id"), str):
            raise SkillError("Every scene must be an object with a string id")
        values.append(scene["id"])
    return values


def find_scene(script: Dict[str, Any], scene_id: str) -> Dict[str, Any]:
    for scene in script.get("scenes", []):
        if isinstance(scene, dict) and scene.get("id") == scene_id:
            return scene
    raise SkillError(f"Scene not found in script.json: {scene_id}")


def listify(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []
