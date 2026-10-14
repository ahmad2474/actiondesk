ALTER TABLE requests ADD COLUMN current_submission_sequence INTEGER, ADD COLUMN proposed_revision_id UUID;
ALTER TABLE approvals ADD COLUMN submission_sequence INTEGER;
ALTER TABLE approvals DROP CONSTRAINT approvals_organization_id_request_id_step_key;
ALTER TABLE approvals ADD CONSTRAINT uq_approval_submission_step UNIQUE(organization_id,request_id,submission_sequence,step);
CREATE UNIQUE INDEX uq_approval_original_step ON approvals(organization_id,request_id,step) WHERE submission_sequence IS NULL;
ALTER TABLE approvals ADD FOREIGN KEY(organization_id,request_id,submission_sequence) REFERENCES request_events(organization_id,request_id,sequence) DEFERRABLE INITIALLY DEFERRED;
-- statement-break
CREATE TABLE request_revisions (
  request_id UUID NOT NULL,
  predecessor_id UUID,
  change_sequence INTEGER,
  event_sequence INTEGER NOT NULL,
  actor_id UUID NOT NULL,
  at TIMESTAMP WITH TIME ZONE NOT NULL,
  kind VARCHAR(20) NOT NULL,
  schema_version INTEGER NOT NULL,
  fields JSONB NOT NULL,
  clarification TEXT NOT NULL,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, request_id, id),
  UNIQUE (organization_id, request_id, event_sequence),
  FOREIGN KEY(organization_id, request_id) REFERENCES requests (organization_id, id),
  FOREIGN KEY(organization_id, actor_id) REFERENCES users (organization_id, id),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(organization_id, request_id, predecessor_id) REFERENCES request_revisions (organization_id, request_id, id),
  CONSTRAINT revision_kind CHECK (kind IN ('submitted', 'captured', 'proposed')),
  CONSTRAINT revision_schema CHECK (schema_version = 1),
  CONSTRAINT revision_clarification_length CHECK (length(clarification) <= 20000),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
