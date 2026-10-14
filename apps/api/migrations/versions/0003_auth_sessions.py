"""Persistent opaque sessions, canonical email uniqueness and account revocation."""

from alembic import op

revision = "0003_auth_sessions"
down_revision = "0002_request_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM users GROUP BY organization_id, lower(btrim(email))
                     HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Canonical email collision within organization; resolve before upgrade';
          END IF;
        END $$;
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_org_email_canonical "
        "ON users(organization_id, lower(btrim(email)))"
    )
    op.execute("""
        CREATE TABLE auth_sessions (
          id UUID PRIMARY KEY, token_hash VARCHAR(64) NOT NULL UNIQUE,
          organization_id UUID NOT NULL, user_id UUID NOT NULL,
          created_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ,
          FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id),
          CONSTRAINT session_positive_lifetime CHECK (expires_at > created_at),
          CONSTRAINT session_seen_after_creation CHECK (last_seen_at >= created_at)
        )
    """)
    op.execute("CREATE INDEX ix_auth_sessions_org_user ON auth_sessions(organization_id,user_id)")
    op.execute("CREATE INDEX ix_auth_sessions_expiry ON auth_sessions(expires_at)")
    # Database enforcement also covers account changes outside the HTTP layer.
    op.execute("""
        CREATE FUNCTION revoke_account_sessions() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.status = 'inactive' THEN
            UPDATE auth_sessions SET revoked_at = now()
              WHERE organization_id = NEW.organization_id AND user_id = NEW.id
                AND revoked_at IS NULL;
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.execute("""
        CREATE TRIGGER account_session_revocation AFTER UPDATE OF status ON users
          FOR EACH ROW EXECUTE FUNCTION revoke_account_sessions()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER account_session_revocation ON users")
    op.execute("DROP FUNCTION revoke_account_sessions()")
    op.drop_table("auth_sessions")
    op.drop_index("uq_users_org_email_canonical", table_name="users")
