// In-memory fixture seed for MockApiClient. Synthetic data only (SPEC.md §6):
// fictional names/IDs, no real PII. Shapes come from ./types (the contract).

import type {
  Application,
  Document,
  QueueItem,
  ScrutinyCheck,
  ScrutinyReport,
  Service,
} from "./types";

export interface MockStore {
  services: Service[];
  applications: Application[];
  documentsByApp: Record<string, Document[]>;
  reportsByApp: Record<string, ScrutinyReport>;
  /** ms taken by each completed scrutiny run (for avgScrutinySeconds). */
  scrutinyDurationsMs: number[];
  seq: number;
}

const CHECK_LABELS: Record<string, string> = {
  C1: "Identity match",
  C2: "Document validity",
  C3: "Completeness",
  C4: "Cross-field consistency",
  C5: "Fraud signals",
};

function checks(overrides: Partial<Record<string, ScrutinyCheck>> = {}): ScrutinyCheck[] {
  const base: ScrutinyCheck[] = [
    { checkId: "C1", label: CHECK_LABELS.C1, status: "pass", severity: "high", evidence: "Name 'Asha Rai' matches Aadhaar-no-XXXX-1234 across 2 documents and application fields.", explanation: "The applicant's name and ID are consistent everywhere they appear." },
    { checkId: "C2", label: CHECK_LABELS.C2, status: "pass", severity: "medium", evidence: "Residence certificate issued 2026-01-12, expires 2029-01-12; issuing authority 'Tehsil office' is plausible.", explanation: "All uploaded documents are within their validity period." },
    { checkId: "C3", label: CHECK_LABELS.C3, status: "pass", severity: "medium", evidence: "Required docTypes present: ['id_proof', 'residence']; all pages legible (OCR confidence > 0.9).", explanation: "The application includes every document this service requires." },
    { checkId: "C4", label: CHECK_LABELS.C4, status: "pass", severity: "low", evidence: "Declared income Rs 8,400/month matches income certificate value Rs 8,400/month.", explanation: "Fields entered by the applicant agree with what the documents say." },
    { checkId: "C5", label: CHECK_LABELS.C5, status: "pass", severity: "high", evidence: "No duplicate document hashes found; no tamper patterns detected.", explanation: "No signs of forgery or reuse of the same document across applications." },
  ];
  return base.map((c) => ({ ...c, ...overrides[c.checkId] }));
}

function report(appId: string, riskScore: number, recommendation: ScrutinyReport["recommendation"], checksList: ScrutinyCheck[], extracted: Record<string, unknown>): ScrutinyReport {
  return {
    applicationId: appId,
    generatedAt: "2026-09-20T10:05:00Z",
    extractedFields: extracted,
    checks: checksList,
    riskScore,
    recommendation,
    modelMeta: { extractor: "template+vlm(mock)", adjudicator: "llm-rules(mock)", latencyMs: 4200, versions: { rules: "v1", prompt: "v1" } },
  };
}

