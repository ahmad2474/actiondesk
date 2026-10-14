-- Legacy records retain NULL workflow_version. No policy, nominee, event or decision is backfilled.
ALTER TABLE requests
  ADD COLUMN workflow_version INTEGER,
  ADD COLUMN submission_sequence INTEGER,
  ADD COLUMN leave_overlap BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN processing_reference VARCHAR(200),
  ADD COLUMN resolution TEXT,
  ADD CONSTRAINT workflow_version CHECK (workflow_version IS NULL OR workflow_version = 1),
  ADD CONSTRAINT submission_sequence CHECK (submission_sequence IS NULL OR submission_sequence > 1),
  ADD CONSTRAINT no_self_processing CHECK (processed_by <> created_by) NOT VALID;
-- statement-break
-- Validate legacy processing attribution explicitly; never rewrite a conflicting processor.
ALTER TABLE requests VALIDATE CONSTRAINT no_self_processing;
-- statement-break
ALTER TABLE approval_policies ADD CONSTRAINT policy_identity_type
  UNIQUE (organization_id, id, request_type);
-- statement-break
CREATE TABLE active_approval_policies (
  organization_id UUID NOT NULL, request_type request_type_enum NOT NULL, policy_id UUID NOT NULL,
  PRIMARY KEY (organization_id, request_type),
  FOREIGN KEY (organization_id, policy_id, request_type)
    REFERENCES approval_policies(organization_id, id, request_type),
  CONSTRAINT active_review_policy_type CHECK (request_type IN ('expense','leave'))
);
-- statement-break
ALTER TABLE approvals ALTER COLUMN approver_id DROP NOT NULL;
-- statement-break
ALTER TABLE approvals DROP CONSTRAINT approval_status;
-- statement-break
ALTER TABLE approvals ADD CONSTRAINT approval_status
  CHECK (status IN ('pending','approved','rejected','cancelled'));
-- statement-break
ALTER TABLE approvals ADD COLUMN closed_event_sequence INTEGER,
  ADD CONSTRAINT approval_closed_event FOREIGN KEY (organization_id, request_id, closed_event_sequence)
    REFERENCES request_events(organization_id, request_id, sequence),
  ADD CONSTRAINT approval_identity UNIQUE (organization_id, id, request_id, requester_id, approver_role);
-- statement-break
CREATE TABLE approval_candidates (
  organization_id UUID NOT NULL, approval_id UUID NOT NULL, user_id UUID NOT NULL,
  request_id UUID NOT NULL, requester_id UUID NOT NULL, required_role role_enum NOT NULL,
  routing_source VARCHAR(30) NOT NULL,
  PRIMARY KEY (organization_id, approval_id, user_id),
  FOREIGN KEY (organization_id, approval_id, request_id, requester_id, required_role)
    REFERENCES approvals(organization_id, id, request_id, requester_id, approver_role),
  FOREIGN KEY (organization_id, user_id) REFERENCES users(organization_id, id),
  CONSTRAINT candidate_not_requester CHECK (user_id <> requester_id),
  CONSTRAINT candidate_routing_source CHECK (routing_source IN ('employee_manager','department_manager','finance'))
);
-- statement-break
CREATE INDEX ix_candidates_org_user ON approval_candidates(organization_id, user_id);
-- statement-break
CREATE TABLE approval_decisions (
  id UUID PRIMARY KEY, organization_id UUID NOT NULL REFERENCES organizations(id),
  approval_id UUID NOT NULL, request_id UUID NOT NULL, requester_id UUID NOT NULL,
  actor_id UUID NOT NULL, required_role role_enum NOT NULL, outcome VARCHAR(20) NOT NULL,
  reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL, event_sequence INTEGER NOT NULL,
  UNIQUE (organization_id, approval_id), UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, approval_id, request_id, requester_id, required_role)
    REFERENCES approvals(organization_id, id, request_id, requester_id, approver_role),
  FOREIGN KEY (organization_id, approval_id, actor_id)
    REFERENCES approval_candidates(organization_id, approval_id, user_id),
  FOREIGN KEY (organization_id, request_id, event_sequence)
    REFERENCES request_events(organization_id, request_id, sequence),
  CONSTRAINT decision_not_requester CHECK (actor_id <> requester_id),
  CONSTRAINT decision_outcome CHECK (outcome IN ('approved','rejected'))
);
-- statement-break
CREATE TABLE mutation_receipts (
  organization_id UUID NOT NULL, actor_id UUID NOT NULL, idempotency_key UUID NOT NULL,
  request_id UUID NOT NULL, action VARCHAR(80) NOT NULL, payload_hash VARCHAR(64) NOT NULL,
  version INTEGER NOT NULL, status request_status_enum NOT NULL, decision_id UUID,
  PRIMARY KEY (organization_id, actor_id, idempotency_key),
  FOREIGN KEY (organization_id, actor_id) REFERENCES users(organization_id, id),
  FOREIGN KEY (organization_id, request_id, version)
    REFERENCES request_events(organization_id, request_id, sequence),
  FOREIGN KEY (organization_id, decision_id) REFERENCES approval_decisions(organization_id, id),
  CONSTRAINT receipt_hash_length CHECK (length(payload_hash) = 64)
);
-- statement-break
CREATE FUNCTION reject_workflow_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'workflow evidence is immutable' USING ERRCODE = '23514';
END $$;
-- statement-break
CREATE TRIGGER immutable_approval_policies BEFORE UPDATE OR DELETE ON approval_policies
  FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_approval_decisions BEFORE UPDATE OR DELETE ON approval_decisions
  FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_mutation_receipts BEFORE UPDATE OR DELETE ON mutation_receipts
  FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE FUNCTION workflow_candidate_eligible(org UUID, approval UUID, actor UUID)
RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM approval_candidates c
      JOIN requests r ON r.organization_id=c.organization_id AND r.id=c.request_id
      JOIN users u ON u.organization_id=c.organization_id AND u.id=c.user_id
      JOIN role_assignments ra ON ra.organization_id=c.organization_id AND ra.user_id=c.user_id
        AND ra.role=c.required_role
    WHERE c.organization_id=org AND c.approval_id=approval AND c.user_id=actor
      AND actor <> r.created_by AND u.status='active'
      AND ra.revoked_at IS NULL AND ra.granted_at <= now()
      AND ((c.routing_source='finance' AND c.required_role='finance')
        OR (c.required_role='manager' AND c.routing_source='employee_manager' AND EXISTS (
          SELECT 1 FROM employee_managers m WHERE m.organization_id=org
            AND m.employee_id=r.created_by AND m.manager_id=actor))
        OR (c.required_role='manager' AND c.routing_source='department_manager' AND EXISTS (
          SELECT 1 FROM department_managers m WHERE m.organization_id=org
            AND m.department_id=r.department_id AND m.manager_id=actor)))
  )
$$;
-- statement-break
CREATE FUNCTION guard_candidate_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; p approval_policies;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'candidate snapshot is immutable' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  IF r.workflow_version IS DISTINCT FROM 1 OR r.status <> 'DRAFT' THEN
    RAISE EXCEPTION 'candidates require a managed draft' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO p FROM approval_policies WHERE organization_id=r.organization_id AND id=r.approval_policy_id;
  IF (NEW.routing_source='finance') <> (NEW.required_role='finance')
     OR (NEW.routing_source='department_manager' AND
         (p.definition->>'allow_department_fallback') IS DISTINCT FROM 'true') THEN
    RAISE EXCEPTION 'candidate source violates policy' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER candidate_snapshot_guard BEFORE INSERT OR UPDATE OR DELETE ON approval_candidates
  FOR EACH ROW EXECUTE FUNCTION guard_candidate_snapshot();
