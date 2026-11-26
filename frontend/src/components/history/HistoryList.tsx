"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { deleteQuestions, type HistoryActionState } from "@/app/(app)/historico/actions";
import { useI18n } from "@/i18n/client";
import type { HistoryItem } from "@/lib/api-types";

type Action = (state: HistoryActionState, form: FormData) => Promise<HistoryActionState>;

const quiet =
  "text-meta font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline disabled:cursor-wait disabled:opacity-60";

/** The person's own questions. Nobody else sees them, not even admins. */
export function HistoryList({
  organizationId,
  retentionDays,
  items,
  action = deleteQuestions,
}: {
  organizationId: string;
  retentionDays: number;
  items: HistoryItem[];
  action?: Action;
}) {
  const { locale, t: all } = useI18n();
  const t = all.history;
  const [state, submit, pending] = useActionState(action, {});
  const [confirming, setConfirming] = useState(false);
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const query = `?org=${encodeURIComponent(organizationId)}`;

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">
        {retentionDays > 0 ? t.lead(retentionDays) : t.notKept}
      </p>

      {items.length ? (
        <>
          <ul className="mt-10 border-t border-line">
            {items.map((item) => (
              <li key={item.id} className="border-b border-line">
                <Link
                  href={`/historico/${item.id}${query}`}
                  className="group flex flex-col gap-1 py-4 sm:flex-row sm:items-baseline sm:gap-6"
                >
                  <span className="min-w-0 flex-1 text-ink group-hover:text-signal-deep">
                    <span className="line-clamp-2">{item.question}</span>
                  </span>
                  <span className="flex shrink-0 items-center gap-3 text-meta text-ink-faint tabular-nums">
                    {item.abstained ? <span className="text-caution">{t.noAnswer}</span> : null}
                    {date.format(new Date(item.created_at))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>

          <div className="mt-6 flex flex-wrap items-center gap-3">
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
