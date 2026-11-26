"use client";

import Link from "next/link";
import { Search } from "lucide-react";
import { useActionState, useState } from "react";

import { deleteQuestions, type HistoryActionState } from "@/app/(app)/historico/actions";
import { useI18n } from "@/i18n/client";
import type { HistoryItem } from "@/lib/api-types";
import { plain } from "@/lib/text";

type Action = (state: HistoryActionState, form: FormData) => Promise<HistoryActionState>;

// A search box only helps once the list is longer than a glance.
const SEARCH_FROM = 6;

const quiet =
  "text-meta font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline disabled:cursor-wait disabled:opacity-60";

/** The person's own questions. Nobody else sees them, not even admins. */
export function HistoryList({
  organizationId,
  retentionDays,
  items,
  now,
  action = deleteQuestions,
}: {
  organizationId: string;
  retentionDays: number;
  items: HistoryItem[];
  /** When the page was made, so "Hoje" is the same on the server and in the browser. */
  now?: string;
  action?: Action;
}) {
  const { locale, t: all } = useI18n();
  const t = all.history;
  const [state, submit, pending] = useActionState(action, {});
  const [confirming, setConfirming] = useState(false);
  const [text, setText] = useState("");
  const [onlyUnanswered, setOnlyUnanswered] = useState(false);
  const time = new Intl.DateTimeFormat(locale, { timeStyle: "short" });
  const dayKey = new Intl.DateTimeFormat(locale, { year: "numeric", month: "2-digit", day: "2-digit" });
  const longDay = new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const query = `?org=${encodeURIComponent(organizationId)}`;
  const [reference] = useState(() => (now ? Date.parse(now) : Date.now()));
  const today = dayKey.format(reference);
  const yesterday = dayKey.format(reference - 86_400_000);
  const unanswered = items.filter((item) => item.abstained).length;

  const wanted = plain(text.trim());
  const shown = items.filter(
    (item) => (!onlyUnanswered || item.abstained) && (!wanted || plain(item.question).includes(wanted)),
  );
  // Questions under the day they were asked, newest first, as they come.
  const days: { key: string; label: string; items: HistoryItem[] }[] = [];
  for (const item of shown) {
    const at = new Date(item.created_at);
    const key = dayKey.format(at);
    const last = days.at(-1);
    if (last?.key === key) last.items.push(item);
    else days.push({ key, label: key === today ? t.today : key === yesterday ? t.yesterday : longDay.format(at), items: [item] });
  }

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">
        {retentionDays > 0 ? t.lead(retentionDays) : t.notKept}
      </p>

      {items.length ? (
        <>
          {items.length >= SEARCH_FROM || unanswered ? (
            <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-3">
              {items.length >= SEARCH_FROM ? (
                <label className="relative w-full sm:w-80">
                  <span className="sr-only">{t.search}</span>
                  <Search
                    aria-hidden
                    className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint"
                    strokeWidth={1.75}
                  />
                  <input
                    type="search"
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    placeholder={t.search}
                    className="h-9 w-full rounded-control border border-line-strong bg-surface pr-3 pl-9 text-body text-ink outline-none placeholder:text-ink-faint focus:border-signal"
                  />
                </label>
              ) : null}
              {unanswered ? (
                <label
                  className={
                    "inline-flex h-9 cursor-pointer items-center gap-2 rounded-control px-3 text-meta font-medium has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-signal " +
                    (onlyUnanswered ? "bg-ink text-white" : "text-ink-soft hover:bg-surface hover:text-ink")
                  }
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={onlyUnanswered}
                    onChange={(event) => setOnlyUnanswered(event.target.checked)}
                  />
                  {t.onlyUnanswered}
                  <span className={"tabular-nums " + (onlyUnanswered ? "text-white/70" : "text-ink-faint")}>{unanswered}</span>
                </label>
              ) : null}
            </div>
          ) : null}

          {days.length ? (
            <div className="mt-6">
              {days.map((day) => (
                <section key={day.key} aria-label={day.label} className="mt-6 first:mt-0">
                  <h2 className="text-meta font-medium text-ink-faint first-letter:uppercase">{day.label}</h2>
                  <ul className="mt-2 border-t border-line">
                    {day.items.map((item) => (
                      <li key={item.id} className="border-b border-line">
                        <Link
                          href={`/historico/${item.id}${query}`}
                          className="group flex flex-col gap-1 py-3.5 sm:flex-row sm:items-baseline sm:gap-6"
                        >
                          <span className="min-w-0 flex-1 text-ink group-hover:text-signal-deep">
                            <span className="line-clamp-2">{item.question}</span>
                          </span>
                          <span className="flex shrink-0 items-center gap-3 text-meta text-ink-faint tabular-nums">
                            {item.abstained ? <span className="text-caution">{t.noAnswer}</span> : null}
                            <time dateTime={item.created_at}>{time.format(new Date(item.created_at))}</time>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          ) : (
            <div className="py-10">
              <p className="text-ink-soft">{t.noMatch}</p>
              <button
                type="button"
                onClick={() => {
                  setText("");
                  setOnlyUnanswered(false);
                }}
                className="mt-2 font-medium text-signal underline underline-offset-4 hover:text-signal-deep"
              >
                {t.clearFilters}
              </button>
            </div>
          )}

          <div className="mt-8 flex flex-wrap items-center gap-3">
            {confirming ? (
              <form action={submit} className="flex flex-wrap items-center gap-3">
                <input type="hidden" name="organizationId" value={organizationId} />
                <p className="text-meta text-ink">{t.deleteAllConfirm}</p>
                <button
                  type="submit"
                  disabled={pending}
                  className="h-9 rounded-control bg-danger px-3 text-meta font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
                >
                  {pending ? t.deleting : t.deleteAllYes}
                </button>
                <button type="button" onClick={() => setConfirming(false)} className={quiet}>
                  {t.cancel}
                </button>
              </form>
            ) : (
              <button type="button" onClick={() => setConfirming(true)} className={quiet}>
                {t.deleteAll}
              </button>
            )}
          </div>
          {state.error ? (
            <p role="alert" className="mt-3 text-meta text-danger">
              {t.errors.unavailable}
            </p>
          ) : null}
        </>
      ) : (
        <section className="mt-12 max-w-[36rem]">
          <h2 className="text-lead font-semibold">{t.emptyTitle}</h2>
          <p className="mt-2 text-ink-soft text-pretty">{retentionDays > 0 ? t.emptyBody : t.emptyNotKept}</p>
          <Link
            href={`/assistente${query}`}
            className="mt-6 inline-flex h-10 items-center rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-signal-deep"
          >
            {t.ask}
          </Link>
        </section>
      )}
    </div>
  );
}