-- statement-break
CREATE FUNCTION guard_approval_plan() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'approval plan is preserved' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  IF TG_OP='INSERT' THEN
    IF r.workflow_version=1 AND (r.status <> 'DRAFT' OR NEW.status <> 'pending') THEN
      RAISE EXCEPTION 'new approval plan requires a draft' USING ERRCODE = '23514';
    END IF;
  ELSE
    IF r.workflow_version IS DISTINCT FROM 1 OR
      ROW(NEW.id,NEW.organization_id,NEW.request_id,NEW.requester_id,NEW.step,NEW.approver_id,NEW.approver_role)
      IS DISTINCT FROM
      ROW(OLD.id,OLD.organization_id,OLD.request_id,OLD.requester_id,OLD.step,OLD.approver_id,OLD.approver_role)
      OR OLD.status <> 'pending' THEN
      RAISE EXCEPTION 'approval plan and prior decisions are immutable' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER approval_plan_guard BEFORE INSERT OR UPDATE OR DELETE ON approvals
  FOR EACH ROW EXECUTE FUNCTION guard_approval_plan();
-- statement-break
CREATE FUNCTION guard_approval_projection() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a approvals; d approval_decisions; r requests;
BEGIN
  SELECT * INTO a FROM approvals WHERE organization_id=NEW.organization_id AND id=NEW.id;
  SELECT * INTO r FROM requests WHERE organization_id=a.organization_id AND id=a.request_id;
  IF r.workflow_version IS DISTINCT FROM 1 THEN RETURN NULL; END IF;
  IF a.status='pending' THEN
    IF a.closed_event_sequence IS NOT NULL OR a.decided_at IS NOT NULL OR a.decision_reason IS NOT NULL
      OR EXISTS (SELECT 1 FROM approval_decisions WHERE organization_id=a.organization_id AND approval_id=a.id) THEN
      RAISE EXCEPTION 'pending step cannot contain a decision' USING ERRCODE='23514';
    END IF;
  ELSIF a.status='cancelled' THEN
    IF a.decided_at IS NOT NULL OR a.decision_reason IS NOT NULL OR EXISTS (
      SELECT 1 FROM approval_decisions WHERE organization_id=a.organization_id AND approval_id=a.id)
      OR NOT EXISTS (SELECT 1 FROM request_events e WHERE e.organization_id=a.organization_id
        AND e.request_id=a.request_id AND e.sequence=a.closed_event_sequence
        AND e.to_state IN ('REJECTED','WITHDRAWN') AND e.action IN ('reject','cancel')) THEN
      RAISE EXCEPTION 'cancelled step requires audited closure' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT * INTO d FROM approval_decisions WHERE organization_id=a.organization_id AND approval_id=a.id;
    IF d.id IS NULL OR ROW(d.outcome,d.reason,d.at,d.event_sequence) IS DISTINCT FROM
      ROW(a.status,a.decision_reason,a.decided_at,a.closed_event_sequence) THEN
      RAISE EXCEPTION 'approval projection requires immutable decision' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER approval_projection_guard AFTER INSERT OR UPDATE ON approvals
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_approval_projection();
-- statement-break
CREATE FUNCTION guard_decision_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; a approvals; e request_events;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  SELECT * INTO a FROM approvals WHERE organization_id=NEW.organization_id AND id=NEW.approval_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id
    AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  IF r.workflow_version IS DISTINCT FROM 1 OR a.status <> 'pending'
    OR (a.approver_id IS NOT NULL AND a.approver_id <> NEW.actor_id)
    OR NOT workflow_candidate_eligible(NEW.organization_id, NEW.approval_id, NEW.actor_id)
    OR e.sequence IS DISTINCT FROM r.version OR e.to_state IS DISTINCT FROM r.status
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR e.reason IS DISTINCT FROM NEW.reason
    OR e.at IS DISTINCT FROM NEW.at OR e.action IS DISTINCT FROM
      (CASE NEW.outcome WHEN 'approved' THEN 'approve' ELSE 'reject' END)
    OR e.from_state IS DISTINCT FROM (CASE a.approver_role WHEN 'manager' THEN 'MANAGER_REVIEW'::request_status_enum
      ELSE 'FINANCE_REVIEW'::request_status_enum END)
    OR EXISTS (SELECT 1 FROM approvals prev WHERE prev.organization_id=a.organization_id
      AND prev.request_id=a.request_id AND prev.step<a.step AND prev.status <> 'approved') THEN
    RAISE EXCEPTION 'decision lacks current eligibility or matching history' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER decision_insert_guard BEFORE INSERT ON approval_decisions
  FOR EACH ROW EXECUTE FUNCTION guard_decision_insert();
