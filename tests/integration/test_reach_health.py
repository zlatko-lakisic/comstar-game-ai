import pytest

from comstar_game_ai.agent.reach.client import check_ada_health, reach_mtls_config
from comstar_game_ai.shared.config import load_config, mtls_material_path


pytestmark = pytest.mark.integration_ada


@pytest.fixture
def config():
    return load_config()


def test_mtls_material_present(config):
    path = mtls_material_path(config)
    assert (path / "cert.pem").is_file()
    assert (path / "key.pem").is_file()
    assert (path / "ca.pem").is_file()


def test_reach_mtls_config(config):
    mtls = reach_mtls_config(config)
    assert mtls.is_configured


@pytest.mark.asyncio
async def test_ada_health(config):
    health = await check_ada_health(config)
    assert health.get("ok") is True
    assert health.get("status_code") == 200