CREATE TABLE request_submissions (
  organization_id UUID NOT NULL,
  request_id UUID NOT NULL,
  sequence INTEGER NOT NULL,
  routing_sequence INTEGER NOT NULL,
  revision_id UUID NOT NULL,
  policy_id UUID NOT NULL,
  leave_overlap BOOLEAN NOT NULL,
  PRIMARY KEY (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, request_id, sequence) REFERENCES request_events (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, request_id, routing_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, request_id, revision_id) REFERENCES request_revisions (organization_id, request_id, id),
  FOREIGN KEY(organization_id, policy_id) REFERENCES approval_policies (organization_id, id),
  CONSTRAINT submission_routing_sequence CHECK (routing_sequence = sequence + 1)
)
-- statement-break
CREATE TABLE request_change_requests (
  organization_id UUID NOT NULL,
  request_id UUID NOT NULL,
  event_sequence INTEGER NOT NULL,
  submission_sequence INTEGER NOT NULL,
  approval_id UUID NOT NULL,
  actor_id UUID NOT NULL,
  requester_id UUID NOT NULL,
  required_role role_enum NOT NULL,
  PRIMARY KEY (organization_id, request_id, event_sequence),
  UNIQUE (organization_id, request_id, submission_sequence),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(organization_id, request_id, submission_sequence) REFERENCES request_submissions (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, approval_id, actor_id) REFERENCES approval_candidates (organization_id, approval_id, user_id),
  FOREIGN KEY(organization_id, approval_id, request_id, requester_id, required_role) REFERENCES approvals (organization_id, id, request_id, requester_id, approver_role),
  CONSTRAINT correction_not_requester CHECK (actor_id <> requester_id)
)
-- statement-break
ALTER TABLE request_revisions ADD CONSTRAINT fk_revision_change FOREIGN KEY(organization_id, request_id, change_sequence) REFERENCES request_change_requests (organization_id, request_id, event_sequence) DEFERRABLE INITIALLY DEFERRED
-- statement-break
ALTER TABLE requests ADD CONSTRAINT fk_current_submission FOREIGN KEY(organization_id, id, current_submission_sequence) REFERENCES request_submissions (organization_id, request_id, sequence) DEFERRABLE INITIALLY DEFERRED
-- statement-break
ALTER TABLE requests ADD CONSTRAINT fk_proposed_revision FOREIGN KEY(organization_id, id, proposed_revision_id) REFERENCES request_revisions (organization_id, request_id, id) DEFERRABLE INITIALLY DEFERRED
-- statement-break
CREATE TRIGGER immutable_request_revisions BEFORE UPDATE OR DELETE ON request_revisions FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_request_submissions BEFORE UPDATE OR DELETE ON request_submissions FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_request_change_requests BEFORE UPDATE OR DELETE ON request_change_requests FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE OR REPLACE FUNCTION guard_candidate_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; p approval_policies; a approvals;
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'candidate snapshot is immutable' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  IF r.workflow_version IS DISTINCT FROM 1 OR r.status NOT IN ('DRAFT','NEEDS_INFO') THEN
    RAISE EXCEPTION 'candidates require a managed draft' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO a FROM approvals WHERE organization_id=NEW.organization_id AND id=NEW.approval_id;
  IF a.submission_sequence IS DISTINCT FROM r.current_submission_sequence OR a.submission_sequence IS DISTINCT FROM r.version+1 THEN
    RAISE EXCEPTION 'candidate requires the new submission plan' USING ERRCODE='23514';
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
CREATE OR REPLACE FUNCTION guard_approval_plan() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests;
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION 'approval plan is preserved' USING ERRCODE = '23514';
  END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  IF TG_OP='INSERT' THEN
    IF r.workflow_version=1 AND (r.status NOT IN ('DRAFT','NEEDS_INFO') OR NEW.status <> 'pending' OR NEW.submission_sequence IS DISTINCT FROM r.current_submission_sequence OR NEW.submission_sequence IS DISTINCT FROM r.version+1) THEN
      RAISE EXCEPTION 'new approval plan requires a draft' USING ERRCODE = '23514';
    END IF;
  ELSE
    IF r.workflow_version IS DISTINCT FROM 1 OR
      ROW(NEW.id,NEW.organization_id,NEW.request_id,NEW.requester_id,NEW.step,NEW.approver_id,NEW.approver_role,NEW.submission_sequence)
      IS DISTINCT FROM
      ROW(OLD.id,OLD.organization_id,OLD.request_id,OLD.requester_id,OLD.step,OLD.approver_id,OLD.approver_role,OLD.submission_sequence)
      OR OLD.status <> 'pending' OR coalesce(OLD.submission_sequence,r.submission_sequence) IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence) THEN
      RAISE EXCEPTION 'approval plan and prior decisions are immutable' USING ERRCODE = '23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION guard_approval_projection() RETURNS trigger LANGUAGE plpgsql AS $$
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
        AND ((e.to_state IN ('REJECTED','WITHDRAWN') AND e.action IN ('reject','cancel'))
          OR (e.to_state='NEEDS_INFO' AND e.action='request_changes' AND EXISTS (
            SELECT 1 FROM request_change_requests c WHERE c.organization_id=a.organization_id
              AND c.request_id=a.request_id AND c.event_sequence=e.sequence
              AND c.submission_sequence=coalesce(a.submission_sequence,r.submission_sequence))))) THEN
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
CREATE OR REPLACE FUNCTION guard_decision_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; a approvals; e request_events;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  SELECT * INTO a FROM approvals WHERE organization_id=NEW.organization_id AND id=NEW.approval_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id
    AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  IF r.workflow_version IS DISTINCT FROM 1 OR a.status <> 'pending' OR coalesce(a.submission_sequence,r.submission_sequence) IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence)
    OR (a.approver_id IS NOT NULL AND a.approver_id <> NEW.actor_id)
    OR NOT workflow_candidate_eligible(NEW.organization_id, NEW.approval_id, NEW.actor_id)
    OR e.sequence IS DISTINCT FROM r.version OR e.to_state IS DISTINCT FROM r.status
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR e.reason IS DISTINCT FROM NEW.reason
    OR e.at IS DISTINCT FROM NEW.at OR e.action IS DISTINCT FROM
      (CASE NEW.outcome WHEN 'approved' THEN 'approve' ELSE 'reject' END)
    OR e.from_state IS DISTINCT FROM (CASE a.approver_role WHEN 'manager' THEN 'MANAGER_REVIEW'::request_status_enum
      ELSE 'FINANCE_REVIEW'::request_status_enum END)
    OR EXISTS (SELECT 1 FROM approvals prev WHERE prev.organization_id=a.organization_id
      AND prev.request_id=a.request_id AND coalesce(prev.submission_sequence,r.submission_sequence)=coalesce(a.submission_sequence,r.submission_sequence) AND prev.step<a.step AND prev.status <> 'approved') THEN
    RAISE EXCEPTION 'decision lacks current eligibility or matching history' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION guard_receipt_insert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM request_events e WHERE e.organization_id=NEW.organization_id
    AND e.request_id=NEW.request_id AND e.sequence=NEW.version AND e.actor_id=NEW.actor_id
    AND e.to_state=NEW.status AND (e.action=NEW.action OR (NEW.action IN ('submit','resubmit') AND e.action='route')))
    OR (NEW.action IN ('approve','reject')) <> (NEW.decision_id IS NOT NULL)
    OR (NEW.decision_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM approval_decisions d
      WHERE d.organization_id=NEW.organization_id AND d.id=NEW.decision_id
        AND d.actor_id=NEW.actor_id AND d.request_id=NEW.request_id AND d.event_sequence=NEW.version)) THEN
    RAISE EXCEPTION 'receipt must reference the recorded outcome' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION guard_frozen_fields() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests;
