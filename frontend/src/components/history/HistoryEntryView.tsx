"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";

import { deleteQuestions, type HistoryActionState } from "@/app/(app)/historico/actions";
import { AnswerDocument } from "@/components/assistant/AnswerDocument";
import { useI18n } from "@/i18n/client";
import type { Answer, HistoryEntry } from "@/lib/api-types";

type Action = (state: HistoryActionState, form: FormData) => Promise<HistoryActionState>;

const quiet =
  "text-meta font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline disabled:cursor-wait disabled:opacity-60";

/** A past answer as it was shown, unless its sources are no longer readable. */
export function HistoryEntryView({
  organizationId,
  entry,
  action = deleteQuestions,
}: {
  organizationId: string;
  entry: HistoryEntry;
  action?: Action;
}) {
  const { locale, t: all } = useI18n();
  const t = all.history;
  const router = useRouter();
  const [state, submit, pending] = useActionState(action, {});
  const query = `?org=${encodeURIComponent(organizationId)}`;
  const again = `/assistente${query}&q=${encodeURIComponent(entry.question)}`;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "long", timeStyle: "short" });

  useEffect(() => {
    if (state.done) router.push(`/historico${query}`);
  }, [state.done, router, query]);

  const answer: Answer | null =
    entry.answer === null
      ? null
      : {
          question: entry.question,
          answer: entry.answer,
          abstained: entry.abstained,
          verified: entry.verified,
          sources: entry.sources,
          prompt_id: "",
          model: null,
          note: null,
          timings_ms: {},
          language: entry.language,
        };

  return (
    <div>
      <nav className="mb-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-meta">
        <Link href={`/historico${query}`} className="font-medium text-cobalt underline-offset-4 hover:underline">
          {t.back}
        </Link>
        <span className="text-ink-faint tabular-nums">{t.askedOn(date.format(new Date(entry.created_at)))}</span>
      </nav>

      {entry.outdated ? (
        <p role="status" className="mb-8 max-w-[40rem] border-l-2 border-caution pl-4 text-body text-caution">
          {t.outdated}
        </p>
      ) : null}

      {answer ? (
        <AnswerDocument answer={answer} />
      ) : (
        <section className="max-w-[40rem]">
          <h1 className="text-question font-semibold tracking-[-0.02em] text-balance">{entry.question}</h1>
          <p role="status" className="mt-6 border-l-2 border-caution pl-4 text-body text-ink">
            {t.hidden}
          </p>
        </section>
      )}

      <div className="mt-10 flex flex-wrap items-center gap-6">
        <Link
          href={again}
          className="inline-flex h-10 items-center rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-cobalt-deep"
        >
          {t.askAgain}
        </Link>
        <form action={submit}>
          <input type="hidden" name="organizationId" value={organizationId} />
          <input type="hidden" name="entryId" value={entry.id} />
          <button type="submit" disabled={pending} className={quiet}>
            {pending ? t.deleting : t.delete}
          </button>
        </form>
      </div>
      {state.error ? (
        <p role="alert" className="mt-3 text-meta text-danger">
          {t.errors.unavailable}
        </p>
      ) : null}
    </div>
  );
}
