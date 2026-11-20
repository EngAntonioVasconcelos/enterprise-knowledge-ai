"use client";

import { useEffect, useRef, useState } from "react";

import { AnswerDocument } from "@/components/assistant/AnswerDocument";
import { Composer } from "@/components/assistant/Composer";
import { useI18n } from "@/i18n/client";
import { type Answer, type AnswerErrorKind, errorKindFromStatus } from "@/lib/api-types";


type State =
  | { status: "idle" }
  | { status: "asking"; question: string; startedAt: number }
  | { status: "answered"; answer: Answer }
  | { status: "failed"; question: string; kind: AnswerErrorKind };

export async function requestAnswer(
  organizationId: string,
  question: string,
  signal?: AbortSignal,
): Promise<{ answer: Answer } | { error: AnswerErrorKind }> {
  let response: Response;
  try {
    response = await fetch("/api/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ organizationId, question }),
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
}: {
  organizationId: string;
  organizationName: string;
}) {
  const t = useI18n().t.assistant;
  const [state, setState] = useState<State>({ status: "idle" });
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function ask(question: string) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setState({ status: "asking", question, startedAt: Date.now() });
    const result = await requestAnswer(organizationId, question, current.signal);
    if (current.signal.aborted) return;
    setState(
      "answer" in result
        ? { status: "answered", answer: result.answer }
        : { status: "failed", question, kind: result.error },
    );
  }

  const busy = state.status === "asking";

  return (
    <div>
      <h1 className="sr-only">{`${t.title}, ${organizationName}`}</h1>
      <Composer onAsk={ask} busy={busy} />

      <div aria-live="polite" className="mt-12">
        {state.status === "idle" ? <EmptyState /> : null}
        {state.status === "asking" ? (
          <Pending question={state.question} startedAt={state.startedAt} />
        ) : null}
        {state.status === "answered" ? <AnswerDocument answer={state.answer} /> : null}
        {state.status === "failed" ? (
          <Failure kind={state.kind} onRetry={() => ask(state.question)} />
        ) : null}
      </div>
    </div>
  );
}

function EmptyState() {
  const t = useI18n().t.assistant;
  return (
    <section className="max-w-[38rem]">
      <h2 className="text-question font-semibold tracking-[-0.02em]">{t.emptyTitle}</h2>
      <p className="mt-4 font-reading text-answer text-ink-soft text-pretty">{t.emptyBody}</p>
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
        <span aria-hidden className="eka-pulse h-0.5 w-12 rounded-full bg-cobalt" />
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
        <a href="/auth/login" className="mt-4 inline-block font-medium text-cobalt underline underline-offset-4">
          {all.signIn.action}
        </a>
      ) : (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 font-medium text-cobalt underline underline-offset-4 hover:text-cobalt-deep"
        >
          {t.tryAgain}
        </button>
      )}
    </section>
  );
}