BEGIN
  IF TG_OP='INSERT' THEN
    SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  ELSE
    SELECT * INTO r FROM requests WHERE organization_id=OLD.organization_id AND id=OLD.request_id FOR UPDATE;
  END IF;
  IF r.type IN ('expense','leave') AND r.status NOT IN ('DRAFT','NEEDS_INFO') AND
     (r.workflow_version=1 OR TG_OP <> 'INSERT') THEN
    RAISE EXCEPTION 'submitted fields are frozen' USING ERRCODE='23514';
  END IF;
  IF r.status='NEEDS_INFO' AND (TG_OP <> 'UPDATE' OR r.current_submission_sequence IS DISTINCT FROM r.version+1) THEN
    RAISE EXCEPTION 'field replacement requires resubmission' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND ROW(OLD.organization_id,OLD.request_id) IS DISTINCT FROM ROW(NEW.organization_id,NEW.request_id) THEN
    RAISE EXCEPTION 'field identity is immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION guard_workflow_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed BOOLEAN;
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.workflow_version=1 AND (NEW.version <> 1 OR NEW.status <>
       CASE NEW.type WHEN 'service' THEN 'SUBMITTED'::request_status_enum ELSE 'DRAFT'::request_status_enum END
       OR NEW.submission_sequence IS NOT NULL OR NEW.approval_policy_id IS NOT NULL
       OR NEW.current_submission_sequence IS NOT NULL OR NEW.proposed_revision_id IS NOT NULL OR NEW.assigned_to IS NOT NULL OR NEW.processed_by IS NOT NULL
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
        NEW.completed_at,NEW.processed_by,NEW.processing_role,NEW.processing_reference,NEW.current_submission_sequence,NEW.proposed_revision_id)
    IS DISTINCT FROM ROW(OLD.status,OLD.version,OLD.approval_policy_id,OLD.submission_sequence,OLD.approved_at,
        OLD.completed_at,OLD.processed_by,OLD.processing_role,OLD.processing_reference,OLD.current_submission_sequence,OLD.proposed_revision_id) THEN
    RAISE EXCEPTION 'legacy approval evidence requires validation; mutation blocked' USING ERRCODE='23514';
  END IF;
  IF OLD.type IN ('expense','leave') AND OLD.status <> 'DRAFT' AND
    ROW(NEW.title,NEW.raw_text,NEW.department_id,NEW.submission_sequence)
    IS DISTINCT FROM ROW(OLD.title,OLD.raw_text,OLD.department_id,OLD.submission_sequence) THEN
    RAISE EXCEPTION 'submitted authoritative fields are frozen' USING ERRCODE='23514';
  END IF;
  IF OLD.type IN ('expense','leave') AND NEW.raw_text IS DISTINCT FROM OLD.raw_text THEN
    RAISE EXCEPTION 'original intake is immutable' USING ERRCODE='23514';
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
    (NEW.approval_policy_id IS DISTINCT FROM OLD.approval_policy_id AND OLD.status NOT IN ('DRAFT','NEEDS_INFO')) OR
    (NEW.submission_sequence IS DISTINCT FROM OLD.submission_sequence AND OLD.status <> 'DRAFT')) THEN
    RAISE EXCEPTION 'evidence changes require their transition' USING ERRCODE='23514';
  END IF;
  IF (NEW.current_submission_sequence IS DISTINCT FROM OLD.current_submission_sequence
        OR NEW.approval_policy_id IS DISTINCT FROM OLD.approval_policy_id
        OR NEW.leave_overlap IS DISTINCT FROM OLD.leave_overlap) AND NOT coalesce((
        OLD.type IN ('expense','leave') AND OLD.status IN ('DRAFT','NEEDS_INFO')
        AND NEW.current_submission_sequence=OLD.version+1),false) THEN
    RAISE EXCEPTION 'submission projection changes require a new submission' USING ERRCODE='23514';
  END IF;
  IF NEW.proposed_revision_id IS DISTINCT FROM OLD.proposed_revision_id AND NOT coalesce((
      OLD.status='NEEDS_INFO' AND ((NEW.status='NEEDS_INFO' AND NEW.version=OLD.version+1 AND NEW.proposed_revision_id IS NOT NULL)
        OR (NEW.current_submission_sequence=OLD.version+1 AND NEW.proposed_revision_id IS NULL))),false) THEN
    RAISE EXCEPTION 'proposal pointer requires revision or resubmission' USING ERRCODE='23514';
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
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('FINANCE_REVIEW','APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR
        (OLD.status='FINANCE_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR
        (OLD.status='NEEDS_INFO' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR (OLD.status='APPROVED' AND NEW.status='COMPLETED')
      WHEN 'leave' THEN
        (OLD.status='DRAFT' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR
        (OLD.status='SUBMITTED' AND NEW.status IN ('MANAGER_REVIEW','WITHDRAWN')) OR
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR (OLD.status='NEEDS_INFO' AND NEW.status IN ('SUBMITTED','WITHDRAWN'))
      ELSE false END;
    IF NOT allowed OR NEW.version <> OLD.version+1 THEN
      RAISE EXCEPTION 'invalid workflow edge or version' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.version IS DISTINCT FROM OLD.version THEN
    IF NOT (OLD.type IN ('expense','leave') AND OLD.status='NEEDS_INFO' AND NEW.version=OLD.version+1
       AND NEW.proposed_revision_id IS DISTINCT FROM OLD.proposed_revision_id AND NEW.proposed_revision_id IS NOT NULL) THEN
    RAISE EXCEPTION 'version requires a state transition' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION require_workflow_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; f request_fields; p approval_policies; e request_events;
        expected_steps INTEGER; actor UUID; required_action TEXT; candidate_count INTEGER;
BEGIN
  IF NEW.workflow_version IS DISTINCT FROM 1 THEN RETURN NULL; END IF;
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id
    AND request_id=NEW.id AND sequence=NEW.version;
  IF TG_OP='UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    actor := e.actor_id;
    required_action := CASE NEW.status WHEN 'SUBMITTED' THEN CASE OLD.status WHEN 'NEEDS_INFO' THEN 'resubmit' ELSE 'submit' END WHEN 'NEEDS_INFO' THEN 'request_changes' WHEN 'TRIAGED' THEN 'triage'
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
    IF required_action IN ('submit','resubmit','route') OR (required_action='cancel' AND
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
      WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)) THEN
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
        AND se.sequence=coalesce(r.current_submission_sequence,r.submission_sequence) AND se.from_state IN ('DRAFT','NEEDS_INFO') AND se.to_state='SUBMITTED'
        AND se.actor_id=r.created_by AND se.action IN ('submit','resubmit'))
    OR NOT EXISTS (SELECT 1 FROM request_events se WHERE se.organization_id=r.organization_id AND se.request_id=r.id
        AND se.sequence=coalesce(r.current_submission_sequence,r.submission_sequence)+1 AND se.from_state='SUBMITTED' AND se.to_state='MANAGER_REVIEW'
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
  IF (SELECT count(*) FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)) <> expected_steps
    OR NOT EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
      AND a.step=1 AND a.approver_role='manager') OR (expected_steps=2 AND NOT EXISTS (
        SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
          AND a.step=2 AND a.approver_role='finance'))
    OR EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
      AND NOT EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=a.organization_id AND c.approval_id=a.id)) THEN
    RAISE EXCEPTION 'complete policy-matching candidate plan required' USING ERRCODE='23514';
  END IF;
  -- Validate routing snapshots when submission occurs, not after candidate roles later change.
  IF TG_OP='UPDATE' AND OLD.status IN ('DRAFT','NEEDS_INFO') AND NEW.status='SUBMITTED' THEN
    IF NOT EXISTS (SELECT 1 FROM active_approval_policies ap WHERE ap.organization_id=r.organization_id
      AND ap.request_type=r.type AND ap.policy_id=r.approval_policy_id) THEN
      RAISE EXCEPTION 'submission must use the explicitly selected policy' USING ERRCODE='23514';
    END IF;
    IF EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=r.organization_id AND c.request_id=r.id AND EXISTS (SELECT 1 FROM approvals ca WHERE ca.organization_id=c.organization_id AND ca.id=c.approval_id
      AND coalesce(ca.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence))
      AND NOT workflow_candidate_eligible(c.organization_id,c.approval_id,c.user_id)) THEN
      RAISE EXCEPTION 'submission candidates must currently qualify' USING ERRCODE='23514';
    END IF;
    SELECT count(*) INTO candidate_count FROM employee_managers m JOIN users u
      ON u.organization_id=m.organization_id AND u.id=m.manager_id JOIN role_assignments ra
      ON ra.organization_id=m.organization_id AND ra.user_id=m.manager_id AND ra.role='manager'
      WHERE m.organization_id=r.organization_id AND m.employee_id=r.created_by AND u.status='active'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now();
    IF candidate_count>0 AND EXISTS (SELECT 1 FROM approval_candidates c WHERE c.organization_id=r.organization_id
      AND c.request_id=r.id AND EXISTS (SELECT 1 FROM approvals ca WHERE ca.organization_id=c.organization_id AND ca.id=c.approval_id
        AND coalesce(ca.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)) AND c.required_role='manager' AND c.routing_source<>'employee_manager') THEN
      RAISE EXCEPTION 'explicit manager has precedence' USING ERRCODE='23514';
    END IF;
  END IF;
  IF NEW.current_submission_sequence IS DISTINCT FROM OLD.current_submission_sequence AND NOT EXISTS (
      SELECT 1 FROM request_submissions rs JOIN request_revisions rv ON rv.organization_id=rs.organization_id AND rv.request_id=rs.request_id AND rv.id=rs.revision_id
      WHERE rs.organization_id=r.organization_id AND rs.request_id=r.id AND rs.sequence=NEW.current_submission_sequence
        AND rs.policy_id=NEW.approval_policy_id AND rv.fields=f.fields AND rs.leave_overlap=NEW.leave_overlap) THEN
    RAISE EXCEPTION 'new projection requires immutable submitted snapshot' USING ERRCODE='23514';
  END IF;
  IF EXISTS (SELECT 1 FROM request_submissions bound JOIN request_revisions snapshot
      ON snapshot.organization_id=bound.organization_id AND snapshot.request_id=bound.request_id AND snapshot.id=bound.revision_id
      WHERE bound.organization_id=r.organization_id AND bound.request_id=r.id
        AND bound.sequence=coalesce(r.current_submission_sequence,r.submission_sequence)
        AND (bound.policy_id IS DISTINCT FROM r.approval_policy_id OR snapshot.fields IS DISTINCT FROM f.fields
          OR bound.leave_overlap IS DISTINCT FROM r.leave_overlap)) THEN
    RAISE EXCEPTION 'current projection must match its immutable submission' USING ERRCODE='23514';
  END IF;
  IF r.status='NEEDS_INFO' AND (NOT EXISTS (SELECT 1 FROM request_change_requests c WHERE c.organization_id=r.organization_id AND c.request_id=r.id AND c.submission_sequence=coalesce(r.current_submission_sequence,r.submission_sequence)) OR EXISTS (
    SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.status='pending')) THEN
    RAISE EXCEPTION 'NEEDS_INFO requires correction evidence and closure' USING ERRCODE='23514';
  END IF;
  IF NEW.status=OLD.status AND NEW.version IS DISTINCT FROM OLD.version THEN
    IF e.action <> 'revise' OR e.actor_id IS DISTINCT FROM r.created_by OR NOT EXISTS (
      SELECT 1 FROM request_revisions rv WHERE rv.organization_id=r.organization_id AND rv.request_id=r.id
        AND rv.id=NEW.proposed_revision_id AND rv.event_sequence=NEW.version AND rv.kind='proposed') THEN
      RAISE EXCEPTION 'same-state revision requires matching evidence' USING ERRCODE='23514';
    END IF;
  END IF;
  IF r.status='MANAGER_REVIEW' AND EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id
    AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.status<>'pending') THEN
    RAISE EXCEPTION 'manager review requires pending steps' USING ERRCODE='23514';
  END IF;
  IF r.status='FINANCE_REVIEW' AND (expected_steps<>2 OR NOT EXISTS (SELECT 1 FROM approvals a
    WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.step=1 AND a.status='approved')
    OR NOT EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
      AND a.step=2 AND a.status='pending')) THEN
    RAISE EXCEPTION 'finance review requires manager decision' USING ERRCODE='23514';
  END IF;
  IF r.status IN ('APPROVED','COMPLETED') AND (r.approved_at IS NULL OR NOT EXISTS (
    SELECT 1 FROM approval_decisions d JOIN approvals a ON a.organization_id=d.organization_id AND a.id=d.approval_id
      WHERE d.organization_id=r.organization_id AND d.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.step=expected_steps
        AND d.outcome='approved' AND d.at=r.approved_at) OR EXISTS (
    SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
      AND (a.status<>'approved' OR NOT EXISTS (SELECT 1 FROM approval_decisions d
        WHERE d.organization_id=a.organization_id AND d.approval_id=a.id AND d.outcome='approved')))) THEN
    RAISE EXCEPTION 'final approval requires all immutable decisions' USING ERRCODE='23514';
  END IF;
  IF r.status='REJECTED' AND (NOT EXISTS (SELECT 1 FROM approval_decisions d WHERE d.organization_id=r.organization_id
    AND d.request_id=r.id AND d.outcome='rejected' AND EXISTS (
      SELECT 1 FROM approvals acted WHERE acted.organization_id=d.organization_id AND acted.id=d.approval_id
        AND coalesce(acted.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence))) OR EXISTS (SELECT 1 FROM approvals a WHERE a.organization_id=r.organization_id
    AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.status='pending')) THEN
    RAISE EXCEPTION 'rejection requires decision and closure' USING ERRCODE='23514';
  END IF;
  IF r.status='WITHDRAWN' AND (r.approved_at IS NOT NULL OR EXISTS (SELECT 1 FROM approvals a
    WHERE a.organization_id=r.organization_id AND a.request_id=r.id AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND a.status='pending')) THEN
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
CREATE FUNCTION validate_revision_fields(kind request_type_enum, fields JSONB) RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF fields->>'type' IS DISTINCT FROM kind::text THEN RETURN false; END IF;
  IF kind='expense' THEN
    RETURN fields - ARRAY['type','vendor','amount','currency','purpose'] = '{}'::jsonb
      AND jsonb_typeof(fields->'amount')='string'
      AND (fields->>'amount') ~ '^[0-9]{1,16}(\.[0-9]{1,2})?$'
      AND (fields->>'amount')::numeric > 0 AND fields->>'currency'='PKR'
      AND jsonb_typeof(fields->'vendor')='string' AND jsonb_typeof(fields->'purpose')='string'
      AND length(btrim(fields->>'vendor')) BETWEEN 1 AND 200
      AND length(btrim(fields->>'purpose')) BETWEEN 1 AND 20000;
  ELSIF kind='leave' THEN
    RETURN fields - ARRAY['type','start_date','end_date','leave_type'] = '{}'::jsonb
      AND (fields->>'start_date') ~ '^\d{4}-\d{2}-\d{2}$'
      AND (fields->>'end_date') ~ '^\d{4}-\d{2}-\d{2}$'
      AND (fields->>'start_date')::date <= (fields->>'end_date')::date
      AND jsonb_typeof(fields->'leave_type')='string'
      AND length(btrim(fields->>'leave_type')) BETWEEN 1 AND 200;
  END IF;
  RETURN false;
