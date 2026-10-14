// Generated from FastAPI OpenAPI. Run make contracts; do not edit.
export interface paths {
    "/approvals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Approvals */
        get: operations["list_approvals"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["current_user"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["get_health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["get_readiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Requests */
        get: operations["list_requests"];
        put?: never;
        /** Create Request */
        post: operations["create_request"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Request */
        get: operations["get_request"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Request Lifecycle */
        get: operations["list_request_lifecycle"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Request Revisions */
        get: operations["list_request_revisions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/requests/{request_id}/transitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Transition Request
         * @description Typed action. Idempotency-Key binds actor, request and canonical payload. Exact retries return the original compact outcome and currently authorized detail.
         */
        post: operations["transition_request"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reversals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Reversals */
        get: operations["list_reversals"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** ApprovalPage */
        ApprovalPage: {
            /** Items */
            items: components["schemas"]["ApprovalRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** ApprovalRead */
        ApprovalRead: {
            approver_role: components["schemas"]["Role"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Status */
            status: string;
            /** Step */
            step: number;
        };
        /** Approve */
        Approve: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "approve";
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** ApproveReversal */
        ApproveReversal: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "approve_reversal";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Reversal Request Id
             * Format: uuid
             */
            reversal_request_id: string;
        };
        /** Assign */
        Assign: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "assign";
            /**
             * Assignee Id
             * Format: uuid
             */
            assignee_id: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** AuthRead */
        AuthRead: {
            /** Csrf Token */
            csrf_token: string;
            /**
             * Session Expires At
             * Format: date-time
             */
            session_expires_at: string;
            user: components["schemas"]["UserRead"];
        };
        /** Cancel */
        Cancel: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "cancel";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** ChangeRequestRead */
        ChangeRequestRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Event Sequence */
            event_sequence: number;
            required_role: components["schemas"]["Role"];
            /** Submission Sequence */
            submission_sequence: number;
        };
        /** Close */
        Close: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "close";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** CreateCorrection */
        CreateCorrection: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "create_correction";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Reversal Request Id
             * Format: uuid
             */
            reversal_request_id: string;
        };
        /** DecisionRead */
        DecisionRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Event Sequence */
            event_sequence: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Outcome */
            outcome: string;
            /** Reason */
            reason: string;
            required_role: components["schemas"]["Role"];
        };
        /** DependencyChecks */
        DependencyChecks: {
            /**
             * Database
             * @enum {string}
             */
            database: "ok" | "unavailable";
            /**
             * Migrations
             * @enum {string}
             */
            migrations: "ok" | "unavailable";
            /**
             * Redis
             * @enum {string}
             */
            redis: "ok" | "unavailable";
        };
        /** ExpenseSubmission */
        ExpenseSubmission: {
            /** Amount */
            amount: string;
            /**
             * Currency
             * @constant
             */
            currency: "PKR";
            /** Purpose */
            purpose: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "expense";
            /** Vendor */
            vendor: string;
        };
        /** Health */
        Health: {
            /**
             * Status
             * @constant
             */
            status: "ok";
        };
        /** LeaveSubmission */
        LeaveSubmission: {
            /**
             * End Date
             * Format: date
             */
            end_date: string;
            /** Leave Type */
            leave_type: string;
            /**
             * Start Date
             * Format: date
             */
            start_date: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "leave";
        };
        /** LifecyclePage */
        LifecyclePage: {
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Reopenings */
            reopenings: components["schemas"]["ServiceReopeningRead"][];
            /** Resolutions */
            resolutions: components["schemas"]["ServiceResolutionRead"][];
            /** Reversal Decisions */
            reversal_decisions: components["schemas"]["ReversalDecisionRead"][];
            /** Reversal Requests */
            reversal_requests: components["schemas"]["ReversalRequestRead"][];
        };
        /** Login */
        Login: {
            /** Email */
            email: string;
            /**
             * Password
             * Format: password
             */
            password: string;
        };
        /** Process */
        Process: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "process";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /** Reference */
            reference: string;
        };
        /** Readiness */
        Readiness: {
            checks: components["schemas"]["DependencyChecks"];
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "not_ready";
        };
        /** Reject */
        Reject: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "reject";
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** RejectReversal */
        RejectReversal: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "reject_reversal";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Reversal Request Id
             * Format: uuid
             */
            reversal_request_id: string;
        };
        /** Reopen */
        Reopen: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "reopen";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /** Resolution Id */
            resolution_id?: string | null;
        };
        /** RequestChanges */
        RequestChanges: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "request_changes";
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** RequestCreate */
        RequestCreate: {
            /**
             * Department Id
             * Format: uuid
             */
            department_id: string;
            /** Raw Text */
            raw_text: string;
            /** Title */
            title: string;
            type: components["schemas"]["RequestType"];
        };
        /** RequestDetail */
        RequestDetail: {
            active_reversal?: components["schemas"]["ReversalRequestRead"] | null;
            /** Approval Policy Id */
            approval_policy_id?: string | null;
            /** Approvals */
            approvals?: components["schemas"]["StepRead"][];
            /** Approved At */
            approved_at?: string | null;
            /** Assigned To */
            assigned_to?: string | null;
            /** Completed At */
            completed_at?: string | null;
            correction?: components["schemas"]["ChangeRequestRead"] | null;
            /** Correction Source Id */
            correction_source_id?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            current_resolution?: components["schemas"]["ServiceResolutionRead"] | null;
            /** Current Submission Sequence */
            current_submission_sequence?: number | null;
            /**
             * Department Id
             * Format: uuid
             */
            department_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Leave Overlap
             * @default false
             */
            leave_overlap: boolean;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Processed By */
            processed_by?: string | null;
            /** Processing Reference */
            processing_reference?: string | null;
            proposed_revision?: components["schemas"]["RevisionRead"] | null;
            /** Raw Text */
            raw_text: string;
            /** Replacement Request Id */
            replacement_request_id?: string | null;
            /** Resolution */
            resolution?: string | null;
            reversal_decision?: components["schemas"]["ReversalDecisionRead"] | null;
            /** Service Cycle Sequence */
            service_cycle_sequence?: number | null;
            status: components["schemas"]["RequestStatus"];
            /** Status History */
            status_history: components["schemas"]["StatusHistoryRead"][];
            /** Structured Fields */
            structured_fields?: {
                [key: string]: unknown;
            } | null;
            /** Title */
            title: string;
            type: components["schemas"]["RequestType"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** RequestPage */
        RequestPage: {
            /** Items */
            items: components["schemas"]["RequestRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** RequestRead */
        RequestRead: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Department Id
             * Format: uuid
             */
            department_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Raw Text */
            raw_text: string;
            status: components["schemas"]["RequestStatus"];
            /** Title */
            title: string;
            type: components["schemas"]["RequestType"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** RequestReversal */
        RequestReversal: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "request_reversal";
            /** Expected Version */
            expected_version: number;
            /**
             * Intent
             * @enum {string}
             */
            intent: "withdraw" | "correct";
            /** Reason */
            reason: string;
        };
        /**
         * RequestStatus
         * @enum {string}
         */
        RequestStatus: "DRAFT" | "SUBMITTED" | "TRIAGED" | "ASSIGNED" | "IN_PROGRESS" | "RESOLVED" | "CLOSED" | "NEEDS_INFO" | "REOPENED" | "CANCELLED" | "MANAGER_REVIEW" | "FINANCE_REVIEW" | "APPROVED" | "COMPLETED" | "REVERSAL_REVIEW" | "REVERSED" | "REJECTED" | "WITHDRAWN";
        /**
         * RequestType
         * @enum {string}
         */
        RequestType: "service" | "expense" | "leave";
        /** Resolve */
        Resolve: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "resolve";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /** Resolution */
            resolution: string;
        };
        /** Resubmit */
        Resubmit: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "resubmit";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** ReversalDecisionRead */
        ReversalDecisionRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /** Event Sequence */
            event_sequence: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Organization Timezone */
            organization_timezone: string;
            /** Outcome */
            outcome: string;
            /**
             * Reversal Request Id
             * Format: uuid
             */
            reversal_request_id: string;
        };
        /** ReversalPage */
        ReversalPage: {
            /** Items */
            items: components["schemas"]["ReversalRequestRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** ReversalRequestRead */
        ReversalRequestRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /** Event Sequence */
            event_sequence: number;
            /**
             * Final Decision Id
             * Format: uuid
             */
            final_decision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Intent */
            intent: string;
            /** Organization Timezone */
            organization_timezone: string;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Submission Sequence */
            submission_sequence: number;
        };
        /** Revise */
        Revise: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "revise";
            /** Clarification */
            clarification: string;
            /** Data */
            data: components["schemas"]["ExpenseSubmission"] | components["schemas"]["LeaveSubmission"];
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** RevisionPage */
        RevisionPage: {
            /** Change Requests */
            change_requests: components["schemas"]["ChangeRequestRead"][];
            /** Items */
            items: components["schemas"]["RevisionRead"][];
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
            /** Submissions */
            submissions: components["schemas"]["SubmissionRead"][];
        };
        /** RevisionRead */
        RevisionRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Change Sequence */
            change_sequence: number | null;
            /** Clarification */
            clarification: string;
            /** Event Sequence */
            event_sequence: number;
            /** Fields */
            fields: {
                [key: string]: unknown;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            /** Predecessor Id */
            predecessor_id: string | null;
            /** Schema Version */
            schema_version: number;
        };
        /**
         * Role
         * @enum {string}
         */
        Role: "employee" | "manager" | "finance" | "admin";
        /** ServiceReopeningRead */
        ServiceReopeningRead: {
            /** Event Sequence */
            event_sequence: number;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Policy Id
             * Format: uuid
             */
            policy_id: string;
            /**
             * Resolution Id
             * Format: uuid
             */
            resolution_id: string;
        };
        /** ServiceResolutionRead */
        ServiceResolutionRead: {
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Body */
            body: string;
            /** Captured At */
            captured_at: string | null;
            /** Captured By */
            captured_by: string | null;
            /** Cycle Sequence */
            cycle_sequence: number;
            /** Event Sequence */
            event_sequence: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** Start */
        Start: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "start";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** StatusHistoryRead */
        StatusHistoryRead: {
            /** Action */
            action: string;
            /** Actor Id */
            actor_id: string | null;
            /**
             * At
             * Format: date-time
             */
            at: string;
            from_state: components["schemas"]["RequestStatus"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reason */
            reason: string;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Sequence */
            sequence: number;
            to_state: components["schemas"]["RequestStatus"];
        };
        /** StepRead */
        StepRead: {
            /** Approver Id */
            approver_id: string | null;
            approver_role: components["schemas"]["Role"];
            /** Candidates */
            candidates: string[];
            decision: components["schemas"]["DecisionRead"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
            /** Step */
            step: number;
        };
        /** SubmissionRead */
        SubmissionRead: {
            /** Approvals */
            approvals?: components["schemas"]["StepRead"][];
            /** Leave Overlap */
            leave_overlap: boolean;
            /** Policy Definition */
            policy_definition: {
                [key: string]: unknown;
            };
            /**
             * Policy Id
             * Format: uuid
             */
            policy_id: string;
            /** Policy Version */
            policy_version: number;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Routing Sequence */
            routing_sequence: number;
            /** Sequence */
            sequence: number;
        };
        /** Submit */
        Submit: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "submit";
            /** Data */
            data: components["schemas"]["ExpenseSubmission"] | components["schemas"]["LeaveSubmission"];
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** TransitionOutcome */
        TransitionOutcome: {
            /** Action */
            action: string;
            /** Decision Id */
            decision_id: string | null;
            /** Related Request Id */
            related_request_id?: string | null;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            status: components["schemas"]["RequestStatus"];
            /** Version */
            version: number;
        };
        /** TransitionRead */
        TransitionRead: {
            outcome: components["schemas"]["TransitionOutcome"];
            request: components["schemas"]["RequestDetail"];
        };
        /** Triage */
        Triage: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            action: "triage";
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
        };
        /** UserRead */
        UserRead: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Department Id */
            department_id: string | null;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Organization Id
             * Format: uuid
             */
            organization_id: string;
            /** Roles */
            roles: components["schemas"]["Role"][];
            status: components["schemas"]["UserStatus"];
        };
        /**
         * UserStatus
         * @enum {string}
         */
        UserStatus: "active" | "inactive";
        /**
         * WorkScope
         * @enum {string}
         */
        WorkScope: "mine" | "participant" | "assigned" | "triage" | "processing";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_approvals: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalPage"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Active organization role required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid pagination */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    login: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Login"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthRead"];
                };
            };
            /** @description Invalid or unavailable authentication */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Origin or CSRF check failed */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Login requires JSON */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Login temporarily rate limited */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Authentication temporarily unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    logout: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid or unavailable authentication */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Origin or CSRF check failed */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Authentication temporarily unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    current_user: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthRead"];
                };
            };
            /** @description Invalid or unavailable authentication */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Origin or CSRF check failed */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Authentication temporarily unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    get_health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    get_readiness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
            /** @description Dependencies or migrations unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
        };
    };
    list_requests: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                scope?: components["schemas"]["WorkScope"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RequestPage"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    create_request: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RequestCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RequestDetail"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Conflicting creation retry */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    get_request: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RequestDetail"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Request missing or not visible */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    list_request_lifecycle: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LifecyclePage"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Request missing or not visible */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    list_request_revisions: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionPage"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Request missing or not visible */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    transition_request: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Submit"] | components["schemas"]["Triage"] | components["schemas"]["Assign"] | components["schemas"]["Start"] | components["schemas"]["Resolve"] | components["schemas"]["Close"] | components["schemas"]["Approve"] | components["schemas"]["Reject"] | components["schemas"]["Process"] | components["schemas"]["Cancel"] | components["schemas"]["RequestChanges"] | components["schemas"]["Revise"] | components["schemas"]["Resubmit"] | components["schemas"]["RequestReversal"] | components["schemas"]["ApproveReversal"] | components["schemas"]["RejectReversal"] | components["schemas"]["CreateCorrection"] | components["schemas"]["Reopen"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransitionRead"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Requester or role restriction */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Request missing or not visible */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid edge, stale version, blocked plan or conflicting retry */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid input or unavailable department */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
    list_reversals: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReversalPage"];
                };
            };
            /** @description Verified active identity required */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Active organization role required */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
            /** @description Invalid pagination */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": {
                        /** Detail */
                        detail: string;
                        /** Status */
                        status: number;
                        /** Title */
                        title: string;
                        /**
                         * Type
                         * @default about:blank
                         */
                        type: string;
                    };
                };
            };
        };
    };
}
