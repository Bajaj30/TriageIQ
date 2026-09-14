"""
File & Shell Tools for Claude Agent
------------------------------------
All tools are sandboxed to WORKSPACE_ROOT.
"""

import subprocess
from pathlib import Path

from config import WORKSPACE_ROOT, ENABLE_SHELL


# ── Sandbox guard ─────────────────────────────────────────────────────────────

def _resolve(path_str: str) -> Path:
    """Resolve a path relative to workspace root, reject path traversal."""
    p = (WORKSPACE_ROOT / path_str).resolve()
    if not str(p).startswith(str(WORKSPACE_ROOT)):
        raise PermissionError(
            f"Access denied: '{path_str}' is outside the workspace root.\n"
            f"Workspace: {WORKSPACE_ROOT}"
        )
    return p


# ── Tool implementations ───────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Read a file inside the workspace. Returns its text content."""
    p = _resolve(path)
    if not p.exists():
        return f"ERROR: File not found: {path}"
    if not p.is_file():
        return f"ERROR: '{path}' is not a file."
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading file: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file inside the workspace (creates dirs as needed)."""
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"ERROR writing file: {e}"


def list_directory(path: str = ".") -> str:
    """List files and directories at the given workspace path."""
    p = _resolve(path)
    if not p.exists():
        return f"ERROR: Path not found: {path}"
    if not p.is_dir():
        return f"ERROR: '{path}' is not a directory."
    entries = []
    for item in sorted(p.iterdir()):
        rel = item.relative_to(WORKSPACE_ROOT)
        marker = "/" if item.is_dir() else ""
        size = f"  ({item.stat().st_size:,} bytes)" if item.is_file() else ""
        entries.append(f"  {rel}{marker}{size}")
    header = f"Contents of {p.relative_to(WORKSPACE_ROOT) if p != WORKSPACE_ROOT else '.'}/:"
    return header + "\n" + "\n".join(entries) if entries else header + "\n  (empty)"


def run_shell_command(command: str) -> str:
    """Run a shell command inside the workspace root. Use with caution."""
    if not ENABLE_SHELL:
        return "ERROR: Shell commands are disabled in config.py (ENABLE_SHELL=False)."
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        parts.append(f"Exit code: {result.returncode}")
        return "\n\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120 seconds."
    except Exception as e:
        return f"ERROR running command: {e}"


# ── Tool definitions for Anthropic API ────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read the text content of any file inside the TriageIQ workspace. "
            "Use a path relative to the workspace root, e.g. 'Learning/Phase0/learning_log.md'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the workspace root.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write (create or overwrite) a file inside the TriageIQ workspace. "
            "Parent directories are created automatically. "
            "Use a relative path from the workspace root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file from the workspace root.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write to the file.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": (
            "List files and subdirectories at a given path inside the TriageIQ workspace. "
            "Defaults to the workspace root if no path is given."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to list. Defaults to '.' (workspace root).",
                    "default": ".",
                }
            },
            "required": [],
        },
    },
    {
        "name": "run_shell_command",
        "description": (
            "Run a shell command inside the TriageIQ workspace root. "
            "Useful for running Python scripts, poetry commands, git status, etc. "
            "Always prefer read_file/write_file for file I/O. "
            "Use this only when you genuinely need to execute something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run (executed via bash in the workspace root).",
                }
            },
            "required": ["command"],
        },
    },
]


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def dispatch_tool(name: str, inputs: dict) -> str:
    """Route a tool call from Claude to the correct Python function."""
    if name == "read_file":
        return read_file(inputs["path"])
    elif name == "write_file":
        return write_file(inputs["path"], inputs["content"])
    elif name == "list_directory":
        return list_directory(inputs.get("path", "."))
    elif name == "run_shell_command":
        return run_shell_command(inputs["command"])
    else:
        return f"ERROR: Unknown tool '{name}'."
