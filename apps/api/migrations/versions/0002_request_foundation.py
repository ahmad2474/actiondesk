"""Role catalog, required department, creation retries and audited state consistency."""

from alembic import op

revision = "0002_request_foundation"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE roles (name role_enum PRIMARY KEY)")
    op.execute("INSERT INTO roles(name) VALUES ('employee'),('manager'),('finance'),('admin')")
    op.execute(
        "ALTER TABLE role_assignments ADD CONSTRAINT fk_role_catalog "
        "FOREIGN KEY (role) REFERENCES roles(name)"
    )
    # Do not guess departments or rewrite existing history. Invalid legacy data blocks upgrade.
    op.execute("ALTER TABLE requests ALTER COLUMN department_id SET NOT NULL")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM requests r WHERE NOT EXISTS (
              SELECT 1 FROM request_events e WHERE e.organization_id = r.organization_id
                AND e.request_id = r.id AND e.sequence = r.version AND e.to_state = r.status
            )
          ) THEN
            RAISE EXCEPTION 'Existing requests require matching current history before upgrade';
          END IF;
        END $$;
    """)
    op.execute("ALTER TABLE requests ADD COLUMN idempotency_key UUID")
    op.execute(
        "ALTER TABLE requests ADD CONSTRAINT uq_request_creation_key "
        "UNIQUE (organization_id, created_by, idempotency_key)"
    )
    op.execute("""
        CREATE FUNCTION require_request_status_event() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' THEN
            IF NEW.status IS NOT DISTINCT FROM OLD.status
               AND NEW.version IS NOT DISTINCT FROM OLD.version THEN
              RETURN NULL;
            END IF;
            IF NEW.version <> OLD.version + 1 OR NOT EXISTS (
              SELECT 1 FROM request_events e WHERE e.organization_id = NEW.organization_id
                AND e.request_id = NEW.id AND e.sequence = NEW.version
                AND e.from_state = OLD.status AND e.to_state = NEW.status
            ) THEN
              RAISE EXCEPTION 'status change requires a matching history event and next version'
                USING ERRCODE = '23514';
            END IF;
          ELSIF NOT EXISTS (
            SELECT 1 FROM request_events e WHERE e.organization_id = NEW.organization_id
              AND e.request_id = NEW.id AND e.sequence = NEW.version AND e.to_state = NEW.status
          ) THEN
            RAISE EXCEPTION 'request creation requires a matching history event'
              USING ERRCODE = '23514';
          END IF;
          RETURN NULL;
        END;
        $$;
    """)
    # Deferred until commit: the request and its event can be inserted in FK-safe order.
    op.execute("""
        CREATE CONSTRAINT TRIGGER request_status_history_required
        AFTER INSERT OR UPDATE ON requests DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION require_request_status_event()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER request_status_history_required ON requests")
    op.execute("DROP FUNCTION require_request_status_event()")
    op.drop_constraint("uq_request_creation_key", "requests", type_="unique")
    op.drop_column("requests", "idempotency_key")
    op.execute("ALTER TABLE requests ALTER COLUMN department_id DROP NOT NULL")
    op.drop_constraint("fk_role_catalog", "role_assignments", type_="foreignkey")
    op.drop_table("roles")
