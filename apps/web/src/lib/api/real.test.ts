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
