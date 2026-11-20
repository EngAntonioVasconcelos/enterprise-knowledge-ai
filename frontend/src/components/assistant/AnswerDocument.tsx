"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import { messages } from "@/i18n/pt-PT";
import type { Answer, AnswerSource } from "@/lib/api-types";
import { paragraphs, splitAnswer } from "@/lib/citations";

const t = messages.assistant;

// The answer reads like an annotated page: the text on the left, the
// passages it cites in the margin. Pointing at a citation lights up its
// passage, and the other way round, so every claim can be checked at once.
export function AnswerDocument({ answer }: { answer: Answer }) {
  const [active, setActive] = useState<number | null>(null);
  const cited = answer.sources.filter((source) => source.cited);
  const consulted = answer.sources.filter((source) => !source.cited);

  return (
    <article className="grid gap-10 lg:grid-cols-[minmax(0,40rem)_minmax(0,1fr)] lg:gap-14">
      <div>
        <h2 className="text-question font-semibold tracking-[-0.02em] text-balance">
          {answer.question}
        </h2>

        {answer.abstained ? (
          <div className="mt-6 rounded-control bg-caution-wash px-5 py-4">
            <p className="font-semibold text-caution">{t.noAnswerTitle}</p>
            <p className="mt-1 font-reading text-answer text-ink">{answer.answer}</p>
          </div>
        ) : (
          <>
            <div className="mt-6 space-y-5 font-reading text-answer text-ink">
              {paragraphs(answer.answer).map((paragraph, index) => (
                <p key={index}>
                  {splitAnswer(paragraph).map((piece, pieceIndex) =>
                    piece.kind === "text" ? (
                      <span key={pieceIndex}>{piece.text}</span>
                    ) : (
                      <CitationMark
                        key={pieceIndex}
                        number={piece.number}
                        active={active === piece.number}
                        onActive={setActive}
                      />
                    ),
                  )}
                </p>
              ))}
            </div>
            {answer.verified ? (
              <p className="mt-6 inline-flex items-center gap-1.5 text-meta text-checked">
                <Check aria-hidden className="size-3.5" strokeWidth={2.5} />
                {t.verified}
              </p>
            ) : null}
          </>
        )}
      </div>

      {answer.sources.length ? (
        <aside aria-label={t.sources} className="lg:pt-14">
          {cited.length ? (
            <SourceList title={t.sources} sources={cited} active={active} onActive={setActive} />
          ) : null}
          {consulted.length ? (
            <div className={cited.length ? "mt-10" : undefined}>
              <SourceList
                title={t.sourcesConsulted}
                sources={consulted}
                active={active}
                onActive={setActive}
                quiet
              />
            </div>
          ) : null}
        </aside>
      ) : null}
    </article>
  );
}

function CitationMark({
  number,
  active,
  onActive,
}: {
  number: number;
  active: boolean;
  onActive: (number: number | null) => void;
}) {
  return (
    <a
      href={`#fonte-${number}`}
      aria-label={`${t.sources} ${number}`}
      onMouseEnter={() => onActive(number)}
      onMouseLeave={() => onActive(null)}
      onFocus={() => onActive(number)}
      onBlur={() => onActive(null)}
      className={
        "mx-0.5 inline-flex min-w-[1.35em] -translate-y-[0.45em] items-center justify-center rounded-[4px] px-1 align-baseline font-sans text-[0.7rem] leading-[1.5] font-semibold no-underline transition-colors " +
        (active ? "bg-cobalt text-white" : "bg-cobalt-wash text-cobalt-deep hover:bg-cobalt hover:text-white")
      }
    >
      {number}
    </a>
  );
}

function SourceList({
  title,
  sources,
  active,
  onActive,
  quiet = false,
}: {
  title: string;
  sources: AnswerSource[];
  active: number | null;
  onActive: (number: number | null) => void;
  quiet?: boolean;
}) {
  return (
    <section>
      <h3 className="text-meta font-semibold text-ink-soft">{title}</h3>
      <ol className="mt-4 space-y-5">
        {sources.map((source) => {
          const lit = active === source.number;
          return (
            <li
              key={source.chunk_id}
              id={`fonte-${source.number}`}
              onMouseEnter={() => onActive(source.number)}
              onMouseLeave={() => onActive(null)}
              className={
                "scroll-mt-24 border-l-2 pl-4 transition-colors " +
                (lit ? "border-cobalt" : quiet ? "border-line" : "border-line-strong")
              }
            >
              <p className="flex gap-2 text-body leading-snug">
                <span
                  className={
                    "font-semibold tabular-nums " + (lit ? "text-cobalt" : quiet ? "text-ink-faint" : "text-ink-soft")
                  }
                >
                  {source.number}
                </span>
                <span className={quiet ? "text-ink-soft" : "font-medium text-ink"}>{source.title}</span>
              </p>
              {source.heading ? (
                <p className="mt-0.5 pl-5 text-meta text-ink-faint">{source.heading}</p>
              ) : null}
              {!quiet ? (
                <blockquote className="mt-2 pl-5 font-reading text-[0.9375rem] leading-relaxed text-ink-soft">
                  {source.snippet}
                </blockquote>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
