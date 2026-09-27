// MockApiClient: ApiHandlers over an in-memory store + simulated latency.
// Server-side only (never import from client components).

import type { ApiHandlers } from "./handlers";
import { buildQueue, seedStore, type MockStore } from "./fixtures";
import type {
  Application,
  CreateApplicationRequest,
  Decision,
  DecisionResult,
  Document,
  MetricsSummary,
  ScrutinyCheck,
  ScrutinyReport,
  UploadDocumentRequest,
} from "./types";

const LATENCY_MIN_MS = 120;
const SCRUTINY_LATENCY_MS = 900; // scrutiny feels heavier than CRUD

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowIso(): string {
  return new Date().toISOString();
}

function fakeSha(contentBase64: string, seq: number): string {
  // Deterministic-looking mock hash; real hashing happens server-side (Track A).
  return `mock-sha-${seq}-${contentBase64.length}`;
}

function defaultChecks(): ScrutinyCheck[] {
  return [
    { checkId: "C1", label: "Identity match", status: "pass", severity: "high", evidence: "Name/ID consistent across documents and application fields (mock).", explanation: "Applicant identity lines up everywhere it appears." },
    { checkId: "C2", label: "Document validity", status: "pass", severity: "medium", evidence: "No expired documents detected (mock).", explanation: "Uploaded documents are within their validity period." },
    { checkId: "C3", label: "Completeness", status: "warn", severity: "medium", evidence: "Legibility of one page is below threshold (mock).", explanation: "One page may need re-upload for reliable reading." },
    { checkId: "C4", label: "Cross-field consistency", status: "pass", severity: "low", evidence: "Declared fields match extracted values (mock).", explanation: "What the applicant typed agrees with the documents." },
    { checkId: "C5", label: "Fraud signals", status: "pass", severity: "high", evidence: "No duplicate hashes or tamper patterns (mock).", explanation: "No signs of forgery or document reuse." },
  ];
}

export function createMockHandlers(seed: MockStore = seedStore()): ApiHandlers {
  const store: MockStore = seed;

  function requireApp(id: string): Application {
    const app = store.applications.find((a) => a.id === id);
    if (!app) throw new Error(`Application ${id} not found`);
    return app;
  }

  function touch(app: Application, status: Application["status"]): void {
    app.status = status;
    app.updatedAt = nowIso();
  }

  return {
    async listServices() {
      await delay(LATENCY_MIN_MS + Math.random() * 150);
      return store.services.map((s) => ({ ...s }));
    },

    async createApplication(req: CreateApplicationRequest) {
      await delay(LATENCY_MIN_MS + Math.random() * 200);
      const app: Application = {
        id: `app-${store.seq++}`,
        serviceId: req.serviceId,
        status: "submitted",
        applicantFields: { ...req.applicantFields },
        createdAt: nowIso(),
        updatedAt: nowIso(),
        timeline: [
          { at: nowIso(), actor: "citizen", event: "application_created", message: "Application submitted." },
        ],
      };
      store.applications.push(app);
      return { ...app };
    },

    async getApplication(id: string) {
      await delay(LATENCY_MIN_MS + Math.random() * 150);
      const app = requireApp(id);
      return { ...app, timeline: [...app.timeline] };
    },

    async uploadDocument(applicationId: string, req: UploadDocumentRequest) {
      await delay(200 + Math.random() * 250);
      const app = requireApp(applicationId);
      const doc: Document = {
        id: `doc-${store.seq++}`,
        docType: req.docType,
        fileName: req.fileName,
        uploadedAt: nowIso(),
        sha256: fakeSha(req.contentBase64, store.seq),
      };
      store.documentsByApp[applicationId] = [
        ...(store.documentsByApp[applicationId] ?? []),
        doc,
      ];
      touch(app, "documents_uploaded");
      app.timeline.push({
        at: nowIso(), actor: "citizen", event: "documents_uploaded",
        message: `Uploaded ${doc.docType} (${doc.fileName}).`,
      });
      return { ...doc };
    },

    async runScrutiny(applicationId: string) {
      await delay(SCRUTINY_LATENCY_MS + Math.random() * 600);
      const app = requireApp(applicationId);
      const docs = store.documentsByApp[applicationId] ?? [];
      const service = store.services.find((s) => s.id === app.serviceId);
      const missing = (service?.requiredDocTypes ?? []).filter(
        (t) => !docs.some((d) => d.docType === t),
      );
      const checksList = defaultChecks().map((c) =>
        c.checkId === "C3" && missing.length > 0
          ? { ...c, status: "fail" as const, evidence: `Missing required docTypes: [${missing.join(", ")}] (mock).`, explanation: "One or more required documents are missing." }
          : c,
      );
      const riskScore = missing.length > 0 ? 60 : 25;
      const latencyMs = SCRUTINY_LATENCY_MS + Math.round(Math.random() * 600);
      const rep: ScrutinyReport = {
        applicationId,
        generatedAt: nowIso(),
        extractedFields: { ...app.applicantFields },
        checks: checksList,
        riskScore,
        recommendation: missing.length > 0 ? "request_info" : "manual_review",
        modelMeta: { extractor: "mock", adjudicator: "mock", latencyMs, versions: { rules: "v1-mock" } },
      };
      store.reportsByApp[applicationId] = rep;
      store.scrutinyDurationsMs.push(SCRUTINY_LATENCY_MS + 200);
      touch(app, "scrutiny_done");
      app.timeline.push({
        at: nowIso(), actor: "system", event: "scrutiny_done",
        message: `Scrutiny complete. Risk score ${riskScore}, recommendation: ${rep.recommendation}.`,
      });
      return { ...rep };
    },

    async getScrutiny(applicationId: string) {
      await delay(LATENCY_MIN_MS + Math.random() * 150);
      requireApp(applicationId); // 404-ish for unknown apps
      const rep = store.reportsByApp[applicationId];
      return rep ? { ...rep } : undefined;
    },

    async getQueue() {
      await delay(LATENCY_MIN_MS + Math.random() * 200);
      return buildQueue(store);
    },

    async postDecision(decision: Decision): Promise<DecisionResult> {
      await delay(200 + Math.random() * 200);
      const app = requireApp(decision.applicationId);
      const status: Application["status"] =
        decision.decision === "approve"
          ? "decided"
          : decision.decision === "reject"
            ? "decided"
            : "info_requested";
      touch(app, status);
      app.timeline.push({
        at: nowIso(), actor: "officer", event: `decision_${decision.decision}`,
        message: `Officer decision: ${decision.decision}. Notes: ${decision.officerNotes}`,
      });
      return { applicationId: app.id, status: app.status };
    },

    async getMetrics() {
      await delay(LATENCY_MIN_MS + Math.random() * 150);
      const total = store.applications.length;
      const decided = store.applications.filter((a) => a.status === "decided").length;
      const pending = total - decided;
      const durs = store.scrutinyDurationsMs;
      const avgScrutinySeconds =
        durs.reduce((s, ms) => s + ms, 0) / Math.max(durs.length, 1) / 1000;
      const flagged = Object.values(store.reportsByApp).filter((r) => r.riskScore >= 60).length;
      const metrics: MetricsSummary = {
        applicationsTotal: total,
        pending,
        decided,
        avgScrutinySeconds: Math.round(avgScrutinySeconds * 10) / 10,
        flagRate: total > 0 ? Math.round((flagged / total) * 100) / 100 : 0,
        evalPrecision: 0.92,
        evalRecall: 0.87,
        generatedAt: nowIso(),
      };
      return metrics;
    },
  };
}
