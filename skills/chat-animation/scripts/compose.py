#!/usr/bin/env python3
"""Compose approved motion and MiMo narration into the final captioned MP4."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from common import (
    SkillError,
    command_path,
    decode_check,
    find_scene,
    iso_now,
    listify,
    load_json,
    media_duration,
    media_summary,
    project_path,
    relative_to_project,
    require_approved,
    require_sample_approved,
    resolve_project_file,
    run,
    stage_scene_ids,
    write_json,
)
from font_setup import load_project_font


def manifest_map(path: Path) -> Dict[str, Dict[str, Any]]:
    manifest = load_json(path)
    result = {}
    for item in listify(manifest.get("scenes")):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            result[item["id"]] = item
    return result


def split_caption_text(text: str, provided: Any, max_chars: int = 24) -> List[str]:
    if isinstance(provided, list):
        values = [str(item).strip() for item in provided if str(item).strip()]
    else:
        values = [
            item.strip()
            for item in re.split(r"(?<=[，。！？；：,.!?;:])", text)
            if item.strip()
        ]
    if not values:
        values = [text.strip()]
    result: List[str] = []
    for value in values:
        value = value.replace("\n", " ").replace("\r", " ").strip()
        if len(value) <= max_chars:
            result.append(value)
            continue
        clauses = [
            item.strip()
            for item in re.split(r"(?<=[，、；：,;:])", value)
            if item.strip()
        ]
        current = ""
        for clause in clauses:
            if current and len(current + clause) > max_chars:
                result.append(current)
                current = clause
            else:
                current += clause
        if current:
            if len(current) <= max_chars:
                result.append(current)
            else:
                for offset in range(0, len(current), max_chars):
                    result.append(current[offset : offset + max_chars])
    return result or [text.strip()]


def detect_silence_centers(path: Path) -> List[float]:
    completed = run(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-38dB:d=0.08",
            "-f",
            "null",
            "-",
        ],
        capture=True,
        check=False,
    )
    stderr = completed.stderr or ""
    starts = [float(value) for value in re.findall(r"silence_start: ([0-9.]+)", stderr)]
    ends = [float(value) for value in re.findall(r"silence_end: ([0-9.]+)", stderr)]
    centers = []
    for index, end in enumerate(ends):
        start = starts[index] if index < len(starts) else end
        centers.append((start + end) / 2.0)
    return centers


def merge_phrases_for_timing(
    phrases: List[str], duration: float, silence_count: int, minimum: float = 0.62
) -> List[str]:
    values = list(phrases)
    maximum_segments = max(1, int(duration / minimum))
    target_count = min(maximum_segments, silence_count + 1 if silence_count else 1)
    while len(values) > target_count and len(values) > 1:
        best_index = min(
            range(len(values) - 1),
            key=lambda index: len(values[index]) + len(values[index + 1]),
        )
        values[best_index : best_index + 2] = [
            values[best_index] + values[best_index + 1]
        ]
    return values


def caption_timeline(
    text: str, provided: Any, audio: Path, duration: float
) -> List[Dict[str, Any]]:
    centers = [
        value for value in detect_silence_centers(audio) if 0.35 < value < duration - 0.35
    ]
    phrases = merge_phrases_for_timing(
        split_caption_text(text, provided), duration, len(centers)
    )
    if len(phrases) == 1:
        return [{"text": phrases[0], "start": 0.0, "end": duration}]
    weights = [max(1, len(re.sub(r"\\s+", "", item))) for item in phrases]
    total_weight = sum(weights)
    targets = []
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        targets.append(duration * cumulative / total_weight)
    boundaries: List[float] = []
    available = list(centers)
    previous = 0.0
    for index, target in enumerate(targets):
        remaining_boundaries = len(targets) - index - 1
        latest = duration - 0.62 * (remaining_boundaries + 1)
        candidates = [
            value
            for value in available
            if value >= previous + 0.62 and value <= latest
        ]
        if candidates:
            selected = min(candidates, key=lambda value: abs(value - target))
            available.remove(selected)
        else:
            selected = min(max(target, previous + 0.62), latest)
        boundaries.append(selected)
        previous = selected
    points = [0.0] + boundaries + [duration]
    return [
        {
            "text": phrase,
            "start": round(points[index], 6),
            "end": round(points[index + 1], 6),
        }
        for index, phrase in enumerate(phrases)
    ]


def normalize_video_to_audio(
    video: Path,
    audio_duration: float,
    output: Path,
    background_hex: str,
) -> Tuple[float, float]:
    raw_duration = media_duration(video)
    factor = audio_duration / raw_duration
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
            str(video),
            "-an",
            "-vf",
            (
                "scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0x{color},"
                f"setpts=PTS*{factor:.12f},fps=24"
            ),
            "-t",
            f"{audio_duration:.6f}",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output),
        ]
    )
    return raw_duration, factor


def concat_file_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'\n"


def concat_media(paths: Sequence[Path], output: Path, *, audio: bool) -> None:
    list_path = output.with_suffix(output.suffix + ".concat.txt")
    list_path.write_text(
        "".join(concat_file_line(path) for path in paths), encoding="utf-8"
    )
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
    ]
    if audio:
        command.extend(["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1"])
    else:
        command.extend(["-c:v", "copy", "-an"])
    command.append(str(output))
    run(command)


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return f"{hours}:{minutes:02d}:{remainder:05.2f}"


def ass_escape(text: str) -> str:
    return (
        text.replace("\\", "＼")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def caption_font_size(text: str) -> int:
    length = len(text)
    if length <= 14:
        return 36
    if length <= 18:
        return 33
    if length <= 22:
        return 30
    return 27


def write_ass(
    path: Path,
    captions: Sequence[Dict[str, Any]],
    *,
    font_name: str,
) -> None:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Caption,{font_name},34,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,48,48,34,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for item in captions:
        text = ass_escape(str(item["text"]))
        size = caption_font_size(text)
        lines.append(
            "Dialogue: 0,"
            f"{ass_time(float(item['start']))},"
            f"{ass_time(float(item['end']))},"
            f"Caption,,0,0,0,,{{\\fs{size}\\q2}}{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def ffmpeg_has_filter(name: str) -> bool:
    completed = run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture=True,
        check=False,
    )
    pattern = re.compile(rf"^\s*\S+\s+{re.escape(name)}\s", re.MULTILINE)
    return bool(pattern.search((completed.stdout or "") + (completed.stderr or "")))


def render_caption_png(
    output: Path,
    text: str,
    *,
    font_size: int,
    font_file: Optional[Path],
    font_name: str,
) -> None:
    if not command_path("magick"):
        raise SkillError(
            "FFmpeg has no ass filter and ImageMagick is unavailable; "
            "install an FFmpeg build with libass or provide ImageMagick."
        )
    font_value = str(font_file) if font_file else font_name
    run(
        [
            "magick",
            "-size",
            "1280x720",
            "xc:none",
            "-gravity",
            "south",
            "-font",
            font_value,
            "-pointsize",
            str(font_size),
            "-fill",
            "white",
            "-stroke",
            "black",
            "-strokewidth",
            "3",
            "-annotate",
            "+0+34",
            text,
            # ImageMagick paints a thick stroke over narrow CJK glyph interiors.
            # Repaint the white fill without a stroke so the requested white-on-
            # black treatment survives at delivery size.
            "-stroke",
            "none",
            "-fill",
            "white",
            "-annotate",
            "+0+34",
            text,
            str(output),
        ]
    )


def build_final(
    base_video: Path,
    narration: Path,
    subtitles: Path,
    output: Path,
    duration: float,
    fonts_dir: Optional[Path],
    captions: Sequence[Dict[str, Any]],
    *,
    font_file: Optional[Path],
    font_name: str,
) -> None:
    has_ass = ffmpeg_has_filter("ass")
    base_command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(base_video),
        "-i",
        str(narration),
    ]
    if has_ass:
        ass_filter = f"ass=filename='{escape_filter_path(subtitles)}'"
        if fonts_dir and fonts_dir.is_dir():
            ass_filter += f":fontsdir='{escape_filter_path(fonts_dir)}'"
        base_command.extend(["-vf", ass_filter])
    else:
        overlays_dir = output.parent / "caption-overlays"
        overlays_dir.mkdir(parents=True, exist_ok=True)
        filter_parts = []
        previous = "[0:v]"
        for index, caption in enumerate(captions):
            overlay = overlays_dir / f"{index + 1:03d}.png"
            render_caption_png(
                overlay,
                str(caption["text"]),
                font_size=caption_font_size(str(caption["text"])),
                font_file=font_file,
                font_name=font_name,
            )
            base_command.extend(["-loop", "1", "-i", str(overlay)])
            output_label = f"[captioned{index}]"
            filter_parts.append(
                f"{previous}[{index + 2}:v]overlay=0:0:"
                f"enable='between(t,{float(caption['start']):.6f},"
                f"{float(caption['end']):.6f})'{output_label}"
            )
            previous = output_label
        if filter_parts:
            base_command.extend(
                ["-filter_complex", ";".join(filter_parts), "-map", previous]
            )
    if has_ass:
        base_command.extend(["-map", "0:v:0"])
    base_command.extend(
        [
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.6f}",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    run(base_command)


def build_contact_sheet(video: Path, output: Path, duration: float) -> None:
    interval = max(0.5, duration / 12.0)
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            (
                f"fps=1/{interval:.6f},scale=320:180,"
                "tile=4x3:padding=2:margin=2:color=0x111111"
            ),
            "-frames:v",
            "1",
            str(output),
        ]
    )


def cmd_compose(args: argparse.Namespace) -> None:
    project = project_path(args.project)
    require_approved(project, "audio")
    for sample_stage in ("visual", "motion", "audio"):
        require_sample_approved(project, sample_stage)
    if not command_path("ffmpeg") or not command_path("ffprobe"):
        raise SkillError("FFmpeg and FFprobe are required for composition")
    script = load_json(project / "script.json")
    scene_ids = stage_scene_ids(script)
    motion = manifest_map(project / "motion" / "motion-manifest.json")
    audio = manifest_map(project / "audio" / "audio-manifest.json")
    composition = project / "composition"
    aligned_dir = composition / "aligned"
    aligned_dir.mkdir(parents=True, exist_ok=True)

    fonts_dir: Optional[Path] = None
    selected_font_file: Optional[Path] = None
    project_font = load_project_font(project)
    selected_font_name = str(args.font_name or "").strip()
    if args.font_file:
        source_font = Path(args.font_file).expanduser().resolve()
        if not source_font.is_file():
            raise SkillError(f"Font file is missing: {source_font}")
        fonts_dir = composition / "fonts"
        fonts_dir.mkdir(exist_ok=True)
        selected_font_file = fonts_dir / source_font.name
        shutil.copyfile(source_font, selected_font_file)
        selected_font_name = selected_font_name or source_font.stem
    elif (composition / "fonts").is_dir():
        selected_font_name = selected_font_name or str(
            project_font.get("family") or "sans-serif"
        )
        fonts_dir = composition / "fonts"
        selected_font_file = next(
            (
                item
                for item in fonts_dir.iterdir()
                if item.suffix.lower() in (".ttf", ".otf", ".ttc")
            ),
            None,
        )
    else:
        selected_font_name = selected_font_name or str(
            project_font.get("family") or "sans-serif"
        )
        selected = str(project_font.get("file") or "").strip()
        if selected:
            preferred = Path(selected).expanduser().resolve()
            if not preferred.is_file():
                raise SkillError(f"Selected caption font is missing: {preferred}")
            fonts_dir = composition / "fonts"
            fonts_dir.mkdir(exist_ok=True)
            selected_font_file = fonts_dir / preferred.name
            # System font files can carry protected macOS flags that copy2 tries
            # to reproduce. Only the font bytes are needed by the renderer.
            shutil.copyfile(preferred, selected_font_file)
    selected_font_name = selected_font_name or "sans-serif"

    timeline_scenes: List[Dict[str, Any]] = []
    global_captions: List[Dict[str, Any]] = []
    audio_paths: List[Path] = []
    scene_durations: Dict[str, float] = {}
    cursor = 0.0
    for scene_id in scene_ids:
        scene = find_scene(script, scene_id)
        audio_item = audio.get(scene_id)
        if not audio_item:
            raise SkillError(f"Missing approved audio artifact for scene {scene_id}")
        audio_path = resolve_project_file(project, str(audio_item.get("audio")))
        duration = media_duration(audio_path)
        scene_durations[scene_id] = duration
        local_captions = caption_timeline(
            str(scene.get("narration", "")).strip(),
            scene.get("caption_phrases"),
            audio_path,
            duration,
        )
        scene_captions = []
        for caption in local_captions:
            global_caption = {
                "text": caption["text"],
                "start": round(cursor + float(caption["start"]), 6),
                "end": round(cursor + float(caption["end"]), 6),
            }
            scene_captions.append(global_caption)
            global_captions.append(global_caption)
        timeline_scenes.append(
            {
                "id": scene_id,
                "start": round(cursor, 6),
                "end": round(cursor + duration, 6),
                "audio_duration": round(duration, 6),
                "audio": relative_to_project(project, audio_path),
                "captions": scene_captions,
            }
        )
        audio_paths.append(audio_path)
        cursor += duration

    request = load_json(project / "request.json")
    transition = request.get("transition") if isinstance(request.get("transition"), dict) else {
        "mode": "hard-cut",
        "duration_seconds": 0.0,
    }
    transition_mode = str(transition.get("mode") or "hard-cut")
    transition_duration = float(transition.get("duration_seconds") or 0.0)
    aligned_paths: List[Path] = []
    timeline_transitions: List[Dict[str, Any]] = []

    if transition_mode == "transition-separated":
        plan = load_json(project / "state" / "motion-plan.json")
        jobs = [item for item in listify(plan.get("jobs")) if isinstance(item, dict)]
        scene_index = {scene_id: index for index, scene_id in enumerate(scene_ids)}
        video_cursor = 0.0
        for job in jobs:
            job_id = str(job.get("id") or "")
            kind = str(job.get("kind") or "")
            motion_item = motion.get(job_id)
            if not job_id or not motion_item:
                raise SkillError(f"Missing approved motion artifact for job {job_id or job}")
            video_path = resolve_project_file(project, str(motion_item.get("video")))
            if kind == "transition":
                target_duration = transition_duration
                from_scene = str(job.get("from_scene") or "")
                to_scene = str(job.get("to_scene") or "")
                if not from_scene or not to_scene:
                    raise SkillError(f"Transition job {job_id} is missing scene endpoints")
                background_scene = find_scene(script, from_scene)
                transition_start = video_cursor
                transition_midpoint = transition_start + target_duration / 2.0
                transition_end = transition_start + target_duration
                expected_handoff = sum(
                    scene_durations[value]
                    for value in scene_ids[: scene_index[to_scene]]
                )
                if abs(transition_midpoint - expected_handoff) > 0.02:
                    raise SkillError(
                        f"Transition {job_id} midpoint does not match narration handoff"
                    )
                timeline_transitions.append(
                    {
                        "id": job_id,
                        "from_scene": from_scene,
                        "to_scene": to_scene,
                        "start": round(transition_start, 6),
                        "midpoint": round(transition_midpoint, 6),
                        "end": round(transition_end, 6),
                    }
                )
            elif kind in ("content", "terminal-content"):
                scene_id = str(job.get("scene_id") or motion_item.get("scene_id") or "")
                if scene_id not in scene_index:
                    raise SkillError(f"Content job {job_id} has invalid scene_id")
                index = scene_index[scene_id]
                deductions = 0.0
                if index > 0:
                    deductions += transition_duration / 2.0
                if index < len(scene_ids) - 1:
                    deductions += transition_duration / 2.0
                target_duration = scene_durations[scene_id] - deductions
                if target_duration <= 0.2:
                    raise SkillError(
                        f"Narration for scene {scene_id} is too short for planned transitions"
                    )
                background_scene = find_scene(script, scene_id)
            else:
                raise SkillError(f"Unsupported motion job kind for composition: {kind}")
            aligned_path = aligned_dir / f"{job_id}.mp4"
            raw_duration, factor = normalize_video_to_audio(
                video_path,
                target_duration,
                aligned_path,
                str(background_scene.get("visual", {}).get("background_hex") or "#000000"),
            )
            aligned_paths.append(aligned_path)
            video_cursor += target_duration
            if kind in ("content", "terminal-content"):
                scene_record = timeline_scenes[scene_index[scene_id]]
                scene_record["content_job"] = job_id
                scene_record["raw_video_duration"] = round(raw_duration, 6)
                scene_record["video_setpts_factor"] = round(factor, 9)
                scene_record["aligned_video"] = relative_to_project(project, aligned_path)
        if abs(video_cursor - cursor) > 0.02:
            raise SkillError("Separated-transition video timeline differs from audio clock")
    else:
        for scene_id in scene_ids:
            scene = find_scene(script, scene_id)
            motion_item = motion.get(scene_id)
            if not motion_item:
                raise SkillError(f"Missing approved motion artifact for scene {scene_id}")
            video_path = resolve_project_file(project, str(motion_item.get("video")))
            slug = str(scene.get("slug") or "scene")
            aligned_path = aligned_dir / f"{scene_id}-{slug}.mp4"
            raw_duration, factor = normalize_video_to_audio(
                video_path,
                scene_durations[scene_id],
                aligned_path,
                str(scene.get("visual", {}).get("background_hex") or "#000000"),
            )
            aligned_paths.append(aligned_path)
            scene_record = timeline_scenes[scene_ids.index(scene_id)]
            scene_record["raw_video_duration"] = round(raw_duration, 6)
            scene_record["video_setpts_factor"] = round(factor, 9)
            scene_record["aligned_video"] = relative_to_project(project, aligned_path)

    timing = {
        "schema_version": "1.0",
        "timebase": "audio",
        "generated_at": iso_now(),
        "transition": {
            "mode": transition_mode,
            "duration_seconds": transition_duration,
        },
        "scenes": timeline_scenes,
        "transitions": timeline_transitions,
        "total_duration": round(cursor, 6),
    }
    timing_path = composition / "timing.json"
    write_json(timing_path, timing)
    subtitles = composition / "subtitles.ass"
    write_ass(subtitles, global_captions, font_name=selected_font_name)

    base_video = composition / "base-video.mp4"
    narration = composition / "narration.wav"
    concat_media(aligned_paths, base_video, audio=False)
    concat_media(audio_paths, narration, audio=True)
    final = composition / "final.mp4"
    build_final(
        base_video,
        narration,
        subtitles,
        final,
        cursor,
        fonts_dir,
        global_captions,
        font_file=selected_font_file,
        font_name=selected_font_name,
    )
    decode_check(final)
    contact = composition / "contact-sheet.jpg"
    build_contact_sheet(final, contact, cursor)
    summary = media_summary(final)
    captions_single_line = all(
        "\n" not in str(item.get("text", "")) and "\r" not in str(item.get("text", ""))
        for item in global_captions
    )
    no_gaps = all(
        abs(
            float(timeline_scenes[index]["end"])
            - float(timeline_scenes[index + 1]["start"])
        )
        < 0.001
        for index in range(len(timeline_scenes) - 1)
    )
    qa = {
        "schema_version": "1.0",
        "checked_at": iso_now(),
        "full_decode_passed": True,
        "single_line_captions": captions_single_line,
        "no_gaps": no_gaps,
        "audio_master_timing": True,
        "media": summary,
        "human_visual_review": "pending",
    }
    write_json(composition / "qa.json", qa)
    print(final)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--font-file")
    parser.add_argument("--font-name")
    parser.set_defaults(func=cmd_compose)
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
