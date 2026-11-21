"use client";

import { Check, Database } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n/client";
import type { Answer, AnswerData, AnswerSource } from "@/lib/api-types";
import { excerpt, paragraphs, passageText, splitAnswer } from "@/lib/citations";


// The answer reads like an annotated page: the text on the left, the
// passages it cites in the margin. Pointing at a citation lights up its
// passage, and the other way round, so every claim can be checked at once.
export function AnswerDocument({ answer }: { answer: Answer }) {
  const t = useI18n().t.assistant;
  // 0 stands for the database rows ([D1]); 1 and up for passages.
  const [active, setActive] = useState<number | null>(null);
  const data = answer.abstained ? null : (answer.data ?? null);
  const cited = answer.sources.filter((source) => source.cited);
  const consulted = answer.sources.filter((source) => !source.cited);

  return (
    <article className="grid gap-10 lg:grid-cols-[minmax(0,40rem)_minmax(18rem,1fr)] lg:gap-14">
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
            <div lang={answer.language} className="mt-6 space-y-5 font-reading text-answer text-ink">
              {paragraphs(answer.answer).map((paragraph, index) => (
                <p key={index}>
                  {splitAnswer(paragraph).map((piece, pieceIndex) =>
                    piece.kind === "text" ? (
                      <span key={pieceIndex}>{piece.text}</span>
                    ) : piece.kind === "data" ? (
                      <DataMark key={pieceIndex} active={active === 0} onActive={setActive} />
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
                {data ? t.verifiedData : t.verified}
              </p>
            ) : null}
          </>
        )}
      </div>

      {data ? (
        <aside aria-label={t.data} className="min-w-0 lg:pt-14">
          <DataPanel data={data} active={active === 0} onActive={setActive} />
        </aside>
      ) : answer.sources.length ? (
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

const MARK =
  "ml-[0.15em] inline-flex min-w-[1.35em] -translate-y-[0.45em] items-center justify-center rounded-[4px] px-1 align-baseline font-sans text-[0.7rem] leading-[1.5] font-semibold no-underline transition-colors ";

function DataMark({ active, onActive }: { active: boolean; onActive: (number: number | null) => void }) {
  const t = useI18n().t.assistant;
  return (
    <a
      href="#dados"
      aria-label={t.dataCitation}
      onMouseEnter={() => onActive(0)}
      onMouseLeave={() => onActive(null)}
      onFocus={() => onActive(0)}
      onBlur={() => onActive(null)}
      className={MARK + (active ? "bg-cobalt text-white" : "bg-cobalt-wash text-cobalt-deep hover:bg-cobalt hover:text-white")}
    >
      <Database aria-hidden className="my-[0.2em] size-[1.15em]" strokeWidth={2.25} />
    </a>
  );
}

// The rows an answer comes from, as read, and the query that read them:
// the person can check every number, as with a passage.
function DataPanel({
  data,
  active,
  onActive,
}: {
  data: AnswerData;
  active: boolean;
  onActive: (number: number | null) => void;
}) {
  const t = useI18n().t.assistant;
  return (
    <section
      id="dados"
      onMouseEnter={() => onActive(0)}
      onMouseLeave={() => onActive(null)}
      className={"scroll-mt-24 border-l-2 pl-4 transition-colors " + (active ? "border-cobalt" : "border-line-strong")}
    >
      <h3 className="text-meta font-semibold text-ink-soft">{t.data}</h3>
      <p className="mt-3 flex items-center gap-2 text-body font-medium text-ink">
        <Database aria-hidden className={"size-4 shrink-0 " + (active ? "text-cobalt" : "text-ink-faint")} strokeWidth={1.75} />
        <span className="truncate">{t.dataFrom(data.connection_name)}</span>
      </p>
      <p className="mt-0.5 pl-6 text-meta text-ink-faint">{t.dataRows(data.rows.length)}</p>

      <div className="mt-4 max-h-80 overflow-auto rounded-control border border-line bg-surface">
        <table className="w-full border-collapse text-left text-meta tabular-nums">
          <thead className="sticky top-0 bg-surface">
            <tr className="border-b border-line">
              {data.columns.map((column, index) => (
                <th key={index} scope="col" className="px-3 py-2 font-medium whitespace-nowrap text-ink-soft">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line last:border-0">
                {row.map((value, index) => (
                  <td key={index} className="px-3 py-1.5 align-top whitespace-nowrap text-ink">
                    {value === null || value === "" ? <span className="text-ink-faint">{t.dataEmpty}</span> : String(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.truncated ? <p className="mt-2 text-meta text-ink-faint">{t.dataMore}</p> : null}

      <details className="mt-4 text-meta">
        <summary className="cursor-pointer font-medium text-cobalt">{t.dataQuery}</summary>
        <p className="mt-2 text-ink-faint">{t.dataQueryHint}</p>
        <pre className="mt-2 overflow-x-auto rounded-control bg-paper px-3 py-2 font-mono text-[0.8125rem] leading-relaxed whitespace-pre-wrap text-ink">
          {data.sql}
        </pre>
      </details>
    </section>
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
  const t = useI18n().t.assistant;
  return (
    <a
      href={`#fonte-${number}`}
      aria-label={t.source(number)}
      onMouseEnter={() => onActive(number)}
      onMouseLeave={() => onActive(null)}
      onFocus={() => onActive(number)}
      onBlur={() => onActive(null)}
      className={
        MARK +
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
              ) : quiet ? (
                // Without a section, a few words tell passages of one document apart.
                <p className="mt-0.5 pl-5 text-meta text-ink-faint">{excerpt(source.snippet)}</p>
              ) : null}
              {!quiet ? (
                <blockquote className="mt-2 pl-5 font-reading text-[0.9375rem] leading-relaxed text-ink-soft">
                  {passageText(source.snippet, source.heading)}
                </blockquote>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
