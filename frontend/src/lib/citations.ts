// An answer is text with citation markers like [1] or [2][3]. The screen
// shows each marker as a link to its source, so the text is cut into
// pieces: plain text and citations, in order.

export type AnswerPiece =
  | { kind: "text"; text: string }
  | { kind: "citation"; number: number }
  | { kind: "data" };

// [1]..[99] cite a document passage; [D1] cites the database rows (AL-4).
const MARKER = /\[(\d{1,2}|D1)\]/g;

export function splitAnswer(answer: string): AnswerPiece[] {
  const pieces: AnswerPiece[] = [];
  let last = 0;
  for (const match of answer.matchAll(MARKER)) {
    const start = match.index ?? 0;
    // A citation hugs the word before it, like a footnote mark.
    const before = answer.slice(last, start).trimEnd();
    if (before) pieces.push({ kind: "text", text: before });
    pieces.push(match[1] === "D1" ? { kind: "data" } : { kind: "citation", number: Number(match[1]) });
    last = start + match[0].length;
  }
  if (last < answer.length) pieces.push({ kind: "text", text: answer.slice(last) });
  return pieces;
}

/** Answers of a few sentences become paragraphs at blank lines only. */
export function paragraphs(answer: string): string[] {
  return answer
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

/**
 * A passage as the margin shows it. Passages begin with their section's
 * heading, which the margin already shows above them: say it once.
 */
export function passageText(snippet: string, heading: string | null): string {
  const text = snippet.trim();
  if (!heading) return text;
  const title = heading.trim();
  return text.startsWith(title) ? text.slice(title.length).trimStart() || text : text;
}

/** The first words of a passage, for a source listed without its text. */
export function excerpt(text: string, words = 12): string {
  const parts = text.trim().split(/\s+/);
  return parts.length > words ? `${parts.slice(0, words).join(" ")}\u2026` : parts.join(" ");
}
