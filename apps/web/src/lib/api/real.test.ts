import { describe, expect, it, vi } from "vitest";
import { ApiError, createRealApiClient } from "./real";
import type { Service } from "./types";

// Minimal Response-like stub — real.ts only reads ok/status/json/text.
function response(status: number, body: unknown) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
        text: async () => JSON.stringify(body),
    } as unknown as Response;
}

const BASE = "http://api.test";

// Vitest infers mock.calls' tuple type from the implementation's parameters,
// so the fakes below declare (url, init) explicitly.
type FakeFetch = (url: string, init: RequestInit) => Promise<Response>;

function clientFor(impl: FakeFetch) {
    const fetchMock = vi.fn(impl);
    const api = createRealApiClient({
        baseUrl: BASE,
        fetchImpl: fetchMock as unknown as typeof fetch,
    });
    return { api, fetchMock };
}

describe("createRealApiClient", () => {
    it("listServices: GETs /services and parses the array (happy path)", async () => {
        const services: Service[] = [
            { id: "svc-1", name: "Income Certificate", requiredDocTypes: ["id_proof"] },
        ];
        const { api, fetchMock } = clientFor(async () => response(200, services));

        const out = await api.listServices();

        expect(out).toEqual(services);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe(`${BASE}/services`);
        expect(init.method).toBe("GET");
    });

    it("getApplication: maps a 404 into a typed ApiError (the 404 path)", async () => {
        const { api } = clientFor(async () => response(404, { detail: "no such app" }));

        let caught: unknown;
        try {
            await api.getApplication("app-9999");
        } catch (err) {
            caught = err;
        }

        expect(caught).toBeInstanceOf(ApiError);
        const e = caught as ApiError;
        expect(e.status).toBe(404);
        expect(e.message).toContain("/applications/app-9999");
        expect(e.detail).toContain("no such app");
    });

    it("getScrutiny: returns undefined on 404 (contract 'not run yet', not an error)", async () => {
        const { api } = clientFor(async () => response(404, {}));
        await expect(api.getScrutiny("app-1")).resolves.toBeUndefined();
    });

    it("createApplication: POSTs a JSON body to /applications", async () => {
        const created = { id: "app-1", serviceId: "svc-1", status: "submitted" };
        const { api, fetchMock } = clientFor(async () => response(201, created));

        const out = await api.createApplication({ serviceId: "svc-1", applicantFields: { a: 1 } });

        expect(out).toEqual(created);
        const [, init] = fetchMock.mock.calls[0];
        expect(init.method).toBe("POST");
        expect(JSON.parse(String(init.body))).toEqual({ serviceId: "svc-1", applicantFields: { a: 1 } });
        expect((init.headers as Record<string, string>)["content-type"]).toBe("application/json");
    });
});

describe("createRealApiClient — remaining endpoints + error mapping", () => {
    it("getQueue: GETs /officer/queue and parses the array", async () => {
        const queue = [{ applicationId: "app-1", serviceId: "svc-1", status: "scrutiny_done", riskScore: 62, updatedAt: "2026-09-20T10:00:00Z" }];
        const { api, fetchMock } = clientFor(async () => response(200, queue));
        await expect(api.getQueue()).resolves.toEqual(queue);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe(`${BASE}/officer/queue`);
        expect(init.method).toBe("GET");
    });

    it("getMetrics: GETs /metrics/summary and parses the object", async () => {
        const metrics = { applicationsTotal: 8, pending: 7, decided: 1, avgScrutinySeconds: 4.4, flagRate: 0.33, generatedAt: "2026-09-27T12:00:00Z" };
        const { api } = clientFor(async () => response(200, metrics));
        await expect(api.getMetrics()).resolves.toEqual(metrics);
    });

    it("postDecision: POSTs the decision body to /officer/decisions", async () => {
        const result = { applicationId: "app-1", status: "decided" };
        const { api, fetchMock } = clientFor(async () => response(200, result));
        const out = await api.postDecision({ applicationId: "app-1", decision: "approve", officerNotes: "ok" });
        expect(out).toEqual(result);
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe(`${BASE}/officer/decisions`);
        expect(init.method).toBe("POST");
        expect(JSON.parse(String(init.body))).toEqual({ applicationId: "app-1", decision: "approve", officerNotes: "ok" });
    });

    it("uploadDocument: POSTs to the id-encoded /applications/{id}/documents", async () => {
        const doc = { id: "doc-1", docType: "id_proof", fileName: "a.txt", uploadedAt: "2026-09-27T12:00:00Z", sha256: "x" };
        const { api, fetchMock } = clientFor(async () => response(201, doc));
        await expect(api.uploadDocument("app 1", { docType: "id_proof", fileName: "a.txt", contentBase64: "eHk=" })).resolves.toEqual(doc);
        const [url] = fetchMock.mock.calls[0];
        expect(url).toBe(`${BASE}/applications/app%201/documents`);
    });

    it("runScrutiny: POSTs with no body to /applications/{id}/scrutiny/run", async () => {
        const report = { applicationId: "app-1", generatedAt: "2026-09-27T12:00:00Z", extractedFields: {}, checks: [], riskScore: 10, recommendation: "approve", modelMeta: {} };
        const { api, fetchMock } = clientFor(async () => response(200, report));
        await api.runScrutiny("app-1");
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe(`${BASE}/applications/app-1/scrutiny/run`);
        expect(init.method).toBe("POST");
        expect(init.body).toBeUndefined();
    });

    it("maps a network failure into ApiError(status 0) with a friendly message", async () => {
        const { api } = clientFor(async () => {
            throw new Error("boom");
        });
        let caught: unknown;
        try {
            await api.getMetrics();
        } catch (e) {
            caught = e;
        }
        expect(caught).toBeInstanceOf(ApiError);
        const e = caught as ApiError;
        expect(e.status).toBe(0);
        expect(e.message).toContain("Could not reach the server");
    });

    it("maps a 5xx into a retryable ApiError message", async () => {
        const { api } = clientFor(async () => response(503, { detail: "down" }));
        await expect(api.getQueue()).rejects.toThrow(/Server error \(503\)/);
    });
});
