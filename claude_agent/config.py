"""
Claude Agent Configuration
--------------------------
Change MODEL_ID to switch between Claude models.
All other tuning knobs live here too.
"""

import os
from pathlib import Path

# ── Model ──────────────────────────────────────────────────────────────────────
MODEL_ID = "claude-fable-5-1"          # Claude Fable 5.1 (latest)
# MODEL_ID = "claude-opus-4-5"         # Most powerful
# MODEL_ID = "claude-sonnet-4-5"       # Fast + capable
# MODEL_ID = "claude-haiku-3-5"        # Fastest / cheapest

# ── Context & output limits ───────────────────────────────────────────────────
MAX_TOKENS = 8192          # Max tokens per response
THINKING_BUDGET = 10_000   # Inner reasoning tokens (set 0 to disable thinking)

# ── Workspace ─────────────────────────────────────────────────────────────────
# All file tools are sandboxed inside this directory.
WORKSPACE_ROOT = Path(__file__).parent.parent.resolve()   # TriageIQ/

# ── Shell commands ─────────────────────────────────────────────────────────────
ENABLE_SHELL = True   # Set False to disable the run_shell_command tool

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are an expert AI coding assistant working on the TriageIQ project.

TriageIQ is a machine-learning system that predicts whether a CFPB consumer complaint \
will result in monetary relief, using a fine-tuned DistilBERT model on 4.8M real complaints \
combined with PostgreSQL-based entity features.

Your workspace is strictly confined to:
  {WORKSPACE_ROOT}

You can read and write any file within this directory using your tools. \
You can also run shell commands from within this directory.

Always think carefully before making irreversible changes (overwriting files, running \
destructive commands). When in doubt, read first, then ask.

Current tech stack: Python 3.11, Poetry, pandas, numpy, pyarrow, matplotlib, \
scikit-learn, PostgreSQL (planned), FastAPI (planned), DistilBERT (planned).
"""
