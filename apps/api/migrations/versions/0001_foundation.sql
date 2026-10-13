CREATE TYPE role_enum AS ENUM ('employee', 'manager', 'finance', 'admin');
-- statement-break
CREATE TYPE request_type_enum AS ENUM ('service', 'expense', 'leave');
-- statement-break
CREATE TYPE request_status_enum AS ENUM (
  'DRAFT', 'SUBMITTED', 'TRIAGED', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED',
  'NEEDS_INFO', 'REOPENED', 'CANCELLED', 'MANAGER_REVIEW', 'FINANCE_REVIEW',
  'APPROVED', 'COMPLETED', 'REJECTED', 'WITHDRAWN'
);
-- statement-break
CREATE TABLE organizations (
  id UUID PRIMARY KEY, slug VARCHAR(80) NOT NULL UNIQUE, name VARCHAR(200) NOT NULL,
  timezone VARCHAR(80) NOT NULL DEFAULT 'UTC', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- statement-break
CREATE TABLE departments (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  name VARCHAR(120) NOT NULL,
  UNIQUE (organization_id, id), UNIQUE (organization_id, name)
);
-- statement-break
CREATE TABLE users (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  email VARCHAR(254) NOT NULL, name VARCHAR(200) NOT NULL, department_id UUID,
  password_hash TEXT, status VARCHAR(20) NOT NULL DEFAULT 'inactive',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id), UNIQUE (organization_id, email),
  FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id),
  CONSTRAINT user_status CHECK (status IN ('active', 'inactive'))
);
-- statement-break
CREATE TABLE role_assignments (
  organization_id UUID NOT NULL, user_id UUID NOT NULL, role role_enum NOT NULL,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(), revoked_at TIMESTAMPTZ,
  PRIMARY KEY (organization_id, user_id, role),
  FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id)
);
-- statement-break
CREATE TABLE employee_managers (
  organization_id UUID NOT NULL, employee_id UUID NOT NULL, manager_id UUID NOT NULL,
  manager_role role_enum NOT NULL DEFAULT 'manager',
  PRIMARY KEY (organization_id, employee_id),
  FOREIGN KEY (organization_id, employee_id) REFERENCES users(organization_id, id),
  FOREIGN KEY (organization_id, manager_id, manager_role)
    REFERENCES role_assignments(organization_id, user_id, role),
  CONSTRAINT manager_not_self CHECK (employee_id <> manager_id),
  CONSTRAINT employee_manager_role CHECK (manager_role = 'manager')
);
-- statement-break
CREATE TABLE department_managers (
  organization_id UUID NOT NULL, department_id UUID NOT NULL, manager_id UUID NOT NULL,
  manager_role role_enum NOT NULL DEFAULT 'manager',
  PRIMARY KEY (organization_id, department_id, manager_id),
  FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id),
  FOREIGN KEY (organization_id, manager_id, manager_role)
    REFERENCES role_assignments(organization_id, user_id, role),
  CONSTRAINT department_manager_role CHECK (manager_role = 'manager')
);
-- statement-break
CREATE TABLE approval_policies (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  name VARCHAR(120) NOT NULL, version INTEGER NOT NULL, request_type request_type_enum NOT NULL,
  definition JSONB NOT NULL,
  UNIQUE (organization_id, id), UNIQUE (organization_id, name, version),
  CONSTRAINT positive_policy_version CHECK (version > 0)
);
-- statement-break
CREATE TABLE requests (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  type request_type_enum NOT NULL, title VARCHAR(200) NOT NULL, raw_text TEXT NOT NULL,
  status request_status_enum NOT NULL, priority VARCHAR(20) NOT NULL DEFAULT 'normal',
  created_by UUID NOT NULL, assigned_to UUID, department_id UUID, approval_policy_id UUID,
  follow_up_to_id UUID, version INTEGER NOT NULL DEFAULT 1,
  due_at TIMESTAMPTZ, approved_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
  processed_by UUID, processing_role role_enum,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id), UNIQUE (organization_id, id, created_by),
  FOREIGN KEY (organization_id, created_by) REFERENCES users(organization_id, id),
  FOREIGN KEY (organization_id, assigned_to) REFERENCES users(organization_id, id),
  FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id),
  FOREIGN KEY (organization_id, approval_policy_id) REFERENCES approval_policies(organization_id, id),
  FOREIGN KEY (organization_id, follow_up_to_id) REFERENCES requests(organization_id, id),
  FOREIGN KEY (organization_id, processed_by, processing_role)
    REFERENCES role_assignments(organization_id, user_id, role),
  CONSTRAINT processing_actor_pair CHECK ((processed_by IS NULL) = (processing_role IS NULL)),
  CONSTRAINT finance_processing_role CHECK (processing_role = 'finance'),
  CONSTRAINT expense_completion_actor
    CHECK (type <> 'expense' OR completed_at IS NULL OR processed_by IS NOT NULL),
  CONSTRAINT expense_completion_timestamp
    CHECK (type <> 'expense' OR status <> 'COMPLETED' OR completed_at IS NOT NULL),
  CONSTRAINT positive_request_version CHECK (version > 0),
  CONSTRAINT follow_up_not_self CHECK (follow_up_to_id <> id),
  CONSTRAINT request_priority CHECK (priority IN ('low', 'normal', 'high', 'urgent'))
);
-- statement-break
CREATE INDEX ix_requests_org_status_created ON requests(organization_id, status, created_at);
-- statement-break
CREATE INDEX ix_requests_org_assignee_status ON requests(organization_id, assigned_to, status);
-- statement-break
CREATE INDEX ix_requests_org_due ON requests(organization_id, due_at);
-- statement-break
CREATE TABLE request_fields (
  organization_id UUID NOT NULL, request_id UUID NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1,
  fields JSONB NOT NULL, PRIMARY KEY (organization_id, request_id),
  FOREIGN KEY (organization_id, request_id) REFERENCES requests(organization_id, id),
  CONSTRAINT positive_fields_version CHECK (schema_version > 0)
);
-- statement-break
CREATE TABLE request_events (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  request_id UUID NOT NULL, sequence INTEGER NOT NULL, actor_id UUID, action VARCHAR(80) NOT NULL,
  from_state request_status_enum, to_state request_status_enum NOT NULL, reason TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL,
  UNIQUE (organization_id, request_id, sequence),
  FOREIGN KEY (organization_id, request_id) REFERENCES requests(organization_id, id),
  FOREIGN KEY (organization_id, actor_id) REFERENCES users(organization_id, id),
  CONSTRAINT positive_event_sequence CHECK (sequence > 0)
);
-- statement-break
CREATE FUNCTION reject_request_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'request_events are append-only';
END;
$$;
-- statement-break
CREATE TRIGGER immutable_request_events BEFORE UPDATE OR DELETE ON request_events
  FOR EACH ROW EXECUTE FUNCTION reject_request_event_mutation();
