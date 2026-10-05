import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "make_release.py"


@pytest.fixture(scope="module")
def release():
    spec = importlib.util.spec_from_file_location("make_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_tree(root: Path) -> None:
    files = {
        "app.py": "",
        "style.py": "",
        "run.bat": "",
        "requirements.txt": "",
        "README.md": "",
        "SPEC.md": "",
        "macrocal/__init__.py": "",
        "macrocal/bot.py": "",
        "macrocal/__pycache__/bot.cpython-313.pyc": "",
        "vendor/ecocal/Calendar.py": "",
        "vendor/ecocal/LICENSE": "",
        "vendor/ecocal/__pycache__/x.pyc": "",
        ".streamlit/config.toml": "",
        ".streamlit/secrets.toml": "FRED_API_KEY = 'real-secret'",
        ".streamlit/secrets.toml.example": "",
        ".env": "GEMINI_API_KEY=real-secret",
        "tests/test_x.py": "",
        ".venv/Scripts/python.exe": "",
        "dist/old.zip": "",
        "wheels/x.whl": "",
        ".git/config": "",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def test_release_contains_the_app_package_and_vendored_ecocal(release, tmp_path):
    build_tree(tmp_path)
    names = {p.as_posix() for p in release.release_files(tmp_path)}
    assert {"app.py", "style.py", "run.bat", "requirements.txt", "README.md"} <= names
    assert {"macrocal/__init__.py", "macrocal/bot.py"} <= names
    assert {"vendor/ecocal/Calendar.py", "vendor/ecocal/LICENSE"} <= names
    assert ".streamlit/config.toml" in names
    assert ".streamlit/secrets.toml.example" in names


def test_release_never_contains_secrets_or_junk(release, tmp_path):
    build_tree(tmp_path)
    names = {p.as_posix() for p in release.release_files(tmp_path)}
    assert ".streamlit/secrets.toml" not in names
    assert ".env" not in names
    assert not any("__pycache__" in n for n in names)
    assert not any(n.startswith((".venv", ".git", "dist", "wheels", "tests")) for n in names)


def test_a_secrets_file_in_the_tree_makes_the_builder_say_so_but_still_leave_it_out(release, tmp_path):
    build_tree(tmp_path)
    assert release.secret_files_present(tmp_path) == [".env", ".streamlit/secrets.toml"]
    assert ".streamlit/secrets.toml" not in {p.as_posix() for p in release.release_files(tmp_path)}


def test_the_zip_name_says_which_python_it_targets(release):
    assert release.release_name("abc1234", ["3.13"], online=False) == "macrocal-abc1234-offline-py313"
    assert release.release_name("abc1234", ["3.13", "3.11"], online=False) == "macrocal-abc1234-offline-py313+311"
    assert release.release_name("abc1234", ["3.13"], online=True) == "macrocal-abc1234-online"
