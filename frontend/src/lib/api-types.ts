// The shapes the backend returns (backend/app/schemas). Only what the
// interface reads.

export type Role = "owner" | "admin" | "member" | "viewer";

export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
  /** The signed-in person's own role in it (list of organizations only). */
  role?: Role;
  /** Days each person's questions are kept; 0 keeps none. */
  history_retention_days?: number;
};

export const RETENTION_DAYS = [0, 30, 90, 365] as const;
export type RetentionDays = (typeof RETENTION_DAYS)[number];

export type HistoryItem = {
  id: string;
  question: string;
  abstained: boolean;
  created_at: string;
};

export type HistoryEntry = {
  id: string;
  question: string;
  /** null when a cited document can no longer be read. */
  answer: string | null;
  abstained: boolean;
  verified: boolean;
  language: string;
  created_at: string;
  sources: AnswerSource[];
  hidden: boolean;
  /** A cited document changed since this answer. */
  outdated: boolean;
};

export type Membership = {
  id: string;
  organization_id: string;
  user_id: string;
  role: Role;
  is_active: boolean;
};

export type Member = {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  membership: Membership;
};

export type Invitation = {
  id: string;
  organization_id: string;
  email: string;
  role: Role;
  status: string;
  expires_at: string;
  created_at: string;
  /** Only while e-mails are not delivered (development): shown once. */
  token?: string | null;
};

export type AnswerSource = {
  number: number;
  cited: boolean;
  chunk_id: string;
  document_id: string;
  version_id: string;
  title: string;
  heading: string | null;
  snippet: string;
  start_char: number;
  end_char: number;
};

export type Answer = {
  question: string;
  answer: string;
  abstained: boolean;
  verified: boolean;
  sources: AnswerSource[];
  prompt_id: string;
  model: string | null;
  note: string | null;
  timings_ms: Record<string, number>;
  /** pt, en or fr: the language the answer is written in. */
  language?: string;
  /** Present when the answer comes from a database (AL-4), cited [D1]. */
  data?: AnswerData | null;
};

export type AnswerData = {
  connection_id: string;
  connection_name: string;
  /** The read-only query that ran. */
  sql: string;
  columns: string[];
  rows: (string | number | boolean | null)[][];
  truncated: boolean;
};

export type AnswerErrorKind =
  | "unavailable"
  | "forbidden"
  | "invalid"
  | "signedOut"
  | "network"
  | "unknown";

export function errorKindFromStatus(status: number): AnswerErrorKind {
  if (status === 401) return "signedOut";
  if (status === 403 || status === 404) return "forbidden";
  if (status === 400 || status === 422) return "invalid";
  if (status === 503) return "unavailable";
  return "unknown";
}

export type Connection = {
  id: string;
  provider: string;
  name: string;
  status: string;
  last_synced_at: string | null;
  last_error: string | null;
  disconnected_at: string | null;
  /** Not secret: for a database, where it is (never the login). */
  settings?: Record<string, unknown>;
};

export type Upload = {
  id: string;
  connection_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

export type DocumentItem = {
  id: string;
  connection_id: string;
  title: string;
  mime_type: string | null;
  status: "pending" | "active" | "failed" | "removed" | string;
  last_synced_at: string | null;
  updated_at: string;
};

export type DashboardData = {
  days: { date: string; questions: number; unanswered: number }[];
  questions: number;
  /** Answered with "no safe answer": where the documents fall short. */
  unanswered: number;
  languages: Record<string, number>;
  /** Only documents the viewer can open. */
  top_documents: { document_id: string; title: string; citations: number }[];
  documents: Record<string, number>;
  members: number;
};

export type GapReason = "no_sources" | "not_found" | "checks" | "not_relevant";

/** Why and where questions found no safe answer (AL-3). No people, no text. */
export type GapsData = {
  days: number;
  unanswered: number;
  reasons: Record<GapReason, number>;
  /** Only documents the viewer can open, read by at least min_questions. */
  documents: { document_id: string; title: string; questions: number }[];
  hidden_documents: number;
  min_questions: number;
};

/** What the worker read from a connected database: names, never rows. */
export type DatabaseColumn = { name: string; type: string; nullable: boolean; comment: string | null };

export type DatabaseTable = {
  schema: string;
  name: string;
  kind: "table" | "view";
  rows_estimate: number | null;
  comment: string | null;
  columns: DatabaseColumn[];
};

export type DatabaseCatalog = { schemas: string[]; tables: DatabaseTable[]; truncated: boolean };

export type DatabaseSource = Connection & {
  catalog: DatabaseCatalog | null;
  catalogUpdatedAt: string | null;
};

export const SSL_MODES = ["require", "verify-ca", "verify-full", "disable"] as const;
export type SslMode = (typeof SSL_MODES)[number];
