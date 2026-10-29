import shutil
import subprocess
from pathlib import Path

import pytest

DEMO = Path(__file__).parents[1] / "scripts" / "demo.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_demo_script_has_valid_syntax() -> None:
    subprocess.run(["bash", "-n", str(DEMO)], check=True)


def test_demo_script_is_executable() -> None:
    assert DEMO.stat().st_mode & 0o111
