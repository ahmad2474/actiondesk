"""Synthetic actors/policies shared by unit adapters and migrated PostgreSQL tests."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.models import (
    ActiveApprovalPolicy,
    ApprovalPolicy,
    DepartmentManager,
    EmployeeManager,
    RoleAssignment,
    User,
)
from app.domain.identity import Principal
from app.domain.types import RequestType, Role
from app.schemas.core import RequestCreate, RequestDetail
from app.schemas.workflow import TransitionRead, transition_adapter
from app.services.requests import create_request
from app.services.transition_service import transition
from tests.unit.support import provision


@dataclass(frozen=True)
class World:
    engine: Engine
    owner: Principal
    department: UUID
    manager: Principal
    finance: Principal
    admin: Principal
    colleague: Principal
    foreign: Principal

    def create(self, kind: str = "expense") -> RequestDetail:
        with Session(self.engine) as session:
            return create_request(
                session,
                self.owner,
                RequestCreate(
                    department_id=self.department,
                    type=RequestType(kind),
                    title="Synthetic",
                    raw_text="Synthetic manual workflow",
                ),
                uuid4(),
            )

    def act(
        self,
        record: RequestDetail,
        actor: Principal,
        action: str,
        *,
        key: UUID | None = None,
        **data: object,
    ) -> TransitionRead:
        payload = transition_adapter.validate_python(
            {
                "action": action,
                "expected_version": record.version,
                "reason": "Synthetic reason",
                **data,
            }
        )
        with Session(self.engine) as session:
            return transition(
                session, actor, record.id, payload, payload.expected_version, key or uuid4()
            )

    def submit(self, kind: str = "expense", amount: str = "100.00") -> RequestDetail:
        record = self.create(kind)
        return self.act(record, self.owner, "submit", data=submission(kind, amount)).request


def submission(kind: str = "expense", amount: str = "100.00") -> dict[str, str]:
    if kind == "expense":
        return {
            "type": kind,
            "amount": amount,
            "currency": "PKR",
            "vendor": "Synthetic vendor",
            "purpose": "Synthetic purpose",
        }
    return {
        "type": kind,
        "start_date": "2026-11-01",
        "end_date": "2026-11-03",
        "leave_type": "annual",
    }


def add_actor(
    engine: Engine, owner: Principal, department: UUID, roles: tuple[Role, ...]
) -> Principal:
    actor = Principal(owner.organization_id, uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            User(
                id=actor.user_id,
                organization_id=actor.organization_id,
                department_id=department,
                name="Synthetic actor",
                email=f"{actor.user_id}@actiondesk.ahmad",
                status="active",
            )
        )
        session.flush()
        session.add_all(
            RoleAssignment(organization_id=actor.organization_id, user_id=actor.user_id, role=role)
            for role in roles
        )
    return actor


def build_world(engine: Engine) -> World:
    owner, department = provision(engine)
    manager = add_actor(engine, owner, department, (Role.EMPLOYEE, Role.MANAGER))
    finance = add_actor(engine, owner, department, (Role.EMPLOYEE, Role.FINANCE))
    admin = add_actor(engine, owner, department, (Role.EMPLOYEE, Role.ADMIN))
    colleague = add_actor(engine, owner, department, (Role.EMPLOYEE,))
    foreign, _ = provision(engine)
    with Session(engine) as session, session.begin():
        session.add(
            EmployeeManager(
                organization_id=owner.organization_id,
                employee_id=owner.user_id,
                manager_id=manager.user_id,
            )
        )
        session.add(
            DepartmentManager(
                organization_id=owner.organization_id,
                department_id=department,
                manager_id=manager.user_id,
            )
        )
        for kind in (RequestType.EXPENSE, RequestType.LEAVE):
            definition: dict[str, object] = {
                "schema_version": 1,
                "allow_department_fallback": False,
            }
            if kind == RequestType.EXPENSE:
                # Test fixture configuration, not a universal or seeded business threshold.
                definition.update(currency="PKR", finance_threshold="100.00")
            policy = ApprovalPolicy(
                id=uuid4(),
                organization_id=owner.organization_id,
                request_type=kind,
                name=f"test-{kind}",
                version=1,
                definition=definition,
            )
            session.add(policy)
            session.flush()
            session.add(
                ActiveApprovalPolicy(
                    organization_id=owner.organization_id, request_type=kind, policy_id=policy.id
                )
            )
    return World(engine, owner, department, manager, finance, admin, colleague, foreign)