export function seedStore(): MockStore {
  const services: Service[] = [
    {
      id: "svc-income-cert",
      name: "Income Certificate",
      requiredDocTypes: ["id_proof", "income_proof"],
      fieldSchema: {
        applicantName: { type: "string", label: "Full name", required: true },
        dob: { type: "date", label: "Date of birth", required: true },
        monthlyIncome: { type: "number", label: "Monthly income (Rs)", required: true },
        address: { type: "string", label: "Residential address", required: true },
      },
    },
    {
      id: "svc-caste-cert",
      name: "Caste Certificate",
      requiredDocTypes: ["id_proof", "residence"],
      fieldSchema: {
        applicantName: { type: "string", label: "Full name", required: true },
        caste: { type: "string", label: "Caste as per records", required: true },
        motherName: { type: "string", label: "Mother's name", required: true },
        address: { type: "string", label: "Residential address", required: true },
      },
    },
    {
      id: "svc-residence-cert",
      name: "Residence Certificate",
      requiredDocTypes: ["id_proof", "residence"],
      fieldSchema: {
        applicantName: { type: "string", label: "Full name", required: true },
        yearsAtAddress: { type: "number", label: "Years at current address", required: true },
        address: { type: "string", label: "Residential address", required: true },
      },
    },
  ];

  // B8 demo seed — dataset-v1 shapes (SPEC.md §6): clean apps score < 30,
  // anomalous apps carry planted-anomaly labels (field_mismatch,
  // duplicate_hash, expired_doc, missing_doc) and risk >= 60 (flag threshold).
  // Dates span 4 days so the dashboard's "apps by day" chart has shape.
  const applications: Application[] = [
    {
      id: "app-1001", serviceId: "svc-income-cert", status: "scrutiny_done",
      applicantFields: { applicantName: "Asha Rai", dob: "1995-04-18", monthlyIncome: 8400, address: "14 Lalbagh Col, Sector 3" },
      createdAt: "2026-09-19T09:00:00Z", updatedAt: "2026-09-20T10:05:00Z",
      timeline: [
        { at: "2026-09-19T09:00:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Income Certificate." },
        { at: "2026-09-19T09:12:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and income_proof." },
        { at: "2026-09-20T10:05:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 12, recommendation: approve." },
      ],
    },
    {
      id: "app-1002", serviceId: "svc-caste-cert", status: "scrutiny_done",
      applicantFields: { applicantName: "Bikash Thapa", caste: "Thapa", motherName: "Sita Thapa", address: "9 Hill Road, Ward 7" },
      createdAt: "2026-09-19T11:30:00Z", updatedAt: "2026-09-22T10:09:00Z",
      timeline: [
        { at: "2026-09-19T11:30:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Caste Certificate." },
        { at: "2026-09-19T11:41:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and residence." },
        { at: "2026-09-20T10:09:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 74, recommendation: manual_review." },
        { at: "2026-09-22T10:09:00Z", actor: "officer", event: "decision_request_info", message: "Officer asked the applicant to confirm the address on the residence document." },
        { at: "2026-09-22T11:02:00Z", actor: "citizen", event: "documents_uploaded", message: "Re-uploaded residence with current address." },
        { at: "2026-09-22T11:40:00Z", actor: "officer", event: "decision_request_info", message: "Officer re-requested info pending re-scrutiny." },
      ],
    },
    {
      id: "app-1003", serviceId: "svc-residence-cert", status: "decided",
      applicantFields: { applicantName: "Chandra Maharjan", yearsAtAddress: 12, address: "22 Pottery Square, Ward 2" },
      createdAt: "2026-09-18T08:15:00Z", updatedAt: "2026-09-20T14:20:00Z",
      timeline: [
        { at: "2026-09-18T08:15:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Residence Certificate." },
        { at: "2026-09-18T08:25:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and residence." },
        { at: "2026-09-19T09:00:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 8, recommendation: approve." },
        { at: "2026-09-20T14:20:00Z", actor: "officer", event: "decision_approved", message: "Officer approved the application." },
      ],
    },
    {
      id: "app-1004", serviceId: "svc-income-cert", status: "info_requested",
      applicantFields: { applicantName: "Dipesh Gurung", dob: "2001-11-02", monthlyIncome: 15000, address: "3 New Town, Ward 11" },
      createdAt: "2026-09-18T15:40:00Z", updatedAt: "2026-09-20T15:05:00Z",
      timeline: [
        { at: "2026-09-18T15:40:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Income Certificate." },
        { at: "2026-09-18T15:52:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof only." },
        { at: "2026-09-19T09:10:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 55, recommendation: request_info." },
        { at: "2026-09-20T15:05:00Z", actor: "officer", event: "decision_request_info", message: "Officer requests a valid income proof document." },
      ],
    },
    {
      id: "app-1005", serviceId: "svc-caste-cert", status: "documents_uploaded",
      applicantFields: { applicantName: "Eisha Karki", caste: "Karki", motherName: "Tara Karki", address: "17 Ring Road, Ward 5" },
      createdAt: "2026-09-20T09:50:00Z", updatedAt: "2026-09-20T10:02:00Z",
      timeline: [
        { at: "2026-09-20T09:50:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Caste Certificate." },
        { at: "2026-09-20T10:02:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and residence." },
      ],
    },
    {
      id: "app-1006", serviceId: "svc-income-cert", status: "scrutiny_done",
      applicantFields: { applicantName: "Fenisha Lama", dob: "1988-07-30", monthlyIncome: 21000, address: "2 Lakeview, Ward 4" },
      createdAt: "2026-09-21T09:20:00Z", updatedAt: "2026-09-21T10:15:00Z",
      timeline: [
        { at: "2026-09-21T09:20:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Income Certificate." },
        { at: "2026-09-21T09:35:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and income_proof." },
        { at: "2026-09-21T10:15:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 68, recommendation: manual_review." },
      ],
    },
    {
      id: "app-1007", serviceId: "svc-caste-cert", status: "scrutiny_done",
      applicantFields: { applicantName: "Ganesh Bhattrai", caste: "Bhattrai", motherName: "Laxmi Bhattrai", address: "5 Temple Street, Ward 1" },
      createdAt: "2026-09-22T08:40:00Z", updatedAt: "2026-09-22T09:10:00Z",
      timeline: [
        { at: "2026-09-22T08:40:00Z", actor: "citizen", event: "application_created", message: "Application submitted for Caste Certificate." },
        { at: "2026-09-22T08:55:00Z", actor: "citizen", event: "documents_uploaded", message: "Uploaded id_proof and residence." },
        { at: "2026-09-22T09:10:00Z", actor: "system", event: "scrutiny_done", message: "Scrutiny complete. Risk score 21, recommendation: approve." },
      ],
    },
  ];

  const documentsByApp: Record<string, Document[]> = {
    "app-1001": [
      { id: "doc-101", docType: "id_proof", fileName: "aadhaar-asha.txt", uploadedAt: "2026-09-19T09:10:00Z", sha256: "mock-sha-0101" },
      { id: "doc-102", docType: "income_proof", fileName: "income-asha.txt", uploadedAt: "2026-09-19T09:12:00Z", sha256: "mock-sha-0102" },
    ],
    "app-1002": [
      { id: "doc-103", docType: "id_proof", fileName: "aadhaar-bikash.txt", uploadedAt: "2026-09-19T11:38:00Z", sha256: "mock-sha-0103" },
      { id: "doc-104", docType: "residence", fileName: "residence-bikash.txt", uploadedAt: "2026-09-19T11:41:00Z", sha256: "mock-sha-0104" },
    ],
    "app-1003": [
      { id: "doc-105", docType: "id_proof", fileName: "aadhaar-chandra.txt", uploadedAt: "2026-09-18T08:22:00Z", sha256: "mock-sha-0105" },
      { id: "doc-106", docType: "residence", fileName: "residence-chandra.txt", uploadedAt: "2026-09-18T08:25:00Z", sha256: "mock-sha-0106" },
    ],
    "app-1004": [
      { id: "doc-107", docType: "id_proof", fileName: "aadhaar-dipesh.txt", uploadedAt: "2026-09-18T15:52:00Z", sha256: "mock-sha-0107" },
    ],
    "app-1005": [
      { id: "doc-108", docType: "id_proof", fileName: "aadhaar-eisha.txt", uploadedAt: "2026-09-20T10:00:00Z", sha256: "mock-sha-0108" },
      { id: "doc-109", docType: "residence", fileName: "residence-eisha.txt", uploadedAt: "2026-09-20T10:02:00Z", sha256: "mock-sha-0104" },
    ],
    "app-1006": [
      { id: "doc-110", docType: "id_proof", fileName: "aadhaar-fenisha.txt", uploadedAt: "2026-09-21T09:30:00Z", sha256: "mock-sha-0110" },
      { id: "doc-111", docType: "income_proof", fileName: "income-fenisha.txt", uploadedAt: "2026-09-21T09:35:00Z", sha256: "mock-sha-0111" },
    ],
    "app-1007": [
      { id: "doc-112", docType: "id_proof", fileName: "aadhaar-ganesh.txt", uploadedAt: "2026-09-22T08:52:00Z", sha256: "mock-sha-0112" },
      { id: "doc-113", docType: "residence", fileName: "residence-ganesh.txt", uploadedAt: "2026-09-22T08:55:00Z", sha256: "mock-sha-0113" },
    ],
  };

  const reportsByApp: Record<string, ScrutinyReport> = {
    // clean (risk < 30, all checks pass)
    "app-1001": report("app-1001", 12, "approve", checks(), { applicantName: "Asha Rai", monthlyIncome: 8400 }),
    // anomalous: field_mismatch + duplicate_hash (planted-anomaly labels from SPEC §6)
    "app-1002": report(
      "app-1002", 74, "manual_review",
      checks({
        C4: { checkId: "C4", label: CHECK_LABELS.C4, status: "fail", severity: "high", evidence: "[field_mismatch] Declared address '9 Hill Road, Ward 7' vs residence doc address '44 Lakeside, Ward 9' — mismatch.", explanation: "The address you filled in does not match the uploaded residence document." },
        C5: { checkId: "C5", label: CHECK_LABELS.C5, status: "fail", severity: "high", evidence: "[duplicate_hash] Document sha256 mock-sha-0104 already used by app-1005 (duplicate hash).", explanation: "The same residence document file appears in two different applications." },
      }),
      { applicantName: "Bikash Thapa", address: "44 Lakeside, Ward 9" },
    ),
    "app-1003": report("app-1003", 8, "approve", checks(), { applicantName: "Chandra Maharjan", yearsAtAddress: 12 }),
    // info_requested: missing_doc (risk just below the 60 flag line)
    "app-1004": report(
      "app-1004", 55, "request_info",
      checks({
        C3: { checkId: "C3", label: CHECK_LABELS.C3, status: "fail", severity: "medium", evidence: "[missing_doc] Required docTypes ['id_proof','income_proof']; only ['id_proof'] uploaded.", explanation: "A required document (income proof) is missing from this application." },
      }),
      { applicantName: "Dipesh Gurung", monthlyIncome: 15000 },
    ),
    // anomalous: expired_doc + tampered_number
    "app-1006": report(
      "app-1006", 68, "manual_review",
      checks({
        C2: { checkId: "C2", label: CHECK_LABELS.C2, status: "fail", severity: "high", evidence: "[expired_doc] Income certificate issued 2023-06-01, expired 2025-06-01 — 1 year past validity at submission.", explanation: "The uploaded income certificate had already expired when the application was made." },
        C4: { checkId: "C4", label: CHECK_LABELS.C4, status: "fail", severity: "medium", evidence: "[tampered_number] Declared income Rs 21,000 vs document Rs 2,100 — digit spacing inconsistent with the template.", explanation: "The income figure in the document looks altered compared to what was declared." },
      }),
      { applicantName: "Fenisha Lama", monthlyIncome: 21000 },
    ),
    // clean
    "app-1007": report("app-1007", 21, "approve", checks(), { applicantName: "Ganesh Bhattrai", caste: "Bhattrai" }),
  };

  return { services, applications, documentsByApp, reportsByApp, scrutinyDurationsMs: [4200, 5100, 3900, 4700, 4400, 4000], seq: 1008 };
}

/** Build QueueItems from the store: everything not yet decided, risk desc. */
export function buildQueue(store: MockStore): QueueItem[] {
  return store.applications
    .filter((a) => a.status !== "decided")
    .map((a) => ({
      applicationId: a.id,
      serviceId: a.serviceId,
      status: a.status,
      riskScore: store.reportsByApp[a.id]?.riskScore ?? 0,
      updatedAt: a.updatedAt,
    }))
    .sort((x, y) => y.riskScore - x.riskScore);
}