-- statement-break
CREATE TABLE approvals (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  request_id UUID NOT NULL, requester_id UUID NOT NULL, step INTEGER NOT NULL,
  approver_id UUID NOT NULL, approver_role role_enum NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending', decision_reason TEXT, decided_at TIMESTAMPTZ,
  UNIQUE (organization_id, request_id, step),
  FOREIGN KEY (organization_id, request_id, requester_id)
    REFERENCES requests(organization_id, id, created_by),
  FOREIGN KEY (organization_id, approver_id, approver_role)
    REFERENCES role_assignments(organization_id, user_id, role),
  CONSTRAINT no_self_approval CHECK (approver_id <> requester_id),
  CONSTRAINT positive_approval_step CHECK (step > 0),
  CONSTRAINT eligible_approval_role CHECK (approver_role IN ('manager', 'finance')),
  CONSTRAINT approval_status CHECK (status IN ('pending', 'approved', 'rejected'))
);
-- statement-break
CREATE INDEX ix_approvals_org_approver_status ON approvals(organization_id, approver_id, status);
-- statement-break
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  request_id UUID NOT NULL, business_key VARCHAR(200) NOT NULL, event_type VARCHAR(100) NOT NULL,
  payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  dispatched_at TIMESTAMPTZ, attempt_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE (organization_id, business_key),
  FOREIGN KEY (organization_id, request_id) REFERENCES requests(organization_id, id),
  CONSTRAINT nonnegative_outbox_attempts CHECK (attempt_count >= 0)
);
-- statement-break
CREATE INDEX ix_outbox_dispatched_created ON outbox_events(dispatched_at, created_at);
-- statement-break
