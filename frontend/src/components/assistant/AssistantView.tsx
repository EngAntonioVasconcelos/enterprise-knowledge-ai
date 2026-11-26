"use client";

import { ArrowUpRight, History } from "lucide-react";
import Link from "next/link";

import { useEffect, useRef, useState } from "react";

import { AnswerEvidence, AnswerText, hasEvidence } from "@/components/assistant/AnswerDocument";
import { Composer } from "@/components/assistant/Composer";
import { useI18n } from "@/i18n/client";
import { type Answer, type AnswerErrorKind, errorKindFromStatus, type HistoryItem } from "@/lib/api-types";


type State =
  | { status: "idle" }
  | { status: "asking"; question: string; startedAt: number }
  | { status: "answered"; answer: Answer }
  | { status: "failed"; question: string; kind: AnswerErrorKind };

export async function requestAnswer(
  organizationId: string,
  question: string,
  signal?: AbortSignal,
  language?: string,
  previous: string[] = [],
): Promise<{ answer: Answer } | { error: AnswerErrorKind }> {
  let response: Response;
  try {
    response = await fetch("/api/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organizationId, question, language, ...(previous.length ? { previous } : {}) }),
      signal,
    });
  } catch {
    return { error: "network" };
  }
  if (!response.ok) {
    return { error: response.status === 502 ? "network" : errorKindFromStatus(response.status) };
  }
  return { answer: (await response.json()) as Answer };
}

