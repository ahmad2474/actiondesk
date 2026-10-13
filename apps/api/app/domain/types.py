from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    FINANCE = "finance"
    ADMIN = "admin"


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
