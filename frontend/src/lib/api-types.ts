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
