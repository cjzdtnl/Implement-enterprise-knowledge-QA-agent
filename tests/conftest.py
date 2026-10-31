from pathlib import Path
import uuid
import os

import pytest

from kb_agent.retrieval import KnowledgeBase
from kb_agent.tools import ToolExecutor
from kb_agent.config import ENV_KEYS


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_model_configuration(request):
    # Offline tests must not inherit a user's real credentials/provider settings.
    if request.node.get_closest_marker("live") is not None:
        yield
        return
    previous = {name: os.environ.get(name) for name in ENV_KEYS}
    for name in ENV_KEYS:
        os.environ.pop(name, None)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def pytest_configure(config):
    # Some Windows machines deny access to an existing shared pytest temp root.
    # A unique workspace directory avoids touching that unrelated directory.
    if not config.option.basetemp:
        temp_parent = ROOT / "work" / "pytest"
        temp_parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(temp_parent / uuid.uuid4().hex)


@pytest.fixture
def kb():
    return KnowledgeBase(ROOT / "data/conflict.json")


@pytest.fixture
def tools(kb):
    return ToolExecutor(kb)
