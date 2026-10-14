import pytest
from sqlalchemy import Engine

from tests.revision_cases import RevisionCases
from tests.workflow_support import World, build_world


@pytest.fixture
def world(unit_engine: Engine) -> World:
    return build_world(unit_engine)


class TestRevisions(RevisionCases):
    pass
