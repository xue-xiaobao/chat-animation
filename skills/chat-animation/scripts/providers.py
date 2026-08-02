#!/usr/bin/env python3
"""Portable visual registration, Agnes generation, and MiMo TTS adapters."""

from __future__ import annotations

import argparse
import base64
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common import (
    MIMO_TOKEN_NAMES,
    ProviderError,
    SkillError,
    agnes_base_url,
    agnes_region,
    agnes_token_names,
    command_path,
    download,
    enforce_sample_generation_gate,
    ffprobe,
    file_record,
    find_scene,
    http_json,
    image_dimensions,
    is_full_auto,
    iso_now,
    listify,
    load_json,
    media_duration,
    project_path,
    relative_to_project,
    require_approved,
    require_sample_approved,
    require_token,
    resolve_project_file,
    run,
    sha256_file,
    sha256_text,
    stage_scene_ids,
    write_json,
)


MIMO_BASE_URL = os.environ.get(
    "CHAT_ANIMATION_MIMO_BASE_URL", "https://api.xiaomimimo.com"
).rstrip("/")
AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"
AGNES_VIDEO_MODEL = "agnes-video-v2.0"
MIMO_PRESET_MODEL = "mimo-v2.5-tts"
MIMO_VOICECLONE_MODEL = "mimo-v2.5-tts-voiceclone"
DEFAULT_AGNES_VIDEO_FRAMES = 169
MIN_AGNES_CONTENT_FRAMES = 81
MAX_AGNES_VIDEO_FRAMES = 441
DEFAULT_MIMO_VOICE = "白桦"
DEFAULT_MIMO_CONTEXT = (
    "自然清晰的中文金融科普解说，成熟可信，语速中等略快，停顿克制；"
    "重点词轻微强调，不夸张，不播报引号。"
)
DEFAULT_VOICE_SECONDS_PER_CHARACTER = 0.215
MIMO_MODEL = MIMO_PRESET_MODEL
FRAME_POLICIES = (
    "distinct-first-end",
    "shared-hero-frame",
)


def project_agnes_config(project: Path) -> Dict[str, str]:
    request = load_json(project / "request.json")
    saved = request.get("agnes")
    if isinstance(saved, dict):
        region = agnes_region(str(saved.get("region") or ""))
        base_url = str(saved.get("base_url") or agnes_base_url(region)).rstrip("/")
    else:
        region = agnes_region()
        base_url = agnes_base_url(region)
    return {"region": region, "base_url": base_url}


def require_project_agnes(project: Path) -> Tuple[Dict[str, str], str]:
    config = project_agnes_config(project)
    token = require_token(agnes_token_names(config["region"]), f"Agnes {config['region']}")
    return config, token


def project_frame_policy(project: Path) -> str:
    selection = load_json(project / "state" / "style-selection.json")
    # Projects created before frame policies existed used distinct keyframes.
    policy = str(selection.get("frame_policy") or "distinct-first-end").strip()
    if policy not in FRAME_POLICIES:
        raise SkillError(f"Invalid project frame policy: {policy}")
    return policy


def next_run_dir(root: Path, scene_id: str) -> Path:
    scene_root = root / "runs" / scene_id
    scene_root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 100):
        candidate = scene_root / f"v{number:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise SkillError(f"Could not allocate a provider run for scene {scene_id}")


def normalize_image(source: Path, output: Path, width: int = 1280, height: int = 720) -> None:
    if not command_path("ffmpeg"):
        raise SkillError("ffmpeg is required to normalize keyframes")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            ),
            "-frames:v",
            "1",
            str(output),
        ]
    )


def build_image_contact_sheet(images: Sequence[Path], output: Path) -> None:
    if not images:
        raise SkillError("No images were provided for the contact sheet")
    if len(images) == 1:
        run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(images[0]),
                "-vf",
                "scale=640:360:force_original_aspect_ratio=increase,crop=640:360",
                "-frames:v",
                "1",
                str(output),
            ]
        )
        return
    columns = min(4, len(images))
    rows = int(math.ceil(len(images) / columns))
    width, height = 320, 180
    command: List[str] = ["ffmpeg", "-y", "-v", "error"]
    for image in images:
        command.extend(["-i", str(image)])
    filters = []
    labels = []
    for index in range(len(images)):
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[v{index}]"
        )
        labels.append(f"[v{index}]")
    layout = []
    for index in range(len(images)):
        x = (index % columns) * width
        y = (index // columns) * height
        layout.append(f"{x}_{y}")
    filters.append(
        "".join(labels)
        + f"xstack=inputs={len(images)}:layout={'|'.join(layout)}:"
        + "fill=0x111111[out]"
    )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-frames:v",
            "1",
            str(output),
        ]
    )
    run(command)


def visual_manifest(project: Path) -> Dict[str, Any]:
    path = project / "visual" / "visual-manifest.json"
    if path.is_file():
        return load_json(path)
    return {
        "schema_version": "1.0",
        "provider": "mixed",
        "scenes": [],
        "contact_sheet": "visual/contact-sheet.jpg",
    }


def upsert_scene(manifest: Dict[str, Any], value: Dict[str, Any]) -> None:
    scenes = listify(manifest.get("scenes"))
    result = []
    replaced = False
    for item in scenes:
        if isinstance(item, dict) and item.get("id") == value.get("id"):
            result.append(value)
            replaced = True
        else:
            result.append(item)
    if not replaced:
        result.append(value)
    result.sort(key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else "")
    manifest["scenes"] = result


