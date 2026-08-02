#!/usr/bin/env python3
"""Project bootstrap, validation, human approval, and status gates."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common import (
    AGNES_GLOBAL_TOKEN_NAMES,
    MIMO_TOKEN_NAMES,
    STAGES,
    SkillError,
    agnes_base_url,
    agnes_region,
    agnes_token_names,
    command_path,
    decode_check,
    file_record,
    find_scene,
    image_dimensions,
    is_full_auto,
    iso_now,
    listify,
    load_json,
    manifest_scene_entry,
    media_duration,
    media_summary,
    parse_rate,
    project_approval_mode,
    project_path,
    read_review,
    require_approved,
    require_sample_approved,
    resolve_project_file,
    review_path,
    sample_entry_sha256,
    sample_review_path,
    sha256_file,
    sha256_text,
    slugify,
    stage_scene_ids,
    token_value,
    token_source,
    write_local_credentials,
    write_json,
)
from font_setup import font_status, initialize_project_font

SKILL_ROOT = Path(__file__).resolve().parent.parent
STYLE_REGISTRY_PATH = SKILL_ROOT / "references" / "styles.json"
STYLE_SELECTION_RELATIVE = Path("state/style-selection.json")
STYLE_DEFINITION_RELATIVE = Path("state/style-definition.md")
TRANSITION_MODES = (
    "hard-cut",
    "transition-separated",
    "transition-fused",
)
DEFAULT_TRANSITION_MODE = "hard-cut"
DEFAULT_TRANSITION_DURATION_SECONDS = 1.0
FRAME_POLICIES = (
    "distinct-first-end",
    "shared-hero-frame",
)


def check(name: str, passed: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def raise_for_checks(stage: str, checks: Sequence[Dict[str, Any]]) -> None:
    failures = [item for item in checks if not item.get("passed")]
    if failures:
        lines = [f"Validation failed for stage '{stage}':"]
        lines.extend(
            f"- {item.get('name')}: {item.get('detail') or 'failed'}"
            for item in failures
        )
        raise SkillError("\n".join(lines))


def load_style_registry() -> Dict[str, Any]:
    registry = load_json(STYLE_REGISTRY_PATH)
    styles = registry.get("styles")
    default_id = str(registry.get("default_style_id", "")).strip()
    if not isinstance(styles, list) or not styles or not default_id:
        raise SkillError(f"Invalid internal style registry: {STYLE_REGISTRY_PATH}")
    ids = [
        str(item.get("id", "")).strip()
        for item in styles
        if isinstance(item, dict)
    ]
    if not all(ids) or len(ids) != len(set(ids)) or default_id not in ids:
        raise SkillError(f"Invalid style ids or default in: {STYLE_REGISTRY_PATH}")
    aliases: List[str] = []
    for item in styles:
        if not isinstance(item, dict):
            raise SkillError(f"Invalid style entry in: {STYLE_REGISTRY_PATH}")
        frame_policy = str(item.get("frame_policy", "")).strip()
        motion_strategy = str(item.get("motion_strategy", "")).strip()
        if frame_policy not in FRAME_POLICIES or not motion_strategy:
            raise SkillError(
                f"Invalid frame_policy or motion_strategy for style "
                f"'{item.get('id')}' in: {STYLE_REGISTRY_PATH}"
            )
        aliases.extend(
            str(value).strip().casefold()
            for value in [item.get("id"), *listify(item.get("aliases"))]
            if str(value).strip()
        )
    if len(aliases) != len(set(aliases)):
        raise SkillError(f"Duplicate style id or alias in: {STYLE_REGISTRY_PATH}")
    return registry


def resolve_style(style_value: Optional[str]) -> Dict[str, Any]:
    registry = load_style_registry()
    requested = str(style_value or registry["default_style_id"]).strip()
    requested_key = requested.casefold()
    for item in registry["styles"]:
        if not isinstance(item, dict):
            continue
        candidates = [str(item.get("id", ""))]
        candidates.extend(str(value) for value in listify(item.get("aliases")))
        if requested_key in {value.strip().casefold() for value in candidates}:
            style_id = str(item.get("id", "")).strip()
            version = str(item.get("version", "")).strip()
            name = str(item.get("name", "")).strip()
            reference = str(item.get("reference", "")).strip()
            if not style_id or not version or not name or not reference:
                raise SkillError(f"Incomplete internal style entry: {requested}")
            return item
    available = ", ".join(
        str(item.get("id"))
        for item in registry["styles"]
        if isinstance(item, dict)
    )
    raise SkillError(f"Unknown style '{requested}'. Available styles: {available}")


def archive_style_snapshot(project: Path) -> None:
    selection = project / STYLE_SELECTION_RELATIVE
    definition = project / STYLE_DEFINITION_RELATIVE
    if not selection.exists() and not definition.exists():
        return
    history_root = project / "state" / "style-history"
    history_root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 100):
        target = history_root / f"v{number:02d}"
        if target.exists():
            continue
        target.mkdir()
        if selection.is_file():
            shutil.copy2(selection, target / selection.name)
        if definition.is_file():
            shutil.copy2(definition, target / definition.name)
        return
    raise SkillError(f"Could not allocate style history in: {history_root}")


def materialize_style_snapshot(
    project: Path, style_value: Optional[str], *, archive_existing: bool = False
) -> Dict[str, Any]:
    style = resolve_style(style_value)
    reference_relative = str(style["reference"])
    reference_path = (SKILL_ROOT / reference_relative).resolve()
    try:
        reference_path.relative_to(SKILL_ROOT)
    except ValueError as exc:
        raise SkillError(f"Style reference escapes skill root: {reference_relative}") from exc
    if not reference_path.is_file():
        raise SkillError(f"Internal style definition is missing: {reference_path}")
    definition = reference_path.read_text(encoding="utf-8")
    if archive_existing:
        archive_style_snapshot(project)
    definition_path = project / STYLE_DEFINITION_RELATIVE
    definition_path.write_text(definition, encoding="utf-8")
    selection = {
        "schema_version": "1.0",
        "id": str(style["id"]),
        "version": str(style["version"]),
        "name": str(style["name"]),
        "motion_strategy": str(style["motion_strategy"]),
        "frame_policy": str(style["frame_policy"]),
        "source": "chat-animation-internal",
        "source_reference": reference_relative,
        "definition_snapshot": str(STYLE_DEFINITION_RELATIVE),
        "definition_sha256": sha256_text(definition),
        "snapshotted_at": iso_now(),
    }
    write_json(project / STYLE_SELECTION_RELATIVE, selection)
    return selection


def preflight_report(requested_agnes_region: Optional[str] = None) -> Dict[str, Any]:
    selected_agnes_region = agnes_region(requested_agnes_region)
    agnes_name, _ = token_value(agnes_token_names(selected_agnes_region))
    mimo_name, _ = token_value(MIMO_TOKEN_NAMES)
    python_ok = sys.version_info >= (3, 9)
    ffmpeg = command_path("ffmpeg")
    ffprobe = command_path("ffprobe")
    magick = command_path("magick")
    ass_filter = False
    if ffmpeg:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ass_filter = bool(
            re.search(
                r"^\s*\S+\s+ass\s",
                (completed.stdout or "") + (completed.stderr or ""),
                re.MULTILINE,
            )
        )
    disk = shutil.disk_usage(Path.cwd())
    disk_free_gb = disk.free / (1024**3)
    blockers: List[str] = []
    style_summary: Optional[Dict[str, Any]] = None
    try:
        registry = load_style_registry()
        style_summary = {
            "default_style_id": registry["default_style_id"],
            "available_style_ids": [
                item["id"] for item in registry["styles"] if isinstance(item, dict)
            ],
        }
    except SkillError as exc:
        blockers.append(str(exc))
    if not agnes_name:
        blockers.append("Agnes API token is missing.")
    if not mimo_name:
        blockers.append("Xiaomi MiMo API token is missing.")
    if not python_ok:
        blockers.append("Python 3.9 or newer is required.")
    if not ffmpeg or not ffprobe:
        blockers.append("FFmpeg and FFprobe are required for media processing.")
    if ffmpeg and not ass_filter and not magick:
        blockers.append(
            "Caption rendering needs FFmpeg with libass or ImageMagick as a fallback."
        )
    if disk_free_gb < 2:
        blockers.append("At least 2 GB of free disk space is required.")
    return {
        "schema_version": "1.0",
        "checked_at": iso_now(),
        "ready": not blockers,
        "tokens": {
            "agnes": {
                "configured": bool(agnes_name),
                "environment_variable": agnes_name,
                "source": token_source(agnes_name),
                "region": selected_agnes_region,
                "base_url": agnes_base_url(selected_agnes_region),
            },
            "mimo": {
                "configured": bool(mimo_name),
                "environment_variable": mimo_name,
                "source": token_source(mimo_name),
            },
        },
        "runtime": {
            "python": platform.python_version(),
            "python_ok": python_ok,
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
            "disk_free_gb": round(disk_free_gb, 2),
            "caption_renderer": (
                "ffmpeg-libass" if ass_filter else ("imagemagick-overlay" if magick else None)
            ),
        },
        "style_registry": style_summary,
        "optional": {
            "imagemagick": magick,
            "caption_font": font_status(),
            "disk_recommendation": (
                "10 GB or more is recommended for multi-scene projects."
                if disk_free_gb < 10
                else "ok"
            ),
        },
        "blockers": blockers,
    }


def cmd_preflight(args: argparse.Namespace) -> None:
    report = preflight_report(args.agnes_region)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"chat-animation preflight: {'READY' if report['ready'] else 'BLOCKED'}")
        print(
            "  Agnes token: "
            + ("configured" if report["tokens"]["agnes"]["configured"] else "missing")
        )
        print(f"  Agnes region: {report['tokens']['agnes']['region']}")
        print(f"  Agnes base URL: {report['tokens']['agnes']['base_url']}")
        print(
            "  MiMo token: "
            + ("configured" if report["tokens"]["mimo"]["configured"] else "missing")
        )
        print(f"  Python: {report['runtime']['python']}")
        print(f"  FFmpeg: {report['runtime']['ffmpeg'] or 'missing'}")
        print(f"  FFprobe: {report['runtime']['ffprobe'] or 'missing'}")
        print(f"  Caption renderer: {report['runtime']['caption_renderer'] or 'missing'}")
        print(f"  Free disk: {report['runtime']['disk_free_gb']} GB")
        if report["style_registry"]:
            print(
                "  Default style: "
                + str(report["style_registry"]["default_style_id"])
            )
        caption_font = report["optional"]["caption_font"]
        print(
            "  Caption font: "
            + str(caption_font["default"])
            + (" (cached)" if caption_font["cached"] else " (downloads at init)")
        )
        if not report["tokens"]["agnes"]["configured"]:
            print("\nAgnes setup:")
            if report["tokens"]["agnes"]["region"] == "cn":
                print("  1. Open https://platform.agnes-ai.cn")
                key_name = "AGNES_CN_API_KEY"
            else:
                print("  1. Open https://platform.agnes-ai.com")
                key_name = "AGNES_GLOBAL_API_KEY"
            print("  2. Console -> API Keys -> Create")
            print(f'  3. export {key_name}="<your-key>"')
        if not report["tokens"]["mimo"]["configured"]:
            print("\nXiaomi MiMo setup:")
            print("  1. Open https://platform.xiaomimimo.com")
            print("  2. Create an API key in the console")
            print('  3. export MIMO_API_KEY="<your-key>"')
        if not report["runtime"]["ffmpeg"] or not report["runtime"]["ffprobe"]:
            print("\nMedia tools:")
            print("  macOS: brew install ffmpeg")
            print("  Debian/Ubuntu: sudo apt install ffmpeg")
    if not report["ready"]:
        raise SkillError(
            "Preflight is blocked. Configure the missing items before starting Stage 1."
        )


def cmd_configure_credentials(args: argparse.Namespace) -> None:
    updates: Dict[str, str] = {}
    if args.from_env:
        global_value = next(
            (os.environ.get(name) for name in AGNES_GLOBAL_TOKEN_NAMES if os.environ.get(name)),
            None,
        )
        if global_value:
            updates["AGNES_GLOBAL_API_KEY"] = global_value
        if os.environ.get("AGNES_CN_API_KEY"):
            updates["AGNES_CN_API_KEY"] = os.environ["AGNES_CN_API_KEY"]
        if os.environ.get("MIMO_API_KEY"):
            updates["MIMO_API_KEY"] = os.environ["MIMO_API_KEY"]
    for profile in args.set_profile or []:
        name, prompt = {
            "agnes-global": ("AGNES_GLOBAL_API_KEY", "Agnes Global API key: "),
            "agnes-cn": ("AGNES_CN_API_KEY", "Agnes CN API key: "),
            "mimo": ("MIMO_API_KEY", "Xiaomi MiMo API key: "),
        }[profile]
        updates[name] = getpass.getpass(prompt)
    if not updates:
        raise SkillError("No credentials were provided")
    path = write_local_credentials(updates)
    print(
        json.dumps(
            {
                "credentials_file": str(path),
                "stored": sorted(updates),
                "protection": "windows-user-acl" if os.name == "nt" else "posix-0600",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def next_project_path(root: Path, name: str) -> Tuple[Path, str]:
    slug = slugify(name)
    for number in range(1, 100):
        version = f"{number:02d}"
        candidate = root / f"{slug}_{version}"
        if not candidate.exists():
            return candidate, version
    raise SkillError(f"Could not allocate a version for project name: {name}")


def cmd_init(args: argparse.Namespace) -> None:
    report = preflight_report(args.agnes_region)
    if not report["ready"] and not args.allow_missing_tokens:
        raise SkillError(
            "Preflight is blocked. Run project.py preflight and configure all required tokens."
        )
    style = resolve_style(args.style)
    if args.full_auto and not str(args.approval_note or "").strip():
        raise SkillError(
            "--full-auto requires --approval-note containing the user's explicit request"
        )
    transition_duration = (
        0.0
        if args.transition_mode == "hard-cut"
        else float(args.transition_duration)
    )
    if transition_duration < 0.2 and args.transition_mode != "hard-cut":
        raise SkillError("Animated transition duration must be at least 0.2 seconds")
    projects_root = Path(args.projects_root).expanduser().resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    project, version = next_project_path(projects_root, args.name)
    project.mkdir()
    for folder in ("visual", "motion", "audio", "composition", "reviews", "state"):
        (project / folder).mkdir()
    style_selection = materialize_style_snapshot(project, str(style["id"]))
    font_selection = initialize_project_font(project)
    selected_agnes_region = str(report["tokens"]["agnes"]["region"])
    request = {
        "schema_version": "1.0",
        "project_name": slugify(args.name),
        "version": version,
        "idea": args.idea,
        "style_id": style_selection["id"],
        "style_version": style_selection["version"],
        "audience": args.audience,
        "desired_takeaway": args.takeaway,
        "target_duration_seconds": args.duration,
        "tone": args.tone,
        "language": args.language,
        "approval_mode": "full-auto" if args.full_auto else "human-gated",
        "approval_note": str(args.approval_note or "").strip(),
        "agnes": {
            "region": selected_agnes_region,
            "base_url": agnes_base_url(selected_agnes_region),
        },
        "transition": {
            "mode": args.transition_mode,
            "duration_seconds": transition_duration,
        },
        "frame": {
            "aspect_ratio": "16:9",
            "width": args.width,
            "height": args.height,
            "fps": args.fps,
        },
        "caption_font": {
            "id": font_selection["id"],
            "family": font_selection["family"],
            "source": font_selection["source"],
        },
        "created_at": iso_now(),
    }
    write_json(project / "request.json", request)
    write_json(project / "state" / "preflight.json", report)
    print(project)


def cmd_set_transition(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    request_path = project / "request.json"
    request = load_json(request_path)
    duration = 0.0 if args.mode == "hard-cut" else float(args.duration)
    if duration < 0.2 and args.mode != "hard-cut":
        raise SkillError("Animated transition duration must be at least 0.2 seconds")
    request["transition"] = {
        "mode": args.mode,
        "duration_seconds": duration,
    }
    request["transition_updated_at"] = iso_now()
    write_json(request_path, request)
    print(
        json.dumps(
            {
                "project": str(project),
                "transition": request["transition"],
                "note": (
                    "Update script.json and state/motion-plan.json, then revalidate "
                    "the director stage. Existing approvals are stale."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_set_approval_mode(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    if args.mode == "full-auto" and not str(args.note or "").strip():
        raise SkillError(
            "Switching to full-auto requires --note with the user's explicit request"
        )
    request_path = project / "request.json"
    request = load_json(request_path)
    request["approval_mode"] = args.mode
    request["approval_note"] = str(args.note or "").strip()
    request["approval_mode_updated_at"] = iso_now()
    write_json(request_path, request)
    print(
        json.dumps(
            {
                "project": str(project),
                "approval_mode": args.mode,
                "note": request["approval_note"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_set_style(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    selection = materialize_style_snapshot(
        project, args.style, archive_existing=True
    )
    request_path = project / "request.json"
    request = load_json(request_path)
    request["style_id"] = selection["id"]
    request["style_version"] = selection["version"]
    write_json(request_path, request)
    print(
        json.dumps(
            {
                "project": str(project),
                "style_id": selection["id"],
                "style_version": selection["version"],
                "snapshot": selection["definition_snapshot"],
                "note": (
                    "Update script.json style_bible and scene prompts, then "
                    "revalidate the director stage."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def validate_director(project: Path) -> Tuple[List[Dict[str, Any]], List[Path]]:
    request_path = project / "request.json"
    request = load_json(request_path)
    script_path = project / "script.json"
    script = load_json(script_path)
    style_selection_path = project / STYLE_SELECTION_RELATIVE
    style_definition_path = project / STYLE_DEFINITION_RELATIVE
    style_selection = load_json(style_selection_path)
    if not style_definition_path.is_file():
        raise SkillError(f"Style definition snapshot is missing: {style_definition_path}")
    style_definition = style_definition_path.read_text(encoding="utf-8")
    checks: List[Dict[str, Any]] = []
    project_data = script.get("project")
    checks.append(
        check(
            "one_sentence_takeaway",
            isinstance(project_data, dict)
            and bool(str(project_data.get("one_sentence_takeaway", "")).strip()),
            "script.project.one_sentence_takeaway is required",
        )
    )
    arc = project_data.get("narrative_arc") if isinstance(project_data, dict) else None
    checks.append(
        check(
            "narrative_arc",
            isinstance(arc, list) and len(arc) >= 3,
            "script.project.narrative_arc needs at least three beats",
        )
    )
    research = script.get("research")
    checks.append(
        check(
            "research_contract",
            isinstance(research, dict)
            and isinstance(research.get("sources"), list)
            and isinstance(research.get("boundaries"), list),
            "script.research must include sources[] and boundaries[]",
        )
    )
    style = script.get("style_bible")
    style_issues: List[str] = []
    if not isinstance(style, dict):
        style_issues.append("script.style_bible must be an object")
        style = {}
    request_style_id = str(request.get("style_id", "")).strip()
    request_style_version = str(request.get("style_version", "")).strip()
    selection_id = str(style_selection.get("id", "")).strip()
    selection_version = str(style_selection.get("version", "")).strip()
    if not request_style_id or request_style_id != selection_id:
        style_issues.append("request.style_id does not match style selection")
    if not request_style_version or request_style_version != selection_version:
        style_issues.append("request.style_version does not match style selection")
    if str(style.get("id", "")).strip() != selection_id:
        style_issues.append("style_bible.id does not match style selection")
    if str(style.get("version", "")).strip() != selection_version:
        style_issues.append("style_bible.version does not match style selection")
    if style.get("source") != "chat-animation-internal":
        style_issues.append("style_bible.source must be chat-animation-internal")
    if style_selection.get("source") != "chat-animation-internal":
        style_issues.append("style selection source must be chat-animation-internal")
    if style_selection.get("definition_snapshot") != str(STYLE_DEFINITION_RELATIVE):
        style_issues.append("style definition snapshot path is invalid")
    if style_selection.get("definition_sha256") != sha256_text(style_definition):
        style_issues.append("style definition snapshot hash does not match")
    if str(style.get("name", "")).strip() != str(
        style_selection.get("name", "")
    ).strip():
        style_issues.append("style_bible.name does not match style selection")
    if not isinstance(style.get("avoid"), list):
        style_issues.append("style_bible.avoid must be a list")
    frame_policy = str(
        style_selection.get("frame_policy") or "distinct-first-end"
    ).strip()
    if frame_policy not in FRAME_POLICIES:
        style_issues.append("style selection frame_policy is invalid")
    if not str(style_selection.get("motion_strategy", "")).strip():
        # Legacy snapshots predate these fields and remain valid only for vox.
        if selection_id != "vox":
            style_issues.append("style selection motion_strategy is missing")
    checks.append(
        check(
            "style_bible",
            not style_issues,
            "; ".join(style_issues),
        )
    )
    request_transition = request.get("transition")
    transition_issues: List[str] = []
    if request_transition is None:
        request_transition = {
            "mode": DEFAULT_TRANSITION_MODE,
            "duration_seconds": (
                0.0
                if DEFAULT_TRANSITION_MODE == "hard-cut"
                else DEFAULT_TRANSITION_DURATION_SECONDS
            ),
        }
    if not isinstance(request_transition, dict):
        transition_issues.append("request.transition must be an object")
        request_transition = {}
    transition_mode = str(request_transition.get("mode", "")).strip()
    try:
        transition_duration = float(request_transition.get("duration_seconds"))
    except (TypeError, ValueError):
        transition_duration = -1.0
    if transition_mode not in TRANSITION_MODES:
        transition_issues.append(
            "request.transition.mode must be hard-cut, transition-separated, or transition-fused"
        )
    if transition_mode == "hard-cut":
        if transition_duration != 0.0:
            transition_issues.append("hard-cut duration_seconds must be 0")
    elif transition_duration < 0.2:
        transition_issues.append("animated transition duration_seconds must be at least 0.2")
    script_transition = (
        project_data.get("transition") if isinstance(project_data, dict) else None
    )
    if "transition" in request:
        if not isinstance(script_transition, dict):
            transition_issues.append("script.project.transition is required")
        else:
            try:
                script_duration = float(script_transition.get("duration_seconds"))
            except (TypeError, ValueError):
                script_duration = -1.0
            if (
                script_transition.get("mode") != transition_mode
                or script_duration != transition_duration
            ):
                transition_issues.append(
                    "script.project.transition must match request.transition"
                )
    checks.append(
        check(
            "transition_strategy",
            not transition_issues,
            "; ".join(transition_issues),
        )
    )
    motion_plan_path = project / "state" / "motion-plan.json"
    motion_plan_issues: List[str] = []
    if "transition" in request:
        if not motion_plan_path.is_file():
            motion_plan_issues.append("state/motion-plan.json is required")
        else:
            motion_plan = load_json(motion_plan_path)
            plan_transition = motion_plan.get("transition")
            if not isinstance(plan_transition, dict):
                motion_plan_issues.append("motion-plan.transition is required")
            else:
                try:
                    plan_duration = float(plan_transition.get("duration_seconds"))
                except (TypeError, ValueError):
                    plan_duration = -1.0
                if (
                    plan_transition.get("mode") != transition_mode
                    or plan_duration != transition_duration
                ):
                    motion_plan_issues.append(
                        "motion-plan.transition must match request.transition"
                    )
            states = motion_plan.get("states")
            jobs = motion_plan.get("jobs")
            handoffs = motion_plan.get("narration_handoffs")
            if not isinstance(states, list) or not states:
                motion_plan_issues.append("motion-plan.states must be a non-empty list")
            if not isinstance(jobs, list):
                motion_plan_issues.append("motion-plan.jobs must be a list")
                jobs = []
            if not isinstance(handoffs, list):
                motion_plan_issues.append(
                    "motion-plan.narration_handoffs must be a list"
                )
            scene_count = len(listify(script.get("scenes")))
            job_kinds = [
                str(item.get("kind"))
                for item in jobs
                if isinstance(item, dict)
            ]
            if len(job_kinds) != len(jobs):
                motion_plan_issues.append("every motion-plan job needs a kind")
            if transition_mode == "hard-cut":
                if any(kind != "content" for kind in job_kinds):
                    motion_plan_issues.append(
                        "hard-cut jobs may only contain optional content jobs"
                    )
            elif transition_mode == "transition-separated":
                if job_kinds.count("content") != scene_count:
                    motion_plan_issues.append(
                        "transition-separated requires one content job per scene"
                    )
                if job_kinds.count("transition") != max(0, scene_count - 1):
                    motion_plan_issues.append(
                        "transition-separated requires one transition job per boundary"
                    )
                if any(kind not in ("content", "transition") for kind in job_kinds):
                    motion_plan_issues.append(
                        "transition-separated only allows content and transition jobs"
                    )
            elif transition_mode == "transition-fused":
                if job_kinds.count("fused") != max(0, scene_count - 1):
                    motion_plan_issues.append(
                        "transition-fused requires one fused job per boundary"
                    )
                if any(kind not in ("fused", "terminal-content") for kind in job_kinds):
                    motion_plan_issues.append(
                        "transition-fused only allows fused and optional terminal-content jobs"
                    )
    checks.append(
        check(
            "motion_plan",
            not motion_plan_issues,
            "; ".join(motion_plan_issues),
        )
    )
    try:
        scene_ids = stage_scene_ids(script)
        scene_contract_ok = bool(scene_ids) and len(scene_ids) == len(set(scene_ids))
    except SkillError:
        scene_ids = []
        scene_contract_ok = False
    checks.append(
        check(
            "scene_ids",
            scene_contract_ok,
            "scenes must be non-empty and have unique string ids",
        )
    )
    scene_details: List[str] = []
    for scene in listify(script.get("scenes")):
        if not isinstance(scene, dict):
            scene_details.append("non-object scene")
            continue
        scene_id = str(scene.get("id", "?"))
        narration = str(scene.get("narration", "")).strip()
        visual = scene.get("visual")
        elements = visual.get("elements") if isinstance(visual, dict) else None
        first_frame = visual.get("first_frame") if isinstance(visual, dict) else None
        issues = []
        if not narration:
            issues.append("narration missing")
        if not isinstance(visual, dict):
            issues.append("visual missing")
        else:
            for field in ("meaning", "metaphor", "end_frame"):
                if not str(visual.get(field, "")).strip():
                    issues.append(f"visual.{field} missing")
            max_elements = 7 if frame_policy == "shared-hero-frame" else 6
            if not isinstance(elements, list) or not 3 <= len(elements) <= max_elements:
                issues.append(
                    f"visual.elements must contain 3-{max_elements} groups"
                )
            if not isinstance(first_frame, dict):
                issues.append("visual.first_frame missing")
            elif first_frame.get("type") != "content-keyframe" or not str(
                first_frame.get("description", "")
            ).strip():
                issues.append(
                    "visual.first_frame must be a described content-keyframe"
                )
            if not isinstance(visual.get("assembly_order"), list):
                issues.append("visual.assembly_order missing")
        first_frame_prompt = str(scene.get("first_frame_prompt", "")).strip()
        image_prompt = str(scene.get("image_prompt", "")).strip()
        motion_prompt = str(scene.get("motion_prompt", "")).strip()
        if len(first_frame_prompt) < 80:
            issues.append("first_frame_prompt is too short")
        if len(image_prompt) < 80:
            issues.append("image_prompt is too short")
        if (
            frame_policy == "shared-hero-frame"
            and first_frame_prompt != image_prompt
        ):
            issues.append(
                "shared-hero-frame requires identical first_frame_prompt and image_prompt"
            )
        lowered = motion_prompt.lower()
        if (
            len(motion_prompt) < 120
            or "image 1" not in lowered
            or "image 2" not in lowered
            or "no camera" not in lowered
        ):
            issues.append("motion_prompt must lock Image 1, Image 2, and camera")
        if issues:
            scene_details.append(f"{scene_id}: {', '.join(issues)}")
    checks.append(
        check(
            "scene_contracts",
            not scene_details,
            "; ".join(scene_details),
        )
    )
    frame = request.get("frame", {})
    checks.append(
        check(
            "frame_contract",
            frame.get("width") == 1280
            and frame.get("height") == 720
            and frame.get("fps") == 24,
            "default delivery contract is 1280x720 at 24fps",
        )
    )
    approval_mode = str(request.get("approval_mode") or "human-gated")
    approval_note = str(request.get("approval_note") or "").strip()
    checks.append(
        check(
            "approval_mode",
            approval_mode in ("human-gated", "full-auto")
            and (approval_mode != "full-auto" or bool(approval_note)),
            "approval_mode must be human-gated, or full-auto with an explicit approval_note",
        )
    )
    raise_for_checks("director", checks)
    artifacts = [
        request_path,
        script_path,
        style_selection_path,
        style_definition_path,
    ]
    if motion_plan_path.is_file():
        artifacts.append(motion_plan_path)
    return checks, artifacts


def manifest_scene_map(
    manifest: Dict[str, Any], name: str
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    values: Dict[str, Dict[str, Any]] = {}
    issues: List[str] = []
    for item in listify(manifest.get("scenes")):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            issues.append(f"{name}: invalid scene record")
            continue
        values[item["id"]] = item
    return values, issues


def validate_visual(
    project: Path, only_scene_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[Path]]:
    require_approved(project, "director")
    script = load_json(project / "script.json")
    all_scene_ids = stage_scene_ids(script)
    scene_ids = [only_scene_id] if only_scene_id else all_scene_ids
    if only_scene_id and only_scene_id not in all_scene_ids:
        raise SkillError(f"Scene not found in script.json: {only_scene_id}")
    manifest_path = project / "visual" / "visual-manifest.json"
    manifest = load_json(manifest_path)
    style_selection = load_json(project / STYLE_SELECTION_RELATIVE)
    frame_policy = str(
        style_selection.get("frame_policy") or "distinct-first-end"
    ).strip()
    if frame_policy not in FRAME_POLICIES:
        raise SkillError(f"Invalid project frame policy: {frame_policy or 'missing'}")
    scene_map, issues = manifest_scene_map(manifest, "visual")
    artifacts = [manifest_path]
    for scene_id in scene_ids:
        item = scene_map.get(scene_id)
        scene = find_scene(script, scene_id)
        if not item:
            issues.append(f"{scene_id}: missing manifest record")
            continue
        expected_first_hash = sha256_text(
            str(scene.get("first_frame_prompt", "")).strip()
        )
        expected_end_hash = sha256_text(str(scene.get("image_prompt", "")).strip())
        if item.get("first_frame_prompt_sha256") != expected_first_hash:
            issues.append(
                f"{scene_id}: first frame was generated from an older prompt"
            )
        if item.get("end_frame_prompt_sha256") != expected_end_hash:
            issues.append(f"{scene_id}: end frame was generated from an older prompt")
        frame_paths: Dict[str, Path] = {}
        for field in ("first_frame", "end_frame"):
            relative = item.get(field)
            if not isinstance(relative, str):
                issues.append(f"{scene_id}: {field} missing")
                continue
            path = resolve_project_file(project, relative)
            if not path.is_file():
                issues.append(f"{scene_id}: file missing: {relative}")
                continue
            frame_paths[field] = path
            artifacts.append(path)
            try:
                width, height = image_dimensions(path)
                if width != 1280 or height != 720:
                    issues.append(
                        f"{scene_id}: {field} is {width}x{height}, expected 1280x720"
                    )
            except SkillError as exc:
                issues.append(f"{scene_id}: {exc}")
        if "first_frame" in frame_paths and "end_frame" in frame_paths:
            frames_match = (
                sha256_file(frame_paths["first_frame"])
                == sha256_file(frame_paths["end_frame"])
            )
            if frame_policy == "distinct-first-end" and frames_match:
                issues.append(
                    f"{scene_id}: first and end frames must be visually distinct"
                )
            if frame_policy == "shared-hero-frame" and not frames_match:
                issues.append(
                    f"{scene_id}: storybook first and end frames must reuse "
                    "the same hero frame"
                )
        qa = item.get("qa")
        required_qa = (
            "first_frame_meaningful",
            "metaphor_readable",
            "anatomy_valid",
            "no_unwanted_text",
            "caption_safe",
        )
        if not isinstance(qa, dict) or not all(qa.get(key) is True for key in required_qa):
            issues.append(f"{scene_id}: visual QA is incomplete or failed")
    contact_relative = manifest.get("contact_sheet")
    contact_path = (
        resolve_project_file(project, contact_relative)
        if isinstance(contact_relative, str)
        else project / "visual" / "contact-sheet.jpg"
    )
    if not contact_path.is_file():
        issues.append("visual contact sheet is missing")
    else:
        artifacts.append(contact_path)
    checks = [
        check("all_scene_frames", not issues, "; ".join(issues)),
        check(
            "scene_count",
            (
                only_scene_id in scene_map
                if only_scene_id
                else set(scene_map) == set(scene_ids)
            ),
            f"manifest={sorted(scene_map)} expected={sorted(scene_ids)}",
        ),
    ]
    raise_for_checks("visual", checks)
    return checks, unique_paths(artifacts)


def validate_motion(
    project: Path, only_scene_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[Path]]:
    require_approved(project, "visual")
    script = load_json(project / "script.json")
    narrative_scene_ids = stage_scene_ids(script)
    visual = load_json(project / "visual" / "visual-manifest.json")
    visual_map, visual_issues = manifest_scene_map(visual, "visual")
    plan_path = project / "state" / "motion-plan.json"
    expected_jobs: Dict[str, Dict[str, Any]] = {}
    if plan_path.is_file():
        plan = load_json(plan_path)
        states = {
            str(item.get("id")): item
            for item in listify(plan.get("states"))
            if isinstance(item, dict) and item.get("id")
        }
        for job in listify(plan.get("jobs")):
            if not isinstance(job, dict):
                continue
            job_id = str(job.get("id") or "")
            first_state = states.get(str(job.get("first")))
            end_state = states.get(str(job.get("end")))
            if not job_id or not first_state or not end_state:
                continue
            first_scene_id = str(first_state.get("scene_id") or "")
            end_scene_id = str(end_state.get("scene_id") or "")
            first_visual = visual_map.get(first_scene_id, {})
            end_visual = visual_map.get(end_scene_id, {})
            first_field = (
                "first_frame"
                if str(first_state.get("role") or "").endswith("first")
                else "end_frame"
            )
            end_field = (
                "first_frame"
                if str(end_state.get("role") or "").endswith("first")
                else "end_frame"
            )
            scene_id = str(job.get("scene_id") or first_scene_id)
            prompt = str(job.get("motion_prompt") or "").strip()
            if not prompt and str(job.get("kind")) in ("content", "terminal-content"):
                prompt = str(find_scene(script, scene_id).get("motion_prompt", "")).strip()
            expected_jobs[job_id] = {
                "prompt": prompt,
                "first_frame": first_visual.get(first_field),
                "end_frame": end_visual.get(end_field),
                "scene_id": scene_id,
                "kind": str(job.get("kind") or ""),
            }
    else:
        for scene_id in narrative_scene_ids:
            scene = find_scene(script, scene_id)
            item = visual_map.get(scene_id, {})
            expected_jobs[scene_id] = {
                "prompt": str(scene.get("motion_prompt", "")).strip(),
                "first_frame": item.get("first_frame"),
                "end_frame": item.get("end_frame"),
                "scene_id": scene_id,
                "kind": "content",
            }
    if only_scene_id:
        if only_scene_id in expected_jobs:
            scene_ids = [only_scene_id]
        else:
            matches = [
                job_id
                for job_id, item in expected_jobs.items()
                if item.get("scene_id") == only_scene_id
                and item.get("kind") in ("content", "terminal-content")
            ]
            if len(matches) != 1:
                raise SkillError(f"Motion job not found for scene: {only_scene_id}")
            scene_ids = matches
    else:
        scene_ids = list(expected_jobs)
    manifest_path = project / "motion" / "motion-manifest.json"
    manifest = load_json(manifest_path)
    issues: List[str] = list(visual_issues)
    if manifest.get("provider") != "agnes":
        issues.append("provider must be agnes")
    if manifest.get("model") != "agnes-video-v2.0":
        issues.append("model must be agnes-video-v2.0")
    if manifest.get("mode") != "keyframes":
        issues.append("mode must be keyframes")
    scene_map, scene_issues = manifest_scene_map(manifest, "motion")
    issues.extend(scene_issues)
    artifacts = [manifest_path]
    for scene_id in scene_ids:
        item = scene_map.get(scene_id)
        expected = expected_jobs[scene_id]
        if not item:
            issues.append(f"{scene_id}: missing motion record")
            continue
        expected_prompt_hash = sha256_text(str(expected.get("prompt") or "").strip())
        if item.get("prompt_sha256") != expected_prompt_hash:
            issues.append(f"{scene_id}: motion video was generated from an older prompt")
        for field in ("first_frame", "end_frame"):
            if item.get(field) != expected.get(field):
                issues.append(f"{scene_id}: {field} does not match motion plan")
        for field in ("first_frame", "end_frame", "video", "provider_record", "contact_sheet"):
            relative = item.get(field)
            if not isinstance(relative, str):
                issues.append(f"{scene_id}: {field} missing")
                continue
            path = resolve_project_file(project, relative)
            if not path.is_file():
                issues.append(f"{scene_id}: file missing: {relative}")
            else:
                artifacts.append(path)
        relative_video = item.get("video")
        if isinstance(relative_video, str):
            video_path = resolve_project_file(project, relative_video)
            if video_path.is_file():
                try:
                    summary = media_summary(video_path)
                    video = summary.get("video") or {}
                    if int(video.get("width") or 0) != 1280 or int(
                        video.get("height") or 0
                    ) != 720:
                        issues.append(f"{scene_id}: motion video is not 1280x720")
                    if abs(parse_rate(video.get("r_frame_rate")) - 24.0) > 0.1:
                        issues.append(f"{scene_id}: motion video is not 24fps")
                    if summary.get("audio") is not None:
                        issues.append(f"{scene_id}: motion delivery video contains audio")
                except SkillError as exc:
                    issues.append(f"{scene_id}: {exc}")
        provider_relative = item.get("provider_record")
        if isinstance(provider_relative, str):
            provider_path = resolve_project_file(project, provider_relative)
            if provider_path.is_file():
                provider = load_json(provider_path)
                if (
                    provider.get("model") != "agnes-video-v2.0"
                    or provider.get("mode") != "keyframes"
                    or len(listify(provider.get("input_frames"))) != 2
                ):
                    issues.append(
                        f"{scene_id}: provider record does not prove two-frame keyframes mode"
                    )
                request = provider.get("request")
                if not isinstance(request, dict) or (
                    request.get("width") != 1280
                    or request.get("height") != 720
                    or request.get("frame_rate") != 24
                    or request.get("mode") != "keyframes"
                    or len(listify(request.get("input_frames"))) != 2
                ):
                    issues.append(
                        f"{scene_id}: provider request summary is not 720P two-keyframe mode"
                    )
        qa = item.get("qa")
        required_qa = (
            "keyframes_respected",
            "camera_locked",
            "no_mutation",
            "end_frame_respected",
        )
        if not isinstance(qa, dict) or not all(qa.get(key) is True for key in required_qa):
            issues.append(f"{scene_id}: motion visual QA is incomplete or failed")
    checks = [
        check("agnes_keyframes_contract", not issues, "; ".join(issues)),
        check(
            "scene_count",
            (
                scene_ids[0] in scene_map
                if only_scene_id
                else set(scene_map) == set(expected_jobs)
            ),
            f"manifest={sorted(scene_map)} expected={sorted(expected_jobs)}",
        ),
    ]
    raise_for_checks("motion", checks)
    return checks, unique_paths(artifacts)


def validate_audio(
    project: Path, only_scene_id: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[Path]]:
    require_approved(project, "motion")
    script = load_json(project / "script.json")
    all_scene_ids = stage_scene_ids(script)
    scene_ids = [only_scene_id] if only_scene_id else all_scene_ids
    if only_scene_id and only_scene_id not in all_scene_ids:
        raise SkillError(f"Scene not found in script.json: {only_scene_id}")
    manifest_path = project / "audio" / "audio-manifest.json"
    manifest = load_json(manifest_path)
    artifacts = [manifest_path]
    issues: List[str] = []
    if manifest.get("provider") != "mimo":
        issues.append("provider must be mimo")
    allowed_models = {
        "mimo-v2.5-tts": "preset",
        "mimo-v2.5-tts-voiceclone": "voiceclone",
    }
    model = manifest.get("model")
    mode = manifest.get("mode", "preset")
    if model not in allowed_models:
        issues.append("unsupported MiMo TTS model")
    elif mode != allowed_models[model]:
        issues.append("MiMo model and mode do not match")
    reference = manifest.get("voice_reference")
    if mode == "voiceclone":
        if not isinstance(reference, dict):
            issues.append("voiceclone mode requires voice_reference")
        else:
            relative = reference.get("path")
            if not isinstance(relative, str):
                issues.append("voice_reference.path is missing")
            else:
                path = resolve_project_file(project, relative)
                if not path.is_file():
                    issues.append(f"voice reference is missing: {relative}")
                else:
                    artifacts.append(path)
                    if path.suffix.lower() not in (".mp3", ".wav"):
                        issues.append("voice reference must be mp3 or wav")
                    if path.stat().st_size > 10 * 1024 * 1024:
                        issues.append("voice reference exceeds 10 MB")
                    if sha256_file(path) != reference.get("sha256"):
                        issues.append("voice reference hash does not match")
    scene_map, scene_issues = manifest_scene_map(manifest, "audio")
    issues.extend(scene_issues)
    for scene_id in scene_ids:
        item = scene_map.get(scene_id)
        scene = find_scene(script, scene_id)
        if not item:
            issues.append(f"{scene_id}: missing audio record")
            continue
        expected_hash = sha256_text(str(scene.get("narration", "")).strip())
        if item.get("narration_sha256") != expected_hash:
            issues.append(f"{scene_id}: narration hash does not match approved script")
        if item.get("model") != model or item.get("mode") != mode:
            issues.append(f"{scene_id}: audio model/mode differs from manifest")
        expected_reference_hash = (
            reference.get("sha256") if isinstance(reference, dict) else None
        )
        if item.get("voice_reference_sha256") != expected_reference_hash:
            issues.append(f"{scene_id}: voice reference differs from manifest")
        for field in ("raw_audio", "audio", "provider_record"):
            relative = item.get(field)
            if not isinstance(relative, str):
                issues.append(f"{scene_id}: {field} missing")
                continue
            path = resolve_project_file(project, relative)
            if not path.is_file():
                issues.append(f"{scene_id}: file missing: {relative}")
            else:
                artifacts.append(path)
        relative_audio = item.get("audio")
        if isinstance(relative_audio, str):
            path = resolve_project_file(project, relative_audio)
            if path.is_file():
                try:
                    actual_duration = media_duration(path)
                    recorded = float(item.get("duration_seconds") or 0)
                    if abs(actual_duration - recorded) > 0.08:
                        issues.append(
                            f"{scene_id}: duration record differs from WAV by more than 80ms"
                        )
                except (SkillError, TypeError, ValueError) as exc:
                    issues.append(f"{scene_id}: {exc}")
        qa = item.get("qa")
        if not isinstance(qa, dict) or not (
            qa.get("narration_verified") is True
            and qa.get("natural_delivery") is True
        ):
            issues.append(f"{scene_id}: audio listening/transcription QA is incomplete")
    checks = [
        check("mimo_audio_contract", not issues, "; ".join(issues)),
        check(
            "scene_count",
            (
                only_scene_id in scene_map
                if only_scene_id
                else set(scene_map) == set(scene_ids)
            ),
            f"manifest={sorted(scene_map)} expected={sorted(scene_ids)}",
        ),
    ]
    raise_for_checks("audio", checks)
    return checks, unique_paths(artifacts)


def validate_composition(project: Path) -> Tuple[List[Dict[str, Any]], List[Path]]:
    require_approved(project, "audio")
    for sample_stage in ("visual", "motion", "audio"):
        require_sample_approved(project, sample_stage)
    final_path = project / "composition" / "final.mp4"
    timing_path = project / "composition" / "timing.json"
    subtitle_path = project / "composition" / "subtitles.ass"
    contact_path = project / "composition" / "contact-sheet.jpg"
    qa_path = project / "composition" / "qa.json"
    required = (final_path, timing_path, subtitle_path, contact_path, qa_path)
    issues = [f"missing: {path.name}" for path in required if not path.is_file()]
    if final_path.is_file():
        try:
            summary = media_summary(final_path)
            video = summary.get("video") or {}
            audio = summary.get("audio")
            if int(video.get("width") or 0) != 1280 or int(
                video.get("height") or 0
            ) != 720:
                issues.append("final.mp4 is not 1280x720")
            if abs(parse_rate(video.get("r_frame_rate")) - 24.0) > 0.1:
                issues.append("final.mp4 is not 24fps")
            if video.get("codec_name") != "h264":
                issues.append("final.mp4 video codec is not H.264")
            if not audio or audio.get("codec_name") != "aac":
                issues.append("final.mp4 audio codec is not AAC")
            decode_check(final_path)
        except SkillError as exc:
            issues.append(str(exc))
    if timing_path.is_file():
        timing = load_json(timing_path)
        if timing.get("timebase") != "audio":
            issues.append("timing.json timebase must be audio")
        captions = [
            caption
            for scene in listify(timing.get("scenes"))
            if isinstance(scene, dict)
            for caption in listify(scene.get("captions"))
            if isinstance(caption, dict)
        ]
        if any("\n" in str(item.get("text", "")) for item in captions):
            issues.append("captions must not contain line breaks")
        try:
            final_duration = media_duration(final_path) if final_path.is_file() else 0
            expected = float(timing.get("total_duration") or 0)
            if expected <= 0 or abs(final_duration - expected) > 0.15:
                issues.append("final duration differs from audio timeline by more than 150ms")
        except (SkillError, TypeError, ValueError) as exc:
            issues.append(str(exc))
    if qa_path.is_file():
        qa = load_json(qa_path)
        for field in (
            "full_decode_passed",
            "single_line_captions",
            "no_gaps",
            "audio_master_timing",
        ):
            if qa.get(field) is not True:
                issues.append(f"composition QA failed or missing: {field}")
    checks = [check("final_media_contract", not issues, "; ".join(issues))]
    raise_for_checks("composition", checks)
    return checks, list(required)


VALIDATORS = {
    "director": validate_director,
    "visual": validate_visual,
    "motion": validate_motion,
    "audio": validate_audio,
    "composition": validate_composition,
}


def unique_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    values = []
    for path in paths:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            values.append(path)
    return values


def validate_stage(project: Path, stage: str) -> Tuple[List[Dict[str, Any]], List[Path]]:
    return VALIDATORS[stage](project)


def validate_sample(
    project: Path, stage: str, scene_id: str
) -> Tuple[List[Dict[str, Any]], List[Path]]:
    if stage == "visual":
        return validate_visual(project, scene_id)
    if stage == "motion":
        return validate_motion(project, scene_id)
    if stage == "audio":
        return validate_audio(project, scene_id)
    raise SkillError(f"Stage '{stage}' does not have a sample gate")


def sample_artifact_paths(project: Path, stage: str, scene_id: str) -> List[Path]:
    entry = manifest_scene_entry(project, stage, scene_id)
    fields = {
        "visual": ("first_frame", "end_frame", "provider_record"),
        "motion": (
            "first_frame",
            "end_frame",
            "raw_video",
            "video",
            "provider_record",
            "contact_sheet",
            "actual_first_frame",
            "actual_last_frame",
        ),
        "audio": ("raw_audio", "audio", "provider_record"),
    }[stage]
    values: List[Path] = []
    for field in fields:
        relative = entry.get(field)
        if isinstance(relative, str):
            path = resolve_project_file(project, relative)
            if path.is_file():
                values.append(path)
    if stage == "audio":
        manifest = load_json(project / "audio" / "audio-manifest.json")
        reference = manifest.get("voice_reference")
        relative = reference.get("path") if isinstance(reference, dict) else None
        if isinstance(relative, str):
            path = resolve_project_file(project, relative)
            if path.is_file():
                values.append(path)
    return unique_paths(values)


def cmd_validate(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    checks, artifacts = validate_stage(project, args.stage)
    result = {
        "stage": args.stage,
        "status": "passed",
        "validated_at": iso_now(),
        "checks": checks,
        "artifact_count": len(artifacts),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_validate_sample(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    checks, artifacts = validate_sample(project, args.stage, args.scene)
    result = {
        "stage": args.stage,
        "scene_id": args.scene,
        "status": "passed",
        "validated_at": iso_now(),
        "checks": checks,
        "artifact_count": len(artifacts),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_approve_sample(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    if is_full_auto(project):
        raise SkillError("Sample approval is skipped in full-auto mode")
    checks, _ = validate_sample(project, args.stage, args.scene)
    artifacts = sample_artifact_paths(project, args.stage, args.scene)
    review = {
        "schema_version": "1.0",
        "gate": "sample",
        "stage": args.stage,
        "scene_id": args.scene,
        "validated_at": iso_now(),
        "sample_entry_sha256": sample_entry_sha256(
            project, args.stage, args.scene
        ),
        "self_review": {"status": "passed", "checks": checks},
        "human_review": {
            "status": "approved",
            "reviewer": args.reviewer,
            "approved_at": iso_now(),
            "note": args.note,
        },
        "approved_artifacts": [file_record(project, path) for path in artifacts],
    }
    path = sample_review_path(project, args.stage)
    write_json(path, review)
    print(path)


def invalidate_downstream(project: Path, stage: str) -> None:
    start = STAGES.index(stage) + 1
    for downstream in STAGES[start:]:
        path = review_path(project, downstream)
        if not path.is_file():
            continue
        review = load_json(path)
        human = review.setdefault("human_review", {})
        if human.get("status") == "approved":
            human["status"] = "stale"
            human["stale_at"] = iso_now()
            human["stale_reason"] = f"Upstream stage '{stage}' was re-approved"
        automation = review.setdefault("automation_review", {})
        if automation.get("status") == "completed":
            automation["status"] = "stale"
            automation["stale_at"] = iso_now()
            automation["stale_reason"] = f"Upstream stage '{stage}' was recompleted"
        write_json(path, review)


def cmd_auto_complete(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    if not is_full_auto(project):
        raise SkillError(
            "auto-complete is only available when request.approval_mode is full-auto"
        )
    stage_index = STAGES.index(args.stage)
    if stage_index:
        require_approved(project, STAGES[stage_index - 1])
    checks, artifacts = validate_stage(project, args.stage)
    request = load_json(project / "request.json")
    review = {
        "schema_version": "1.0",
        "stage": args.stage,
        "approval_mode": "full-auto",
        "validated_at": iso_now(),
        "self_review": {"status": "passed", "checks": checks},
        "human_review": {
            "status": "skipped",
            "reason": "User explicitly requested full-auto execution",
        },
        "automation_review": {
            "status": "completed",
            "completed_at": iso_now(),
            "authorization_note": request.get("approval_note", ""),
        },
        "approved_artifacts": [file_record(project, path) for path in artifacts],
    }
    write_json(review_path(project, args.stage), review)
    invalidate_downstream(project, args.stage)
    print(review_path(project, args.stage))


def cmd_approve(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    if is_full_auto(project):
        raise SkillError("This project is full-auto; use auto-complete instead of approve")
    stage_index = STAGES.index(args.stage)
    if stage_index:
        require_approved(project, STAGES[stage_index - 1])
    if args.stage in ("visual", "motion", "audio"):
        require_sample_approved(project, args.stage)
    checks, artifacts = validate_stage(project, args.stage)
    review = {
        "schema_version": "1.0",
        "stage": args.stage,
        "validated_at": iso_now(),
        "self_review": {"status": "passed", "checks": checks},
        "human_review": {
            "status": "approved",
            "reviewer": args.reviewer,
            "approved_at": iso_now(),
            "note": args.note,
        },
        "approved_artifacts": [file_record(project, path) for path in artifacts],
    }
    write_json(review_path(project, args.stage), review)
    invalidate_downstream(project, args.stage)
    print(review_path(project, args.stage))


def cmd_status(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    values = []
    for stage in STAGES:
        review = read_review(project, stage)
        status = "not_approved"
        detail = ""
        if review:
            if review.get("automation_review", {}).get("status") == "completed":
                status = "auto_completed"
            else:
                status = str(review.get("human_review", {}).get("status") or "not_approved")
            if status in ("approved", "auto_completed"):
                try:
                    require_approved(project, stage)
                except SkillError as exc:
                    status = "stale"
                    detail = str(exc)
        values.append({"stage": stage, "status": status, "detail": detail})
    samples = []
    for stage in ("visual", "motion", "audio"):
        status = "skipped" if is_full_auto(project) else "not_approved"
        detail = ""
        path = sample_review_path(project, stage)
        if path.is_file() and not is_full_auto(project):
            try:
                review = require_sample_approved(project, stage)
                status = str(review.get("human_review", {}).get("status") or "approved")
            except SkillError as exc:
                status = "stale"
                detail = str(exc)
        samples.append({"stage": stage, "status": status, "detail": detail})
    print(
        json.dumps(
            {
                "project": str(project),
                "approval_mode": project_approval_mode(project),
                "stages": values,
                "sample_gates": samples,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="Check tokens and media runtime.")
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--agnes-region", choices=("global", "cn"))
    preflight.set_defaults(func=cmd_preflight)

    configure = sub.add_parser(
        "configure-credentials",
        help="Store provider credentials once in the private user credentials file.",
    )
    configure_mode = configure.add_mutually_exclusive_group(required=True)
    configure_mode.add_argument(
        "--from-env",
        action="store_true",
        help="Import currently exported credentials without printing them.",
    )
    configure_mode.add_argument(
        "--set",
        dest="set_profile",
        action="append",
        choices=("agnes-global", "agnes-cn", "mimo"),
        help="Prompt securely for one profile; repeat to configure multiple profiles.",
    )
    configure.set_defaults(func=cmd_configure_credentials)

    init = sub.add_parser("init", help="Create a versioned project.")
    init.add_argument("--projects-root", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--idea", required=True)
    init.add_argument(
        "--style",
        help="Internal style id or alias; defaults to styles.json default_style_id.",
    )
    init.add_argument("--audience", default="没有专业背景的成年人")
    init.add_argument("--takeaway", default="")
    init.add_argument("--duration", type=int, default=90)
    init.add_argument("--tone", default="有趣但不轻浮")
    init.add_argument("--language", default="zh-CN")
    init.add_argument("--width", type=int, default=1280)
    init.add_argument("--height", type=int, default=720)
    init.add_argument("--fps", type=int, default=24)
    init.add_argument(
        "--agnes-region",
        choices=("global", "cn"),
        help="Bind this project to the global or CN Agnes API profile.",
    )
    init.add_argument(
        "--transition-mode",
        choices=TRANSITION_MODES,
        default=DEFAULT_TRANSITION_MODE,
        help="Editing strategy; defaults to a hard cut.",
    )
    init.add_argument(
        "--transition-duration",
        type=float,
        default=DEFAULT_TRANSITION_DURATION_SECONDS,
        help="Target animated transition duration in seconds; default 1.0.",
    )
    init.add_argument(
        "--full-auto",
        action="store_true",
        help="Only when the user explicitly asks to skip every human approval.",
    )
    init.add_argument(
        "--approval-note",
        default="",
        help="The user's explicit authorization for full-auto mode.",
    )
    init.add_argument(
        "--allow-missing-tokens",
        action="store_true",
        help="Offline test/bootstrap only; production must not use this.",
    )
    init.set_defaults(func=cmd_init)

    approval_mode = sub.add_parser(
        "set-approval-mode", help="Switch a project between human-gated and full-auto."
    )
    approval_mode.add_argument("project")
    approval_mode.add_argument("--mode", choices=("human-gated", "full-auto"), required=True)
    approval_mode.add_argument("--note", default="")
    approval_mode.set_defaults(func=cmd_set_approval_mode)

    set_transition = sub.add_parser(
        "set-transition", help="Set the editing transition strategy for a project."
    )
    set_transition.add_argument("project")
    set_transition.add_argument("--mode", choices=TRANSITION_MODES, required=True)
    set_transition.add_argument(
        "--duration", type=float, default=DEFAULT_TRANSITION_DURATION_SECONDS
    )
    set_transition.set_defaults(func=cmd_set_transition)

    set_style = sub.add_parser(
        "set-style", help="Snapshot a registered internal style into a project."
    )
    set_style.add_argument("project")
    set_style.add_argument("--style", required=True)
    set_style.set_defaults(func=cmd_set_style)

    validate = sub.add_parser("validate", help="Run deterministic stage validation.")
    validate.add_argument("project")
    validate.add_argument("stage", choices=STAGES)
    validate.set_defaults(func=cmd_validate)

    validate_sample_parser = sub.add_parser(
        "validate-sample", help="Validate one costly stage sample before batch work."
    )
    validate_sample_parser.add_argument("project")
    validate_sample_parser.add_argument(
        "stage", choices=("visual", "motion", "audio")
    )
    validate_sample_parser.add_argument("--scene", required=True)
    validate_sample_parser.set_defaults(func=cmd_validate_sample)

    approve_sample = sub.add_parser(
        "approve-sample", help="Record explicit human approval of one stage sample."
    )
    approve_sample.add_argument("project")
    approve_sample.add_argument("stage", choices=("visual", "motion", "audio"))
    approve_sample.add_argument("--scene", required=True)
    approve_sample.add_argument("--reviewer", required=True)
    approve_sample.add_argument("--note", required=True)
    approve_sample.set_defaults(func=cmd_approve_sample)

    auto_complete = sub.add_parser(
        "auto-complete",
        help="Validate and record a stage completion without human review in full-auto mode.",
    )
    auto_complete.add_argument("project")
    auto_complete.add_argument("stage", choices=STAGES)
    auto_complete.set_defaults(func=cmd_auto_complete)

    approve = sub.add_parser(
        "approve", help="Record explicit human approval after validation."
    )
    approve.add_argument("project")
    approve.add_argument("stage", choices=STAGES)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--note", required=True)
    approve.set_defaults(func=cmd_approve)

    status = sub.add_parser("status", help="Show gate status and stale approvals.")
    status.add_argument("project")
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except SkillError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