EXCEPTION WHEN invalid_text_representation OR datetime_field_overflow OR invalid_datetime_format THEN RETURN false;
END $$;
-- statement-break
CREATE FUNCTION guard_revision_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events; c request_change_requests; rs request_submissions; prev request_revisions;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  IF r.workflow_version IS DISTINCT FROM 1 OR NOT coalesce(validate_revision_fields(r.type,NEW.fields),false)
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR e.at IS DISTINCT FROM NEW.at OR btrim(e.reason)=''
    OR NOT EXISTS (SELECT 1 FROM users u JOIN role_assignments ra ON ra.organization_id=u.organization_id AND ra.user_id=u.id
      WHERE u.organization_id=r.organization_id AND u.id=NEW.actor_id AND u.status='active'
        AND ra.revoked_at IS NULL AND ra.granted_at<=now()) THEN
    RAISE EXCEPTION 'revision lacks valid fields and matching actor/time evidence' USING ERRCODE='23514';
  END IF;
  IF NEW.kind='proposed' THEN
    SELECT * INTO c FROM request_change_requests WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND event_sequence=NEW.change_sequence;
    SELECT * INTO rs FROM request_submissions WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=c.submission_sequence;
    SELECT * INTO prev FROM request_revisions WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND id=NEW.predecessor_id;
    IF e.action<>'revise' OR e.from_state<>'NEEDS_INFO' OR e.to_state<>'NEEDS_INFO'
      OR NEW.event_sequence IS DISTINCT FROM r.version OR r.status<>'NEEDS_INFO'
      OR r.proposed_revision_id IS DISTINCT FROM NEW.id
      OR NEW.actor_id<>r.created_by OR length(btrim(NEW.clarification)) NOT BETWEEN 1 AND 20000
      OR c.event_sequence IS NULL OR NEW.event_sequence<=c.event_sequence OR prev.id IS NULL
      OR NOT ((prev.kind='proposed' AND prev.change_sequence=c.event_sequence) OR prev.id=rs.revision_id)
      OR EXISTS (SELECT 1 FROM request_revisions later WHERE later.organization_id=NEW.organization_id AND later.request_id=NEW.request_id
        AND later.kind='proposed' AND later.change_sequence=c.event_sequence
        AND later.event_sequence>prev.event_sequence AND later.event_sequence<NEW.event_sequence)
      OR ROW(prev.fields,prev.clarification) IS NOT DISTINCT FROM ROW(NEW.fields,NEW.clarification)
      OR NOT EXISTS (SELECT 1 FROM request_events re WHERE re.organization_id=r.organization_id AND re.request_id=r.id
        AND re.sequence=NEW.event_sequence-1 AND re.to_state='NEEDS_INFO') THEN
      RAISE EXCEPTION 'proposal requires current correction and latest predecessor' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.kind='submitted' THEN
    IF e.action<>'submit' OR e.from_state<>'DRAFT' OR e.to_state<>'SUBMITTED' OR NEW.actor_id<>r.created_by
      OR NEW.event_sequence IS DISTINCT FROM r.submission_sequence
      OR r.current_submission_sequence IS DISTINCT FROM NEW.event_sequence
      OR NEW.predecessor_id IS NOT NULL OR NEW.change_sequence IS NOT NULL OR NEW.clarification<>'' THEN
      RAISE EXCEPTION 'initial snapshot requires submission evidence' USING ERRCODE='23514';
    END IF;
  ELSE
    IF e.action<>'request_changes' OR e.to_state<>'NEEDS_INFO' OR NEW.predecessor_id IS NOT NULL
      OR NEW.event_sequence IS DISTINCT FROM r.version OR r.status<>'NEEDS_INFO'
      OR NEW.change_sequence IS NOT NULL OR NEW.clarification<>'' OR NOT EXISTS (
        SELECT 1 FROM request_submissions bound WHERE bound.organization_id=r.organization_id AND bound.request_id=r.id
          AND bound.sequence=r.submission_sequence AND bound.revision_id=NEW.id) THEN
      RAISE EXCEPTION 'capture requires original submission and correction evidence' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER revision_evidence_required AFTER INSERT ON request_revisions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_revision_evidence();