export function AssistantView({
  organizationId,
  organizationName,
  initialQuestion = null,
  firstName = null,
  recent = [],
}: {
  organizationId: string;
  organizationName: string;
  /** Asked at once: "Ask again" from the history. */
  initialQuestion?: string | null;
  /** To greet the person by name. */
  firstName?: string | null;
  /** The person's own latest questions, to pick up where they left off. */
  recent?: HistoryItem[];
}) {
  const { locale, t: all } = useI18n();
  const t = all.assistant;
  const [state, setState] = useState<State>({ status: "idle" });
  // The questions already answered in this conversation, oldest first. A
  // follow-up sends the last two; earlier answers are never sent.
  const [thread, setThread] = useState<string[]>([]);
  const [conversation, setConversation] = useState(0);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  const asked = useRef(false);
  useEffect(() => {
    if (!initialQuestion || asked.current) return;
    asked.current = true;
    // Out of the address, so reloading the page does not ask again.
    const url = new URL(window.location.href);
    url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
    void ask(initialQuestion);
    // In development React mounts twice and the first mount's request is
    // cancelled: let the second mount ask again instead of waiting forever.
    return () => {
      asked.current = false;
    };
    // Only once, when the page opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function ask(question: string, earlier: string[] = thread) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ status: "asking", question, startedAt: Date.now() });
    // The interface language helps only when the question does not show its own.
    const result = await requestAnswer(
      organizationId,
      question,
      current.signal,
      locale.slice(0, 2),
      earlier.slice(-2),
    );
    if (current.signal.aborted) return;
    if ("answer" in result) {
      setState({ status: "answered", answer: result.answer });
      setThread([...earlier, question]);
    } else {
      setState({ status: "failed", question, kind: result.error });
    }
  }

  function startOver() {
    controller.current?.abort();
    setThread([]);
    setState({ status: "idle" });
    // A new composer, empty.
    setConversation((value) => value + 1);
  }

  const busy = state.status === "asking";
  // 0 stands for the database rows ([D1]); 1 and up for passages.
  const [active, setActive] = useState<number | null>(null);
  const earlier = state.status === "answered" ? thread.slice(0, -1) : thread;

  return (
    // The Bancada: the conversation on the left, the evidence always on the
    // right, so every claim can be checked without scrolling.
    <div className="lg:grid lg:min-h-[calc(100dvh-3.75rem)] lg:grid-cols-[minmax(0,1fr)_minmax(22rem,27rem)]">
      <div className="flex min-w-0 flex-col px-5 py-8 sm:px-8 lg:px-14 lg:pt-10 lg:pb-0">
        <h1 className="sr-only">{`${t.title}, ${organizationName}`}</h1>
        <div className="mx-auto flex w-full max-w-[44rem] flex-1 flex-col">
          {earlier.length ? (
            <ol aria-label={t.inConversation} className="mb-8 space-y-2 border-l-2 border-line pl-4">
              {earlier.slice(-3).map((question, index) => (
                <li key={index} className="text-body text-ink-faint">
                  {question}
                </li>
              ))}
            </ol>
          ) : null}

          <div aria-live="polite">
            {state.status === "idle" ? (
              <EmptyState firstName={firstName} recent={recent} organizationId={organizationId} />
            ) : null}
            {state.status === "asking" ? <Pending question={state.question} startedAt={state.startedAt} /> : null}
            {state.status === "answered" ? (
              <AnswerText answer={state.answer} active={active} onActive={setActive} />
            ) : null}
            {state.status === "failed" ? <Failure kind={state.kind} onRetry={() => ask(state.question)} /> : null}
          </div>

          {/* The next question, always within reach at the bottom. */}
          <div className="mt-10 lg:sticky lg:bottom-0 lg:mt-auto lg:bg-paper lg:pt-8 lg:pb-8">
            <Composer
              key={conversation}
              onAsk={(question) => ask(question)}
              busy={busy}
              placeholder={thread.length ? t.followUpPlaceholder : undefined}
            />
            {thread.length ? (
              <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-meta">
                <p className="text-ink-faint">{t.inConversationCount(thread.length)}</p>
                <button
                  type="button"
                  onClick={startOver}
                  className="font-medium text-signal underline-offset-4 hover:underline"
                >
                  {t.newConversation}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <section
        aria-labelledby="provas-title"
        className="border-t border-line bg-surface px-5 py-8 sm:px-8 lg:sticky lg:top-15 lg:h-[calc(100dvh-3.75rem)] lg:overflow-y-auto lg:border-t-0 lg:border-l lg:px-7"
      >
        <div className="flex items-baseline gap-2.5">
          <h2 id="provas-title" className="text-body font-semibold text-ink">
            {t.evidence.title}
          </h2>
          <span className="text-meta text-ink-faint">{t.evidence.hint}</span>
        </div>
        <div className="mt-6">
          {state.status === "answered" && hasEvidence(state.answer) ? (
            <AnswerEvidence answer={state.answer} active={active} onActive={setActive} />
          ) : (
            <p className="max-w-[24rem] text-meta text-ink-soft text-pretty">
              {state.status === "asking"
                ? t.evidence.asking
                : state.status === "answered"
                  ? t.evidence.none
                  : t.evidence.idle}
            </p>
          )}
        </div>
        <p className="mt-10 text-[0.75rem] leading-relaxed text-ink-faint">{t.evidence.onlyYours}</p>
      </section>
    </div>
  );
}

function EmptyState({
  firstName,
  recent,
  organizationId,
}: {
  firstName: string | null;
  recent: HistoryItem[];
  organizationId: string;
}) {
  const t = useI18n().t.assistant;
  const query = `?org=${encodeURIComponent(organizationId)}`;
  return (
    <section className="max-w-[40rem]">
      <h2 className="text-question font-semibold tracking-[-0.02em] text-balance">
        {firstName ? t.emptyTitleNamed(firstName) : t.emptyTitle}
      </h2>
      <p className="mt-4 font-reading text-answer text-ink-soft text-pretty">{t.emptyBody}</p>
      {recent.length ? (
        <div className="mt-10">
          <h3 className="text-meta font-medium text-ink-faint">{t.recentTitle}</h3>
          <ul className="mt-3 border-t border-line">
            {recent.map((item) => (
              <li key={item.id} className="border-b border-line">
                <Link
                  href={`/historico/${item.id}${query}`}
                  className="group flex items-center gap-3 py-3 text-body text-ink-soft transition-colors hover:text-ink"
                >
                  <History aria-hidden className="size-4 shrink-0 text-ink-faint group-hover:text-signal" strokeWidth={1.75} />
                  <span className="min-w-0 flex-1 truncate">{item.question}</span>
                  <ArrowUpRight aria-hidden className="size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function Pending({ question, startedAt }: { question: string; startedAt: number }) {
  const t = useI18n().t.assistant;
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);

  return (
    <section aria-busy="true" className="max-w-[40rem]">
      <h2 className="text-question font-semibold tracking-[-0.02em] text-balance">{question}</h2>
      <p className="mt-6 flex items-center gap-3 text-meta text-ink-soft">
        <span aria-hidden className="eka-pulse h-0.5 w-12 rounded-full bg-signal" />
        {t.asking}
        <span className="tabular-nums text-ink-faint">{t.elapsed(seconds)}</span>
      </p>
    </section>
  );
}

function Failure({ kind, onRetry }: { kind: AnswerErrorKind; onRetry: () => void }) {
  const { t: all } = useI18n();
  const t = all.assistant;
  return (
    <section role="alert" className="max-w-[40rem] border-l-2 border-danger pl-5">
      <h2 className="text-lead font-semibold">{t.errorTitle}</h2>
      <p className="mt-2 text-ink-soft">{t.errors[kind]}</p>
      {kind === "signedOut" ? (
        <a href="/auth/login" className="mt-4 inline-block font-medium text-signal underline underline-offset-4">
          {all.signIn.action}
        </a>
      ) : (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 font-medium text-signal underline underline-offset-4 hover:text-signal-deep"
        >
          {t.tryAgain}
        </button>
      )}
    </section>
  );
}
