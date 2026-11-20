// The shapes the backend returns (backend/app/schemas). Only what the
// interface reads.

export type Organization = {
  id: string;
  name: string;
  slug: string;
  status: string;
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
