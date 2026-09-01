"""Model adapter for the evaluation harness.

The harness never talks to a provider SDK directly; it calls run_model(),
which shells out to headless Claude Code (`claude -p`) and needs no API key
beyond the operator's existing login.

Context isolation: children run from an empty temp cwd (no project CLAUDE.md,
hooks, or project plugins); every fixture carries its own doctrine, so all
models receive identical context - that is the point of the matrix.
"""

import json
import shutil
import tempfile
import subprocess

DEFAULT_TIMEOUT = 300


class AdapterError(RuntimeError):
    pass


def run_model(model: str, prompt: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    exe = shutil.which("claude")
    if exe is None:
        raise AdapterError("claude CLI not on PATH - install Claude Code or "
                           "add another adapter")
    # NOTE: --bare would give the cleanest context but skips login-credential
    # loading (verified: "Not logged in" under --bare, works without). The
    # compromise: run from an empty temp cwd so no project CLAUDE.md, hooks,
    # or project plugins leak in; whatever user-level context remains is
    # identical across models, which is what the matrix requires.
    # Pure-text single-turn fixtures: no tools needed, no permission flags.
    argv = [exe, "-p", "--model", model, "--output-format", "json"]
    with tempfile.TemporaryDirectory(prefix="lz-eval-") as td:
        r = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=td)
    if r.returncode != 0:
        raise AdapterError(f"claude -p exited {r.returncode}: "
                           f"{(r.stderr or r.stdout)[-400:]}")
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise AdapterError(f"non-json CLI output: {r.stdout[:200]}") from e
    if payload.get("is_error"):
        raise AdapterError(f"model call errored: {payload.get('result', '')[:200]}")
    return {
        "text": payload.get("result", ""),
        "cost_usd": payload.get("total_cost_usd"),
        "session_id": payload.get("session_id"),
        "raw": payload,
    }
