"use client";

import Link from "next/link";
import { useState } from "react";

import { useI18n } from "@/i18n/client";
import type { DashboardData } from "@/lib/api-types";

// Answered and "no safe answer": cobalt and amber, checked for colour
// blindness against the page (dataviz validator, adjacent pair).
const ANSWERED = "var(--color-cobalt)";
const UNANSWERED = "#c07a1a";

/** The last 30 days in numbers. Never who asked, never what. */
export function DashboardView({ organizationId, data }: { organizationId: string; data: DashboardData }) {
  const { locale, t: all } = useI18n();
  const t = all.dashboard;
  const number = new Intl.NumberFormat(locale);
  const percent = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 });
  const rate = data.questions ? data.unanswered / data.questions : 0;
  const query = `?org=${encodeURIComponent(organizationId)}`;
  const ready = data.documents.active ?? 0;
  const failed = data.documents.failed ?? 0;

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>

      <dl className="mt-10 grid grid-cols-2 gap-x-8 gap-y-6 border-y border-line py-6 md:grid-cols-4">
        <Stat label={t.questions} value={number.format(data.questions)} />
        <Stat
          label={t.unanswered}
          value={number.format(data.unanswered)}
          note={data.questions ? t.ofQuestions(percent.format(rate)) : undefined}
        />
        <Stat label={t.members} value={number.format(data.members)} />
        <Stat
          label={t.documentsReady}
          value={number.format(ready)}
          note={failed ? t.documentsFailed(number.format(failed)) : undefined}
        />
      </dl>

      <DayChart data={data} />

      {data.unanswered ? (
        <p className="mt-6 max-w-[40rem] border-l-2 border-caution pl-4 text-body text-ink text-pretty">
          {t.gapHint}{" "}
          <Link href={`/documentos${query}`} className="font-medium text-cobalt underline underline-offset-4">
            {t.addDocuments}
          </Link>
        </p>
      ) : null}

      <section aria-labelledby="top-documents" className="mt-14">
        <h2 id="top-documents" className="text-lead font-semibold">
          {t.topDocuments}
        </h2>
        <p className="mt-1 max-w-[40rem] text-meta text-ink-soft">{t.topDocumentsHint}</p>
        {data.top_documents.length ? (
          <ol className="mt-5 space-y-3">
            {data.top_documents.map((document) => (
              <li key={document.document_id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,16rem)_minmax(0,1fr)_auto]">
                <span className="col-start-1 row-start-1 truncate text-body text-ink" title={document.title}>
                  {document.title}
                </span>
                <span aria-hidden className="col-span-2 row-start-2 h-2 sm:col-span-1 sm:col-start-2 sm:row-start-1">
                  <span
                    className="block h-2 rounded-r-[4px]"
                    style={{
                      width: `${(document.citations / data.top_documents[0]!.citations) * 100}%`,
                      background: ANSWERED,
                    }}
                  />
                </span>
                <span className="col-start-2 row-start-1 text-right text-meta text-ink-soft tabular-nums sm:col-start-3">
                  {t.citations(document.citations)}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-5 text-ink-soft">{t.noCitations}</p>
        )}
      </section>

      <section aria-labelledby="languages" className="mt-14">
        <h2 id="languages" className="text-lead font-semibold">
          {t.languages}
        </h2>
        <dl className="mt-4 flex flex-wrap gap-x-10 gap-y-3">
          {(["pt", "en", "fr"] as const).map((language) => (
            <div key={language}>
              <dt className="text-meta text-ink-soft">{t.languageNames[language]}</dt>
              <dd className="text-lead font-semibold tabular-nums">{number.format(data.languages[language] ?? 0)}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <dt className="text-meta text-ink-soft">{label}</dt>
      <dd className="mt-1 text-[2rem] leading-none font-semibold tracking-[-0.02em] tabular-nums">{value}</dd>
      {note ? <dd className="mt-1.5 text-meta text-ink-faint">{note}</dd> : null}
    </div>
  );
}

function DayChart({ data }: { data: DashboardData }) {
  const { locale, t: all } = useI18n();
  const t = all.dashboard;
  const [active, setActive] = useState<number | null>(null);
  const day = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
  const top = Math.max(1, ...data.days.map((d) => d.questions));
  const shown = active === null ? null : data.days[active];
  const label = (index: number) => day.format(new Date(`${data.days[index]!.date}T00:00:00Z`));

  return (
    <section aria-labelledby="per-day" className="mt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="per-day" className="text-lead font-semibold">
          {t.perDay}
        </h2>
        <ul className="flex gap-5 text-meta text-ink-soft">
          <li className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-[2px]" style={{ background: ANSWERED }} />
            {t.answered}
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-[2px]" style={{ background: UNANSWERED }} />
            {t.unanswered}
          </li>
        </ul>
      </div>

      {data.questions ? (
        <div className="relative mt-5">
          <div aria-hidden className="flex h-40 items-end gap-[2px] border-b border-line" onPointerLeave={() => setActive(null)}>
            {data.days.map((d, index) => {
              const answered = d.questions - d.unanswered;
              return (
                <div
                  key={d.date}
                  onPointerEnter={() => setActive(index)}
                  className="flex h-full min-w-0 flex-1 flex-col justify-end"
                >
                  <div className={"flex flex-col justify-end gap-[2px] " + (active === index ? "opacity-80" : "")} style={{ height: `${(d.questions / top) * 100}%` }}>
                    {d.unanswered ? (
                      <span className="block rounded-t-[4px]" style={{ flexGrow: d.unanswered, background: UNANSWERED }} />
                    ) : null}
                    {answered ? (
                      <span
                        className={"block " + (d.unanswered ? "" : "rounded-t-[4px]")}
                        style={{ flexGrow: answered, background: ANSWERED }}
                      />
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
          {shown ? (
            <div
              role="presentation"
              className="pointer-events-none absolute top-0 z-10 -translate-x-1/2 rounded-control border border-line bg-surface px-3 py-2 text-meta whitespace-nowrap shadow-[0_2px_8px_rgb(23_32_51/0.08)]"
              style={{ left: `${Math.min(88, Math.max(12, ((active! + 0.5) / data.days.length) * 100))}%` }}
            >
              <p className="font-medium text-ink">{label(active!)}</p>
              <p className="text-ink-soft">
                <strong className="font-semibold text-ink tabular-nums">{shown.questions - shown.unanswered}</strong> {t.answered}
              </p>
              <p className="text-ink-soft">
                <strong className="font-semibold text-ink tabular-nums">{shown.unanswered}</strong> {t.unanswered}
              </p>
            </div>
          ) : null}
          <div aria-hidden className="mt-2 flex justify-between text-meta text-ink-faint tabular-nums">
            <span>{label(0)}</span>
            <span>{label(Math.floor(data.days.length / 2))}</span>
            <span>{t.today}</span>
          </div>
        </div>
      ) : (
        <p className="mt-5 text-ink-soft">{t.noQuestions}</p>
      )}

      <details className="mt-4 text-meta">
        <summary className="cursor-pointer font-medium text-cobalt">{t.asTable}</summary>
        <table className="mt-3 w-full max-w-md border-collapse text-left">
          <thead>
            <tr className="border-b border-line text-ink-faint">
              <th scope="col" className="py-1.5 pr-4 font-medium">{t.day}</th>
              <th scope="col" className="py-1.5 pr-4 font-medium">{t.answered}</th>
              <th scope="col" className="py-1.5 font-medium">{t.unanswered}</th>
            </tr>
          </thead>
          <tbody>
            {data.days.map((d, index) => (
              <tr key={d.date} className="border-b border-line tabular-nums">
                <td className="py-1.5 pr-4">{label(index)}</td>
                <td className="py-1.5 pr-4">{d.questions - d.unanswered}</td>
                <td className="py-1.5">{d.unanswered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