-- statement-break
CREATE FUNCTION guard_receipt_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM request_events e WHERE e.organization_id=NEW.organization_id
    AND e.request_id=NEW.request_id AND e.sequence=NEW.version AND e.actor_id=NEW.actor_id
    AND e.to_state=NEW.status AND (e.action=NEW.action OR (NEW.action='submit' AND e.action='route')))
    OR (NEW.action IN ('approve','reject')) <> (NEW.decision_id IS NOT NULL)
    OR (NEW.decision_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM approval_decisions d
      WHERE d.organization_id=NEW.organization_id AND d.id=NEW.decision_id
        AND d.actor_id=NEW.actor_id AND d.request_id=NEW.request_id AND d.event_sequence=NEW.version)) THEN
    RAISE EXCEPTION 'receipt must reference the recorded outcome' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER receipt_insert_guard BEFORE INSERT ON mutation_receipts
  FOR EACH ROW EXECUTE FUNCTION guard_receipt_insert();
-- statement-break
CREATE FUNCTION guard_frozen_fields() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests;
BEGIN
  IF TG_OP='INSERT' THEN
    SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  ELSE
    SELECT * INTO r FROM requests WHERE organization_id=OLD.organization_id AND id=OLD.request_id FOR UPDATE;
  END IF;
  IF r.type IN ('expense','leave') AND r.status <> 'DRAFT' AND
     (r.workflow_version=1 OR TG_OP <> 'INSERT') THEN
    RAISE EXCEPTION 'submitted fields are frozen' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND ROW(OLD.organization_id,OLD.request_id) IS DISTINCT FROM ROW(NEW.organization_id,NEW.request_id) THEN
    RAISE EXCEPTION 'field identity is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER frozen_request_fields BEFORE INSERT OR UPDATE OR DELETE ON request_fields
  FOR EACH ROW EXECUTE FUNCTION guard_frozen_fields();
