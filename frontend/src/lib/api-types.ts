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
