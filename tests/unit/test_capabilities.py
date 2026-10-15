import pytest
from sqlalchemy import Engine

from tests.capability_cases import CapabilityCases
from tests.workflow_support import World, build_world


@pytest.fixture
def world(unit_engine: Engine) -> World:
    return build_world(unit_engine)


class TestCapabilities(CapabilityCases):
    pass
