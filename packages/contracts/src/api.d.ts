// Generated from FastAPI OpenAPI. Run make contracts; do not edit.
export interface paths {
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
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
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
        /** Health */
        Health: {
            /**
             * Status
             * @constant
             */
            status: "ok";
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
        /** Readiness */
        Readiness: {
            checks: components["schemas"]["DependencyChecks"];
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "not_ready";
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
            /** Status History */
            status_history: components["schemas"]["StatusHistoryRead"][];
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
        /**
         * RequestStatus
         * @enum {string}
         */
        RequestStatus: "DRAFT" | "SUBMITTED" | "TRIAGED" | "ASSIGNED" | "IN_PROGRESS" | "RESOLVED" | "CLOSED" | "NEEDS_INFO" | "REOPENED" | "CANCELLED" | "MANAGER_REVIEW" | "FINANCE_REVIEW" | "APPROVED" | "COMPLETED" | "REJECTED" | "WITHDRAWN";
        /**
         * RequestType
         * @enum {string}
         */
        RequestType: "service" | "expense" | "leave";
        /**
         * Role
         * @enum {string}
         */
        Role: "employee" | "manager" | "finance" | "admin";
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
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
}