def register_visual(
    project: Path,
    scene_id: str,
    end_source: Path,
    *,
    first_source: Path,
    provider: str,
    model: str,
    provider_record: Optional[Path] = None,
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    require_approved(project, "director")
    enforce_sample_generation_gate(project, "visual", [scene_id])
    script = load_json(project / "script.json")
    scene = find_scene(script, scene_id)
    if not first_source.is_file():
        raise SkillError(f"First frame source is missing: {first_source}")
    if not end_source.is_file():
        raise SkillError(f"End frame source is missing: {end_source}")
    frame_policy = project_frame_policy(project)
    frames_match = sha256_file(first_source) == sha256_file(end_source)
    if frame_policy == "distinct-first-end" and frames_match:
        raise SkillError(
            f"Scene {scene_id} first and end frames are identical; provide two "
            "visually distinct content keyframes"
        )
    if frame_policy == "shared-hero-frame" and not frames_match:
        raise SkillError(
            f"Scene {scene_id} uses shared-hero-frame; first and end must be "
            "the same image"
        )
    manifest = visual_manifest(project)
    run_dir = run_dir or next_run_dir(project / "visual", scene_id)
    if frame_policy == "shared-hero-frame":
        original_first = run_dir / f"hero-original{first_source.suffix.lower() or '.img'}"
        shutil.copy2(first_source, original_first)
        first_output = project / "visual" / f"{scene_id}-hero.png"
        normalize_image(original_first, first_output)
        end_output = first_output
    else:
        original_first = run_dir / f"first-original{first_source.suffix.lower() or '.img'}"
        original_end = run_dir / f"end-original{end_source.suffix.lower() or '.img'}"
        shutil.copy2(first_source, original_first)
        shutil.copy2(end_source, original_end)
        first_output = project / "visual" / f"{scene_id}-first.png"
        end_output = project / "visual" / f"{scene_id}-end.png"
        normalize_image(original_first, first_output)
        normalize_image(original_end, end_output)

    width, height = image_dimensions(end_output)
    entry = {
        "id": scene_id,
        "provider": provider,
        "model": model,
        "frame_policy": frame_policy,
        "first_frame": relative_to_project(project, first_output),
        "end_frame": relative_to_project(project, end_output),
        "first_frame_prompt_sha256": sha256_text(
            str(scene.get("first_frame_prompt", "")).strip()
        ),
        "end_frame_prompt_sha256": sha256_text(
            str(scene.get("image_prompt", "")).strip()
        ),
        "provider_record": (
            relative_to_project(project, provider_record)
            if provider_record and provider_record.is_file()
            else None
        ),
        "width": width,
        "height": height,
        "qa": {
            "first_frame_meaningful": False,
            "metaphor_readable": False,
            "anatomy_valid": False,
            "no_unwanted_text": False,
            "caption_safe": False,
            "note": "Agent must inspect the actual image before setting these fields true.",
        },
    }
    upsert_scene(manifest, entry)
    keyframe_images = []
    seen_keyframes = set()
    for item in listify(manifest.get("scenes")):
        if not isinstance(item, dict):
            continue
        for field in ("first_frame", "end_frame"):
            relative = item.get(field)
            if isinstance(relative, str):
                path = resolve_project_file(project, relative)
                if path.is_file() and path not in seen_keyframes:
                    keyframe_images.append(path)
                    seen_keyframes.add(path)
    contact_path = project / "visual" / "contact-sheet.jpg"
    build_image_contact_sheet(keyframe_images, contact_path)
    manifest["contact_sheet"] = relative_to_project(project, contact_path)
    write_json(project / "visual" / "visual-manifest.json", manifest)
    return entry


def extract_image_url(data: Dict[str, Any]) -> str:
    candidates: List[str] = []
    direct = data.get("image_url")
    if isinstance(direct, str):
        candidates.append(direct)
    for item in listify(data.get("data")):
        if isinstance(item, dict):
            for key in ("url", "image_url"):
                value = item.get(key)
                if isinstance(value, str):
                    candidates.append(value)
    for candidate in candidates:
        if candidate.startswith(("http://", "https://")):
            return candidate
    raise ProviderError("Agnes image response did not contain a downloadable URL")


def cmd_register_visual(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    entry = register_visual(
        project,
        args.scene,
        Path(args.end).expanduser().resolve(),
        first_source=Path(args.first).expanduser().resolve(),
        provider=args.provider,
        model=args.model,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def request_agnes_image(
    token: str, base_url: str, prompt: str, output: Path, *, timeout: int
) -> Dict[str, Any]:
    payload = {
        "model": AGNES_IMAGE_MODEL,
        "prompt": prompt,
        "size": "1280x720",
        "extra_body": {"response_format": "url"},
    }
    response = http_json(
        "POST",
        f"{base_url}/v1/images/generations",
        token=token,
        payload=payload,
        timeout=timeout,
    )
    image_url = extract_image_url(response)
    download(image_url, output, timeout=timeout)
    return {
        "output_url": image_url,
        "response_summary": {
            "created": response.get("created"),
            "usage": response.get("usage"),
        },
    }


def cmd_agnes_image(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    require_approved(project, "director")
    enforce_sample_generation_gate(project, "visual", [args.scene])
    agnes, token = require_project_agnes(project)
    script = load_json(project / "script.json")
    scene = find_scene(script, args.scene)
    frame_policy = project_frame_policy(project)
    first_prompt = str(scene.get("first_frame_prompt", "")).strip()
    end_prompt = str(scene.get("image_prompt", "")).strip()
    if not first_prompt:
        raise SkillError(f"Scene {args.scene} has no first_frame_prompt")
    if not end_prompt:
        raise SkillError(f"Scene {args.scene} has no image_prompt")
    run_dir = next_run_dir(project / "visual", args.scene)
    provider_path = run_dir / "provider.json"
    request_summary = {
        "model": AGNES_IMAGE_MODEL,
        "size": "1280x720",
        "frame_policy": frame_policy,
        "frames": {
            "first": {"prompt_sha256": sha256_text(first_prompt)},
            "end": {"prompt_sha256": sha256_text(end_prompt)},
        },
    }
    record: Dict[str, Any] = {
        "provider": "agnes",
        "agnes": agnes,
        "model": AGNES_IMAGE_MODEL,
        "status": "submitting",
        "created_at": iso_now(),
        "request": request_summary,
    }
    write_json(provider_path, record)
    first_download = run_dir / (
        "hero-download" if frame_policy == "shared-hero-frame" else "first-download"
    )
    end_download = (
        first_download
        if frame_policy == "shared-hero-frame"
        else run_dir / "end-download"
    )
    try:
        if frame_policy == "shared-hero-frame":
            record["status"] = "submitting-hero"
            write_json(provider_path, record)
            hero_result = request_agnes_image(
                token, agnes["base_url"], end_prompt, first_download, timeout=args.timeout
            )
            record["outputs"] = {
                "hero": hero_result,
                "reuse": {"first": "hero", "end": "hero"},
            }
        else:
            record["status"] = "submitting-first"
            write_json(provider_path, record)
            first_result = request_agnes_image(
                token, agnes["base_url"], first_prompt, first_download, timeout=args.timeout
            )
            record["outputs"] = {"first": first_result}
            record["status"] = "submitting-end"
            write_json(provider_path, record)
            end_result = request_agnes_image(
                token, agnes["base_url"], end_prompt, end_download, timeout=args.timeout
            )
            record["outputs"]["end"] = end_result
        record.update(
            {
                "status": "completed",
                "completed_at": iso_now(),
            }
        )
        write_json(provider_path, record)
    except Exception as exc:
        record.update({"status": "failed", "failed_at": iso_now(), "error": str(exc)})
        write_json(provider_path, record)
        raise
    entry = register_visual(
        project,
        args.scene,
        end_download,
        first_source=first_download,
        provider="agnes",
        model=AGNES_IMAGE_MODEL,
        provider_record=provider_path,
        run_dir=run_dir,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def video_status(data: Dict[str, Any]) -> str:
    for key in ("status", "state"):
        value = data.get(key)
        if isinstance(value, str):
            return value.lower()
    nested = data.get("data")
    if isinstance(nested, dict):
        return video_status(nested)
    return "unknown"


def lookup_id(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    for container in (data, data.get("data")):
        if not isinstance(container, dict):
            continue
        value = container.get("video_id")
        if isinstance(value, str) and value:
            return "video_id", value
    for container in (data, data.get("data")):
        if not isinstance(container, dict):
            continue
        value = container.get("task_id") or container.get("id")
        if isinstance(value, str) and value:
            return "task_id", value
    return None, None


def extract_video_url(data: Dict[str, Any]) -> Optional[str]:
    preferred = ("video_url", "url", "remixed_from_video_id")

    def visit(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            for key in preferred:
                item = value.get(key)
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    return item
            for item in value.values():
                found = visit(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = visit(item)
                if found:
                    return found
        return None

    return visit(data)


def retrieve_video(
    token: str, base_url: str, kind: str, identifier: str, timeout: int
) -> Dict[str, Any]:
    if kind == "video_id":
        query = urllib.parse.urlencode(
            {"video_id": identifier, "model_name": AGNES_VIDEO_MODEL}
        )
        return http_json(
            "GET", f"{base_url}/agnesapi?{query}", token=token, timeout=timeout
        )
    quoted = urllib.parse.quote(identifier, safe="")
    return http_json(
        "GET", f"{base_url}/v1/videos/{quoted}", token=token, timeout=timeout
    )


def is_queue_full(exc: Exception) -> bool:
    text = str(exc).lower()
    if isinstance(exc, ProviderError):
        text += " " + exc.body.lower()
    return "video_queue_full" in text or "queue full" in text or (
        isinstance(exc, ProviderError) and exc.status == 503
    )


def standardize_motion(
    source: Path, output: Path, background_hex: str, fps: int = 24
) -> None:
    color = background_hex.strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        color = "000000"
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-an",
            "-vf",
            (
                "scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x{color},fps={fps}"
            ),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def build_video_contact_sheet(video: Path, output: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            "fps=1,scale=256:144,tile=7x1:padding=2:margin=2:color=0x111111",
            "-frames:v",
            "1",
            str(output),
        ]
    )


def extract_video_edge_frames(video: Path, first: Path, last: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(first),
        ]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-sseof",
            "-0.08",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(last),
        ]
    )


def motion_manifest(project: Path) -> Dict[str, Any]:
    path = project / "motion" / "motion-manifest.json"
    if path.is_file():
        return load_json(path)
    return {
        "schema_version": "1.0",
        "provider": "agnes",
        "model": AGNES_VIDEO_MODEL,
        "mode": "keyframes",
        "scenes": [],
    }


def visual_scene(project: Path, scene_id: str) -> Dict[str, Any]:
    manifest = load_json(project / "visual" / "visual-manifest.json")
    for item in listify(manifest.get("scenes")):
        if isinstance(item, dict) and item.get("id") == scene_id:
            return item
    raise SkillError(f"Scene {scene_id} is missing from visual-manifest.json")


def motion_job_specs(project: Path, script: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Resolve the motion-plan interface into concrete two-keyframe jobs.

    Legacy projects without a motion plan keep their scene-shaped jobs. New
    projects expose content/transition/fused jobs while hiding state-to-file
    resolution from the Agnes adapter.
    """
    plan_path = project / "state" / "motion-plan.json"
    if not plan_path.is_file():
        return [
            {
                "id": scene_id,
                "kind": "content",
                "scene_id": scene_id,
                "first_frame": visual_scene(project, scene_id)["first_frame"],
                "end_frame": visual_scene(project, scene_id)["end_frame"],
                "prompt": str(find_scene(script, scene_id).get("motion_prompt", "")).strip(),
                "slug": str(find_scene(script, scene_id).get("slug") or "scene"),
                "background_hex": str(
                    find_scene(script, scene_id).get("visual", {}).get("background_hex")
                    or "#000000"
                ),
                "target_duration_seconds": find_scene(script, scene_id).get(
                    "target_duration_seconds"
                ),
            }
            for scene_id in stage_scene_ids(script)
        ]

    plan = load_json(plan_path)
    states = {
        str(item.get("id")): item
        for item in listify(plan.get("states"))
        if isinstance(item, dict) and item.get("id")
    }
    values: List[Dict[str, Any]] = []
    for item in listify(plan.get("jobs")):
        if not isinstance(item, dict):
            raise SkillError("Every motion-plan job must be an object")
        job_id = str(item.get("id") or "").strip()
        kind = str(item.get("kind") or "").strip()
        first_state = states.get(str(item.get("first")))
        end_state = states.get(str(item.get("end")))
        if not job_id or not kind or not first_state or not end_state:
            raise SkillError(f"Invalid motion-plan job: {item}")
        first_scene_id = str(first_state.get("scene_id") or "")
        end_scene_id = str(end_state.get("scene_id") or "")
        first_visual = visual_scene(project, first_scene_id)
        end_visual = visual_scene(project, end_scene_id)
        first_role = str(first_state.get("role") or "")
        end_role = str(end_state.get("role") or "")
        first_field = "first_frame" if first_role.endswith("first") else "end_frame"
        end_field = "first_frame" if end_role.endswith("first") else "end_frame"
        scene_id = str(item.get("scene_id") or first_scene_id)
        scene = find_scene(script, scene_id)
        prompt = str(item.get("motion_prompt") or "").strip()
        if not prompt and kind in ("content", "terminal-content"):
            prompt = str(scene.get("motion_prompt") or "").strip()
        if not prompt:
            raise SkillError(f"Motion-plan job {job_id} has no motion_prompt")
        values.append(
            {
                "id": job_id,
                "kind": kind,
                "scene_id": scene_id,
                "from_scene": item.get("from_scene") or first_scene_id,
                "to_scene": item.get("to_scene") or end_scene_id,
                "first_frame": first_visual[first_field],
                "end_frame": end_visual[end_field],
                "prompt": prompt,
                "slug": str(item.get("slug") or job_id),
                "background_hex": str(
                    scene.get("visual", {}).get("background_hex") or "#000000"
                ),
                "target_duration_seconds": item.get("target_duration_seconds"),
            }
        )
    return values


def narration_character_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))


def default_voice_timing_profile() -> Dict[str, Any]:
    profile = {
        "schema_version": "1.0",
        "source": "built-in-default",
        "model": MIMO_PRESET_MODEL,
        "mode": "preset",
        "voice": DEFAULT_MIMO_VOICE,
        "voice_reference_sha256": None,
        "context": DEFAULT_MIMO_CONTEXT,
        "context_sha256": sha256_text(DEFAULT_MIMO_CONTEXT),
        "seconds_per_character": DEFAULT_VOICE_SECONDS_PER_CHARACTER,
        "characters_per_second": round(
            1.0 / DEFAULT_VOICE_SECONDS_PER_CHARACTER, 6
        ),
    }
    profile["profile_id"] = voice_timing_profile_id(
        profile["model"],
        profile["mode"],
        profile["voice"],
        profile["voice_reference_sha256"],
        profile["context_sha256"],
    )
    return profile


def voice_timing_profile_id(
    model: str,
    mode: str,
    voice: str,
    reference_hash: Optional[str],
    context_hash: str,
) -> str:
    return sha256_text(
        json.dumps(
            {
                "model": model,
                "mode": mode,
                "voice": voice,
                "voice_reference_sha256": reference_hash,
                "context_sha256": context_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def voice_timing_cache_path() -> Path:
    configured = os.environ.get("CHAT_ANIMATION_VOICE_TIMING_CACHE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".config" / "chat-animation" / "voice-timing-profiles.json"


def load_voice_timing_cache() -> Dict[str, Any]:
    path = voice_timing_cache_path()
    if not path.is_file():
        return {"schema_version": "1.0", "profiles": {}}
    value = load_json(path)
    if not isinstance(value.get("profiles"), dict):
        raise SkillError(f"Invalid voice timing cache: {path}")
    return value


def voice_timing_profile(project: Path) -> Dict[str, Any]:
    path = project / "state" / "voice-timing.json"
    if not path.is_file():
        return default_voice_timing_profile()
    value = load_json(path)
    try:
        seconds_per_character = float(value.get("seconds_per_character"))
    except (TypeError, ValueError):
        seconds_per_character = 0.0
    if seconds_per_character <= 0:
        raise SkillError(f"Invalid voice timing profile: {path}")
    return value


def nearest_agnes_frame_count(target_seconds: float) -> int:
    target_frames = max(1.0, float(target_seconds) * 24.0)
    candidates = range(MIN_AGNES_CONTENT_FRAMES, MAX_AGNES_VIDEO_FRAMES + 1, 8)
    return min(candidates, key=lambda value: (abs(value - target_frames), -value))


def motion_duration_plan(
    project: Path,
    job: Dict[str, Any],
    script: Dict[str, Any],
    explicit_num_frames: Optional[int],
) -> Dict[str, Any]:
    if explicit_num_frames is not None:
        return {
            "source": "cli-override",
            "narration_characters": None,
            "seconds_per_character": None,
            "target_duration_seconds": round(explicit_num_frames / 24.0, 6),
            "num_frames": explicit_num_frames,
            "raw_duration_seconds": round(explicit_num_frames / 24.0, 6),
        }
    if str(job.get("kind") or "") not in ("content", "terminal-content"):
        return {
            "source": "transition-default",
            "narration_characters": None,
            "seconds_per_character": None,
            "target_duration_seconds": round(DEFAULT_AGNES_VIDEO_FRAMES / 24.0, 6),
            "num_frames": DEFAULT_AGNES_VIDEO_FRAMES,
            "raw_duration_seconds": round(DEFAULT_AGNES_VIDEO_FRAMES / 24.0, 6),
        }
    scene = find_scene(script, str(job.get("scene_id") or ""))
    character_count = narration_character_count(str(scene.get("narration") or ""))
    configured_target = job.get("target_duration_seconds")
    try:
        target_seconds = float(configured_target)
    except (TypeError, ValueError):
        target_seconds = 0.0
    source = "motion-plan"
    if target_seconds <= 0:
        timing = voice_timing_profile(project)
        seconds_per_character = float(timing["seconds_per_character"])
        target_seconds = character_count * seconds_per_character
        source = f"voice-timing:{timing.get('source') or 'unknown'}"
    else:
        timing = voice_timing_profile(project)
        seconds_per_character = float(timing["seconds_per_character"])
    if target_seconds <= 0:
        target_seconds = DEFAULT_AGNES_VIDEO_FRAMES / 24.0
        source = "content-default"
    num_frames = nearest_agnes_frame_count(target_seconds)
    return {
        "source": source,
        "narration_characters": character_count,
        "seconds_per_character": seconds_per_character,
        "voice": timing.get("voice"),
        "voice_timing_source": timing.get("source"),
        "target_duration_seconds": round(target_seconds, 6),
        "num_frames": num_frames,
        "raw_duration_seconds": round(num_frames / 24.0, 6),
    }


def select_motion_job(
    project: Path, script: Dict[str, Any], requested_id: str
) -> Dict[str, Any]:
    jobs = motion_job_specs(project, script)
    for item in jobs:
        if item["id"] == requested_id:
            return item
    content_matches = [
        item
        for item in jobs
        if item.get("scene_id") == requested_id and item.get("kind") == "content"
    ]
    if len(content_matches) == 1:
        return content_matches[0]
    raise SkillError(f"Motion job not found: {requested_id}")


def existing_pending_record(project: Path, manifest: Dict[str, Any], scene_id: str) -> Optional[Path]:
    active_statuses = (
        "queued",
        "in_progress",
        "queue_wait",
        "submission_intent",
        "submission_uncertain",
        "completed_remote",
    )

    def is_resumable(path: Path) -> bool:
        record = load_json(path)
        status = str(record.get("status") or "")
        if status in active_statuses:
            return True
        if status not in ("completed", "succeeded", "success"):
            return False
        # A remote completion is not a finished local run until both the raw
        # download and standardized delivery exist. Treat an interrupted
        # download/standardization as resumable so recovery never resubmits.
        raw_relative = record.get("raw_video")
        delivery_relative = record.get("delivery_video")
        if not isinstance(raw_relative, str) or not isinstance(delivery_relative, str):
            return True
        return not (
            resolve_project_file(project, raw_relative).is_file()
            and resolve_project_file(project, delivery_relative).is_file()
        )

    for item in listify(manifest.get("scenes")):
        if not isinstance(item, dict) or item.get("id") != scene_id:
            continue
        relative = item.get("provider_record")
        if not isinstance(relative, str):
            continue
        path = resolve_project_file(project, relative)
        if path.is_file() and is_resumable(path):
            return path
    scene_runs = project / "motion" / "runs" / scene_id
    if scene_runs.is_dir():
        for path in sorted(scene_runs.glob("v*/provider.json"), reverse=True):
            if is_resumable(path):
                return path
    return None


def generate_motion_scene(
    project: Path,
    scene_id: str,
    *,
    poll: bool,
    interval: int,
    timeout: int,
    num_frames: Optional[int],
    retry_uncertain: bool,
) -> Dict[str, Any]:
    agnes, token = require_project_agnes(project)
    script = load_json(project / "script.json")
    job = select_motion_job(project, script, scene_id)
    duration_plan = motion_duration_plan(project, job, script, num_frames)
    num_frames = int(duration_plan["num_frames"])
    scene_id = str(job["id"])
    first = resolve_project_file(project, str(job["first_frame"]))
    end = resolve_project_file(project, str(job["end_frame"]))
    prompt = str(job.get("prompt", "")).strip()
    if not prompt:
        raise SkillError(f"Motion job {scene_id} has no motion_prompt")
    manifest = motion_manifest(project)

    existing = None
    for item in listify(manifest.get("scenes")):
        if isinstance(item, dict) and item.get("id") == scene_id:
            existing = item
            relative_video = item.get("video")
            if isinstance(relative_video, str):
                video_path = resolve_project_file(project, relative_video)
                if (
                    video_path.is_file()
                    and item.get("prompt_sha256") == sha256_text(prompt)
                    and item.get("requested_num_frames") == num_frames
                ):
                    print(f"{scene_id}: existing motion video is current; skipping")
                    return item

    pending_path = existing_pending_record(project, manifest, scene_id)
    if pending_path:
        run_dir = pending_path.parent
        record = load_json(pending_path)
        recorded_agnes = record.get("agnes")
        if isinstance(recorded_agnes, dict) and recorded_agnes != agnes:
            raise SkillError(
                "Existing Agnes task belongs to a different region or API base URL; "
                "restore it with the project configuration that created it."
            )
        if record.get("status") == "submission_uncertain" and not retry_uncertain:
            raise SkillError(
                f"Scene {scene_id} has an uncertain prior submission. Inspect "
                f"{pending_path} and use --retry-uncertain only after approving a new call."
            )
    else:
        run_dir = next_run_dir(project / "motion", scene_id)
        pending_path = run_dir / "provider.json"
        record = {}

    kind = record.get("lookup_kind")
    identifier = record.get("lookup_id")
    if (
        record.get("status") == "submission_intent"
        and (not kind or not identifier)
        and not retry_uncertain
    ):
        raise SkillError(
            f"Scene {scene_id} stopped after writing submission_intent and has no "
            "provider ID. Treat it as uncertain; inspect the Agnes console, then "
            "use --retry-uncertain only if a new call is approved."
        )
    remote: Dict[str, Any]
    if not kind or not identifier or (
        record.get("status") == "submission_uncertain" and retry_uncertain
    ):
        request_summary = {
            "model": AGNES_VIDEO_MODEL,
            "mode": "keyframes",
            "width": 1280,
            "height": 720,
            "num_frames": num_frames,
            "frame_rate": 24,
            "duration_plan": duration_plan,
            "prompt_sha256": sha256_text(prompt),
            "input_frames": [
                {
                    "path": relative_to_project(project, first),
                    "sha256": sha256_file(first),
                },
                {
                    "path": relative_to_project(project, end),
                    "sha256": sha256_file(end),
                },
            ],
        }
        record = {
            "provider": "agnes",
            "agnes": agnes,
            "model": AGNES_VIDEO_MODEL,
            "mode": "keyframes",
            "status": "submission_intent",
            "created_at": iso_now(),
            "request": request_summary,
            "input_frames": [job["first_frame"], job["end_frame"]],
        }
        write_json(pending_path, record)
        payload = {
            "model": AGNES_VIDEO_MODEL,
            "prompt": prompt,
            "width": 1280,
            "height": 720,
            "num_frames": num_frames,
            "frame_rate": 24,
            "extra_body": {
                "image": [data_url(first), data_url(end)],
                "mode": "keyframes",
            },
        }
        attempts = 0
        while True:
            attempts += 1
            try:
                remote = http_json(
                    "POST",
                    f"{agnes['base_url']}/v1/videos",
                    token=token,
                    payload=payload,
                    timeout=timeout,
                )
                break
            except Exception as exc:
                if is_queue_full(exc) and attempts <= 10:
                    record.update(
                        {
                            "status": "queue_wait",
                            "queue_attempts": attempts,
                            "last_error": str(exc),
                            "updated_at": iso_now(),
                        }
                    )
                    write_json(pending_path, record)
                    time.sleep(interval)
                    continue
                record.update(
                    {
                        "status": (
                            "submission_uncertain"
                            if not isinstance(exc, ProviderError)
                            else "failed"
                        ),
                        "failed_at": iso_now(),
                        "error": str(exc),
                    }
                )
                write_json(pending_path, record)
                raise
        kind, identifier = lookup_id(remote)
        if not kind or not identifier:
            record.update(
                {
                    "status": "failed",
                    "failed_at": iso_now(),
                    "error": "Create response had no video_id/task_id",
                    "response": remote,
                }
            )
            write_json(pending_path, record)
            raise ProviderError("Agnes video create response had no video_id or task_id")
        record.update(
            {
                "status": video_status(remote),
                "submitted_at": iso_now(),
                "lookup_kind": kind,
                "lookup_id": identifier,
                "create_response": remote,
            }
        )
        write_json(pending_path, record)
    else:
        remote = record.get("last_response") or record.get("create_response") or {}

    if not poll and video_status(remote) not in ("completed", "succeeded", "success"):
        record["status"] = video_status(remote)
        write_json(pending_path, record)
        return {
            "id": scene_id,
            "provider_record": relative_to_project(project, pending_path),
            "status": record["status"],
        }

    started = time.time()
    while video_status(remote) not in ("completed", "succeeded", "success"):
        status = video_status(remote)
        if status in ("failed", "error", "cancelled", "canceled"):
            record.update(
                {
                    "status": "failed",
                    "failed_at": iso_now(),
                    "last_response": remote,
                }
            )
            write_json(pending_path, record)
            raise ProviderError(f"Agnes video task failed for scene {scene_id}: {remote}")
        if time.time() - started > argsafe_timeout(timeout):
            record.update({"status": status, "last_response": remote, "updated_at": iso_now()})
            write_json(pending_path, record)
            raise SkillError(f"Timed out waiting for scene {scene_id}; rerun to resume polling")
        time.sleep(interval)
        remote = retrieve_video(
            token, agnes["base_url"], str(kind), str(identifier), timeout
        )
        record.update(
            {
                "status": video_status(remote),
                "last_response": remote,
                "updated_at": iso_now(),
            }
        )
        write_json(pending_path, record)

    output_url = extract_video_url(remote)
    if not output_url:
        raise ProviderError(f"Completed Agnes task has no video URL for scene {scene_id}")
    raw_video = run_dir / "raw.mp4"
    if not raw_video.is_file():
        download(output_url, raw_video, timeout=max(timeout, 300))
    slug = str(job.get("slug") or "motion")
    delivery = project / "motion" / f"{scene_id}-{slug}.mp4"
    background = str(job.get("background_hex") or "#000000")
    standardize_motion(raw_video, delivery, background)
    contact = run_dir / "contact-sheet.jpg"
    actual_first = run_dir / "video-first-frame.jpg"
    actual_last = run_dir / "video-last-frame.jpg"
    build_video_contact_sheet(delivery, contact)
    extract_video_edge_frames(delivery, actual_first, actual_last)
    record.update(
        {
            "status": "completed",
            "completed_at": iso_now(),
            "output_url": output_url,
            "raw_video": relative_to_project(project, raw_video),
            "delivery_video": relative_to_project(project, delivery),
            "delivery_sha256": sha256_file(delivery),
        }
    )
    write_json(pending_path, record)
    entry = {
        "id": scene_id,
        "kind": job.get("kind"),
        "scene_id": job.get("scene_id"),
        "from_scene": job.get("from_scene"),
        "to_scene": job.get("to_scene"),
        "first_frame": job["first_frame"],
        "end_frame": job["end_frame"],
        "prompt_sha256": sha256_text(prompt),
        "provider_record": relative_to_project(project, pending_path),
        "raw_video": relative_to_project(project, raw_video),
        "video": relative_to_project(project, delivery),
        "contact_sheet": relative_to_project(project, contact),
        "actual_first_frame": relative_to_project(project, actual_first),
        "actual_last_frame": relative_to_project(project, actual_last),
        "width": 1280,
        "height": 720,
        "fps": 24,
        "requested_num_frames": num_frames,
        "duration_plan": duration_plan,
        "has_audio": False,
        "qa": {
            "keyframes_respected": False,
            "camera_locked": False,
            "no_mutation": False,
            "end_frame_respected": False,
            "note": "Agent must inspect the actual video before setting these fields true.",
        },
    }
    upsert_scene(manifest, entry)
    write_json(project / "motion" / "motion-manifest.json", manifest)
    return entry


def argsafe_timeout(request_timeout: int) -> int:
    return max(900, request_timeout * 10)


def cmd_agnes_video(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    require_approved(project, "visual")
    if args.num_frames is not None and (
        (args.num_frames - 1) % 8 != 0 or args.num_frames > MAX_AGNES_VIDEO_FRAMES
    ):
        raise SkillError("--num-frames must be <=441 and satisfy 8n+1")
    script = load_json(project / "script.json")
    scene_ids = (
        [str(item["id"]) for item in motion_job_specs(project, script)]
        if args.all
        else [str(select_motion_job(project, script, args.scene)["id"])]
    )
    if args.all:
        require_sample_approved(project, "motion")
    else:
        enforce_sample_generation_gate(project, "motion", scene_ids)
    results = []
    for scene_id in scene_ids:
        results.append(
            generate_motion_scene(
                project,
                scene_id,
                poll=args.poll,
                interval=args.interval,
                timeout=args.timeout,
                num_frames=args.num_frames,
                retry_uncertain=args.retry_uncertain,
            )
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def extract_audio_data(response: Dict[str, Any]) -> str:
    try:
        value = response["choices"][0]["message"]["audio"]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            "MiMo response did not contain choices[0].message.audio.data"
        ) from exc
    if not isinstance(value, str) or not value:
        raise ProviderError("MiMo returned empty audio data")
    return value


def sanitize_mimo_response(response: Dict[str, Any]) -> Dict[str, Any]:
    result = json.loads(json.dumps(response))
    try:
        audio = result["choices"][0]["message"]["audio"]
        if isinstance(audio, dict) and "data" in audio:
            raw = audio.pop("data")
            audio["data_bytes_base64"] = len(raw) if isinstance(raw, str) else None
    except (KeyError, IndexError, TypeError):
        pass
    return result


def detect_silences(path: Path, noise: str = "-38dB", minimum: float = 0.10) -> List[Dict[str, float]]:
    completed = run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise}:d={minimum}",
            "-f",
            "null",
            "-",
        ],
        capture=True,
        check=False,
    )
    starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", completed.stderr or "")]
    ends = [
        (float(end), float(duration))
        for end, duration in re.findall(
            r"silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)",
            completed.stderr or "",
        )
    ]
    values = []
    for index, (end, duration) in enumerate(ends):
        start = starts[index] if index < len(starts) else max(0.0, end - duration)
        values.append({"start": start, "end": end, "duration": duration})
    return values


def clean_audio(raw_path: Path, clean_path: Path) -> Dict[str, Any]:
    raw_duration = media_duration(raw_path)
    silences = detect_silences(raw_path)
    filter_value = (
        "silenceremove="
        "start_periods=1:"
        "start_duration=0.05:"
        "start_threshold=-38dB:"
        "start_silence=0.03:"
        "stop_periods=-1:"
        "stop_duration=0.12:"
        "stop_threshold=-38dB:"
        "stop_silence=0.16"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(raw_path),
            "-af",
            filter_value,
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(clean_path),
        ]
    )
    clean_duration = media_duration(clean_path)
    return {
        "filter": filter_value,
        "raw_duration_seconds": round(raw_duration, 6),
        "clean_duration_seconds": round(clean_duration, 6),
        "removed_seconds": round(max(0.0, raw_duration - clean_duration), 6),
        "max_detected_silence_seconds": round(
            max((item["duration"] for item in silences), default=0.0), 6
        ),
        "detected_silence_seconds": round(
            sum(item["duration"] for item in silences), 6
        ),
    }


def prepare_voice_reference(project: Path, source: Path) -> Dict[str, Any]:
    if not source.is_file():
        raise SkillError(f"Voice reference is missing: {source}")
    suffix = source.suffix.lower()
    mime_types = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
    if suffix not in mime_types:
        raise SkillError("MiMo voice cloning accepts only .mp3 or .wav reference audio")
    size = source.stat().st_size
    if size > 10 * 1024 * 1024:
        raise SkillError("MiMo voice reference exceeds the 10 MB limit")
    digest = sha256_file(source)
    target = project / "audio" / "reference" / f"voice-{digest[:12]}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or sha256_file(target) != digest:
        shutil.copy2(source, target)
    encoded = base64.b64encode(target.read_bytes()).decode("ascii")
    return {
        "path": relative_to_project(project, target),
        "sha256": digest,
        "bytes": size,
        "mime_type": mime_types[suffix],
        "data_url": f"data:{mime_types[suffix]};base64,{encoded}",
    }


def mimo_voice_config(
    project: Path, *, voice: Optional[str], voice_file: Optional[Path]
) -> Dict[str, Any]:
    if voice_file:
        reference = prepare_voice_reference(project, voice_file)
        return {
            "mode": "voiceclone",
            "model": MIMO_VOICECLONE_MODEL,
            "voice": "user-reference",
            "voice_payload": reference["data_url"],
            "voice_reference": {
                key: reference[key]
                for key in ("path", "sha256", "bytes", "mime_type")
            },
        }
    selected_voice = str(voice or DEFAULT_MIMO_VOICE).strip()
    if not selected_voice:
        raise SkillError("MiMo preset voice must not be empty")
    return {
        "mode": "preset",
        "model": MIMO_PRESET_MODEL,
        "voice": selected_voice,
        "voice_payload": selected_voice,
        "voice_reference": None,
    }


def audio_manifest(
    project: Path, voice_config: Dict[str, Any], context: str
) -> Dict[str, Any]:
    path = project / "audio" / "audio-manifest.json"
    if path.is_file():
        value = load_json(path)
        value["model"] = voice_config["model"]
        value["mode"] = voice_config["mode"]
        value["voice"] = voice_config["voice"]
        value["voice_reference"] = voice_config["voice_reference"]
        value["context"] = context
        return value
    return {
        "schema_version": "1.0",
        "provider": "mimo",
        "model": voice_config["model"],
        "mode": voice_config["mode"],
        "voice": voice_config["voice"],
        "voice_reference": voice_config["voice_reference"],
        "context": context,
        "scenes": [],
    }


def synthesize_scene(
    project: Path,
    scene_id: str,
    *,
    voice_config: Dict[str, Any],
    context: str,
    timeout: int,
) -> Dict[str, Any]:
    token = require_token(MIMO_TOKEN_NAMES, "Xiaomi MiMo")
    script = load_json(project / "script.json")
    scene = find_scene(script, scene_id)
    narration = str(scene.get("narration", "")).strip()
    narration_hash = sha256_text(narration)
    context_hash = sha256_text(context)
    model = str(voice_config["model"])
    mode = str(voice_config["mode"])
    voice = str(voice_config["voice"])
    reference = voice_config.get("voice_reference")
    reference_hash = (
        str(reference.get("sha256"))
        if isinstance(reference, dict) and reference.get("sha256")
        else None
    )
    slug = str(scene.get("slug") or "scene")
    raw_path = project / "audio" / f"{scene_id}-{slug}-raw.wav"
    clean_path = project / "audio" / f"{scene_id}-{slug}.wav"
    manifest = audio_manifest(project, voice_config, context)
    for item in listify(manifest.get("scenes")):
        if (
            isinstance(item, dict)
            and item.get("id") == scene_id
            and item.get("narration_sha256") == narration_hash
            and item.get("model") == model
            and item.get("mode") == mode
            and item.get("voice") == voice
            and item.get("voice_reference_sha256") == reference_hash
            and item.get("context_sha256") == context_hash
            and isinstance(item.get("audio"), str)
            and resolve_project_file(project, item["audio"]).is_file()
        ):
            print(f"{scene_id}: existing MiMo WAV is current; skipping")
            return item

    prior_provider_path: Optional[Path] = None
    scene_runs = project / "audio" / "runs" / scene_id
    if raw_path.is_file() and scene_runs.is_dir():
        for candidate in sorted(scene_runs.glob("v*/provider.json"), reverse=True):
            candidate_record = load_json(candidate)
            if (
                candidate_record.get("model") == model
                and candidate_record.get("mode") == mode
                and candidate_record.get("voice") == voice
                and candidate_record.get("voice_reference_sha256") == reference_hash
                and candidate_record.get("narration_sha256") == narration_hash
                and candidate_record.get("context_sha256") == context_hash
            ):
                prior_provider_path = candidate
                break
    if prior_provider_path:
        record = load_json(prior_provider_path)
        cleanup = clean_audio(raw_path, clean_path)
        record.update(
            {
                "status": "completed",
                "completed_at": iso_now(),
                "recovery": "Reused locally saved raw WAV; no second MiMo call.",
                "raw_audio": relative_to_project(project, raw_path),
                "audio": relative_to_project(project, clean_path),
                "audio_sha256": sha256_file(clean_path),
            }
        )
        record.pop("failed_at", None)
        record.pop("error", None)
        write_json(prior_provider_path, record)
        entry = {
            "id": scene_id,
            "model": model,
            "mode": mode,
            "voice": voice,
            "voice_reference_sha256": reference_hash,
            "context_sha256": context_hash,
            "narration_sha256": narration_hash,
            "raw_audio": relative_to_project(project, raw_path),
            "audio": relative_to_project(project, clean_path),
            "duration_seconds": round(media_duration(clean_path), 6),
            "provider_record": relative_to_project(project, prior_provider_path),
            "cleanup": cleanup,
            "qa": {
                "narration_verified": False,
                "natural_delivery": False,
                "note": "Agent must listen or transcribe before setting these fields true.",
            },
        }
        upsert_scene(manifest, entry)
        write_json(project / "audio" / "audio-manifest.json", manifest)
        return entry

    run_dir = next_run_dir(project / "audio", scene_id)
    provider_path = run_dir / "provider.json"
    messages = []
    if context:
        messages.append({"role": "user", "content": context})
    messages.append({"role": "assistant", "content": narration})
    payload = {
        "model": model,
        "messages": messages,
        "audio": {"format": "wav", "voice": voice_config["voice_payload"]},
    }
    record: Dict[str, Any] = {
        "provider": "mimo",
        "model": model,
        "mode": mode,
        "voice": voice,
        "voice_reference": reference,
        "voice_reference_sha256": reference_hash,
        "status": "submitting",
        "created_at": iso_now(),
        "narration_sha256": narration_hash,
        "context_sha256": context_hash,
    }
    write_json(provider_path, record)
    try:
        response = http_json(
            "POST",
            f"{MIMO_BASE_URL}/v1/chat/completions",
            token=token,
            payload=payload,
            timeout=timeout,
        )
        encoded = extract_audio_data(response)
        try:
            audio_bytes = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ProviderError("MiMo returned invalid base64 audio") from exc
        raw_path.write_bytes(audio_bytes)
        cleanup = clean_audio(raw_path, clean_path)
        record.update(
            {
                "status": "completed",
                "completed_at": iso_now(),
                "response": sanitize_mimo_response(response),
                "raw_audio": relative_to_project(project, raw_path),
                "audio": relative_to_project(project, clean_path),
                "audio_sha256": sha256_file(clean_path),
            }
        )
        write_json(provider_path, record)
    except Exception as exc:
        record.update({"status": "failed", "failed_at": iso_now(), "error": str(exc)})
        write_json(provider_path, record)
        raise
    entry = {
        "id": scene_id,
        "model": model,
        "mode": mode,
        "voice": voice,
        "voice_reference_sha256": reference_hash,
        "context_sha256": context_hash,
        "narration_sha256": narration_hash,
        "raw_audio": relative_to_project(project, raw_path),
        "audio": relative_to_project(project, clean_path),
        "duration_seconds": round(media_duration(clean_path), 6),
        "provider_record": relative_to_project(project, provider_path),
        "cleanup": cleanup,
        "qa": {
            "narration_verified": False,
            "natural_delivery": False,
            "note": "Agent must listen or transcribe before setting these fields true.",
        },
    }
    upsert_scene(manifest, entry)
    write_json(project / "audio" / "audio-manifest.json", manifest)
    return entry


def cmd_mimo_tts(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    require_approved(project, "motion")
    script = load_json(project / "script.json")
    scene_ids = stage_scene_ids(script) if args.all else [args.scene]
    if args.all:
        require_sample_approved(project, "audio")
    else:
        enforce_sample_generation_gate(project, "audio", scene_ids)
    timing = voice_timing_profile(project)
    selected_voice = args.voice
    if not selected_voice and not args.voice_file:
        if timing.get("mode") == "voiceclone":
            raise SkillError(
                "The selected cloned voice requires --voice-file for final narration."
            )
        selected_voice = str(timing.get("voice") or DEFAULT_MIMO_VOICE)
    context = str(args.context or timing.get("context") or DEFAULT_MIMO_CONTEXT)
    voice_file = Path(args.voice_file).expanduser().resolve() if args.voice_file else None
    voice_config = mimo_voice_config(
        project, voice=selected_voice, voice_file=voice_file
    )
    requested_reference = voice_config.get("voice_reference")
    requested_reference_hash = (
        requested_reference.get("sha256")
        if isinstance(requested_reference, dict)
        else None
    )
    requested_profile_id = voice_timing_profile_id(
        str(voice_config["model"]),
        str(voice_config["mode"]),
        str(voice_config["voice"]),
        requested_reference_hash,
        sha256_text(context),
    )
    if requested_profile_id != timing.get("profile_id"):
        raise SkillError(
            "Narration settings differ from the voice timing used for motion; "
            "calibrate this voice before motion generation, then regenerate affected "
            "motion clips."
        )
    if args.all and not is_full_auto(project):
        sample_review = require_sample_approved(project, "audio")
        sample_scene = str(sample_review.get("scene_id"))
        sample_entry = next(
            (
                item
                for item in listify(
                    load_json(project / "audio" / "audio-manifest.json").get("scenes")
                )
                if isinstance(item, dict) and item.get("id") == sample_scene
            ),
            {},
        )
        if (
            sample_entry.get("model") != voice_config["model"]
            or sample_entry.get("mode") != voice_config["mode"]
            or sample_entry.get("voice") != voice_config["voice"]
            or sample_entry.get("voice_reference_sha256") != requested_reference_hash
            or sample_entry.get("context_sha256") != sha256_text(context)
        ):
            raise SkillError(
                "Batch audio settings differ from the approved sample. Regenerate and "
                "re-approve one audio sample with the new voice method first."
            )
    results = []
    for scene_id in scene_ids:
        results.append(
            synthesize_scene(
                project,
                scene_id,
                voice_config=voice_config,
                context=context,
                timeout=args.timeout,
            )
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def cmd_mimo_calibrate(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    require_approved(project, "director")
    script = load_json(project / "script.json")
    scenes = [item for item in listify(script.get("scenes")) if isinstance(item, dict)]
    if not scenes:
        raise SkillError("Voice calibration requires at least one scripted scene")
    if args.scene:
        scene = find_scene(script, args.scene)
    else:
        scene = max(
            scenes,
            key=lambda item: narration_character_count(str(item.get("narration") or "")),
        )
    scene_id = str(scene.get("id") or "")
    character_count = narration_character_count(str(scene.get("narration") or ""))
    if character_count <= 0:
        raise SkillError(f"Scene {scene_id} has no effective narration characters")
    voice_file = Path(args.voice_file).expanduser().resolve() if args.voice_file else None
    voice_config = mimo_voice_config(
        project, voice=args.voice, voice_file=voice_file
    )
    reference = voice_config.get("voice_reference")
    reference_hash = (
        str(reference.get("sha256"))
        if isinstance(reference, dict) and reference.get("sha256")
        else None
    )
    context_hash = sha256_text(args.context)
    profile_id = voice_timing_profile_id(
        str(voice_config["model"]),
        str(voice_config["mode"]),
        str(voice_config["voice"]),
        reference_hash,
        context_hash,
    )
    default_profile = default_voice_timing_profile()
    if profile_id == default_profile["profile_id"]:
        write_json(project / "state" / "voice-timing.json", default_profile)
        print(json.dumps(default_profile, ensure_ascii=False, indent=2))
        return
    current_path = project / "state" / "voice-timing.json"
    if current_path.is_file():
        current = load_json(current_path)
        if current.get("profile_id") == profile_id:
            print(json.dumps(current, ensure_ascii=False, indent=2))
            return
    cache = load_voice_timing_cache()
    cached = cache["profiles"].get(profile_id)
    if isinstance(cached, dict):
        profile = dict(cached)
        profile["source"] = "cached-measurement"
        profile["loaded_at"] = iso_now()
        write_json(current_path, profile)
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return
    entry = synthesize_scene(
        project,
        scene_id,
        voice_config=voice_config,
        context=args.context,
        timeout=args.timeout,
    )
    duration = float(entry["duration_seconds"])
    seconds_per_character = duration / character_count
    profile = {
        "schema_version": "1.0",
        "profile_id": profile_id,
        "source": "measured-sample",
        "measured_at": iso_now(),
        "model": voice_config["model"],
        "mode": voice_config["mode"],
        "voice": voice_config["voice"],
        "voice_reference_sha256": reference_hash,
        "context": args.context,
        "context_sha256": context_hash,
        "sample_scene_id": scene_id,
        "sample_narration_sha256": sha256_text(str(scene.get("narration") or "")),
        "sample_characters": character_count,
        "sample_duration_seconds": round(duration, 6),
        "seconds_per_character": round(seconds_per_character, 9),
        "characters_per_second": round(1.0 / seconds_per_character, 6),
        "sample_audio": entry["audio"],
    }
    write_json(current_path, profile)
    cached_profile = dict(profile)
    cached_profile.pop("sample_audio", None)
    cache["profiles"][profile_id] = cached_profile
    write_json(voice_timing_cache_path(), cache)
    print(json.dumps(profile, ensure_ascii=False, indent=2))


def cmd_auth_smoke(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected_agnes_region = agnes_region(args.agnes_region)
    selected_agnes_base_url = agnes_base_url(selected_agnes_region)
    agnes_token = require_token(
        agnes_token_names(selected_agnes_region), f"Agnes {selected_agnes_region}"
    )
    mimo_token = require_token(MIMO_TOKEN_NAMES, "Xiaomi MiMo")
    agnes = http_json(
        "POST",
        f"{selected_agnes_base_url}/v1/chat/completions",
        token=agnes_token,
        payload={
            "model": "agnes-2.0-flash",
            "messages": [{"role": "user", "content": "Reply with exactly OK."}],
            "max_tokens": 8,
        },
        timeout=args.timeout,
    )
    mimo = http_json(
        "POST",
        f"{MIMO_BASE_URL}/v1/chat/completions",
        token=mimo_token,
        payload={
            "model": MIMO_MODEL,
            "messages": [{"role": "assistant", "content": "测试通过。"}],
            "audio": {"format": "wav", "voice": args.voice},
        },
        timeout=args.timeout,
    )
    audio = base64.b64decode(extract_audio_data(mimo), validate=True)
    wav = output / "mimo-smoke.wav"
    wav.write_bytes(audio)
    duration = media_duration(wav)
    result = {
        "agnes": {
            "ok": bool(agnes.get("choices")),
            "model": "agnes-2.0-flash",
            "region": selected_agnes_region,
            "base_url": selected_agnes_base_url,
        },
        "mimo": {
            "ok": duration > 0,
            "model": MIMO_MODEL,
            "voice": args.voice,
            "audio": str(wav),
            "duration_seconds": round(duration, 6),
        },
    }
    write_json(output / "auth-smoke.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser(
        "register-visual", help="Import host-generated first/end frames."
    )
    register.add_argument("project")
    register.add_argument("--scene", required=True)
    register.add_argument("--end", required=True)
    register.add_argument("--first", required=True)
    register.add_argument("--provider", default="user-provided")
    register.add_argument("--model", default="none")
    register.set_defaults(func=cmd_register_visual)

    image = sub.add_parser(
        "agnes-image", help="Generate distinct content-rich first and end frames via Agnes."
    )
    image.add_argument("project")
    image.add_argument("--scene", required=True)
    image.add_argument("--timeout", type=int, default=180)
    image.set_defaults(func=cmd_agnes_image)

    video = sub.add_parser(
        "agnes-video", help="Generate keyframe videos via Agnes Video."
    )
    video.add_argument("project")
    selector = video.add_mutually_exclusive_group(required=True)
    selector.add_argument("--scene")
    selector.add_argument("--all", action="store_true")
    video.add_argument("--poll", action="store_true")
    video.add_argument("--interval", type=int, default=15)
    video.add_argument("--timeout", type=int, default=180)
    video.add_argument(
        "--num-frames",
        type=int,
        default=None,
        help=(
            "Explicit Agnes frame count (8n+1, <=441). Omit to estimate each "
            "content job from narration length; transitions keep the 169-frame default."
        ),
    )
    video.add_argument("--retry-uncertain", action="store_true")
    video.set_defaults(func=cmd_agnes_video)

    mimo = sub.add_parser("mimo-tts", help="Generate scene narration via Xiaomi MiMo.")
    mimo.add_argument("project")
    selector = mimo.add_mutually_exclusive_group(required=True)
    selector.add_argument("--scene")
    selector.add_argument("--all", action="store_true")
    voice_source = mimo.add_mutually_exclusive_group(required=False)
    voice_source.add_argument(
        "--voice",
        help="MiMo preset voice selected by the user.",
    )
    voice_source.add_argument(
        "--voice-file",
        help="User-authorized .mp3/.wav sample for mimo-v2.5-tts-voiceclone.",
    )
    mimo.add_argument(
        "--context",
        default=None,
        help=(
            "Delivery instruction. Omit to reuse the calibrated profile context, "
            "or the built-in default when no calibration exists."
        ),
    )
    mimo.add_argument("--timeout", type=int, default=180)
    mimo.set_defaults(func=cmd_mimo_tts)

    calibrate = sub.add_parser(
        "mimo-calibrate",
        help="Measure one selected MiMo voice once before motion generation.",
    )
    calibrate.add_argument("project")
    calibrate.add_argument(
        "--scene",
        help="Representative scene to synthesize; defaults to the longest narration.",
    )
    calibration_voice = calibrate.add_mutually_exclusive_group(required=True)
    calibration_voice.add_argument("--voice")
    calibration_voice.add_argument("--voice-file")
    calibrate.add_argument("--context", default=DEFAULT_MIMO_CONTEXT)
    calibrate.add_argument("--timeout", type=int, default=180)
    calibrate.set_defaults(func=cmd_mimo_calibrate)

    smoke = sub.add_parser(
        "auth-smoke", help="Make one minimal Agnes text and MiMo TTS live call."
    )
    smoke.add_argument("--output", required=True)
    smoke.add_argument("--agnes-region", choices=("global", "cn"))
    smoke.add_argument("--voice", default="茉莉")
    smoke.add_argument("--timeout", type=int, default=180)
    smoke.set_defaults(func=cmd_auth_smoke)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (SkillError, ProviderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
