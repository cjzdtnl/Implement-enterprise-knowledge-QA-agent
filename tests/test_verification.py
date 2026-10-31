from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scripts.verify import build_commands, run_checks


def test_offline_verification_never_schedules_live():
    commands = build_commands(offline_only=True, provider="deepseek", env_file=Path("never-read.env"))
    assert {name for name, _ in commands} == {"pip-check", "offline-tests", "mock-evaluation", "retrieval-evaluation"}
    assert all("live" not in arguments and "--env-file" not in arguments for _, arguments in commands)


@pytest.mark.parametrize("step,expected", [("offline-tests", 1), ("live-evaluation", 2)])
def test_verification_propagates_failed_subprocess(tmp_path, monkeypatch, step, expected):
    def fake_process(command, **kwargs):
        return CompletedProcess(command, returncode=1, stdout="EXPLICIT TEST FIXTURE", stderr="simulated failure")
    monkeypatch.setattr("scripts.verify.subprocess.run", fake_process)
    code, directory = run_checks(tmp_path, [(step, ["-m", "fixture-command"])])
    assert code == expected
    assert (directory / (step + ".stderr.txt")).read_text(encoding="utf-8") == "simulated failure"
