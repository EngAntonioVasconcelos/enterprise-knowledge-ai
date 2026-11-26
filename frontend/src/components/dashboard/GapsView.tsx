"use client";

import Link from "next/link";

import { useI18n } from "@/i18n/client";
import type { GapReason, GapsData } from "@/lib/api-types";

// The same amber as "no safe answer" on the Dashboard.
const GAP = "#c07a1a";
const REASONS: GapReason[] = ["no_sources", "not_found", "checks", "not_relevant"];

/** Why and where questions found no safe answer. Never who asked, never what. */
export function GapsView({ organizationId, data }: { organizationId: string; data: GapsData }) {
  const { locale, t: all } = useI18n();
  const t = all.gaps;
  const number = new Intl.NumberFormat(locale);
  const query = `?org=${encodeURIComponent(organizationId)}`;
  const top = data.documents[0]?.questions ?? 1;

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>

      {data.unanswered === 0 ? (
        <section className="mt-10 max-w-[40rem] border-y border-line py-8">
          <h2 className="text-lead font-semibold">{t.noneTitle}</h2>
          <p className="mt-2 text-body text-ink-soft text-pretty">{t.noneBody}</p>
        </section>
      ) : (
        <>
          <section aria-labelledby="gap-reasons" className="mt-10">
            <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line pb-3">
              <h2 id="gap-reasons" className="text-lead font-semibold">
                {t.reasonsTitle}
              </h2>
              <p className="text-meta text-ink-soft tabular-nums">{t.unanswered(data.unanswered)}</p>
            </div>
            <ul className="divide-y divide-line">
              {REASONS.map((reason) => {
                const count = data.reasons[reason] ?? 0;
                return (
                  <li
                    key={reason}
                    className={"grid grid-cols-[3.5rem_minmax(0,1fr)] gap-x-4 py-5 " + (count ? "" : "opacity-55")}
                  >
                    <span className="text-[2rem] leading-none font-semibold tracking-[-0.02em] tabular-nums">
                      {number.format(count)}
                    </span>
                    <div className="max-w-[40rem]">
                      <h3 className="text-body font-semibold text-ink">{t.reasons[reason].label}</h3>
                      <p className="mt-1 text-body text-ink-soft text-pretty">{t.reasons[reason].hint}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>

          <section aria-labelledby="gap-documents" className="mt-14">
            <h2 id="gap-documents" className="text-lead font-semibold">
              {t.documentsTitle}
            </h2>
            <p className="mt-1 max-w-[40rem] text-meta text-ink-soft text-pretty">{t.documentsHint(data.min_questions)}</p>
            {data.documents.length ? (
              <ol className="mt-5 space-y-3">
                {data.documents.map((document) => (
                  <li
                    key={document.document_id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_auto]"
                  >
                    <span className="col-start-1 row-start-1 truncate text-body text-ink" title={document.title}>
                      {document.title}
                    </span>
                    <span aria-hidden className="col-span-2 row-start-2 h-2 sm:col-span-1 sm:col-start-2 sm:row-start-1">
                      <span
                        className="block h-2 rounded-r-[4px]"
                        style={{ width: `${(document.questions / top) * 100}%`, background: GAP }}
                      />
                    </span>
                    <span className="col-start-2 row-start-1 text-right text-meta text-ink-soft tabular-nums sm:col-start-3">
                      {t.questions(document.questions)}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-5 text-ink-soft">{t.noDocuments(data.min_questions)}</p>
            )}
            {data.hidden_documents ? (
              <p className="mt-4 text-meta text-ink-faint">{t.hidden(data.hidden_documents)}</p>
            ) : null}
          </section>
        </>
      )}

      <p className="mt-12">
        <Link
          href={`/documentos${query}`}
          className="inline-flex h-10 items-center rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-signal-deep"
        >
          {t.addDocuments}
        </Link>
      </p>
    </div>
  );
}
