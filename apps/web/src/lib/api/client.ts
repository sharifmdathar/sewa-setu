// ApiClient factory. Server-side only: import from server components /
// route handlers, never from client components (AGENTS.md: ApiClient only).
//
// Env: API_MODE = "mock" | "real" (default "mock"); API_BASE_URL = pipeline
// API base (used from B7/RealApiClient onwards). See apps/web/.env.example.

import type { ApiClient, ApiHandlers } from "./handlers";
import { createMockHandlers } from "./mock";

export type ApiMode = "mock" | "real";

export function apiMode(): ApiMode {
  return process.env.API_MODE === "real" ? "real" : "mock";
}

export function apiBaseUrl(): string {
  return process.env.API_BASE_URL ?? "http://localhost:8000";
}

function buildHandlers(): ApiHandlers {
  const mode = apiMode();
  if (mode === "mock") return createMockHandlers();
  // "real" transport (fetch-based RealApiClient) is prompt B7's scope.
  // Until then we fail loudly rather than silently serving mocks in real mode.
  throw new Error(
    'API_MODE=real requires the RealApiClient (Track B prompt B7, not yet built). Set API_MODE=mock.',
  );
}

function fromHandlers(h: ApiHandlers): ApiClient {
  return {
    listServices: () => Promise.resolve(h.listServices()),
    createApplication: (req) => Promise.resolve(h.createApplication(req)),
    getApplication: (id) => Promise.resolve(h.getApplication(id)),
    uploadDocument: (appId, req) => Promise.resolve(h.uploadDocument(appId, req)),
    runScrutiny: (appId) => Promise.resolve(h.runScrutiny(appId)),
    getScrutiny: (appId) => Promise.resolve(h.getScrutiny(appId)),
    getQueue: () => Promise.resolve(h.getQueue()),
    postDecision: (d) => Promise.resolve(h.postDecision(d)),
    getMetrics: () => Promise.resolve(h.getMetrics()),
  };
}

// Single client per server process so MockApiClient's in-memory store persists
// across calls. On `next dev` the server module registry is reset on every
// recompile, which would wipe a plain module-level `let` and lose writes
// between a server action and the page it redirects to. We therefore cache the
// client on globalThis (the same pattern Next recommends for DB connections).
type GlobalStore = { __sewaApiClient?: ApiClient };
const g = globalThis as unknown as GlobalStore;

export function getApiClient(): ApiClient {
  if (!g.__sewaApiClient) g.__sewaApiClient = fromHandlers(buildHandlers());
  return g.__sewaApiClient;
}

/** Convenience singleton for server components: `import { api } from "@/lib/api/client"`. */
export const api: ApiClient = new Proxy({} as ApiClient, {
  get(_target, prop: keyof ApiClient) {
    return getApiClient()[prop];
  },
});

/** Explicit getter (avoids Proxy edge cases in some bundlers). */
export function apiClient(): ApiClient {
  return getApiClient();
}
