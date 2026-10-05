"""Guards against committing real keys. The tracked example file must hold placeholders only."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".streamlit" / "secrets.toml.example"


def filled_values(text: str) -> list[str]:
    """Names of uncommented settings that have a non-empty value."""
    found = []
    for line in text.splitlines():
        m = re.match(r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*"([^"]*)"', line)
        if m and m.group(2).strip():
            found.append(m.group(1))
    return found


def test_the_detector_catches_a_pasted_key_and_ignores_comments_and_blanks():
    polluted = 'FRED_API_KEY = "abc123"\n# GEMINI_API_KEY = "abc"\nGEMINI_API_KEY = ""\n'
    assert filled_values(polluted) == ["FRED_API_KEY"]


def test_the_committed_example_file_holds_placeholders_only():
    assert filled_values(EXAMPLE.read_text(encoding="utf-8")) == []


def test_real_secret_files_are_not_tracked_by_git():
    tracked = subprocess.run(
        ["git", "ls-files", ".streamlit/secrets.toml", ".env"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.split()
    assert tracked == []
