import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def _allow_local_sockets(socket_enabled):
    yield
