from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import get_engine
from app.main import EXPECTED_REVISION


@pytest.fixture
def database() -> Iterator[Engine]:
    # Test databases only. Never downgrade, truncate, or reset the development database.
    settings = get_settings()
    url = make_url(settings.database_url)
    name = "actiondesk_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = url.set(database=name).render_as_string(hide_password=False)
    patch = pytest.MonkeyPatch()
    patch.setenv("ACTIONDESK_DATABASE_URL", test_url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = get_engine()
    try:
        configuration = Config("alembic.ini")
        command.upgrade(configuration, "head")
        command.upgrade(configuration, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == EXPECTED_REVISION
            )
        command.check(configuration)  # Compare reviewed DDL and SQLAlchemy metadata.
        yield engine
    finally:
        engine.dispose()
        get_engine.cache_clear()
        patch.undo()
        get_settings.cache_clear()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()
