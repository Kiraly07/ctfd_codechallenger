"""Language catalog and hard limits for the Judge0 challenge type.

Language ids are the Judge0 CE 1.13.1 defaults. Users never send a raw
language_id; the server maps a slug from this catalog.
"""

from __future__ import annotations

# slug -> (judge0 language_id, label, codemirror mode)
LANGUAGES = {
    "python3": (71, "Python 3", "python"),
    "c": (50, "C", "text/x-csrc"),
    "cpp": (54, "C++", "text/x-c++src"),
    "java": (62, "Java", "text/x-java"),
    "javascript": (63, "JavaScript", "javascript"),
    "go": (60, "Go", "go"),
    "rust": (73, "Rust", "rust"),
}

DEFAULT_LANGUAGES = ["python3", "c", "cpp", "java", "javascript", "go", "rust"]

COMPARISON_MODES = ("trim", "exact", "whitespace-insensitive")

# Hard ceilings. Admin settings cannot raise these.
MAX_CODE_SIZE = 64 * 1024
MAX_INPUT_SIZE = 64 * 1024
MAX_OUTPUT_SIZE = 64 * 1024
MAX_TEST_CASES = 50
MAX_STARTER_SIZE = 16 * 1024

MIN_CPU_TIME = 0.1
MAX_CPU_TIME = 15.0
MIN_MEMORY_KB = 2048
MAX_MEMORY_KB = 512000

DEFAULT_CPU_TIME = 2.0
DEFAULT_MEMORY_KB = 128000
DEFAULT_COMPARISON = "trim"

# Run does not solve. Submit is the scored path and is tighter.
RUN_PER_MINUTE = 12
SUBMIT_PER_MINUTE = 6

JUDGE0_TIMEOUT_SECONDS = 30

CONFIG_URL_KEY = "judge0_url"
CONFIG_TOKEN_KEY = "judge0_api_token"

ENV_URL = "JUDGE0_URL"
ENV_TOKEN = "JUDGE0_API_TOKEN"
