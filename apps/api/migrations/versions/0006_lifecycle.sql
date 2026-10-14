ALTER TABLE requests ADD COLUMN active_reversal_id UUID, ADD COLUMN service_cycle_sequence INTEGER, ADD COLUMN latest_resolution_id UUID;
ALTER TABLE mutation_receipts ADD COLUMN related_request_id UUID;
ALTER TABLE mutation_receipts ADD FOREIGN KEY(organization_id,related_request_id) REFERENCES requests(organization_id,id);
ALTER TABLE request_revisions DROP CONSTRAINT revision_kind;
ALTER TABLE request_revisions ADD CONSTRAINT revision_kind CHECK(kind IN ('submitted','captured','proposed','approval_capture'));
-- statement-break
CREATE TABLE request_reversal_requests (
  request_id UUID NOT NULL,
  requester_id UUID NOT NULL,
  submission_sequence INTEGER NOT NULL,
  final_decision_id UUID NOT NULL,
  actor_id UUID NOT NULL,
  event_sequence INTEGER NOT NULL,
  intent VARCHAR(20) NOT NULL,
  organization_timezone VARCHAR(80) NOT NULL,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, request_id, id),
  UNIQUE (organization_id, request_id, event_sequence),
  FOREIGN KEY(organization_id, request_id, requester_id) REFERENCES requests (organization_id, id, created_by),
  FOREIGN KEY(organization_id, request_id, submission_sequence) REFERENCES request_submissions (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(organization_id, actor_id) REFERENCES users (organization_id, id),
  FOREIGN KEY(organization_id, final_decision_id) REFERENCES approval_decisions (organization_id, id),
  CONSTRAINT reversal_intent CHECK (intent IN ('withdraw','correct')),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
CREATE TABLE request_reversal_decisions (
  request_id UUID NOT NULL,
  reversal_request_id UUID NOT NULL,
  actor_id UUID NOT NULL,
  event_sequence INTEGER NOT NULL,
  outcome VARCHAR(20) NOT NULL,
  organization_timezone VARCHAR(80) NOT NULL,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, reversal_request_id),
  FOREIGN KEY(organization_id, request_id, reversal_request_id) REFERENCES request_reversal_requests (organization_id, request_id, id),
  FOREIGN KEY(organization_id, actor_id) REFERENCES users (organization_id, id),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  CONSTRAINT reversal_outcome CHECK (outcome IN ('accepted','denied')),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
CREATE TABLE request_correction_links (
  organization_id UUID NOT NULL,
  source_id UUID NOT NULL,
  child_id UUID NOT NULL,
  reversal_request_id UUID NOT NULL,
  event_sequence INTEGER NOT NULL,
  PRIMARY KEY (organization_id, source_id),
  FOREIGN KEY(organization_id, source_id, reversal_request_id) REFERENCES request_reversal_requests (organization_id, request_id, id),
  FOREIGN KEY(organization_id, child_id) REFERENCES requests (organization_id, id),
  FOREIGN KEY(organization_id, source_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  UNIQUE (organization_id, child_id),
  CONSTRAINT correction_not_self CHECK (child_id <> source_id)
)
-- statement-break
CREATE TABLE service_resolutions (
  request_id UUID NOT NULL,
  cycle_sequence INTEGER NOT NULL,
  event_sequence INTEGER NOT NULL,
  actor_id UUID NOT NULL,
  at TIMESTAMP WITH TIME ZONE NOT NULL,
  body TEXT NOT NULL,
  captured_by UUID,
  captured_at TIMESTAMP WITH TIME ZONE,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, request_id, id),
  UNIQUE (organization_id, request_id, event_sequence),
  UNIQUE (organization_id, request_id, cycle_sequence),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, request_id, cycle_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, actor_id) REFERENCES users (organization_id, id),
  FOREIGN KEY(organization_id, captured_by) REFERENCES users (organization_id, id),
  CONSTRAINT resolution_body_length CHECK (length(btrim(body)) BETWEEN 1 AND 20000),
  CONSTRAINT resolution_capture_pair CHECK ((captured_at IS NULL) = (captured_by IS NULL)),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
CREATE TABLE service_reopen_policies (
  name VARCHAR(120) NOT NULL,
  version INTEGER NOT NULL,
  definition JSONB NOT NULL,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, name, version),
  CONSTRAINT positive_reopen_policy_version CHECK (version > 0),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
CREATE TABLE active_service_reopen_policies (
  organization_id UUID NOT NULL,
  policy_id UUID NOT NULL,
  PRIMARY KEY (organization_id),
  FOREIGN KEY(organization_id, policy_id) REFERENCES service_reopen_policies (organization_id, id)
)
-- statement-break
CREATE TABLE service_reopenings (
  request_id UUID NOT NULL,
  resolution_id UUID NOT NULL,
  event_sequence INTEGER NOT NULL,
  policy_id UUID NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  id UUID NOT NULL,
  organization_id UUID NOT NULL,
  PRIMARY KEY (id),
  UNIQUE (organization_id, request_id, event_sequence),
  UNIQUE (organization_id, resolution_id),
  FOREIGN KEY(organization_id, request_id, resolution_id) REFERENCES service_resolutions (organization_id, request_id, id),
  FOREIGN KEY(organization_id, request_id, event_sequence) REFERENCES request_events (organization_id, request_id, sequence),
  FOREIGN KEY(organization_id, policy_id) REFERENCES service_reopen_policies (organization_id, id),
  FOREIGN KEY(organization_id) REFERENCES organizations (id)
)
-- statement-break
ALTER TABLE requests ADD CONSTRAINT fk_active_reversal FOREIGN KEY(organization_id, id, active_reversal_id) REFERENCES request_reversal_requests (organization_id, request_id, id) DEFERRABLE INITIALLY DEFERRED
-- statement-break
ALTER TABLE requests ADD CONSTRAINT fk_latest_resolution FOREIGN KEY(organization_id, id, latest_resolution_id) REFERENCES service_resolutions (organization_id, request_id, id) DEFERRABLE INITIALLY DEFERRED
-- statement-break
ALTER TABLE requests ADD CONSTRAINT fk_service_cycle FOREIGN KEY(organization_id, id, service_cycle_sequence) REFERENCES request_events (organization_id, request_id, sequence) DEFERRABLE INITIALLY DEFERRED
-- statement-break
CREATE TRIGGER immutable_request_reversal_requests BEFORE UPDATE OR DELETE ON request_reversal_requests FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_request_reversal_decisions BEFORE UPDATE OR DELETE ON request_reversal_decisions FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_request_correction_links BEFORE UPDATE OR DELETE ON request_correction_links FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_service_resolutions BEFORE UPDATE OR DELETE ON service_resolutions FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_service_reopen_policies BEFORE UPDATE OR DELETE ON service_reopen_policies FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE TRIGGER immutable_service_reopenings BEFORE UPDATE OR DELETE ON service_reopenings FOR EACH ROW EXECUTE FUNCTION reject_workflow_evidence_mutation();
-- statement-break
CREATE OR REPLACE FUNCTION guard_workflow_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE allowed BOOLEAN;
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.workflow_version=1 AND (NEW.version <> 1 OR NEW.status <>
       CASE NEW.type WHEN 'service' THEN 'SUBMITTED'::request_status_enum ELSE 'DRAFT'::request_status_enum END
       OR NEW.submission_sequence IS NOT NULL OR NEW.approval_policy_id IS NOT NULL
       OR NEW.active_reversal_id IS NOT NULL OR NEW.service_cycle_sequence IS NOT NULL OR NEW.latest_resolution_id IS NOT NULL OR NEW.current_submission_sequence IS NOT NULL OR NEW.proposed_revision_id IS NOT NULL OR NEW.assigned_to IS NOT NULL OR NEW.processed_by IS NOT NULL
       OR NEW.approved_at IS NOT NULL OR NEW.completed_at IS NOT NULL) THEN
      RAISE EXCEPTION 'managed request must begin at its initial state' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
  END IF;
  IF ROW(NEW.id,NEW.organization_id,NEW.type,NEW.created_by,NEW.workflow_version)
     IS DISTINCT FROM ROW(OLD.id,OLD.organization_id,OLD.type,OLD.created_by,OLD.workflow_version) THEN
    RAISE EXCEPTION 'request identity and workflow provenance are immutable' USING ERRCODE='23514';
  END IF;
  IF OLD.workflow_version IS DISTINCT FROM 1 AND (NEW.status IN ('REOPENED','REVERSAL_REVIEW','REVERSED')
    OR NEW.active_reversal_id IS DISTINCT FROM OLD.active_reversal_id
    OR NEW.service_cycle_sequence IS DISTINCT FROM OLD.service_cycle_sequence
    OR NEW.latest_resolution_id IS DISTINCT FROM OLD.latest_resolution_id) THEN
    RAISE EXCEPTION 'unvalidated legacy lifecycle mutation is blocked' USING ERRCODE='23514';
  END IF;
  IF OLD.type IN ('expense','leave') AND OLD.workflow_version IS NULL AND
    ROW(NEW.status,NEW.version,NEW.approval_policy_id,NEW.submission_sequence,NEW.approved_at,
        NEW.completed_at,NEW.processed_by,NEW.processing_role,NEW.processing_reference,NEW.current_submission_sequence,NEW.proposed_revision_id,NEW.active_reversal_id,NEW.service_cycle_sequence,NEW.latest_resolution_id)
    IS DISTINCT FROM ROW(OLD.status,OLD.version,OLD.approval_policy_id,OLD.submission_sequence,OLD.approved_at,
        OLD.completed_at,OLD.processed_by,OLD.processing_role,OLD.processing_reference,OLD.current_submission_sequence,OLD.proposed_revision_id,OLD.active_reversal_id,OLD.service_cycle_sequence,OLD.latest_resolution_id) THEN
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
    (OLD.type='service' AND OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED' AND (OLD.resolution IS NULL OR OLD.workflow_version IS NULL)) THEN
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
  IF NEW.follow_up_to_id IS DISTINCT FROM OLD.follow_up_to_id THEN
    RAISE EXCEPTION 'correction provenance is immutable' USING ERRCODE='23514';
  END IF;
  IF NEW.active_reversal_id IS DISTINCT FROM OLD.active_reversal_id AND NOT (
      OLD.type IN ('expense','leave') AND OLD.status='APPROVED' AND NEW.status='REVERSAL_REVIEW'
      AND NEW.version=OLD.version+1 AND NEW.active_reversal_id IS NOT NULL) THEN
    RAISE EXCEPTION 'reversal pointer requires its transition' USING ERRCODE='23514';
  END IF;
  IF NEW.service_cycle_sequence IS DISTINCT FROM OLD.service_cycle_sequence AND NOT coalesce((
      OLD.type='service' AND ((OLD.status='ASSIGNED' AND NEW.status='IN_PROGRESS' AND NEW.service_cycle_sequence=NEW.version)
        OR (OLD.status='RESOLVED' AND NEW.status='REOPENED' AND NEW.service_cycle_sequence=NEW.version)
        OR (OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED' AND OLD.service_cycle_sequence IS NULL))),false) THEN
    RAISE EXCEPTION 'service cycle requires its transition' USING ERRCODE='23514';
  END IF;
  IF NEW.latest_resolution_id IS DISTINCT FROM OLD.latest_resolution_id AND NOT coalesce((OLD.type='service' AND
      ((OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED') OR (OLD.status='RESOLVED' AND NEW.status='REOPENED'))),false) THEN
    RAISE EXCEPTION 'resolution pointer requires resolve or trusted reopening capture' USING ERRCODE='23514';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    allowed := CASE OLD.type
      WHEN 'service' THEN
        (OLD.status='SUBMITTED' AND NEW.status IN ('TRIAGED','CANCELLED')) OR
        (OLD.status='TRIAGED' AND NEW.status IN ('ASSIGNED','CANCELLED')) OR
        (OLD.status='ASSIGNED' AND NEW.status IN ('IN_PROGRESS','CANCELLED')) OR
        (OLD.status='IN_PROGRESS' AND NEW.status='RESOLVED') OR
        (OLD.status='RESOLVED' AND NEW.status IN ('CLOSED','REOPENED')) OR (OLD.status='REOPENED' AND NEW.status='IN_PROGRESS')
      WHEN 'expense' THEN
        (OLD.status='DRAFT' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR
        (OLD.status='SUBMITTED' AND NEW.status IN ('MANAGER_REVIEW','WITHDRAWN')) OR
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('FINANCE_REVIEW','APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR
        (OLD.status='FINANCE_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR
        (OLD.status='NEEDS_INFO' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR (OLD.status='APPROVED' AND NEW.status IN ('COMPLETED','REVERSAL_REVIEW')) OR (OLD.status='REVERSAL_REVIEW' AND NEW.status IN ('APPROVED','REVERSED'))
      WHEN 'leave' THEN
        (OLD.status='DRAFT' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR
        (OLD.status='SUBMITTED' AND NEW.status IN ('MANAGER_REVIEW','WITHDRAWN')) OR
        (OLD.status='MANAGER_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','WITHDRAWN','NEEDS_INFO')) OR (OLD.status='NEEDS_INFO' AND NEW.status IN ('SUBMITTED','WITHDRAWN')) OR (OLD.status='APPROVED' AND NEW.status='REVERSAL_REVIEW') OR (OLD.status='REVERSAL_REVIEW' AND NEW.status IN ('APPROVED','REVERSED'))
      ELSE false END;
    IF NOT allowed OR NEW.version <> OLD.version+1 THEN
      RAISE EXCEPTION 'invalid workflow edge or version' USING ERRCODE='23514';
    END IF;
  ELSIF NEW.version IS DISTINCT FROM OLD.version THEN
    IF NOT ((OLD.type IN ('expense','leave') AND OLD.status='REVERSED' AND NEW.version=OLD.version+1) OR (OLD.type IN ('expense','leave') AND OLD.status='NEEDS_INFO' AND NEW.version=OLD.version+1
       AND NEW.proposed_revision_id IS DISTINCT FROM OLD.proposed_revision_id AND NEW.proposed_revision_id IS NOT NULL)) THEN
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
      WHEN 'REJECTED' THEN 'reject' WHEN 'APPROVED' THEN CASE OLD.status WHEN 'REVERSAL_REVIEW' THEN 'reject_reversal' ELSE 'approve' END WHEN 'REVERSAL_REVIEW' THEN 'request_reversal' WHEN 'REVERSED' THEN 'approve_reversal' WHEN 'REOPENED' THEN 'reopen' WHEN 'COMPLETED' THEN 'process'
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
    IF (NEW.status<>'REVERSED' OR e.action<>'create_correction') AND (e.action <> 'revise' OR e.actor_id IS DISTINCT FROM r.created_by OR NOT EXISTS (
      SELECT 1 FROM request_revisions rv WHERE rv.organization_id=r.organization_id AND rv.request_id=r.id
        AND rv.id=NEW.proposed_revision_id AND rv.event_sequence=NEW.version AND rv.kind='proposed')) THEN
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
  IF r.status IN ('APPROVED','COMPLETED','REVERSAL_REVIEW','REVERSED') AND (r.approved_at IS NULL OR NOT EXISTS (
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
CREATE OR REPLACE FUNCTION guard_revision_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
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
    IF NOT ((NEW.kind='captured' AND e.action='request_changes' AND e.to_state='NEEDS_INFO') OR (NEW.kind='approval_capture' AND e.action='request_reversal' AND e.to_state='REVERSAL_REVIEW')) OR NEW.predecessor_id IS NOT NULL
      OR NEW.event_sequence IS DISTINCT FROM r.version OR r.status NOT IN ('NEEDS_INFO','REVERSAL_REVIEW')
      OR NEW.change_sequence IS NOT NULL OR NEW.clarification<>'' OR NOT EXISTS (
        SELECT 1 FROM request_submissions bound WHERE bound.organization_id=r.organization_id AND bound.request_id=r.id
          AND bound.sequence=r.submission_sequence AND bound.revision_id=NEW.id) THEN
      RAISE EXCEPTION 'capture requires original submission and correction evidence' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE OR REPLACE FUNCTION guard_submission_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
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
    IF NEW.sequence<>r.submission_sequence OR rv.kind NOT IN ('submitted','captured','approval_capture') THEN
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
  IF (NEW.action='create_correction') <> (NEW.related_request_id IS NOT NULL) OR
    (NEW.related_request_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM request_correction_links c
      WHERE c.organization_id=NEW.organization_id AND c.source_id=NEW.request_id
        AND c.child_id=NEW.related_request_id AND c.event_sequence=NEW.version)) THEN
    RAISE EXCEPTION 'correction receipt requires its unique child link' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
-- statement-break
CREATE FUNCTION lifecycle_final_candidate(org UUID, request UUID, actor UUID) RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT 1 FROM requests r JOIN approvals a ON a.organization_id=r.organization_id AND a.request_id=r.id
    JOIN approval_decisions d ON d.organization_id=a.organization_id AND d.approval_id=a.id
    WHERE r.organization_id=org AND r.id=request AND a.status='approved' AND d.outcome='approved'
      AND coalesce(a.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence)
      AND NOT EXISTS (SELECT 1 FROM approvals later WHERE later.organization_id=a.organization_id AND later.request_id=a.request_id
        AND coalesce(later.submission_sequence,r.submission_sequence)=coalesce(r.current_submission_sequence,r.submission_sequence) AND later.step>a.step)
      AND d.at=r.approved_at AND workflow_candidate_eligible(org,a.id,actor))
$$;
-- statement-break
CREATE FUNCTION lifecycle_reversal_boundary(org UUID, request UUID, operation_time TIMESTAMPTZ) RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE r requests; o organizations; f request_fields;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=org AND id=request;
  IF r.type NOT IN ('expense','leave') OR r.workflow_version IS DISTINCT FROM 1 OR r.processed_by IS NOT NULL
    OR r.completed_at IS NOT NULL OR r.processing_role IS NOT NULL OR r.processing_reference IS NOT NULL THEN RETURN false; END IF;
  IF r.type='expense' THEN RETURN true; END IF;
  SELECT * INTO o FROM organizations WHERE id=org;
  SELECT * INTO f FROM request_fields WHERE organization_id=org AND request_id=request;
  IF NOT EXISTS (SELECT 1 FROM pg_timezone_names WHERE name=o.timezone)
    OR NOT coalesce(validate_revision_fields('leave',f.fields),false) THEN RETURN false; END IF;
  RETURN (operation_time AT TIME ZONE o.timezone)::date < (f.fields->>'start_date')::date
    AND (clock_timestamp() AT TIME ZONE o.timezone)::date < (f.fields->>'start_date')::date;
END $$;
-- statement-break
CREATE FUNCTION guard_reversal_request() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events; d approval_decisions; a approvals; o organizations;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  SELECT * INTO d FROM approval_decisions WHERE organization_id=NEW.organization_id AND id=NEW.final_decision_id;
  SELECT * INTO a FROM approvals WHERE organization_id=d.organization_id AND id=d.approval_id;
  SELECT * INTO o FROM organizations WHERE id=NEW.organization_id;
  IF r.status<>'REVERSAL_REVIEW' OR r.active_reversal_id IS DISTINCT FROM NEW.id OR e.sequence IS DISTINCT FROM r.version
    OR e.action IS DISTINCT FROM 'request_reversal' OR e.from_state IS DISTINCT FROM 'APPROVED' OR e.to_state IS DISTINCT FROM r.status
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR NEW.organization_timezone IS DISTINCT FROM o.timezone
    OR NEW.submission_sequence IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence)
    OR d.request_id IS DISTINCT FROM r.id OR d.outcome IS DISTINCT FROM 'approved' OR d.at IS DISTINCT FROM r.approved_at
    OR coalesce(a.submission_sequence,r.submission_sequence) IS DISTINCT FROM NEW.submission_sequence
    OR EXISTS (SELECT 1 FROM approvals later WHERE later.organization_id=r.organization_id AND later.request_id=r.id
      AND coalesce(later.submission_sequence,r.submission_sequence)=NEW.submission_sequence AND later.step>a.step)
    OR (NEW.actor_id<>r.created_by AND NOT lifecycle_final_candidate(NEW.organization_id,NEW.request_id,NEW.actor_id))
    OR NOT lifecycle_reversal_boundary(NEW.organization_id,NEW.request_id,e.at) THEN
    RAISE EXCEPTION 'reversal requires current approved source and current actor eligibility' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER reversal_request_evidence AFTER INSERT ON request_reversal_requests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_reversal_request();
-- statement-break
CREATE FUNCTION guard_reversal_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; q request_reversal_requests; e request_events; o organizations;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id FOR UPDATE;
  SELECT * INTO q FROM request_reversal_requests WHERE organization_id=NEW.organization_id AND id=NEW.reversal_request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  SELECT * INTO o FROM organizations WHERE id=NEW.organization_id;
  IF r.active_reversal_id IS DISTINCT FROM q.id OR q.request_id IS DISTINCT FROM r.id
    OR q.submission_sequence IS DISTINCT FROM coalesce(r.current_submission_sequence,r.submission_sequence)
    OR NEW.actor_id=r.created_by OR NEW.actor_id=q.actor_id OR NOT lifecycle_final_candidate(NEW.organization_id,NEW.request_id,NEW.actor_id)
    OR e.sequence IS DISTINCT FROM r.version OR e.actor_id IS DISTINCT FROM NEW.actor_id
    OR e.from_state IS DISTINCT FROM 'REVERSAL_REVIEW' OR e.to_state IS DISTINCT FROM r.status
    OR e.action IS DISTINCT FROM (CASE NEW.outcome WHEN 'accepted' THEN 'approve_reversal' ELSE 'reject_reversal' END)
    OR r.status IS DISTINCT FROM (CASE NEW.outcome WHEN 'accepted' THEN 'REVERSED'::request_status_enum ELSE 'APPROVED'::request_status_enum END)
    OR NEW.organization_timezone IS DISTINCT FROM o.timezone
    OR (NEW.outcome='accepted' AND NOT lifecycle_reversal_boundary(NEW.organization_id,NEW.request_id,e.at)) THEN
    RAISE EXCEPTION 'reversal decision requires independent current final-step candidate' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER reversal_decision_evidence AFTER INSERT ON request_reversal_decisions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_reversal_decision();
-- statement-break
CREATE FUNCTION guard_correction_link() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source requests; child requests; q request_reversal_requests; e request_events;
BEGIN
  SELECT * INTO source FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.source_id FOR UPDATE;
  SELECT * INTO child FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.child_id;
  SELECT * INTO q FROM request_reversal_requests WHERE organization_id=NEW.organization_id AND id=NEW.reversal_request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.source_id AND sequence=NEW.event_sequence;
  IF source.status<>'REVERSED' OR source.active_reversal_id IS DISTINCT FROM q.id OR q.intent<>'correct'
    OR source.processed_by IS NOT NULL OR source.completed_at IS NOT NULL
    OR NOT EXISTS (SELECT 1 FROM request_reversal_decisions d WHERE d.organization_id=NEW.organization_id AND d.reversal_request_id=q.id AND d.outcome='accepted')
    OR e.sequence IS DISTINCT FROM source.version OR e.action IS DISTINCT FROM 'create_correction'
    OR e.actor_id IS DISTINCT FROM source.created_by OR e.from_state IS DISTINCT FROM 'REVERSED' OR e.to_state IS DISTINCT FROM 'REVERSED'
    OR child.follow_up_to_id IS DISTINCT FROM source.id OR child.created_by IS DISTINCT FROM source.created_by
    OR child.type IS DISTINCT FROM source.type OR child.department_id IS DISTINCT FROM source.department_id
    OR child.raw_text IS DISTINCT FROM source.raw_text OR child.title IS DISTINCT FROM source.title OR child.due_at IS DISTINCT FROM source.due_at
    OR child.status IS DISTINCT FROM 'DRAFT' OR child.version<>1 OR child.workflow_version IS DISTINCT FROM 1
    OR child.approved_at IS NOT NULL OR child.current_submission_sequence IS NOT NULL OR child.approval_policy_id IS NOT NULL
    OR NOT EXISTS (SELECT 1 FROM request_events ce WHERE ce.organization_id=NEW.organization_id AND ce.request_id=child.id
      AND ce.sequence=1 AND ce.action='created' AND ce.to_state='DRAFT' AND ce.actor_id=source.created_by AND ce.at=e.at) THEN
    RAISE EXCEPTION 'correction link requires a unique new draft of accepted correction reversal' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER correction_link_evidence AFTER INSERT ON request_correction_links
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_correction_link();
-- statement-break
CREATE FUNCTION guard_service_resolution() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events; cycle request_events;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  SELECT * INTO cycle FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.cycle_sequence;
  IF r.type<>'service' OR r.workflow_version IS DISTINCT FROM 1 OR e.action IS DISTINCT FROM 'resolve'
    OR e.from_state IS DISTINCT FROM 'IN_PROGRESS' OR e.to_state IS DISTINCT FROM 'RESOLVED'
    OR e.actor_id IS DISTINCT FROM NEW.actor_id OR NEW.actor_id IS DISTINCT FROM r.assigned_to OR e.at IS DISTINCT FROM NEW.at
    OR cycle.action NOT IN ('start','reopen') OR NEW.cycle_sequence>=NEW.event_sequence
    OR (NEW.captured_at IS NULL AND (r.latest_resolution_id IS DISTINCT FROM NEW.id OR r.service_cycle_sequence IS DISTINCT FROM NEW.cycle_sequence
      OR r.status<>'RESOLVED' OR r.version<>NEW.event_sequence))
    OR (NEW.captured_at IS NOT NULL AND (r.resolution IS DISTINCT FROM NEW.body OR cycle.action<>'start'
      OR NOT EXISTS (SELECT 1 FROM service_reopenings sr JOIN request_events re ON re.organization_id=sr.organization_id
        AND re.request_id=sr.request_id AND re.sequence=sr.event_sequence WHERE sr.organization_id=NEW.organization_id
          AND sr.request_id=NEW.request_id AND sr.resolution_id=NEW.id AND re.actor_id=NEW.captured_by AND re.at=NEW.captured_at))) THEN
    RAISE EXCEPTION 'service resolution requires actual cycle, actor and resolution evidence' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER service_resolution_evidence AFTER INSERT ON service_resolutions
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_service_resolution();
-- statement-break
CREATE FUNCTION guard_service_reopening() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events; resolution service_resolutions; p service_reopen_policies;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.request_id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.request_id AND sequence=NEW.event_sequence;
  SELECT * INTO resolution FROM service_resolutions WHERE organization_id=NEW.organization_id AND id=NEW.resolution_id;
  SELECT * INTO p FROM service_reopen_policies WHERE organization_id=NEW.organization_id AND id=NEW.policy_id;
  IF r.workflow_version IS DISTINCT FROM 1 OR r.type<>'service' OR r.status<>'REOPENED' OR r.completed_at IS NOT NULL
    OR r.service_cycle_sequence IS DISTINCT FROM NEW.event_sequence OR r.latest_resolution_id IS DISTINCT FROM resolution.id
    OR r.version<>NEW.event_sequence OR e.action IS DISTINCT FROM 'reopen' OR e.from_state IS DISTINCT FROM 'RESOLVED' OR e.to_state IS DISTINCT FROM 'REOPENED'
    OR e.sequence<>resolution.event_sequence+1
    OR p.definition->>'schema_version' IS DISTINCT FROM '1' OR jsonb_typeof(p.definition->'window_seconds') IS DISTINCT FROM 'number'
    OR (p.definition->>'window_seconds') !~ '^[0-9]+$' OR (p.definition->>'window_seconds')::numeric NOT BETWEEN 3600 AND 2592000
    OR NEW.expires_at IS DISTINCT FROM resolution.at + (p.definition->>'window_seconds')::integer * interval '1 second'
    OR e.at<resolution.at OR e.at>NEW.expires_at OR clock_timestamp()>NEW.expires_at
    OR NOT EXISTS (SELECT 1 FROM active_service_reopen_policies ap WHERE ap.organization_id=NEW.organization_id AND ap.policy_id=NEW.policy_id)
    OR NOT (e.actor_id=r.created_by OR EXISTS (SELECT 1 FROM role_assignments ra WHERE ra.organization_id=NEW.organization_id AND ra.user_id=e.actor_id
      AND ra.revoked_at IS NULL AND ra.granted_at<=now() AND (ra.role='admin' OR (ra.role='manager' AND EXISTS (
        SELECT 1 FROM department_managers dm WHERE dm.organization_id=NEW.organization_id AND dm.department_id=r.department_id AND dm.manager_id=e.actor_id))))) THEN
    RAISE EXCEPTION 'reopening requires current resolution, authorized actor and explicit valid window' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM users u JOIN role_assignments ra ON ra.organization_id=u.organization_id AND ra.user_id=u.id
    WHERE u.organization_id=r.organization_id AND u.id=r.assigned_to AND u.department_id=r.department_id AND u.status='active'
      AND ra.revoked_at IS NULL AND ra.granted_at<=now()) THEN
    RAISE EXCEPTION 'retained assignee must remain valid' USING ERRCODE='23514';
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER service_reopening_evidence AFTER INSERT ON service_reopenings
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION guard_service_reopening();
-- statement-break
CREATE FUNCTION require_lifecycle_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r requests; e request_events;
BEGIN
  SELECT * INTO r FROM requests WHERE organization_id=NEW.organization_id AND id=NEW.id;
  SELECT * INTO e FROM request_events WHERE organization_id=NEW.organization_id AND request_id=NEW.id AND sequence=NEW.version;
  IF TG_OP='INSERT' THEN
    IF NEW.follow_up_to_id IS NOT NULL AND NEW.workflow_version=1 AND NOT EXISTS (SELECT 1 FROM request_correction_links c
      WHERE c.organization_id=NEW.organization_id AND c.child_id=NEW.id AND c.source_id=NEW.follow_up_to_id) THEN
      RAISE EXCEPTION 'new correction provenance requires its immutable link' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
  END IF;
  IF NEW.status='REVERSAL_REVIEW' AND NOT EXISTS (SELECT 1 FROM request_reversal_requests q WHERE q.organization_id=NEW.organization_id
    AND q.request_id=NEW.id AND q.id=NEW.active_reversal_id AND q.event_sequence=NEW.version) AND OLD.status<>NEW.status THEN
    RAISE EXCEPTION 'reversal hold requires immutable request evidence' USING ERRCODE='23514';
  END IF;
  IF OLD.status='REVERSAL_REVIEW' AND NEW.status IN ('APPROVED','REVERSED') AND NOT EXISTS (SELECT 1 FROM request_reversal_decisions d
    WHERE d.organization_id=NEW.organization_id AND d.request_id=NEW.id AND d.reversal_request_id=NEW.active_reversal_id AND d.event_sequence=NEW.version) THEN
    RAISE EXCEPTION 'reversal outcome requires immutable decision evidence' USING ERRCODE='23514';
  END IF;
  IF NEW.status=OLD.status AND NEW.version<>OLD.version AND NEW.status='REVERSED' AND NOT EXISTS (
    SELECT 1 FROM request_correction_links c WHERE c.organization_id=NEW.organization_id AND c.source_id=NEW.id AND c.event_sequence=NEW.version) THEN
    RAISE EXCEPTION 'correction self-edge requires child evidence' USING ERRCODE='23514';
  END IF;
  IF NEW.type='service' AND NEW.workflow_version=1 THEN
    IF OLD.status='RESOLVED' AND NEW.status='REOPENED' AND NOT EXISTS (SELECT 1 FROM service_reopenings sr
      WHERE sr.organization_id=NEW.organization_id AND sr.request_id=NEW.id AND sr.event_sequence=NEW.version) THEN
      RAISE EXCEPTION 'reopening requires immutable evidence' USING ERRCODE='23514';
    END IF;
    IF NEW.status IN ('RESOLVED','CLOSED') AND NEW.service_cycle_sequence IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM service_resolutions resolution WHERE resolution.organization_id=NEW.organization_id AND resolution.request_id=NEW.id
        AND resolution.id=NEW.latest_resolution_id AND resolution.cycle_sequence=NEW.service_cycle_sequence
        AND ((NEW.status='RESOLVED' AND resolution.event_sequence=NEW.version) OR NEW.status='CLOSED')) THEN
      RAISE EXCEPTION 'resolution/closure requires the current cycle resolution' USING ERRCODE='23514';
    END IF;
    IF OLD.status='REOPENED' AND NEW.status='IN_PROGRESS' AND NOT EXISTS (SELECT 1 FROM users u JOIN role_assignments ra
      ON ra.organization_id=u.organization_id AND ra.user_id=u.id WHERE u.organization_id=NEW.organization_id AND u.id=NEW.assigned_to
        AND u.department_id=NEW.department_id AND u.status='active' AND ra.revoked_at IS NULL AND ra.granted_at<=now()) THEN
      RAISE EXCEPTION 'restart requires retained valid assignee' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NULL;
END $$;
-- statement-break
CREATE CONSTRAINT TRIGGER lifecycle_evidence_required AFTER INSERT OR UPDATE ON requests
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION require_lifecycle_evidence();
