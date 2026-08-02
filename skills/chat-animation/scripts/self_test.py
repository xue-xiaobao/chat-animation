#!/usr/bin/env python3
"""Offline end-to-end test with local mock Agnes/MiMo providers."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from common import load_json, write_json


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROJECT_CLI = SCRIPT_DIR / "project.py"
PROVIDERS_CLI = SCRIPT_DIR / "providers.py"
COMPOSE_CLI = SCRIPT_DIR / "compose.py"


def run_cli(
    command: list[str],
    *,
    env: Dict[str, str],
    expect: int = 0,
) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"Command returned {completed.returncode}, expected {expect}:\n"
            f"{' '.join(command)}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


def make_test_media(root: Path) -> tuple[Path, Path, Path, Path]:
    first = root / "first.png"
    end = root / "end.png"
    video = root / "mock.mp4"
    wav = root / "mock.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2D1747:s=1280x720:r=24",
            "-vf",
            "drawbox=x=260:y=180:w=300:h=300:color=0xE94F37:t=fill",
            "-frames:v",
            "1",
            str(first),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2D1747:s=1280x720:r=24",
            "-vf",
            "drawbox=x=260:y=180:w=300:h=300:color=0xE94F37:t=fill,"
            "drawbox=x=720:y=220:w=260:h=260:color=0x2CB5A0:t=fill",
            "-frames:v",
            "1",
            str(end),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x2D1747:s=1280x720:d=3.4:r=24",
            "-vf",
            "drawbox=x='260+20*t':y=180:w=300:h=300:color=0xE94F37:t=fill,"
            "drawbox=x='720-20*t':y=220:w=260:h=260:color=0x2CB5A0:t=fill",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2.2:sample_rate=48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav),
        ],
        check=True,
    )
    return first, end, video, wav


class MockState:
    video: Path
    first_image: Path
    end_image: Path
    wav_bytes: bytes
    base_url: str
    image_requests: list[Dict[str, Any]]
    video_requests: list[Dict[str, Any]]
    mimo_requests: list[Dict[str, Any]]


def start_mock_server(
    video: Path, first_image: Path, end_image: Path, wav: Path
) -> tuple[ThreadingHTTPServer, MockState]:
    state = MockState()
    state.video = video
    state.first_image = first_image
    state.end_image = end_image
    state.wav_bytes = wav.read_bytes()
    state.image_requests = []
    state.video_requests = []
    state.mimo_requests = []

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value: Dict[str, Any], status: int = 200) -> None:
            raw = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/v1/videos":
                state.video_requests.append(payload)
                self.send_json({"video_id": "mock-video-1", "status": "queued"})
                return
            if self.path == "/v1/images/generations":
                state.image_requests.append(payload)
                prompt = str(payload.get("prompt", "")).lower()
                filename = (
                    "mock-first.png"
                    if "first keyframe" in prompt or "initial state" in prompt
                    else "mock-end.png"
                )
                self.send_json(
                    {"data": [{"url": f"{state.base_url}/files/{filename}"}]}
                )
                return
            if self.path == "/v1/chat/completions":
                if payload.get("model") in (
                    "mimo-v2.5-tts",
                    "mimo-v2.5-tts-voiceclone",
                ):
                    state.mimo_requests.append(payload)
                    self.send_json(
                        {
                            "id": "mock-mimo-1",
                            "choices": [
                                {
                                    "message": {
                                        "audio": {
                                            "data": base64.b64encode(
                                                state.wav_bytes
                                            ).decode("ascii")
                                        }
                                    }
                                }
                            ],
                        }
                    )
                else:
                    self.send_json(
                        {"choices": [{"message": {"content": "OK"}}], "usage": {}}
                    )
                return
            self.send_json({"error": "not found"}, status=404)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/agnesapi?"):
                self.send_json(
                    {
                        "video_id": "mock-video-1",
                        "status": "completed",
                        "video_url": f"{state.base_url}/files/mock.mp4",
                    }
                )
                return
            if self.path == "/files/mock.mp4":
                raw = state.video.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if self.path in ("/files/mock-first.png", "/files/mock-end.png"):
                source = (
                    state.first_image
                    if self.path.endswith("mock-first.png")
                    else state.end_image
                )
                raw = source.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_json({"error": "not found"}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.base_url = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, state


def sample_script() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": {
            "title": "最小闭环测试",
            "one_sentence_takeaway": "清楚的流程让复杂动画可以逐层检查。",
            "narrative_arc": ["提出问题", "解释机制", "给出结论"],
            "transition": {
                "mode": "transition-separated",
                "duration_seconds": 1.0,
            },
        },
        "research": {
            "question_type": "concept",
            "supporting_points": ["分层可以局部返工"],
            "misconceptions": [],
            "boundaries": ["这是工作流测试"],
            "sources": [],
        },
        "style_bible": {
            "id": "vox",
            "version": "2.0",
            "source": "chat-animation-internal",
            "name": "Vox Style",
            "continuity": "flat purple paper, cream keylines",
            "caption_safe_area": "lower 16 percent",
            "avoid": ["logo", "watermark", "UI", "glossy 3D"],
        },
        "scenes": [
            {
                "id": "01",
                "slug": "test",
                "purpose": "测试最小闭环",
                "narration": "清楚的流程，让复杂动画也能逐层检查。",
                "caption_phrases": ["清楚的流程", "让复杂动画也能逐层检查。"],
                "emotion": "笃定",
                "visual": {
                    "meaning": "两个模块稳定落位",
                    "metaphor": "红色和青绿色纸片从两侧进入并锁定",
                    "elements": ["红色模块", "青绿模块", "连接关系"],
                    "background_hex": "#2D1747",
                    "accent_colors": ["#E94F37", "#2CB5A0", "#F3E8CE"],
                    "first_frame": {
                        "type": "content-keyframe",
                        "description": "红色模块已在画面左侧，关系尚未连接",
                    },
                    "end_frame": "两个模块在画面中央稳定落位",
                    "assembly_order": ["红色模块", "青绿模块", "连接关系"],
                    "ambiguities_to_avoid": ["不要出现交易界面"],
                },
                "first_frame_prompt": (
                    "Create a content-rich first keyframe for a locked 16:9 "
                    "editorial paper collage showing the initial state: one large "
                    "red cardstock module already visible on a flat purple paper "
                    "field, crisp cream keylines, soft shadows, no text, no logo, "
                    "no UI, no watermark, and a quiet lower caption area."
                ),
                "image_prompt": (
                    "Create a completed 16:9 editorial paper collage with two "
                    "large colored cardstock modules on a flat purple paper field, "
                    "crisp cream keylines, soft paper shadows, no text, no logo, "
                    "no UI, no watermark, and a quiet lower caption area."
                ),
                "motion_prompt": (
                    "Use Image 1 as the exact first frame and Image 2 as the exact "
                    "completed last frame. Lock the camera and background. Slide "
                    "the existing red paper module in slowly, then the teal module. "
                    "Hold the final composition with one slow 0.5% breathing pulse. "
                    "No camera movement, no cut, no new object, no morphing, no text, "
                    "no sound. End on Image 2."
                ),
            }
        ],
    }


def sample_motion_plan() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "transition": {
            "mode": "transition-separated",
            "duration_seconds": 1.0,
        },
        "states": [
            {"id": "01-first", "scene_id": "01", "role": "content-first"},
            {"id": "01-end", "scene_id": "01", "role": "content-end"},
        ],
        "jobs": [
            {
                "id": "content-01",
                "kind": "content",
                "first": "01-first",
                "end": "01-end",
            }
        ],
        "narration_handoffs": [],
    }


def sample_storybook_script() -> Dict[str, Any]:
    value = sample_script()
    value["style_bible"].update(
        {
            "id": "storybook",
            "version": "1.0",
            "name": "storybook",
            "continuity": "warm layered cut-paper storybook diorama",
        }
    )
    hero_prompt = (
        "Create an authoritative hero frame for a locked 16:9 warm tactile "
        "layered cut-paper storybook diorama. Show two friendly paper-sticker "
        "characters beside a small village shop, already arranged in their final "
        "positions, with warm off-white outlines, fine paper fibers, soft consistent "
        "shadows, natural hands and feet, no text, no logo, no UI, no watermark, "
        "and a visually quiet lower caption area."
    )
    value["scenes"][0]["first_frame_prompt"] = hero_prompt
    value["scenes"][0]["image_prompt"] = hero_prompt
    value["scenes"][0]["motion_prompt"] = (
        "Use Image 1 and Image 2 as the exact same authoritative hero frame. "
        "Lock the camera and background. Gently scale the foreground paper-sticker "
        "characters from 96% to 100% without overshoot, then apply only one slow "
        "breathing pulse while every position remains fixed. No camera movement, "
        "no translation, no morphing, no text, no new object, no scene transition, "
        "and no sound. End on Image 2."
    )
    return value


def sample_two_scene_script() -> Dict[str, Any]:
    value = sample_script()
    second = json.loads(json.dumps(value["scenes"][0]))
    second["id"] = "02"
    second["slug"] = "second"
    second["purpose"] = "测试第二个内容动画"
    second["narration"] = "第二个场景继续解释，并在转场中点接过旁白。"
    second["caption_phrases"] = ["第二个场景继续解释", "并在转场中点接过旁白。"]
    second["first_frame_prompt"] = second["first_frame_prompt"].replace(
        "one large red", "one large mustard"
    )
    second["image_prompt"] = second["image_prompt"].replace(
        "two large colored", "three large colored"
    )
    second["motion_prompt"] = second["motion_prompt"].replace(
        "red paper module", "mustard paper module"
    )
    value["scenes"].append(second)
    return value


def sample_two_scene_motion_plan() -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "transition": {
            "mode": "transition-separated",
            "duration_seconds": 1.0,
        },
        "states": [
            {"id": "01-first", "scene_id": "01", "role": "content-first"},
            {"id": "01-end", "scene_id": "01", "role": "content-end"},
            {"id": "02-first", "scene_id": "02", "role": "content-first"},
            {"id": "02-end", "scene_id": "02", "role": "content-end"},
        ],
        "jobs": [
            {
                "id": "content-01",
                "kind": "content",
                "scene_id": "01",
                "first": "01-first",
                "end": "01-end",
            },
            {
                "id": "transition-01-02",
                "kind": "transition",
                "from_scene": "01",
                "to_scene": "02",
                "first": "01-end",
                "end": "02-first",
                "motion_prompt": (
                    "Use Image 1 as the exact completed first state and Image 2 as "
                    "the exact next content-rich state. Preserve the existing paper "
                    "anchor, use no empty reset and no hard cut, introduce no unrelated "
                    "object, no text and no sound. End exactly on Image 2."
                ),
            },
            {
                "id": "content-02",
                "kind": "content",
                "scene_id": "02",
                "first": "02-first",
                "end": "02-end",
            },
        ],
        "narration_handoffs": [
            {"from_scene": "01", "to_scene": "02", "at": "transition-midpoint"}
        ],
    }


def set_all_qa_true(path: Path, keys: list[str]) -> None:
    value = load_json(path)
    for item in value.get("scenes", []):
        qa = item.setdefault("qa", {})
        for key in keys:
            qa[key] = True
        qa["note"] = "Offline integration fixture inspected by the test harness."
    write_json(path, value)


def main() -> None:
    runtime_sources = [SKILL_ROOT / "SKILL.md"]
    runtime_sources.extend(sorted((SKILL_ROOT / "references").glob("*")))
    runtime_sources.extend(
        path
        for path in sorted((SKILL_ROOT / "scripts").glob("*.py"))
        if path.name != "self_test.py"
    )
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in runtime_sources
        if path.is_file()
    ).casefold()
    for forbidden in (
        "$skills_path",
        "/.codex/skills/",
        "/.agents/skills/",
        "npx skills",
        "skill://",
    ):
        assert forbidden not in runtime_text, f"external Skill route leaked: {forbidden}"

    with tempfile.TemporaryDirectory(prefix="chat-animation-self-test-") as temp_name:
        root = Path(temp_name)
        first, end, mock_video, mock_wav = make_test_media(root)
        server, state = start_mock_server(mock_video, first, end, mock_wav)
        try:
            clean_env = dict(os.environ)
            for name in (
                "AGNES_API_KEY",
                "AGNES_API_TOKEN",
                "APIHUB_AGNES_API_KEY",
                "AGNES_GLOBAL_API_KEY",
                "AGNES_CN_API_KEY",
                "MIMO_API_KEY",
                "CHAT_ANIMATION_AGNES_REGION",
                "CHAT_ANIMATION_AGNES_BASE_URL",
                "CHAT_ANIMATION_AGNES_GLOBAL_BASE_URL",
                "CHAT_ANIMATION_AGNES_CN_BASE_URL",
                "CHAT_ANIMATION_CREDENTIALS_FILE",
            ):
                clean_env.pop(name, None)
            credentials_file = root / "user-home" / ".chat-animation" / "credentials.env"
            clean_env["CHAT_ANIMATION_CREDENTIALS_FILE"] = str(credentials_file)
            blocked = run_cli(
                [sys.executable, str(PROJECT_CLI), "preflight"],
                env=clean_env,
                expect=2,
            )
            assert "BLOCKED" in blocked.stdout

            configure_env = dict(clean_env)
            configure_env.update(
                {
                    "AGNES_CN_API_KEY": "mock-cn-agnes-token",
                    "MIMO_API_KEY": "mock-mimo-token",
                }
            )
            configured = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "configure-credentials",
                    "--from-env",
                ],
                env=configure_env,
            )
            configured_report = json.loads(configured.stdout)
            assert configured_report["stored"] == ["AGNES_CN_API_KEY", "MIMO_API_KEY"]
            assert credentials_file.is_file()
            if os.name != "nt":
                assert credentials_file.stat().st_mode & 0o777 == 0o600

            cn_env = dict(clean_env)
            cn_env["CHAT_ANIMATION_AGNES_REGION"] = "cn"
            cn_ready = run_cli(
                [sys.executable, str(PROJECT_CLI), "preflight", "--json"],
                env=cn_env,
            )
            cn_report = json.loads(cn_ready.stdout)
            assert cn_report["tokens"]["agnes"] == {
                "configured": True,
                "environment_variable": "AGNES_CN_API_KEY",
                "region": "cn",
                "base_url": "https://api.agnes-ai.cn",
                "source": "credentials-file",
            }
            cn_env["CHAT_ANIMATION_DISABLE_FONT_DOWNLOAD"] = "1"
            cn_created = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(root / "cn-projects"),
                    "--name",
                    "cn-region-test",
                    "--idea",
                    "测试 Agnes CN 项目绑定",
                ],
                env=cn_env,
            )
            cn_request = load_json(Path(cn_created.stdout.strip()) / "request.json")
            assert cn_request["agnes"] == {
                "region": "cn",
                "base_url": "https://api.agnes-ai.cn",
            }
            ambiguous_env = dict(cn_env)
            ambiguous_env.pop("CHAT_ANIMATION_AGNES_REGION", None)
            ambiguous_env["AGNES_GLOBAL_API_KEY"] = "mock-global-agnes-token"
            ambiguous = run_cli(
                [sys.executable, str(PROJECT_CLI), "preflight", "--json"],
                env=ambiguous_env,
                expect=2,
            )
            assert "Both Agnes Global and CN credentials are configured" in ambiguous.stderr

            env = dict(clean_env)
            env.update(
                {
                    "AGNES_API_KEY": "mock-agnes-token",
                    "MIMO_API_KEY": "mock-mimo-token",
                    "CHAT_ANIMATION_AGNES_REGION": "global",
                    "CHAT_ANIMATION_AGNES_BASE_URL": state.base_url,
                    "CHAT_ANIMATION_MIMO_BASE_URL": state.base_url,
                    "CHAT_ANIMATION_DISABLE_FONT_DOWNLOAD": "1",
                    "CHAT_ANIMATION_FONT_CACHE_DIR": str(root / "font-cache"),
                    "CHAT_ANIMATION_VOICE_TIMING_CACHE": str(
                        root / "voice-timing-cache.json"
                    ),
                }
            )
            ready = run_cli(
                [sys.executable, str(PROJECT_CLI), "preflight", "--json"],
                env=env,
            )
            ready_report = json.loads(ready.stdout)
            assert ready_report["style_registry"] == {
                "default_style_id": "vox",
                "available_style_ids": ["vox", "storybook"],
            }
            assert set(ready_report["optional"]) == {
                "imagemagick",
                "caption_font",
                "disk_recommendation",
            }
            projects = root / "projects"
            created_1 = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "workflow-test",
                    "--idea",
                    "测试五阶段动画",
                ],
                env=env,
            )
            project = Path(created_1.stdout.strip())
            created_2 = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "workflow-test",
                    "--idea",
                    "测试第二版",
                ],
                env=env,
            )
            assert project.name.endswith("_01")
            assert Path(created_2.stdout.strip()).name.endswith("_02")
            request = load_json(project / "request.json")
            style_selection = load_json(project / "state" / "style-selection.json")
            font_selection = load_json(project / "state" / "font-selection.json")
            assert request["style_id"] == "vox"
            assert request["style_version"] == "2.0"
            assert font_selection["requested"] == "smiley-sans"
            assert font_selection["source"].startswith("system-fallback")
            assert request["caption_font"]["family"] == font_selection["family"]
            assert request["transition"] == {
                "mode": "hard-cut",
                "duration_seconds": 0.0,
            }
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "set-transition",
                    str(project),
                    "--mode",
                    "transition-fused",
                    "--duration",
                    "1.4",
                ],
                env=env,
            )
            assert load_json(project / "request.json")["transition"] == {
                "mode": "transition-fused",
                "duration_seconds": 1.4,
            }
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "set-transition",
                    str(project),
                    "--mode",
                    "hard-cut",
                ],
                env=env,
            )
            assert load_json(project / "request.json")["transition"] == {
                "mode": "hard-cut",
                "duration_seconds": 0.0,
            }
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "set-transition",
                    str(project),
                    "--mode",
                    "transition-separated",
                ],
                env=env,
            )
            assert style_selection["source"] == "chat-animation-internal"
            assert (project / "state" / "style-definition.md").is_file()
            unknown_style = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "unknown-style",
                    "--idea",
                    "不应创建",
                    "--style",
                    "missing-style",
                ],
                env=env,
                expect=2,
            )
            assert "Unknown style" in unknown_style.stderr

            write_json(project / "script.json", sample_script())
            write_json(project / "state" / "motion-plan.json", sample_motion_plan())
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "set-style",
                    str(project),
                    "--style",
                    "纸拼贴",
                ],
                env=env,
            )
            assert (
                project / "state" / "style-history" / "v01" / "style-selection.json"
            ).is_file()
            assert (
                project / "state" / "style-history" / "v01" / "style-definition.md"
            ).is_file()
            wrong_style_name = sample_script()
            wrong_style_name["style_bible"]["name"] = "适用题材列表"
            write_json(project / "script.json", wrong_style_name)
            rejected_name = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate",
                    str(project),
                    "director",
                ],
                env=env,
                expect=2,
            )
            assert "style_bible.name does not match style selection" in (
                rejected_name.stderr
            )
            write_json(project / "script.json", sample_script())
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "register-visual",
                    str(project),
                    "--scene",
                    "01",
                    "--end",
                    str(end),
                    "--first",
                    str(first),
                ],
                env=env,
                expect=2,
            )
            run_cli(
                [sys.executable, str(PROJECT_CLI), "validate", str(project), "director"],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(project),
                    "director",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "fixture approved",
                ],
                env=env,
            )
            identical_keyframes = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "register-visual",
                    str(project),
                    "--scene",
                    "01",
                    "--first",
                    str(end),
                    "--end",
                    str(end),
                ],
                env=env,
                expect=2,
            )
            assert "first and end frames are identical" in identical_keyframes.stderr
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-image",
                    str(project),
                    "--scene",
                    "01",
                ],
                env=env,
            )
            blocked_second_visual = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "register-visual",
                    str(project),
                    "--scene",
                    "02",
                    "--end",
                    str(end),
                    "--first",
                    str(first),
                ],
                env=env,
                expect=2,
            )
            assert "Only one sample scene" in blocked_second_visual.stderr
            visual_manifest = project / "visual" / "visual-manifest.json"
            set_all_qa_true(
                visual_manifest,
                [
                    "first_frame_meaningful",
                    "metaphor_readable",
                    "anatomy_valid",
                    "no_unwanted_text",
                    "caption_safe",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate-sample",
                    str(project),
                    "visual",
                    "--scene",
                    "01",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve-sample",
                    str(project),
                    "visual",
                    "--scene",
                    "01",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "visual sample approved",
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(PROJECT_CLI), "validate", str(project), "visual"],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(project),
                    "visual",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "fixture approved",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(project),
                    "--voice-file",
                    str(mock_wav),
                    "--context",
                    "自然清晰的中文科普解说，语速中等，停顿克制，重点词略加强调。",
                ],
                env=env,
            )
            blocked_motion_batch = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(project),
                    "--all",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                ],
                env=env,
                expect=2,
            )
            assert "sample has not been human-approved" in blocked_motion_batch.stderr
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(project),
                    "--scene",
                    "01",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                ],
                env=env,
            )
            motion_manifest = project / "motion" / "motion-manifest.json"
            set_all_qa_true(
                motion_manifest,
                [
                    "keyframes_respected",
                    "camera_locked",
                    "no_mutation",
                    "end_frame_respected",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate-sample",
                    str(project),
                    "motion",
                    "--scene",
                    "01",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve-sample",
                    str(project),
                    "motion",
                    "--scene",
                    "01",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "motion sample approved",
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(PROJECT_CLI), "validate", str(project), "motion"],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(project),
                    "motion",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "fixture approved",
                ],
                env=env,
            )
            blocked_audio_batch = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(project),
                    "--all",
                    "--voice-file",
                    str(mock_wav),
                ],
                env=env,
                expect=2,
            )
            assert "sample has not been human-approved" in blocked_audio_batch.stderr
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(project),
                    "--scene",
                    "01",
                    "--voice-file",
                    str(mock_wav),
                ],
                env=env,
            )
            audio_manifest = project / "audio" / "audio-manifest.json"
            set_all_qa_true(
                audio_manifest, ["narration_verified", "natural_delivery"]
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate-sample",
                    str(project),
                    "audio",
                    "--scene",
                    "01",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve-sample",
                    str(project),
                    "audio",
                    "--scene",
                    "01",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "audio sample approved",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(project),
                    "--all",
                    "--voice-file",
                    str(mock_wav),
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(PROJECT_CLI), "validate", str(project), "audio"],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(project),
                    "audio",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "fixture approved",
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(COMPOSE_CLI), str(project)],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate",
                    str(project),
                    "composition",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(project),
                    "composition",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "fixture approved",
                ],
                env=env,
            )
            status = run_cli(
                [sys.executable, str(PROJECT_CLI), "status", str(project)], env=env
            )
            status_data = json.loads(status.stdout)
            assert all(item["status"] == "approved" for item in status_data["stages"])

            assert len(state.image_requests) == 2
            assert all(
                item["model"] == "agnes-image-2.1-flash"
                for item in state.image_requests
            )
            assert state.image_requests[0]["prompt"] != state.image_requests[1]["prompt"]
            generated_visual = load_json(project / "visual" / "visual-manifest.json")
            generated_entry = generated_visual["scenes"][0]
            generated_provider = load_json(
                project / generated_entry["provider_record"]
            )
            assert generated_provider["agnes"] == {
                "region": "global",
                "base_url": state.base_url,
            }
            assert "first_frame_reused_from" not in generated_entry
            assert generated_entry["first_frame_prompt_sha256"]
            assert generated_entry["end_frame_prompt_sha256"]
            assert (project / generated_entry["first_frame"]).read_bytes() != (
                project / generated_entry["end_frame"]
            ).read_bytes()

            storybook_created = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "storybook-test",
                    "--idea",
                    "测试共享主画面风格",
                    "--style",
                    "storybook",
                    "--transition-mode",
                    "transition-separated",
                ],
                env=env,
            )
            storybook_project = Path(storybook_created.stdout.strip())
            storybook_selection = load_json(
                storybook_project / "state" / "style-selection.json"
            )
            assert storybook_selection["id"] == "storybook"
            assert storybook_selection["frame_policy"] == "shared-hero-frame"
            assert (
                storybook_selection["motion_strategy"]
                == "same-frame-breathing-keyframes"
            )
            write_json(storybook_project / "script.json", sample_storybook_script())
            write_json(
                storybook_project / "state" / "motion-plan.json",
                sample_motion_plan(),
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "validate",
                    str(storybook_project),
                    "director",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "approve",
                    str(storybook_project),
                    "director",
                    "--reviewer",
                    "self-test-human",
                    "--note",
                    "storybook fixture approved",
                ],
                env=env,
            )
            rejected_distinct_storybook = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "register-visual",
                    str(storybook_project),
                    "--scene",
                    "01",
                    "--first",
                    str(first),
                    "--end",
                    str(end),
                ],
                env=env,
                expect=2,
            )
            assert "must be the same image" in rejected_distinct_storybook.stderr
            storybook_image_request_start = len(state.image_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-image",
                    str(storybook_project),
                    "--scene",
                    "01",
                ],
                env=env,
            )
            assert len(state.image_requests) - storybook_image_request_start == 1
            storybook_visual = load_json(
                storybook_project / "visual" / "visual-manifest.json"
            )["scenes"][0]
            assert storybook_visual["frame_policy"] == "shared-hero-frame"
            assert (
                storybook_visual["first_frame"] == storybook_visual["end_frame"]
            )
            assert len(state.video_requests) == 1
            video_request = state.video_requests[0]
            assert video_request["model"] == "agnes-video-v2.0"
            assert video_request["width"] == 1280
            assert video_request["height"] == 720
            assert video_request["extra_body"]["mode"] == "keyframes"
            assert len(video_request["extra_body"]["image"]) == 2
            assert len(state.mimo_requests) == 1
            assert state.mimo_requests[0]["model"] == "mimo-v2.5-tts-voiceclone"
            assert state.mimo_requests[0]["audio"]["voice"].startswith(
                "data:audio/wav;base64,"
            )

            missing_auto_note = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "auto-without-note",
                    "--idea",
                    "不应创建",
                    "--full-auto",
                ],
                env=env,
                expect=2,
            )
            assert "requires --approval-note" in missing_auto_note.stderr

            created_auto = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "full-auto-test",
                    "--idea",
                    "测试全自动完成",
                    "--full-auto",
                    "--approval-note",
                    "请全自动完成，跳过所有审批",
                    "--transition-mode",
                    "transition-separated",
                ],
                env=env,
            )
            auto_project = Path(created_auto.stdout.strip())
            auto_request = load_json(auto_project / "request.json")
            assert auto_request["approval_mode"] == "full-auto"
            assert auto_request["approval_note"] == "请全自动完成，跳过所有审批"
            write_json(auto_project / "script.json", sample_script())
            write_json(
                auto_project / "state" / "motion-plan.json", sample_motion_plan()
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(auto_project),
                    "director",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-image",
                    str(auto_project),
                    "--scene",
                    "01",
                ],
                env=env,
            )
            set_all_qa_true(
                auto_project / "visual" / "visual-manifest.json",
                [
                    "first_frame_meaningful",
                    "metaphor_readable",
                    "anatomy_valid",
                    "no_unwanted_text",
                    "caption_safe",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(auto_project),
                    "visual",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(auto_project),
                    "--voice",
                    "茉莉",
                    "--context",
                    "自然清晰的中文科普解说，语速中等，停顿克制，重点词略加强调。",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(auto_project),
                    "--all",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                    "--num-frames",
                    "81",
                ],
                env=env,
            )
            set_all_qa_true(
                auto_project / "motion" / "motion-manifest.json",
                [
                    "keyframes_respected",
                    "camera_locked",
                    "no_mutation",
                    "end_frame_respected",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(auto_project),
                    "motion",
                ],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(auto_project),
                    "--all",
                    "--voice",
                    "茉莉",
                ],
                env=env,
            )
            set_all_qa_true(
                auto_project / "audio" / "audio-manifest.json",
                ["narration_verified", "natural_delivery"],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(auto_project),
                    "audio",
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(COMPOSE_CLI), str(auto_project)],
                env=env,
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(auto_project),
                    "composition",
                ],
                env=env,
            )
            auto_status = run_cli(
                [sys.executable, str(PROJECT_CLI), "status", str(auto_project)],
                env=env,
            )
            auto_status_data = json.loads(auto_status.stdout)
            assert auto_status_data["approval_mode"] == "full-auto"
            assert all(
                item["status"] == "auto_completed"
                for item in auto_status_data["stages"]
            )
            assert all(
                item["status"] == "skipped"
                for item in auto_status_data["sample_gates"]
            )
            assert not list((auto_project / "reviews").glob("*-sample.json"))
            for review_path_value in (auto_project / "reviews").glob("*.json"):
                review_value = load_json(review_path_value)
                assert review_value["human_review"]["status"] == "skipped"
                assert review_value["automation_review"]["status"] == "completed"

            created_transition = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "transition-separated-test",
                    "--idea",
                    "测试内容动画、独立转场和下一内容动画",
                    "--full-auto",
                    "--approval-note",
                    "请全自动完成，跳过所有审批",
                    "--transition-mode",
                    "transition-separated",
                ],
                env=env,
            )
            transition_project = Path(created_transition.stdout.strip())
            write_json(transition_project / "script.json", sample_two_scene_script())
            write_json(
                transition_project / "state" / "motion-plan.json",
                sample_two_scene_motion_plan(),
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(transition_project),
                    "director",
                ],
                env=env,
            )
            for scene_id in ("01", "02"):
                run_cli(
                    [
                        sys.executable,
                        str(PROVIDERS_CLI),
                        "agnes-image",
                        str(transition_project),
                        "--scene",
                        scene_id,
                    ],
                    env=env,
                )
            set_all_qa_true(
                transition_project / "visual" / "visual-manifest.json",
                [
                    "first_frame_meaningful",
                    "metaphor_readable",
                    "anatomy_valid",
                    "no_unwanted_text",
                    "caption_safe",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(transition_project),
                    "visual",
                ],
                env=env,
            )
            default_calibration_start = len(state.mimo_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(transition_project),
                    "--voice",
                    "白桦",
                ],
                env=env,
            )
            assert len(state.mimo_requests) == default_calibration_start
            assert load_json(transition_project / "state" / "voice-timing.json")[
                "source"
            ] == "built-in-default"
            calibration_request_start = len(state.mimo_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(transition_project),
                    "--voice",
                    "茉莉",
                ],
                env=env,
            )
            assert len(state.mimo_requests) - calibration_request_start == 1
            timing_profile = load_json(
                transition_project / "state" / "voice-timing.json"
            )
            assert timing_profile["voice"] == "茉莉"
            assert timing_profile["source"] == "measured-sample"
            assert timing_profile["seconds_per_character"] > 0
            repeat_calibration_start = len(state.mimo_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(transition_project),
                    "--voice",
                    "茉莉",
                ],
                env=env,
            )
            assert len(state.mimo_requests) == repeat_calibration_start
            cached_project_result = run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "init",
                    "--projects-root",
                    str(projects),
                    "--name",
                    "voice-cache-test",
                    "--idea",
                    "复用相同音色速度",
                    "--full-auto",
                    "--approval-note",
                    "请全自动完成，跳过所有审批",
                    "--transition-mode",
                    "transition-separated",
                ],
                env=env,
            )
            cached_project = Path(cached_project_result.stdout.strip())
            write_json(cached_project / "script.json", sample_two_scene_script())
            write_json(
                cached_project / "state" / "motion-plan.json",
                sample_two_scene_motion_plan(),
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(cached_project),
                    "director",
                ],
                env=env,
            )
            cross_project_request_start = len(state.mimo_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-calibrate",
                    str(cached_project),
                    "--voice",
                    "茉莉",
                ],
                env=env,
            )
            assert len(state.mimo_requests) == cross_project_request_start
            assert load_json(cached_project / "state" / "voice-timing.json")[
                "source"
            ] == "cached-measurement"
            transition_video_request_start = len(state.video_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(transition_project),
                    "--all",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                ],
                env=env,
            )
            transition_motion = load_json(
                transition_project / "motion" / "motion-manifest.json"
            )
            assert {item["id"] for item in transition_motion["scenes"]} == {
                "content-01",
                "transition-01-02",
                "content-02",
            }
            assert len(state.video_requests) - transition_video_request_start == 3
            duration_requests = state.video_requests[transition_video_request_start:]
            duration_frame_counts = [item["num_frames"] for item in duration_requests]
            assert duration_frame_counts == [
                81,
                169,
                81,
            ], duration_frame_counts
            content_duration_plans = [
                item["duration_plan"]
                for item in transition_motion["scenes"]
                if item["id"].startswith("content-")
            ]
            assert all(
                item["source"] == "voice-timing:measured-sample"
                and item["voice"] == "茉莉"
                for item in content_duration_plans
            )
            frame_change_request_start = len(state.video_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(transition_project),
                    "--scene",
                    "01",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                    "--num-frames",
                    "89",
                ],
                env=env,
            )
            assert len(state.video_requests) - frame_change_request_start == 1
            assert state.video_requests[-1]["num_frames"] == 89
            transition_motion = load_json(
                transition_project / "motion" / "motion-manifest.json"
            )
            changed_content = next(
                item
                for item in transition_motion["scenes"]
                if item["id"] == "content-01"
            )
            assert changed_content["requested_num_frames"] == 89
            changed_delivery = transition_project / changed_content["video"]
            changed_delivery.unlink()
            completed_recovery_request_start = len(state.video_requests)
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "agnes-video",
                    str(transition_project),
                    "--scene",
                    "01",
                    "--poll",
                    "--interval",
                    "1",
                    "--timeout",
                    "30",
                    "--num-frames",
                    "89",
                ],
                env=env,
            )
            assert len(state.video_requests) == completed_recovery_request_start
            set_all_qa_true(
                transition_project / "motion" / "motion-manifest.json",
                [
                    "keyframes_respected",
                    "camera_locked",
                    "no_mutation",
                    "end_frame_respected",
                ],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(transition_project),
                    "motion",
                ],
                env=env,
            )
            mismatched_voice = run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(transition_project),
                    "--all",
                    "--voice",
                    "苏打",
                ],
                env=env,
                expect=2,
            )
            assert (
                "calibrate this voice before motion generation"
                in mismatched_voice.stderr
            )
            run_cli(
                [
                    sys.executable,
                    str(PROVIDERS_CLI),
                    "mimo-tts",
                    str(transition_project),
                    "--all",
                    "--voice",
                    "茉莉",
                ],
                env=env,
            )
            set_all_qa_true(
                transition_project / "audio" / "audio-manifest.json",
                ["narration_verified", "natural_delivery"],
            )
            run_cli(
                [
                    sys.executable,
                    str(PROJECT_CLI),
                    "auto-complete",
                    str(transition_project),
                    "audio",
                ],
                env=env,
            )
            run_cli(
                [sys.executable, str(COMPOSE_CLI), str(transition_project)],
                env=env,
            )
            transition_timing = load_json(
                transition_project / "composition" / "timing.json"
            )
            assert transition_timing["transition"] == {
                "mode": "transition-separated",
                "duration_seconds": 1.0,
            }
            assert len(transition_timing["transitions"]) == 1
            assert abs(
                transition_timing["transitions"][0]["midpoint"]
                - transition_timing["scenes"][0]["end"]
            ) < 0.001

            style_definition = project / "state" / "style-definition.md"
            original_style_definition = style_definition.read_text(encoding="utf-8")
            style_definition.write_text(
                original_style_definition + "\n<!-- changed -->\n",
                encoding="utf-8",
            )
            style_stale = run_cli(
                [sys.executable, str(PROJECT_CLI), "status", str(project)], env=env
            )
            style_stale_data = json.loads(style_stale.stdout)
            assert all(
                item["status"] == "stale" for item in style_stale_data["stages"]
            )
            style_definition.write_text(
                original_style_definition,
                encoding="utf-8",
            )
            restored = run_cli(
                [sys.executable, str(PROJECT_CLI), "status", str(project)], env=env
            )
            restored_data = json.loads(restored.stdout)
            assert all(
                item["status"] == "approved" for item in restored_data["stages"]
            )

            changed_script = load_json(project / "script.json")
            changed_script["project"]["title"] = "changed after approval"
            write_json(project / "script.json", changed_script)
            stale = run_cli(
                [sys.executable, str(PROJECT_CLI), "status", str(project)], env=env
            )
            stale_data = json.loads(stale.stdout)
            assert all(item["status"] == "stale" for item in stale_data["stages"])

            final = project / "composition" / "final.mp4"
            result = {
                "status": "passed",
                "tests": {
                    "missing_token_gate": True,
                    "versioning": True,
                    "internal_style_registry": True,
                    "storybook_shared_hero_frame_style": True,
                    "unknown_style_gate": True,
                    "style_name_contract": True,
                    "style_switch_archives_snapshot": True,
                    "style_snapshot_invalidates_downstream": True,
                    "stage_boundary_rejection": True,
                    "five_stage_approval": True,
                    "agnes_two_keyframes_720p_request": True,
                    "built_in_agnes_image_adapter": True,
                    "content_rich_independent_first_frames": True,
                    "visual_sample_gate": True,
                    "motion_sample_gate": True,
                    "audio_sample_gate": True,
                    "mimo_voiceclone_contract": True,
                    "ffmpeg_composition": True,
                    "upstream_change_invalidates_downstream": True,
                    "self_contained_runtime": True,
                    "explicit_full_auto_mode": True,
                    "default_hard_cut_transition_mode": True,
                    "agnes_cn_preflight_profile": True,
                    "agnes_region_persisted_in_project_and_provider": True,
                    "cross_platform_one_time_credentials_file": True,
                    "separated_transition_runtime": True,
                    "narration_aware_motion_duration": True,
                    "default_voice_timing_needs_no_calibration": True,
                    "changed_voice_is_measured_once": True,
                    "voice_timing_cache_reused_across_projects": True,
                    "uncalibrated_voice_change_is_blocked": True,
                    "frame_count_change_regenerates_motion": True,
                    "completed_download_recovery_avoids_resubmission": True,
                },
                "final_video_bytes": final.stat().st_size,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
