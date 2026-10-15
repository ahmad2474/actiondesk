import pytest
from sqlalchemy import Engine

from tests.capability_cases import CapabilityCases
from tests.workflow_support import World, build_world

pytestmark = pytest.mark.integration


@pytest.fixture
def world(database: Engine) -> World:
    return build_world(database)


class TestCapabilities(CapabilityCases):
    pass