-- statement-break
CREATE FUNCTION guard_workflow_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed BOOLEAN;
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.workflow_version=1 AND (NEW.version <> 1 OR NEW.status <>
       CASE NEW.type WHEN 'service' THEN 'SUBMITTED'::request_status_enum ELSE 'DRAFT'::request_status_enum END
       OR NEW.submission_sequence IS NOT NULL OR NEW.approval_policy_id IS NOT NULL
       OR NEW.assigned_to IS NOT NULL OR NEW.processed_by IS NOT NULL
       OR NEW.approved_at IS NOT NULL OR NEW.completed_at IS NOT NULL) THEN
      RAISE EXCEPTION 'managed request must begin at its initial state' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.organization_id,NEW.type,NEW.created_by,NEW.workflow_version)
     IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.type,OLD.created_by,OLD.workflow_version) THEN
    RAISE EXCEPTION 'request identity and workflow provenance are immutable' USING ERRCODE='23514';
  END IF;
  IF OLD.type IN ('expense','leave') AND OLD.workflow_version IS NULL AND
    ROW(NEW.status,NEW.version,NEW.approval_policy_id,NEW.submission_sequence,NEW.approved_at,
        NEW.completed_at,NEW.processed_by,NEW.processing_role,NEW.processing_reference)
    IS DISTINCT FROM ROW(OLD.status,OLD.version,OLD.approval_policy_id,OLD.submission_sequence,OLD.approved_at,
        OLD.completed_at,OLD.processed_by,OLD.processing_role,OLD.processing_reference) THEN
    RAISE EXCEPTION 'legacy approval evidence requires validation; mutation blocked' USING ERRCODE='23514';
  END IF;
  IF OLD.type IN ('expense','leave') AND OLD.status <> 'DRAFT' AND
    ROW(NEW.title,NEW.raw_text,NEW.department_id,NEW.approval_policy_id,NEW.submission_sequence,NEW.leave_overlap)
    IS DISTINCT FROM ROW(OLD.title,OLD.raw_text,OLD.department_id,OLD.approval_policy_id,OLD.submission_sequence,OLD.leave_overlap) THEN
    RAISE EXCEPTION 'submitted authoritative fields are frozen' USING ERRCODE='23514';
  END IF;
  IF (OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at)
     OR (OLD.completed_at IS NOT NULL AND NEW.completed_at IS DISTINCT FROM OLD.completed_at)
     OR (OLD.processed_by IS NOT NULL AND ROW(NEW.processed_by,NEW.processing_role,NEW.processing_reference)
       IS DISTINCT FROM ROW(OLD.processed_by,OLD.processing_role,OLD.processing_reference))
     OR NEW.due_at IS DISTINCT FROM OLD.due_at THEN
    RAISE EXCEPTION 'durable completion evidence and due date are preserved' USING ERRCODE='23514';
  END IF;
  IF NEW.assigned_to IS DISTINCT FROM OLD.assigned_to AND NOT
    (OLD.type='service' AND OLD.status='TRIAGED' AND NEW.status='ASSIGNED') THEN
    RAISE EXCEPTION 'assignment requires its authorized transition' USING ERRCODE='23514';
  END IF;
  IF NEW.resolution IS DISTINCT FROM OLD.resolution AND NOT
    (OLD.type='service' AND OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED') THEN
    RAISE EXCEPTION 'resolution requires its transition' USING ERRCODE='23514';
  END IF;
  IF OLD.workflow_version=1 AND (
    (NEW.approved_at IS DISTINCT FROM OLD.approved_at AND NEW.status <> 'APPROVED') OR
    (NEW.completed_at IS DISTINCT FROM OLD.completed_at AND NEW.status NOT IN ('COMPLETED','CLOSED')) OR
    (NEW.processed_by IS DISTINCT FROM OLD.processed_by AND NEW.status <> 'COMPLETED') OR
    (NEW.processing_reference IS DISTINCT FROM OLD.processing_reference AND NEW.status <> 'COMPLETED') OR
    (NEW.approval_policy_id IS DISTINCT FROM OLD.approval_policy_id AND OLD.status <> 'DRAFT') OR
    (NEW.submission_sequence IS DISTINCT FROM OLD.submission_sequence AND OLD.status <> 'DRAFT')) THEN
    RAISE EXCEPTION 'evidence changes require their transition' USING ERRCODE='23514';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    allowed := CASE OLD.type
      WHEN 'service' THEN
        (OLD.status='SUBMITTED' AND NEW.status IN ('TRIAGED','CANCELLED')) OR
        (OLD.status='TRIAGED' AND NEW.status IN ('ASSIGNED','CANCELLED')) OR
        (OLD.status='ASSIGNED' AND NEW.status IN ('IN_PROGRESS','CANCELLED')) OR
        (OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED') OR
        (OLD.status='RESOLVED' AND NEW.status='CLOSED')
      WHEN 'expense' THEN
        (OLD.status='DRAFT' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR
        (OLD.status='SUBMITTED' AND NEW.status IN ('MANAGER_REVIEW','WITHDRAWN')) OR
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('FINANCE_REVIEW','APPROVED','REJECTED','WITHDRAWN')) OR
        (OLD.status='FINANCE_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN')) OR
        (OLD.status='APPROVED' AND NEW.status='COMPLETED')
      WHEN 'leave' THEN
        (OLD.status='DRAFT' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR
        (OLD.status='SUBMITTED' AND NEW.status IN ('MANAGER_REVIEW','WITHDRAWN')) OR
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN'))
      ELSE false END;
    IF NOT allowed OR NEW.version <> OLD.version+1 THEN
      RAISE EXCEPTION 'invalid workflow edge or version' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.version IS DISTINCT FROM OLD.version THEN
    RAISE EXCEPTION 'version requires a state transition' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE TRIGGER workflow_request_guard BEFORE INSERT OR UPDATE ON requests
  FOR EACH ROW EXECUTE FUNCTION guard_workflow_request();
-- statement-break
CREATE FUNCTION require_workflow_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; f request_fields; p approval_policies; e request_events;
        expected_steps INTEGER; actor UUID; required_action TEXT; candidate_count INTEGER;
BEGIN
  IF NEW.workflow_version IS DISTINCT FROM 1 THEN RETURN NULL; END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id
    AND request_id=NEW.id AND sequence=NEW.version;
  IF TG_OP='UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    actor := e.actor_id;
    required_action := CASE NEW.status WHEN 'SUBMITTED' THEN 'submit' WHEN 'TRIAGED' THEN 'triage'
      WHEN 'ASSIGNED' THEN 'assign' WHEN 'IN_PROGRESS' THEN 'start' WHEN 'RESOLVED' THEN 'resolve'
      WHEN 'CLOSED' THEN 'close' WHEN 'CANCELLED' THEN 'cancel' WHEN 'WITHDRAWN' THEN 'cancel'
      WHEN 'REJECTED' THEN 'reject' WHEN 'APPROVED' THEN 'approve' WHEN 'COMPLETED' THEN 'process'
      WHEN 'MANAGER_REVIEW' THEN 'route' WHEN 'FINANCE_REVIEW' THEN 'approve' END;
    IF e.action IS DISTINCT FROM required_action OR actor IS NULL OR btrim(e.reason)='' OR NOT EXISTS (
      SELECT 1 FROM users u JOIN role_assignments ra ON ra.organization_id=u.organization_id AND ra.user_id=u.id
      WHERE u.organization_id=r.organization_id AND u.id=actor AND u.status='active'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now()) THEN
      RAISE EXCEPTION 'transition needs an active actor and matching action' USING ERRCODE='23514';
    END IF;
    IF required_action IN ('submit','route') OR (required_action='cancel' AND
      (r.type <> 'service' OR OLD.status IN ('SUBMITTED','TRIAGED'))) THEN
      IF actor <> r.created_by THEN
        RAISE EXCEPTION 'requester action requires owner' USING ERRCODE='23514';
      END IF;
    END IF;
    IF r.type='service' THEN
      IF required_action IN ('triage','assign') OR (required_action='cancel' AND OLD.status='ASSIGNED') THEN
        IF NOT EXISTS (SELECT 1 FROM role_assignments ra WHERE ra.organization_id=r.organization_id
          AND ra.user_id=actor AND ra.revoked_at IS NULL AND ra.granted_at<=now() AND
          (ra.role='admin' OR (ra.role='manager' AND EXISTS (SELECT 1 FROM department_managers m
            WHERE m.organization_id=r.organization_id AND m.department_id=r.department_id AND m.manager_id=actor)))) THEN
          RAISE EXCEPTION 'service routing requires scoped manager or admin' USING ERRCODE='23514';
        END IF;
      END IF;
      IF required_action IN ('start','resolve') AND actor IS DISTINCT FROM NEW.assigned_to THEN
        RAISE EXCEPTION 'service progress requires assignee' USING ERRCODE='23514';
      END IF;
      IF required_action='assign' AND NOT EXISTS (SELECT 1 FROM users u JOIN role_assignments ra
        ON ra.organization_id=u.organization_id AND ra.user_id=u.id WHERE u.organization_id=r.organization_id
        AND u.id=NEW.assigned_to AND u.department_id=NEW.department_id AND u.status='active'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now()) THEN
        RAISE EXCEPTION 'assignment requires active department member' USING ERRCODE='23514';
      END IF;
      IF required_action='resolve' AND (NEW.resolution IS NULL OR btrim(NEW.resolution)='') THEN
        RAISE EXCEPTION 'resolution description required' USING ERRCODE='23514';
      END IF;
      IF required_action='close' AND (NEW.completed_at IS NULL OR
        (actor <> r.created_by AND NOT EXISTS (SELECT 1 FROM role_assignments ra
          WHERE ra.organization_id=r.organization_id AND ra.user_id=actor AND ra.role='admin'
            AND ra.revoked_at IS NULL AND ra.granted_at<=now()))) THEN
        RAISE EXCEPTION 'closure requires requester/admin and timestamp' USING ERRCODE='23514';
      END IF;
    END IF;
  END IF;
  IF r.type='service' THEN RETURN NULL; END IF;
  IF r.submission_sequence IS NULL THEN
    IF r.status NOT IN ('DRAFT','WITHDRAWN') OR EXISTS (SELECT 1 FROM approvals a
      WHERE a.organization_id=r.organization_id AND a.request_id=r.id) THEN
      RAISE EXCEPTION 'submitted request requires complete plan' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
  END IF;
  SELECT * INTO f FROM request_fields WHERE organization_id=r.organization_id AND request_id=r.id;
  SELECT * INTO p FROM approval_policies WHERE organization_id=r.organization_id AND id=r.approval_policy_id;
  IF f.request_id IS NULL OR f.schema_version<>1 OR p.id IS NULL OR p.request_type<>r.type
    OR (p.definition->>'schema_version') IS DISTINCT FROM '1'
    OR (p.definition->>'allow_department_fallback') IS NULL
    OR (p.definition->>'allow_department_fallback') NOT IN ('true','false')
    OR f.fields->>'type' IS DISTINCT FROM r.type::text OR NOT EXISTS (
      SELECT 1 FROM request_events se WHERE se.organization_id=r.organization_id AND se.request_id=r.id
        AND se.sequence=r.submission_sequence AND se.from_state='DRAFT' AND se.to_state='SUBMITTED'
        AND se.actor_id=r.created_by AND se.action='submit')
    OR NOT EXISTS (SELECT 1 FROM request_events se WHERE se.organization_id=r.organization_id AND se.request_id=r.id
        AND se.sequence=r.submission_sequence+1 AND se.from_state='SUBMITTED' AND se.to_state='MANAGER_REVIEW'
        AND se.actor_id=r.created_by AND se.action='route') THEN
    RAISE EXCEPTION 'submission fields, policy and history required' USING ERRCODE='23514';
  END IF;
  expected_steps := 1;
  IF r.type='expense' THEN
    IF jsonb_typeof(f.fields->'amount') IS DISTINCT FROM 'string'
      OR (f.fields->>'amount') !~ '^[0-9]{1,16}(\.[0-9]{1,2})?$'
      OR (f.fields->>'amount')::numeric<=0 OR (f.fields->>'currency') IS DISTINCT FROM 'PKR'
      OR NULLIF(btrim(f.fields->>'vendor'),'') IS NULL OR NULLIF(btrim(f.fields->>'purpose'),'') IS NULL
      OR p.definition->>'currency' IS DISTINCT FROM f.fields->>'currency'
      OR jsonb_typeof(p.definition->'finance_threshold') IS DISTINCT FROM 'string'
      OR (p.definition->>'finance_threshold') !~ '^[0-9]{1,16}(\.[0-9]{1,2})?$' THEN
      RAISE EXCEPTION 'expense fields and configured threshold required' USING ERRCODE='23514';
    END IF;
    IF (f.fields->>'amount')::numeric > (p.definition->>'finance_threshold')::numeric THEN expected_steps:=2; END IF;
  ELSE
    IF NULLIF(f.fields->>'start_date','') IS NULL OR NULLIF(f.fields->>'end_date','') IS NULL
      OR (f.fields->>'start_date')::date > (f.fields->>'end_date')::date
      OR NULLIF(btrim(f.fields->>'leave_type'),'') IS NULL
      OR NULLIF(p.definition->>'currency','') IS NOT NULL OR NULLIF(p.definition->>'finance_threshold','') IS NOT NULL THEN
      RAISE EXCEPTION 'ordered leave dates and manager policy required' USING ERRCODE='23514';
    END IF;
  END IF;
  IF (SELECT count(*) FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id) <> expected_steps
    OR NOT EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id
      AND a.step=1 AND a.approver_role='manager') OR (expected_steps=2 AND NOT EXISTS (
        SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id
          AND a.step=2 AND a.approver_role='finance'))
    OR EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id
      AND NOT EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=a.organization_id AND c.approval_id=a.id)) THEN
    RAISE EXCEPTION 'complete policy-matching candidate plan required' USING ERRCODE='23514';
  END IF;
  -- Validate routing snapshots when submission occurs, not after candidate roles later change.
  IF TG_OP='UPDATE' AND OLD.status='DRAFT' AND NEW.status='SUBMITTED' THEN
    IF NOT EXISTS (SELECT 1 FROM active_approval_policies ap WHERE ap.organization_id=r.organization_id
      AND ap.request_type=r.type AND ap.policy_id=r.approval_policy_id) THEN
      RAISE EXCEPTION 'submission must use the explicitly selected policy' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=r.organization_id AND c.request_id=r.id
      AND NOT workflow_candidate_eligible(c.organization_id,c.approval_id,c.user_id)) THEN
      RAISE EXCEPTION 'submission candidates must currently qualify' USING ERRCODE='23514';
    END IF;
    SELECT count(*) INTO candidate_count FROM employee_managers m JOIN users u
      ON u.organization_id=m.organization_id AND u.id=m.manager_id JOIN role_assignments ra
      ON ra.organization_id=m.organization_id AND ra.user_id=m.manager_id AND ra.role='manager'
      WHERE m.organization_id=r.organization_id AND m.employee_id=r.created_by AND u.status='active'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now();
    IF candidate_count>0 AND EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=r.organization_id
      AND c.request_id=r.id AND c.required_role='manager' AND c.routing_source<>'employee_manager') THEN
      RAISE EXCEPTION 'explicit manager has precedence' USING ERRCODE='23514';
    END IF;
  END IF;
  IF r.status='MANAGER_REVIEW' AND EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id
    AND a.request_id=r.id AND a.status<>'pending') THEN
    RAISE EXCEPTION 'manager review requires pending steps' USING ERRCODE='23514';
  END IF;
  IF r.status='FINANCE_REVIEW' AND (expected_steps<>2 OR NOT EXISTS (SELECT 1 FROM approvals a
    WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND a.step=1 AND a.status='approved')
    OR NOT EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id
      AND a.step=2 AND a.status='pending')) THEN
    RAISE EXCEPTION 'finance review requires manager decision' USING ERRCODE='23514';
  END IF;
  IF r.status IN ('APPROVED','COMPLETED') AND (r.approved_at IS NULL OR NOT EXISTS (
    SELECT 1 FROM approval_decisions d JOIN approvals a ON a.organization_id=d.organization_id AND a.id=d.approval_id
      WHERE d.organization_id=r.organization_id AND d.request_id=r.id AND a.step=expected_steps
        AND d.outcome='approved' AND d.at=r.approved_at) OR EXISTS (
    SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id
      AND (a.status<>'approved' OR NOT EXISTS (SELECT 1 FROM approval_decisions d
        WHERE d.organization_id=a.organization_id AND d.approval_id=a.id AND d.outcome='approved')))) THEN
    RAISE EXCEPTION 'final approval requires all immutable decisions' USING ERRCODE='23514';
  END IF;
  IF r.status='REJECTED' AND (NOT EXISTS (SELECT 1 FROM approval_decisions d WHERE d.organization_id=r.organization_id
    AND d.request_id=r.id AND d.outcome='rejected') OR EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id
    AND a.request_id=r.id AND a.status='pending')) THEN
    RAISE EXCEPTION 'rejection requires decision and closure' USING ERRCODE='23514';
  END IF;
  IF r.status='WITHDRAWN' AND (r.approved_at IS NOT NULL OR EXISTS (SELECT 1 FROM approvals a
    WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND a.status='pending')) THEN
    RAISE EXCEPTION 'withdrawal requires pending steps closed' USING ERRCODE='23514';
  END IF;
  IF r.status='COMPLETED' AND (r.type<>'expense' OR r.completed_at IS NULL OR r.completed_at IS DISTINCT FROM e.at
    OR r.processed_by IS NULL
    OR r.processed_by=r.created_by OR NULLIF(btrim(r.processing_reference),'') IS NULL
    OR e.actor_id IS DISTINCT FROM r.processed_by OR NOT EXISTS (SELECT 1 FROM users u JOIN role_assignments ra
      ON ra.organization_id=u.organization_id AND ra.user_id=u.id WHERE u.organization_id=r.organization_id
        AND u.id=r.processed_by AND u.status='active' AND ra.role='finance'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now())) THEN
    RAISE EXCEPTION 'expense completion needs valid finance processing attribution' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER workflow_evidence_required AFTER INSERT OR UPDATE ON requests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_workflow_evidence();
