"use client";

import { useActionState, useState } from "react";

import { saveSettings, type SettingsState } from "@/app/(app)/definicoes/actions";
import { useI18n } from "@/i18n/client";
import { RETENTION_DAYS, type RetentionDays } from "@/lib/api-types";

type Action = (state: SettingsState, form: FormData) => Promise<SettingsState>;

export function SettingsForm({
  organizationId,
  name,
  retentionDays,
  action = saveSettings,
}: {
  organizationId: string;
  name: string;
  retentionDays: number;
  action?: Action;
}) {
  const t = useI18n().t.settings;
  const [state, submit, pending] = useActionState(action, {});
  const [retention, setRetention] = useState<number>(retentionDays);
  const shorter = retention < retentionDays;

  return (
    <form action={submit} noValidate>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>

      <input type="hidden" name="organizationId" value={organizationId} />
      <input type="hidden" name="currentName" value={name} />
      <input type="hidden" name="currentRetention" value={retentionDays} />

      <section className="mt-10">
        <label htmlFor="organization-name" className="block font-semibold text-ink">
          {t.nameLabel}
        </label>
        <p id="organization-name-hint" className="mt-1 text-meta text-ink-faint">
          {t.nameHint}
        </p>
        <input
          id="organization-name"
          name="name"
          defaultValue={name}
          required
          minLength={2}
          maxLength={150}
          autoComplete="organization"
          aria-invalid={state.error === "invalidName" || undefined}
          aria-describedby="organization-name-hint"
          className="mt-3 h-11 w-full max-w-md rounded-control border border-line-strong bg-surface px-3.5 text-body text-ink outline-none transition-colors focus:border-cobalt"
        />
      </section>

      <fieldset className="mt-10">
        <legend className="font-semibold text-ink">{t.historyLabel}</legend>
        <p className="mt-1 max-w-[40rem] text-meta text-ink-soft text-pretty">{t.historyHint}</p>
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {RETENTION_DAYS.map((days) => (
            <label
              key={days}
              className={
                "flex cursor-pointer items-center gap-2.5 rounded-control border px-3.5 py-3 text-body transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-cobalt " +
                (retention === days ? "border-cobalt bg-cobalt-wash text-ink" : "border-line-strong bg-surface text-ink-soft hover:border-ink-soft")
              }
            >
              <input
                type="radio"
                name="retention"
                value={days}
                checked={retention === days}
                onChange={() => setRetention(days)}
                className="accent-[var(--color-cobalt)]"
              />
              {t.retention[days as RetentionDays]}
            </label>
          ))}
        </div>
        {shorter ? (
          <p role="status" className="mt-3 max-w-[40rem] border-l-2 border-caution pl-4 text-meta text-caution">
            {retention === 0 ? t.stopWarning : t.shorterWarning}
          </p>
        ) : null}
      </fieldset>

      <div className="mt-10 flex flex-wrap items-center gap-4" aria-live="polite">
        <button
          type="submit"
          disabled={pending}
          className="h-11 rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-cobalt-deep disabled:cursor-wait disabled:bg-ink-soft"
        >
          {pending ? t.saving : t.save}
        </button>
        {state.saved && !pending ? <p className="text-meta text-checked">{t.saved}</p> : null}
        {state.error ? (
          <p role="alert" className="text-meta text-danger">
            {t.errors[state.error]}
          </p>
        ) : null}
      </div>
    </form>
  );
}
