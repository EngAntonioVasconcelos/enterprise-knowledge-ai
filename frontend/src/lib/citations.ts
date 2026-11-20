// An answer is text with citation markers like [1] or [2][3]. The screen
// shows each marker as a link to its source, so the text is cut into
// pieces: plain text and citations, in order.

export type AnswerPiece =
  | { kind: "text"; text: string }
  | { kind: "citation"; number: number };

const MARKER = /\[(\d{1,2})\]/g;

export function splitAnswer(answer: string): AnswerPiece[] {
  const pieces: AnswerPiece[] = [];
  let last = 0;
  for (const match of answer.matchAll(MARKER)) {
    const start = match.index ?? 0;
    // A citation hugs the word before it, like a footnote mark.
    const before = answer.slice(last, start).trimEnd();
    if (before) pieces.push({ kind: "text", text: before });
    pieces.push({ kind: "citation", number: Number(match[1]) });
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
