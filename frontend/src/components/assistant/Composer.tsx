"use client";

import { type FormEvent, type KeyboardEvent, useState } from "react";

import { useI18n } from "@/i18n/client";

const MAX = 500;

export function Composer({
  onAsk,
  busy,
  placeholder,
}: {
  onAsk: (question: string) => void;
  busy: boolean;
  placeholder?: string;
}) {
  const t = useI18n().t.assistant;
  const [question, setQuestion] = useState("");
  const trimmed = question.trim();

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!trimmed || busy) return;
    onAsk(trimmed);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="max-w-[46rem]">
      <label htmlFor="question" className="sr-only">
        {t.title}
      </label>
      <div className="rounded-panel border border-line-strong bg-surface transition-colors focus-within:border-signal">
        <textarea
          id="question"
          name="question"
          rows={2}
          maxLength={MAX}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t.placeholder}
          className="block w-full resize-none bg-transparent px-5 pt-4 pb-2 text-lead outline-none placeholder:text-ink-faint [field-sizing:content]"
        />
        <div className="flex items-center justify-end gap-4 px-5 pb-3 sm:justify-between">
          <p className="hidden text-meta text-ink-faint sm:block">{t.hint}</p>
          <button
            type="submit"
            disabled={!trimmed || busy}
            className="h-9 shrink-0 rounded-control bg-ink px-4 text-body font-medium text-white transition-colors hover:bg-signal-deep disabled:cursor-not-allowed disabled:bg-line-strong"
          >
            {t.ask}
          </button>
        </div>
      </div>
    </form>
  );
}
