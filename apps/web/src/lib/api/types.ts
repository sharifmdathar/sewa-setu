// Hand-generated from shared/contracts/openapi.yaml (v1.0.0, FROZEN).
// Field names, enum values and optionality MUST match the contract exactly.

/** components.schemas.AppStatus */
export type AppStatus =
  | "submitted"
  | "documents_uploaded"
  | "scrutiny_pending"
  | "scrutiny_done"
  | "decided"
  | "info_requested";

/** components.schemas.Service */
export interface Service {
  id: string;
  name: string;
  requiredDocTypes: string[];
  fieldSchema?: Record<string, unknown>;
}

/** components.schemas.TimelineEvent */
export interface TimelineEvent {
  at: string; // date-time
  actor: "citizen" | "system" | "officer";
  event: string;
  message: string;
}

/** components.schemas.Application */
export interface Application {
  id: string;
  serviceId: string;
  status: AppStatus;
  applicantFields: Record<string, unknown>;
  createdAt: string; // date-time
  updatedAt: string; // date-time
  timeline: TimelineEvent[];
}

/** components.schemas.Document */
export interface Document {
  id: string;
  docType: string;
  fileName: string;
  uploadedAt: string; // date-time
  sha256: string;
}

/** components.schemas.ScrutinyCheck */
export interface ScrutinyCheck {
  checkId: string;
  label: string;
  status: "pass" | "fail" | "warn" | "info";
  severity: "low" | "medium" | "high";
  evidence: string;
  explanation: string;
}

/** components.schemas.ScrutinyReport */
export interface ScrutinyReport {
  applicationId: string;
  generatedAt: string; // date-time
  extractedFields: Record<string, unknown>;
  checks: ScrutinyCheck[];
  riskScore: number; // integer 0–100
  recommendation: "approve" | "request_info" | "manual_review" | "reject";
  modelMeta: {
    extractor?: string;
    adjudicator?: string;
    latencyMs?: number;
    versions?: Record<string, unknown>;
  };
}

/** components.schemas.QueueItem */
export interface QueueItem {
  applicationId: string;
  serviceId: string;
  status: AppStatus;
  riskScore: number; // integer
  updatedAt: string; // date-time
}

/** components.schemas.Decision */
export interface Decision {
  applicationId: string;
  decision: "approve" | "reject" | "request_info";
  officerNotes: string;
}

/** components.schemas.MetricsSummary */
export interface MetricsSummary {
  applicationsTotal: number;
  pending: number;
  decided: number;
  avgScrutinySeconds: number;
  flagRate: number;
  evalPrecision?: number;
  evalRecall?: number;
  generatedAt: string; // date-time
}

// ---- Request payload shapes (inline schemas in the contract's paths) ----

/** POST /applications — requestBody */
export interface CreateApplicationRequest {
  serviceId: string;
  applicantFields: Record<string, unknown>;
}

/** POST /applications/{id}/documents — requestBody */
export interface UploadDocumentRequest {
  docType: string;
  fileName: string;
  contentBase64: string;
}

/** POST /officer/decisions — 200 response */
export interface DecisionResult {
  applicationId: string;
  status: AppStatus;
}