-- statement-break
CREATE FUNCTION guard_submission_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events; route request_events; rv request_revisions; f request_fields; p approval_policies;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.sequence;
  SELECT * INTO route FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.routing_sequence;
  SELECT * INTO rv FROM request_revisions WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND id=NEW.revision_id;
  SELECT * INTO f FROM request_fields WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id;
  SELECT * INTO p FROM approval_policies WHERE organization_id=NEW.organization_id AND id=NEW.policy_id;
  IF r.workflow_version IS DISTINCT FROM 1 OR NEW.sequence IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence)
    OR e.actor_id IS DISTINCT FROM r.created_by OR route.actor_id IS DISTINCT FROM r.created_by
    OR e.to_state<>'SUBMITTED' OR route.from_state<>'SUBMITTED' OR route.to_state<>'MANAGER_REVIEW' OR route.action<>'route'
    OR p.request_type IS DISTINCT FROM r.type OR rv.id IS NULL OR NOT coalesce(validate_revision_fields(r.type,rv.fields),false)
    OR NEW.policy_id IS DISTINCT FROM r.approval_policy_id OR rv.fields IS DISTINCT FROM f.fields OR NEW.leave_overlap IS DISTINCT FROM r.leave_overlap THEN
    RAISE EXCEPTION 'submission must bind trusted fields policy and history' USING ERRCODE='23514';
  END IF;
  IF e.action='submit' AND e.from_state='DRAFT' THEN
    IF NEW.sequence<>r.submission_sequence OR rv.kind NOT IN ('submitted','captured') THEN
      RAISE EXCEPTION 'original submission binding is invalid' USING ERRCODE='23514';
    END IF;
  ELSIF e.action='resubmit' AND e.from_state='NEEDS_INFO' THEN
    IF rv.kind<>'proposed' OR rv.actor_id<>r.created_by OR NOT EXISTS (
       SELECT 1 FROM request_change_requests c WHERE c.organization_id=r.organization_id AND c.request_id=r.id
        AND c.event_sequence=rv.change_sequence AND c.event_sequence<e.sequence)
      OR EXISTS (SELECT 1 FROM request_revisions later WHERE later.organization_id=r.organization_id AND later.request_id=r.id
        AND later.change_sequence=rv.change_sequence AND later.event_sequence>rv.event_sequence AND later.event_sequence<e.sequence)
      OR NOT EXISTS (SELECT 1 FROM request_events previous WHERE previous.organization_id=r.organization_id AND previous.request_id=r.id
        AND previous.sequence=e.sequence-1 AND previous.action='revise') THEN
      RAISE EXCEPTION 'resubmission requires latest proposed revision' USING ERRCODE='23514';
    END IF;
  ELSE RAISE EXCEPTION 'invalid submission event' USING ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER submission_evidence_required AFTER INSERT ON request_submissions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_submission_evidence();
