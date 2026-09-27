// Transport-agnostic handler types for the ApiClient contract methods.
// MockApiClient wires these to in-memory fixtures; RealApiClient (B7) will
// wire them to fetch against API_BASE_URL. Handlers run server-side only,
// so they may return values synchronously.

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

export type HandlerResult<T> = T | Promise<T>;

export interface ApiHandlers {
  listServices: () => HandlerResult<Service[]>;
  createApplication: (
    req: CreateApplicationRequest,
  ) => HandlerResult<Application>;
  getApplication: (id: string) => HandlerResult<Application>;
  uploadDocument: (
    applicationId: string,
    req: UploadDocumentRequest,
  ) => HandlerResult<Document>;
  runScrutiny: (applicationId: string) => HandlerResult<ScrutinyReport>;
  /** undefined = scrutiny not run yet (contract 404). */
  getScrutiny: (
    applicationId: string,
  ) => HandlerResult<ScrutinyReport | undefined>;
  getQueue: () => HandlerResult<QueueItem[]>;
  postDecision: (decision: Decision) => HandlerResult<DecisionResult>;
  getMetrics: () => HandlerResult<MetricsSummary>;
}

/** Public API surface used by every component/page (AGENTS.md: ApiClient only). */
export interface ApiClient {
  listServices(): Promise<Service[]>;
  createApplication(req: CreateApplicationRequest): Promise<Application>;
  getApplication(id: string): Promise<Application>;
  uploadDocument(
    applicationId: string,
    req: UploadDocumentRequest,
  ): Promise<Document>;
  runScrutiny(applicationId: string): Promise<ScrutinyReport>;
  /** undefined = scrutiny not run yet (contract 404). */
  getScrutiny(applicationId: string): Promise<ScrutinyReport | undefined>;
  getQueue(): Promise<QueueItem[]>;
  postDecision(decision: Decision): Promise<DecisionResult>;
  getMetrics(): Promise<MetricsSummary>;
}
