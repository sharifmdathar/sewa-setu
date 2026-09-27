// RealApiClient (B7): fetch implementation of the exact ApiClient surface
// against API_BASE_URL. Server-side only. Maps non-2xx into a typed ApiError
// with a human-readable message so routes can feed ErrorState directly
// (AGENTS.md: never throw raw Response/any). Relative imports keep this
// runnable by vitest without path-alias config.

import type { ApiClient } from "./handlers";
import type {
    Application,
    CreateApplicationRequest,
    Decision,
    DecisionResult,
    Document,
    MetricsSummary,
    QueueItem,
    ScrutinyReport,
    Service,
    UploadDocumentRequest,
} from "./types";

/** Error carrying an HTTP status + safe message for ErrorState rendering. */
export class ApiError extends Error {
    readonly status: number;
    readonly url: string;
    readonly detail?: string;

    constructor(message: string, status: number, url: string, detail?: string) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.url = url;
        this.detail = detail;
    }
}

export interface RealApiClientOptions {
    baseUrl: string;
    /** Injectable for tests; defaults to global fetch. */
    fetchImpl?: typeof fetch;
    timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 10_000;

function statusMessage(status: number, path: string): string {
    if (status === 404) return `Not found: ${path}`;
    if (status === 400 || status === 422) return `Invalid request to ${path}.`;
    if (status >= 500) return `Server error (${status}) on ${path}. Please retry.`;
    return `Request to ${path} failed (HTTP ${status}).`;
}

export function createRealApiClient(opts: RealApiClientOptions): ApiClient {
    const base = opts.baseUrl.replace(/\/+$/, "");
    const doFetch = opts.fetchImpl ?? globalThis.fetch;
    const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;

    async function request<T>(
        method: "GET" | "POST",
        path: string,
        body?: unknown,
    ): Promise<T> {
        const url = `${base}${path}`;
        let res: Response;
        try {
            res = await doFetch(url, {
                method,
                headers: body !== undefined ? { "content-type": "application/json" } : undefined,
                body: body !== undefined ? JSON.stringify(body) : undefined,
                signal: AbortSignal.timeout(timeoutMs),
                cache: "no-store",
            });
        } catch (err) {
            // Network failure / abort -> ErrorState-friendly, never rethrow unknown.
            const reason = err instanceof Error ? err.message : "network error";
            throw new ApiError(`Could not reach the server (${reason}).`, 0, url);
        }
        if (!res.ok) {
            const text = await res.text().catch(() => "");
            throw new ApiError(statusMessage(res.status, path), res.status, url, text || undefined);
        }
        if (res.status === 204) return undefined as T;
        return (await res.json()) as T;
    }

    return {
        listServices: () => request<Service[]>("GET", "/services"),
        createApplication: (req: CreateApplicationRequest) =>
            request<Application>("POST", "/applications", req),
        getApplication: (id: string) =>
            request<Application>("GET", `/applications/${encodeURIComponent(id)}`),
        uploadDocument: (applicationId: string, req: UploadDocumentRequest) =>
            request<Document>(
                "POST",
                `/applications/${encodeURIComponent(applicationId)}/documents`,
                req,
            ),
        runScrutiny: (applicationId: string) =>
            request<ScrutinyReport>(
                "POST",
                `/applications/${encodeURIComponent(applicationId)}/scrutiny/run`,
            ),
        // Contract: GET scrutiny returns 404 when not run yet -> undefined (not throw).
        getScrutiny: async (applicationId: string) => {
            try {
                return await request<ScrutinyReport>(
                    "GET",
                    `/applications/${encodeURIComponent(applicationId)}/scrutiny`,
                );
            } catch (err) {
                if (err instanceof ApiError && err.status === 404) return undefined;
                throw err;
            }
        },
        getQueue: () => request<QueueItem[]>("GET", "/officer/queue"),
        postDecision: (decision: Decision) =>
            request<DecisionResult>("POST", "/officer/decisions", decision),
        getMetrics: () => request<MetricsSummary>("GET", "/metrics/summary"),
    };
}