-- statement-break
CREATE FUNCTION guard_change_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; a approvals; e request_events;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id;
  SELECT * INTO a FROM approvals WHERE organization_id=NEW.organization_id AND id=NEW.approval_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  IF r.workflow_version IS DISTINCT FROM 1 OR e.action<>'request_changes' OR e.to_state<>'NEEDS_INFO'
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR e.sequence IS DISTINCT FROM r.version
    OR NEW.submission_sequence IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence)
    OR NEW.submission_sequence IS DISTINCT FROM coalesce(a.submission_sequence,r.submission_sequence)
    OR NOT workflow_candidate_eligible(NEW.organization_id,NEW.approval_id,NEW.actor_id)
    OR e.from_state IS DISTINCT FROM (CASE a.approver_role WHEN 'manager' THEN 'MANAGER_REVIEW'::request_status_enum ELSE 'FINANCE_REVIEW'::request_status_enum END)
    OR a.status<>'cancelled' OR a.closed_event_sequence IS DISTINCT FROM e.sequence
    OR EXISTS (SELECT 1 FROM approval_decisions d WHERE d.organization_id=a.organization_id AND d.approval_id=a.id)
    OR EXISTS (SELECT 1 FROM approvals prev WHERE prev.organization_id=a.organization_id AND prev.request_id=a.request_id
      AND coalesce(prev.submission_sequence,r.submission_sequence)=NEW.submission_sequence AND prev.step<a.step AND prev.status<>'approved') THEN
    RAISE EXCEPTION 'correction requires current actionable candidate and closure' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER change_evidence_required AFTER INSERT ON request_change_requests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_change_evidence();
