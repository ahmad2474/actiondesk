from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    FINANCE = "finance"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RequestType(StrEnum):
    SERVICE = "service"
    EXPENSE = "expense"
    LEAVE = "leave"


class RequestStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    TRIAGED = "TRIAGED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    NEEDS_INFO = "NEEDS_INFO"
    REOPENED = "REOPENED"
    CANCELLED = "CANCELLED"
    MANAGER_REVIEW = "MANAGER_REVIEW"
    FINANCE_REVIEW = "FINANCE_REVIEW"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


# Creation is the only operation in milestone 1. Existing historical states stay intact.
def initial_request_status(request_type: RequestType) -> RequestStatus:
    return RequestStatus.SUBMITTED if request_type == RequestType.SERVICE else RequestStatus.DRAFT
