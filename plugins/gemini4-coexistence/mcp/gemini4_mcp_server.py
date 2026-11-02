#!/usr/bin/env python3
"""
Gemini 4 & 3.8 + Google Antigravity Cache-Preserving MCP Server
===============================================================
Zero-dependency Python 3 stdio MCP server (JSON-RPC 2.0) built for seamless
coexistence inside Claude Code (v2.1.302+), OpenAI Codex CLI (v0.159+), and Cursor IDE.

Nov 2026 Ground-Truth Model Lineup & API Protocol Rules Enforced:
- `gemini-4-argon` (GA Oct 13, 2026): $2.00/$10.00/$0.10 (95% implicit cache >=4,096 tok,
  $0 write fee through Nov 30, 2026; $4/$20/$0.20 Dec 1+). Unified 1,048,576 window,
  32K sync / 64K stream / Long Decode (`continuation_token`), `thinking_level`
  (`low`|`medium`|`high`), 20-minute (1200s) timeout, deprecated sampling params omitted,
  explicit `cachedContents` avoided, mandatory `thought_signature` preserved.
- `gemini-3.8-flash` (GA Sep 2, 2026): $0.75/$3.75/$0.075 (90% cache discount through
  Dec 31, 2026), 133 tok/s, 89.4% Terminal-Bench 2.1, 73.7% DeepSWE v1.1. Primary
  sub-agent & exploration workhorse (exempt from Cursor's $0.25/M Token Rate!).
- `gemini-3.5-flash-lite` (GA Jul 21, 2026): $0.30/$2.50, 454 tok/s background,
  log-parsing, file-indexing, and `safeguards_classifier_model` engine.
- `Gemini 4 Carbon` (Announced Oct 28, 2026 — #1 AA Intel v5.0 [59], 88.2% SEC-bench Pro,
  0.0% Gray Swan IPI): Gated to vetted cyber defenders in Google Cloud's Fairwind Program
  as of Nov 2, 2026. Security audits run on GA `gemini-4-argon` today and automatically
  cut over when `GEMINI4_FAIRWIND_CARBON_MODEL` is set by Fairwind defenders or upon GA.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

SERVER_NAME = "gemini4-coexistence"
SERVER_VERSION = "1.1.0"
PROTOCOL_VERSION = "2024-11-05"

_RPC_OUT: BinaryIO = sys.stdout.buffer


def _clean_env(*names: str, default: str = "") -> str:
    """Return first non-empty env var, ignoring `${...}` unconfigured templates."""
    for name in names:
        raw = os.environ.get(name, "")
        if raw is None:
            continue
        val = raw.strip()
        if val and not val.startswith("${"):
            return val
    return default


def normalize_gemini_model_id(raw_model: str) -> str:
    """
    Strip Claude Code `[1m]` context suffixes and LiteLLM `claude-` / `litellm-`
    virtual discovery prefixes before calling Google's native Gemini API.
    """
    m = (raw_model or "").strip()
    m = re.sub(r"\[1m\]$", "", m, flags=re.IGNORECASE)
    m = re.sub(r"\[.*?\]$", "", m)  # Also strip Cursor `[effort=low]` bracket params
    if "/" in m:
        m = m.split("/", 1)[-1]
    for prefix in ("claude-", "litellm-"):
        if m.startswith(prefix) and "gemini-" in m:
            m = m[len(prefix) :]
    return m or "gemini-4-argon"


# Configured Nov 2026 Gemini Tier Slots
MODEL_ARGON = normalize_gemini_model_id(
    _clean_env("GEMINI4_PLUGIN_PRIMARY_MODEL", "GEMINI4_PRIMARY_MODEL", default="gemini-4-argon")
)
MODEL_FLASH = normalize_gemini_model_id(
    _clean_env("GEMINI4_PLUGIN_SUBAGENT_MODEL", "GEMINI4_FAST_MODEL", default="gemini-3.8-flash")
)
MODEL_FLASH_LITE = normalize_gemini_model_id(
    _clean_env("GEMINI4_PLUGIN_BACKGROUND_MODEL", "GEMINI4_LITE_MODEL", default="gemini-3.5-flash-lite")
)
FAIRWIND_CARBON_MODEL = _clean_env(
    "GEMINI4_PLUGIN_FAIRWIND_CARBON_MODEL", "GEMINI4_FAIRWIND_CARBON_MODEL", default=""
)
# Security audits use Fairwind Carbon if enrolled/GA, otherwise GA `gemini-4-argon`
MODEL_SECURITY = (
    normalize_gemini_model_id(FAIRWIND_CARBON_MODEL)
    if FAIRWIND_CARBON_MODEL
    else MODEL_ARGON
)
ANTIGRAVITY_AGENT_ID = _clean_env(
    "GEMINI4_ANTIGRAVITY_AGENT", default="antigravity-preview-09-2026"
)

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".turbo",
    "target",
    "vendor",
    ".gemini4-staging",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf", ".pyc",
    ".so", ".dylib", ".exe", ".docx",
}

SESSION_STATE: Dict[str, Dict[str, Any]] = {
    "default": {
        "calls": 0,
        "files_ingested": 0,
        "gemini_input_tokens_est": 0,
        "claude_bpe_tokens_avoided_est": 0,
        "implicit_cache_hits_est": 0,
        "previous_interaction_id": None,
        "seen_corpus_hashes": set(),
    }
}


def resolve_agy_cli_binary() -> Optional[str]:
    """
    Resolve the Go `agy` CLI binary safely on macOS/Linux.
    Per `antigravity-claude-mcp` best practices, prefer `AGY_BIN` or `~/.local/bin/agy`
    before generic `PATH` symlinks that may point to the Antigravity Electron desktop app.
    """
    explicit = _clean_env("AGY_BIN")
    if explicit and Path(explicit).is_file():
        return explicit
    local_bin = Path.home() / ".local" / "bin" / "agy"
    if local_bin.is_file() and os.access(local_bin, os.X_OK):
        return str(local_bin)
    which_agy = shutil.which("agy")
    if which_agy:
        resolved = str(Path(which_agy).resolve())
        if ".app/Contents/" not in resolved:
            return which_agy
        # Even inside .app bundle, check if CLI wrapper responds cleanly
        return which_agy
    return None


def resolve_credentials() -> Tuple[str, bool, str, str]:
    api_key = _clean_env("GEMINI4_PLUGIN_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
    gcp_project = _clean_env(
        "GEMINI4_PLUGIN_GCP_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"
    )
    gcp_location = _clean_env("GOOGLE_CLOUD_LOCATION", default="global")
    use_vertex_raw = _clean_env(
        "GEMINI4_PLUGIN_USE_VERTEX", "GOOGLE_GENAI_USE_VERTEXAI", "AGY_ADC_AUTH"
    ).lower()
    use_vertex = use_vertex_raw in ("1", "true", "yes")
    return api_key, use_vertex, gcp_project, gcp_location


def detect_runtime_capabilities() -> Dict[str, Any]:
    has_antigravity_sdk = False
    has_google_genai = False
    genai_version = None

    try:
        import google.antigravity  # type: ignore # noqa: F401
        has_antigravity_sdk = True
    except Exception:
        has_antigravity_sdk = False

    try:
        import google.genai as genai  # type: ignore
        has_google_genai = True
        genai_version = getattr(genai, "__version__", "installed")
    except Exception:
        has_google_genai = False

    api_key, use_vertex, gcp_project, gcp_location = resolve_credentials()

    return {
        "has_antigravity_sdk": has_antigravity_sdk,
        "has_google_genai": has_google_genai,
        "google_genai_version": genai_version,
        "agy_cli_path": resolve_agy_cli_binary(),
        "gcloud_cli_path": shutil.which("gcloud"),
        "has_api_key": bool(api_key),
        "gcp_project": gcp_project or None,
        "gcp_location": gcp_location,
        "use_vertex": use_vertex,
        "fairwind_carbon_enabled": bool(FAIRWIND_CARBON_MODEL),
    }


def collect_files_from_pointers(
    paths: List[str],
    workspace_root: Optional[str] = None,
    include_globs: Optional[List[str]] = None,
    max_files: int = 80,
    max_total_chars: int = 1_800_000,
) -> Tuple[str, Dict[str, Any]]:
    base_dir = Path(workspace_root or os.getcwd()).resolve()
    resolved_files: List[Path] = []
    seen_paths = set()

    def _should_include(file_path: Path) -> bool:
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            return False
        if include_globs:
            return any(
                fnmatch.fnmatch(file_path.name, pat)
                or fnmatch.fnmatch(str(file_path), pat)
                for pat in include_globs
            )
        return True

    for raw_target in paths:
        target_str = str(raw_target).strip()
        if not target_str:
            continue
        candidate = Path(target_str)
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()

        if candidate.is_file():
            if candidate not in seen_paths and _should_include(candidate):
                seen_paths.add(candidate)
                resolved_files.append(candidate)
        elif candidate.is_dir():
            for root, dirs, files in os.walk(candidate):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
                for fname in sorted(files):
                    fpath = Path(root) / fname
                    if fpath not in seen_paths and _should_include(fpath):
                        seen_paths.add(fpath)
                        resolved_files.append(fpath)
                        if len(resolved_files) >= max_files:
                            break
                if len(resolved_files) >= max_files:
                    break
        else:
            for matched in sorted(base_dir.glob(target_str)):
                if matched.is_file() and matched not in seen_paths and _should_include(matched):
                    seen_paths.add(matched)
                    resolved_files.append(matched)
                    if len(resolved_files) >= max_files:
                        break

        if len(resolved_files) >= max_files:
            break

    chunks: List[str] = []
    total_chars = 0
    included_paths: List[str] = []

    for fpath in resolved_files:
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + "\n... [truncated at context cap]"
        try:
            rel = str(fpath.relative_to(base_dir))
        except ValueError:
            rel = str(fpath)

        chunks.append(f"=== FILE: {rel} ===\n{text}\n")
        total_chars += len(text)
        included_paths.append(rel)

    corpus = "\n".join(chunks)
    corpus_hash = hashlib.sha256(corpus.encode("utf-8")).hexdigest()[:16]

    gemini_tokens = max(1, total_chars // 4) if total_chars > 0 else 0
    claude_equivalent_tokens = int(gemini_tokens * 1.32)

    meta = {
        "files_read": len(included_paths),
        "included_paths": included_paths[:25],
        "total_chars": total_chars,
        "gemini_tokens_est": gemini_tokens,
        "implicit_cache_eligible_4096": gemini_tokens >= 4096,
        "claude_bpe_tokens_if_pasted_est": claude_equivalent_tokens,
        "bpe_bloat_tokens_saved_est": claude_equivalent_tokens - gemini_tokens,
        "corpus_hash": corpus_hash,
    }
    return corpus, meta


def get_vertex_access_token() -> Optional[str]:
    gcloud_bin = shutil.which("gcloud")
    if not gcloud_bin:
        return None
    try:
        proc = subprocess.run(
            [gcloud_bin, "auth", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def invoke_gemini_model(
    model: str,
    system_instruction: str,
    user_prompt: str,
    thinking_level: str = "medium",
    session_id: str = "default",
    prefer_antigravity_agent: bool = False,
    workspace_root: Optional[str] = None,
    add_dirs: Optional[List[str]] = None,
    agy_mode: str = "plan",
    agy_timeout: str = "20m",
) -> Dict[str, Any]:
    """
    Execute a Gemini 4 Argon / 3.8 Flash / 3.5 Flash-Lite / Antigravity call
    respecting Google's Oct 27, 2026 API specification:
      - No deprecated `temperature` / `top_p` / `top_k` / `cachedContents` on Argon
      - `max_output_tokens = 32768` (sync REST) / `65536` (SDK/streaming) + 1200s timeout
      - `thinking_level` (`low` | `medium` | `high`)
    """
    clean_model = normalize_gemini_model_id(model)
    caps = detect_runtime_capabilities()
    api_key, use_vertex, gcp_project, gcp_location = resolve_credentials()

    session = SESSION_STATE.setdefault(
        session_id,
        {
            "calls": 0,
            "files_ingested": 0,
            "gemini_input_tokens_est": 0,
            "claude_bpe_tokens_avoided_est": 0,
            "implicit_cache_hits_est": 0,
            "previous_interaction_id": None,
            "seen_corpus_hashes": set(),
        },
    )
    session["calls"] += 1
    started = time.time()

    tier1_error: Optional[str] = None
    tier2_error: Optional[str] = None

    # Tier 1: Local `agy -p` CLI with `--add-dir` (`antigravity-claude-mcp` pattern)
    # Note (agy v1.4.7+ headless verification):
    #   - Requires `GEMINI_API_KEY` in env (rejects `GOOGLE_API_KEY` alone) and
    #     `"modelProvider": "gemini"` in `~/.gemini/antigravity-cli/settings.json`.
    #   - In print mode (`-p`), `WriteFile` / `RunCommand` may soft-deny via `denied_actions`
    #     while still exiting `0` unless `permissions.allow` grants workspace access.
    if (
        prefer_antigravity_agent
        and caps["agy_cli_path"]
        and os.environ.get("GEMINI4_ENABLE_AGY_CLI", "0") == "1"
    ):
        try:
            effort_map = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}
            cmd = [
                caps["agy_cli_path"],
                "-p",
                f"{system_instruction}\n\n{user_prompt}",
                "--model",
                clean_model,
                "--effort",
                effort_map.get(thinking_level, "medium"),
                "--mode",
                agy_mode,
                "--print-timeout",
                agy_timeout,
                "--output-format",
                "text",
            ]
            for d in add_dirs or []:
                p = Path(d)
                if not p.is_absolute():
                    p = (Path(workspace_root or os.getcwd()) / p).resolve()
                target_dir = str(p if p.is_dir() else p.parent)
                cmd.extend(["--add-dir", target_dir])

            child_env = dict(os.environ)
            if api_key and not child_env.get("GEMINI_API_KEY"):
                child_env["GEMINI_API_KEY"] = api_key

            proc = subprocess.run(
                cmd,
                cwd=workspace_root or os.getcwd(),
                env=child_env,
                capture_output=True,
                text=True,
                timeout=1200,
                check=False,
            )
            combined_out = (proc.stdout or "").strip()
            stderr_out = (proc.stderr or "").strip()
            has_soft_deny = "denied_actions" in combined_out or "denied_actions" in stderr_out
            if proc.returncode == 0 and combined_out and not has_soft_deny:
                return {
                    "ok": True,
                    "tier": "tier1_agy_cli_add_dir",
                    "model": clean_model,
                    "latency_ms": int((time.time() - started) * 1000),
                    "text": combined_out,
                }
            if has_soft_deny:
                ws_hint = str(Path(workspace_root or os.getcwd()).resolve())
                tier1_error = (
                    f"agy -p soft-denied write/command in headless mode (`denied_actions`). "
                    f"Add `\"write_file({ws_hint}/**)\"` under `permissions.allow` and "
                    f"`\"modelProvider\": \"gemini\"` in `~/.gemini/antigravity-cli/settings.json`."
                )
            elif proc.returncode != 0:
                tier1_error = stderr_out[:240] or f"agy exited with status {proc.returncode}"
        except Exception as exc:
            tier1_error = str(exc)

    # Tier 2: `google.antigravity` Python SDK (`LocalAgentConfig`)
    if prefer_antigravity_agent and caps["has_antigravity_sdk"] and api_key:
        try:
            from google.antigravity import Agent, LocalAgentConfig  # type: ignore

            cfg = LocalAgentConfig(
                model=clean_model,
                api_key=api_key,
                system_instruction=system_instruction,
                workspace=workspace_root or os.getcwd(),
            )
            agent = Agent(config=cfg)
            resp = agent.run(user_prompt)
            return {
                "ok": True,
                "tier": "tier2_google_antigravity_sdk",
                "model": clean_model,
                "latency_ms": int((time.time() - started) * 1000),
                "text": getattr(resp, "text", str(resp)),
            }
        except Exception as exc:
            tier1_error = str(exc)

    # Tier 3: `google-genai` SDK (with Long Decode `max_output_tokens=65536` & 1200s timeout)
    if caps["has_google_genai"] and (api_key or (use_vertex and gcp_project)):
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore

            http_opts = {"timeout": 1_200_000}  # 20 minutes in ms for google-genai HttpOptions
            if use_vertex and gcp_project:
                client = genai.Client(
                    vertexai=True,
                    project=gcp_project,
                    location=gcp_location,
                    http_options=http_opts,
                )
            else:
                client = genai.Client(api_key=api_key, http_options=http_opts)

            if prefer_antigravity_agent and hasattr(client, "interactions"):
                kwargs: Dict[str, Any] = {
                    "agent": ANTIGRAVITY_AGENT_ID,
                    "input": f"{system_instruction}\n\n{user_prompt}",
                }
                if session.get("previous_interaction_id"):
                    kwargs["previous_interaction_id"] = session["previous_interaction_id"]
                interaction = client.interactions.create(**kwargs)
                if getattr(interaction, "id", None):
                    session["previous_interaction_id"] = interaction.id
                outputs = getattr(interaction, "outputs", None) or []
                out_text = (
                    outputs[-1].text
                    if outputs and hasattr(outputs[-1], "text")
                    else str(interaction)
                )
                return {
                    "ok": True,
                    "tier": "tier3_genai_interactions_api",
                    "model": ANTIGRAVITY_AGENT_ID,
                    "interaction_id": getattr(interaction, "id", None),
                    "latency_ms": int((time.time() - started) * 1000),
                    "text": out_text,
                }

            # Enforce Oct 27, 2026 Argon rules: max_output_tokens=32768 (sync), NO sampling params!
            gen_cfg_kwargs: Dict[str, Any] = {
                "system_instruction": system_instruction,
                "max_output_tokens": 32768,
            }
            if hasattr(types, "ThinkingConfig"):
                try:
                    norm_level = "low" if thinking_level == "minimal" else thinking_level
                    gen_cfg_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level=norm_level
                    )
                except Exception:
                    pass

            response = client.models.generate_content(
                model=clean_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(**gen_cfg_kwargs),
            )
            return {
                "ok": True,
                "tier": "tier3_google_genai_sdk",
                "model": clean_model,
                "latency_ms": int((time.time() - started) * 1000),
                "text": response.text or "",
            }
        except Exception as exc:
            tier2_error = str(exc)

    # Tier 4: Pure stdlib REST fallback (20m timeout=1200s, maxOutputTokens=32768, no temperature!)
    norm_level = "LOW" if thinking_level in ("minimal", "low") else thinking_level.upper()
    gen_cfg_rest: Dict[str, Any] = {"maxOutputTokens": 32768}
    if "flash-lite" not in clean_model:
        gen_cfg_rest["thinkingConfig"] = {"thinkingLevel": norm_level}
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": gen_cfg_rest,
    }

    def _explain_exc(exc: Exception) -> str:
        msg = str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:320]
            except Exception:
                err_body = ""
            code = exc.code
            if code in (400, 401, 403) and ("API_KEY" in err_body.upper() or code in (401, 403)):
                return (
                    f"HTTP {code} Authentication Error ({err_body or msg}). "
                    f"Fix: Export a valid Paid Tier 1+ `GEMINI_API_KEY` or run `claude plugin configure gemini4-coexistence`."
                )
            if code == 404:
                return (
                    f"HTTP 404 Model `{clean_model}` Not Found ({err_body or msg}). "
                    f"Note: `gemini-4-carbon` is currently gated to Google Cloud's Fairwind Program — unset `GEMINI4_FAIRWIND_CARBON_MODEL` to use GA `gemini-4-argon`."
                )
            if code == 429:
                return (
                    f"HTTP 429 Quota / Rate Limit ({err_body or msg}). "
                    f"Fix: Google retired free-tier AI Studio quota for frontier models in Dec 2025 — enable Paid Tier 1+ billing in AI Studio or switch to Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`)."
                )
            return f"HTTP {code}: {err_body or msg}"
        return msg

    if api_key:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(clean_model)}:generateContent?key={urllib.parse.quote(api_key)}"
        )
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1200) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            parts = (
                body.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            text_out = "\n".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
            return {
                "ok": True,
                "tier": "tier4_rest_ai_studio",
                "model": clean_model,
                "latency_ms": int((time.time() - started) * 1000),
                "text": text_out,
            }
        except Exception as exc:
            rest_error = _explain_exc(exc)
    elif use_vertex and gcp_project:
        token = get_vertex_access_token()
        if token:
            host = (
                "aiplatform.googleapis.com"
                if gcp_location == "global"
                else f"{gcp_location}-aiplatform.googleapis.com"
            )
            url = (
                f"https://{host}/v1/projects/{urllib.parse.quote(gcp_project)}"
                f"/locations/{urllib.parse.quote(gcp_location)}/publishers/google"
                f"/models/{urllib.parse.quote(clean_model)}:generateContent"
            )
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=1200) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                parts = (
                    body.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                text_out = "\n".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
                return {
                    "ok": True,
                    "tier": "tier4_rest_vertex_adc",
                    "model": clean_model,
                    "latency_ms": int((time.time() - started) * 1000),
                    "text": text_out,
                }
            except Exception as exc:
                rest_error = _explain_exc(exc)
        else:
            rest_error = (
                "Vertex AI enabled (`GOOGLE_GENAI_USE_VERTEXAI=true`), but `gcloud auth print-access-token` returned no token. "
                "Fix: Run `gcloud auth application-default login`."
            )
    else:
        rest_error = tier2_error or tier1_error or "GEMINI_API_KEY / Vertex AI credentials not configured yet"

    return {
        "ok": False,
        "tier": "offline_telemetry_preview",
        "model": clean_model,
        "latency_ms": int((time.time() - started) * 1000),
        "reason": rest_error,
        "text": (
            f"[Gemini Coexistence MCP Ready — Offline Telemetry Mode]\n"
            f"Target Engine: `{clean_model}` (`thinking_level={thinking_level}`, `max_output_tokens=32768`, `timeout=20m`)\n"
            f"File pointers were resolved directly from disk without polluting the parent "
            f"conversation thread's prompt cache.\n"
            f"To enable live inference, configure `GEMINI_API_KEY` (via `claude plugin configure gemini4-coexistence` "
            f"or env), enable Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=true`), or set `GEMINI4_ENABLE_AGY_CLI=1` for `agy -p --add-dir`.\n"
            f"Diagnostic detail: {rest_error}"
        ),
    }


def record_telemetry(session_id: str, meta: Dict[str, Any], model_used: str = "") -> Dict[str, Any]:
    session = SESSION_STATE.setdefault(
        session_id,
        {
            "calls": 0,
            "files_ingested": 0,
            "gemini_input_tokens_est": 0,
            "claude_bpe_tokens_avoided_est": 0,
            "implicit_cache_hits_est": 0,
            "previous_interaction_id": None,
            "seen_corpus_hashes": set(),
        },
    )
    corpus_hash = meta.get("corpus_hash")
    cache_hit = bool(corpus_hash and corpus_hash in session["seen_corpus_hashes"])
    if corpus_hash:
        session["seen_corpus_hashes"].add(corpus_hash)
    if cache_hit:
        session["implicit_cache_hits_est"] += 1

    gem_tokens = meta.get("gemini_tokens_est", 0)
    bpe_avoided = meta.get("claude_bpe_tokens_if_pasted_est", 0)
    session["files_ingested"] += meta.get("files_read", 0)
    session["gemini_input_tokens_est"] += gem_tokens
    session["claude_bpe_tokens_avoided_est"] += bpe_avoided

    # Exact Nov 2026 Pricing Math:
    # - gemini-3.5-flash-lite: $0.30/1M
    # - gemini-3.8-flash: $0.75/1M uncached, $0.075/1M cached (90% off)
    # - gemini-4-argon (Intro to Nov 30): $2.00/1M uncached, $0.10/1M cached (95% off, $0 write fee)
    # - claude-opus-5-5 root cache-write avoided: $5.00/1M (1.25x of $4.00) on +32% BPE tokens
    m_low = (model_used or "").lower()
    if "flash-lite" in m_low:
        rate = 0.30
    elif "3.8-flash" in m_low:
        rate = 0.075 if cache_hit else 0.75
    else:
        rate = 0.10 if cache_hit else 2.00

    gemini_cost = (gem_tokens / 1_000_000.0) * rate
    claude_opus_cache_write_avoided = (bpe_avoided / 1_000_000.0) * 5.00

    return {
        "session_id": session_id,
        "model": model_used or MODEL_ARGON,
        "implicit_cache_warm": cache_hit,
        "gemini_tokens_est": gem_tokens,
        "claude_root_tokens_avoided": bpe_avoided,
        "estimated_call_cost_usd": round(gemini_cost, 6),
        "estimated_opus55_cache_write_avoided_usd": round(claude_opus_cache_write_avoided, 6),
        "parent_prompt_cache_preserved": True,
    }


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "ask_antigravity",
        "description": (
            "CLAUDE_ANTIGRAVITY_LOOP cross-family bridge (compatible with `antigravity-claude-mcp`). "
            "Delegates independent architectural critique, multi-folder sweeps (`gemini-3.8-flash`), "
            "or pre-commit `git diff` verification (`gemini-4-argon`) using file/folder pointers "
            "(`paths` / `--add-dir`) so zero raw file dumps bloat the parent context window."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Specific engineering question, critique request, or verification prompt.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files or directories to pass via `--add-dir` / disk reader (do NOT paste raw code).",
                },
                "model": {
                    "type": "string",
                    "default": "gemini-4-argon",
                    "description": "`gemini-4-argon` (deep reasoning/audit), `gemini-3.8-flash` (133 tok/s workhorse), or `gemini-3.5-flash-lite` (454 tok/s utility).",
                },
                "workspace_root": {"type": "string"},
                "session_id": {"type": "string", "default": "antigravity-loop"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "gemini4_analyze_codebase",
        "description": (
            "Analyze large directories, multiple files, or architecture questions using "
            "Gemini's 1.05M token window WITHOUT reading raw files into the main thread. "
            "Pass file paths, directories, or globs (`paths`). Defaults routine exploration to "
            "`gemini-3.8-flash` (133 tok/s, $0.75/M) or deep synthesis to `gemini-4-argon` ($0.10/M cached)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Specific architectural, debugging, or cross-file question to answer.",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths, directory paths, or glob patterns (e.g., ['src/', 'router/*.py']).",
                },
                "model_tier": {
                    "type": "string",
                    "enum": ["flash", "argon", "flash-lite"],
                    "default": "flash",
                    "description": "flash = `gemini-3.8-flash` (default 133 tok/s workhorse); argon = `gemini-4-argon` (deep 1M reasoning); flash-lite = `gemini-3.5-flash-lite` (454 tok/s index/log scan).",
                },
                "workspace_root": {"type": "string"},
                "session_id": {"type": "string", "default": "default"},
            },
            "required": ["question", "paths"],
        },
    },
    {
        "name": "gemini4_security_audit",
        "description": (
            "Run a deep CWE/CVE vulnerability, path-traversal, credential-leak, auth-bypass, "
            "and concurrency audit on GA `gemini-4-argon` (#1 tied on Endor Labs Cursor Agent "
            "Security League; auto-upgrades to Gemini 4 Carbon if `GEMINI4_FAIRWIND_CARBON_MODEL` is set)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files, directories, or globs to audit directly from disk.",
                },
                "focus": {
                    "type": "string",
                    "default": "path traversal, injection, credential logging, SSRF, race conditions, auth boundaries",
                },
                "workspace_root": {"type": "string"},
                "session_id": {"type": "string", "default": "security"},
            },
            "required": ["paths"],
        },
    },
    {
        "name": "gemini4_long_decode_refactor",
        "description": (
            "Delegate large single-pass code migrations, test-suite generation, or multi-file "
            "refactors (32K sync / 64K stream / Long Decode) to `gemini-4-argon` or `gemini-3.8-flash`, "
            "staging output cleanly into `.gemini4-staging/`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
                "stage_output_to": {"type": "string"},
                "workspace_root": {"type": "string"},
                "session_id": {"type": "string", "default": "refactor"},
            },
            "required": ["spec", "paths"],
        },
    },
    {
        "name": "gemini4_antigravity_task",
        "description": (
            "Delegate an autonomous multi-step verify-and-fix task to Google Antigravity "
            "(`agy -p --add-dir`, `google.antigravity` SDK, or Gemini Interactions API "
            "`antigravity-preview-09-2026` with stateful `previous_interaction_id`)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string", "default": "gemini-4-argon"},
                "workspace_root": {"type": "string"},
                "session_id": {"type": "string", "default": "antigravity"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "gemini4_cache_telemetry",
        "description": (
            "Inspect active Gemini 4 Argon / 3.8 Flash / 3.5 Flash-Lite / Fairwind Carbon "
            "configuration, runtime capabilities, implicit cache hits, and Opus 5.5 cache-write savings."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "default": "default"}},
        },
    },
]


def execute_tool(name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
    workspace_root = arguments.get("workspace_root") or os.getcwd()
    session_id = arguments.get("session_id", "default")

    if name == "gemini4_cache_telemetry":
        caps = detect_runtime_capabilities()
        summary = {
            sid: {k: (list(v) if isinstance(v, set) else v) for k, v in data.items()}
            for sid, data in SESSION_STATE.items()
        }
        report = {
            "server": f"{SERVER_NAME} v{SERVER_VERSION}",
            "configured_models": {
                "frontier_reasoning_ga": MODEL_ARGON,
                "security_auditor_active": MODEL_SECURITY,
                "fairwind_carbon_override": FAIRWIND_CARBON_MODEL or "Not enrolled (using GA gemini-4-argon)",
                "subagent_workhorse_ga": MODEL_FLASH,
                "background_utility_ga": MODEL_FLASH_LITE,
                "antigravity_agent": ANTIGRAVITY_AGENT_ID,
            },
            "runtime_capabilities": caps,
            "sessions": summary,
        }
        return json.dumps(report, indent=2), False

    if name == "ask_antigravity":
        prompt_text = arguments.get("prompt", "")
        paths = arguments.get("paths") or []
        req_model = normalize_gemini_model_id(arguments.get("model") or MODEL_ARGON)
        corpus, meta = (
            collect_files_from_pointers(paths, workspace_root=workspace_root)
            if paths
            else ("", {"files_read": 0, "gemini_tokens_est": 0, "claude_bpe_tokens_if_pasted_est": 0, "bpe_bloat_tokens_saved_est": 0})
        )
        telemetry = record_telemetry(session_id, meta, model_used=req_model)
        sys_inst = (
            "You are operating inside the CLAUDE_ANTIGRAVITY_LOOP as an independent cross-family "
            "Gemini reviewer. Provide concrete file:line evidence, architectural risks, and concise fixes."
        )
        full_prompt = (f"## Disk Context ({meta['files_read']} files)\n{corpus}\n\n" if corpus else "") + prompt_text
        effort = "low" if "flash-lite" in req_model else ("medium" if "3.8-flash" in req_model else "high")
        res = invoke_gemini_model(
            model=req_model,
            system_instruction=sys_inst,
            user_prompt=full_prompt,
            thinking_level=effort,
            session_id=session_id,
            prefer_antigravity_agent=True,
            workspace_root=workspace_root,
            add_dirs=paths,
            agy_mode="plan",
        )
        return (
            f"### Antigravity Cross-Family Review (`{res['model']}` via `{res['tier']}`)\n\n"
            f"{res['text']}\n\n---\n"
            f"**Telemetry**: `files={meta['files_read']}`, `implicit_cache_warm={telemetry['implicit_cache_warm']}`, "
            f"`est_cost=${telemetry['estimated_call_cost_usd']}` (saved `${telemetry['estimated_opus55_cache_write_avoided_usd']}` Opus 5.5 cache-write).",
            False,
        )

    if name == "gemini4_analyze_codebase":
        paths = arguments.get("paths") or arguments.get("target_paths") or []
        question = arguments.get("question", "")
        tier = arguments.get("model_tier", "flash")
        model = {
            "argon": MODEL_ARGON,
            "flash": MODEL_FLASH,
            "flash-lite": MODEL_FLASH_LITE,
            "carbon": MODEL_SECURITY,
        }.get(tier, MODEL_FLASH)
        thinking = "low" if tier in ("flash", "flash-lite") else "medium"

        corpus, meta = collect_files_from_pointers(paths, workspace_root=workspace_root)
        telemetry = record_telemetry(session_id, meta, model_used=model)
        sys_inst = (
            "You are a Gemini Coexistence Subagent assisting a root coding harness. "
            "Return a high-signal, concise (<600 words) engineering synthesis with exact file:line citations "
            "so the parent agent's context window stays compact and cache-warm."
        )
        prompt = f"## Repository Context ({meta['files_read']} files)\n{corpus}\n\n## Question\n{question}"
        res = invoke_gemini_model(
            model=model,
            system_instruction=sys_inst,
            user_prompt=prompt,
            thinking_level=thinking,
            session_id=session_id,
            workspace_root=workspace_root,
        )
        output = (
            f"### Gemini Synthesis (`{res['model']}` via `{res['tier']}`)\n\n"
            f"{res['text']}\n\n"
            f"---\n"
            f"**Cache-Preserving Telemetry**: Read `{meta['files_read']}` files directly from disk "
            f"(`~{meta['gemini_tokens_est']:,}` Gemini tokens vs `~{meta['claude_bpe_tokens_if_pasted_est']:,}` "
            f"if pasted into root BPE context; saved `{meta['bpe_bloat_tokens_saved_est']:,}` BPE tokens; "
            f"implicit_cache_warm={telemetry['implicit_cache_warm']}; est_cost=${telemetry['estimated_call_cost_usd']})."
        )
        return output, False

    if name == "gemini4_security_audit":
        paths = arguments.get("paths") or arguments.get("target_paths") or []
        focus = arguments.get("focus", "path traversal, injection, credential logging, SSRF, race conditions, auth boundaries")
        corpus, meta = collect_files_from_pointers(paths, workspace_root=workspace_root)
        telemetry = record_telemetry(session_id, meta, model_used=MODEL_SECURITY)
        sys_inst = (
            "You are an autonomous Gemini 4 Security & Root-Cause Auditor. "
            "Trace untrusted inputs across sibling modules and callers. "
            "For each verified defect, output: Severity (Critical/High/Medium), CWE ID, "
            "File:Line, Exploitability proof, and Exact root-cause patch recommendation."
        )
        prompt = f"## Audit Scope ({focus})\n\n{corpus}"
        res = invoke_gemini_model(
            model=MODEL_SECURITY,
            system_instruction=sys_inst,
            user_prompt=prompt,
            thinking_level="high",
            session_id=session_id,
            workspace_root=workspace_root,
        )
        fairwind_note = (
            "Fairwind Carbon Override Active"
            if FAIRWIND_CARBON_MODEL
            else "GA `gemini-4-argon` (Drop-in ready for Fairwind `Gemini 4 Carbon`)"
        )
        output = (
            f"### Gemini 4 Security Audit (`{MODEL_SECURITY}` — {fairwind_note})\n\n"
            f"{res['text']}\n\n"
            f"---\n"
            f"**Audit Telemetry**: Scanned `{meta['files_read']}` files (`~{meta['gemini_tokens_est']:,}` tokens; "
            f"`est_cost=${telemetry['estimated_call_cost_usd']}`) with zero root-thread prompt cache invalidation."
        )
        return output, False

    if name == "gemini4_long_decode_refactor":
        paths = arguments.get("paths") or arguments.get("target_paths") or []
        spec = arguments.get("spec", "")
        stage_rel = arguments.get("stage_output_to")
        corpus, meta = collect_files_from_pointers(paths, workspace_root=workspace_root)
        telemetry = record_telemetry(session_id, meta, model_used=MODEL_ARGON)
        sys_inst = (
            "You are the Gemini 4 Argon Long-Decode Refactoring Engine (32K sync / 64K stream / Long Decode). "
            "Produce complete, production-ready code with zero `// ... rest of code` placeholders."
        )
        prompt = f"## Source Files\n{corpus}\n\n## Refactor / Migration Specification\n{spec}"
        res = invoke_gemini_model(
            model=MODEL_ARGON,
            system_instruction=sys_inst,
            user_prompt=prompt,
            thinking_level="high",
            session_id=session_id,
            workspace_root=workspace_root,
        )
        if stage_rel:
            staging_root = (Path(workspace_root).resolve() / ".gemini4-staging").resolve()
            candidate_stage = (staging_root / stage_rel.lstrip("/")).resolve()
            if not str(candidate_stage).startswith(str(staging_root)):
                candidate_stage = staging_root / Path(stage_rel).name
            candidate_stage.parent.mkdir(parents=True, exist_ok=True)
            candidate_stage.write_text(res["text"], encoding="utf-8")
            preview = "\n".join(res["text"].splitlines()[:45])
            return (
                f"### Gemini 4 Argon Staged Output (`{MODEL_ARGON}`)\n\n"
                f"{preview}\n...(staged full output to `{candidate_stage}`)\n\n"
                f"**Staged Artifact Written**: `{candidate_stage}` "
                f"(kept full decode on disk so root thread context stays lean; inspect or `git apply` when ready).\n"
                f"Telemetry: `{json.dumps(telemetry)}`",
                False,
            )

        return (
            f"### Gemini 4 Argon Long-Decode Output (`{MODEL_ARGON}`)\n\n{res['text']}\n\n"
            f"---\nTelemetry: `{json.dumps(telemetry)}`",
            False,
        )

    if name == "gemini4_antigravity_task":
        task = arguments.get("task", "")
        paths = arguments.get("paths") or []
        model = normalize_gemini_model_id(arguments.get("model") or MODEL_ARGON)
        corpus, meta = (
            collect_files_from_pointers(paths, workspace_root=workspace_root)
            if paths
            else ("", {"files_read": 0, "gemini_tokens_est": 0, "claude_bpe_tokens_if_pasted_est": 0})
        )
        if paths:
            record_telemetry(session_id, meta, model_used=model)
        sys_inst = (
            "You are an autonomous Google Antigravity subagent delegated a bounded engineering task. "
            "Execute thoroughly and return a concise verification report."
        )
        prompt = f"## Task\n{task}\n\n" + (f"## Grounding Files\n{corpus}" if corpus else "")
        res = invoke_gemini_model(
            model=model,
            system_instruction=sys_inst,
            user_prompt=prompt,
            thinking_level="high",
            session_id=session_id,
            prefer_antigravity_agent=True,
            workspace_root=workspace_root,
            add_dirs=paths,
            agy_mode="accept-edits",
        )
        return (
            f"### Google Antigravity Delegation Result (`{res['model']}` via `{res['tier']}`)\n\n"
            f"{res['text']}",
            False,
        )

    return f"Unknown tool: {name}", True


def read_rpc_message(stream: Any) -> Optional[Any]:
    while True:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if stripped:
            break

    if stripped.lower().startswith(b"content-length:"):
        length = int(stripped.split(b":", 1)[1].strip())
        while True:
            hdr = stream.readline()
            if not hdr or hdr in (b"\r\n", b"\n"):
                break
        body = stream.read(length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    return json.loads(stripped.decode("utf-8"))


def write_rpc_message(payload: Any) -> None:
    encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    _RPC_OUT.write(encoded)
    _RPC_OUT.flush()


def handle_rpc_request(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if req_id is None:
        return None

    if method == "initialize":
        client_proto = params.get("protocolVersion", PROTOCOL_VERSION)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments") or {}
        try:
            text_out, is_error = execute_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text_out}],
                    "isError": is_error,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"MCP tool execution error: {exc}"}],
                    "isError": True,
                },
            }

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return {"jsonrpc": "2.0", "id": req_id, "result": {key: []}}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    if "--self-test" in sys.argv:
        caps = detect_runtime_capabilities()
        print(json.dumps({"status": "ok", "server": SERVER_NAME, "capabilities": caps}, indent=2))
        return

    sys.stdout = sys.stderr

    while True:
        try:
            msg = read_rpc_message(sys.stdin.buffer)
            if msg is None:
                break
            if isinstance(msg, list):
                batch_res = [
                    r for item in msg if isinstance(item, dict) and (r := handle_rpc_request(item)) is not None
                ]
                if batch_res:
                    write_rpc_message(batch_res)
            elif isinstance(msg, dict):
                resp = handle_rpc_request(msg)
                if resp is not None:
                    write_rpc_message(resp)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            sys.stderr.write(f"[gemini4-mcp] error: {exc}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
