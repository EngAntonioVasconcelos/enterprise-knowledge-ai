"use client";

import { useActionState } from "react";

import {
  createOrganization,
  type CreateOrganizationState,
} from "@/app/(app)/assistente/actions";
import { useI18n } from "@/i18n/client";

// The first thing a new account does: name its organization. One field;
// the technical name is made from it.
export function CreateOrganization({
  action = createOrganization,
}: {
  action?: (state: CreateOrganizationState, form: FormData) => Promise<CreateOrganizationState>;
}) {
  const t = useI18n().t.onboarding;
  const [state, submit, pending] = useActionState(action, {});
  const error = state.error ? t.errors[state.error] : null;

  return (
    <form action={submit} className="mt-8 max-w-md" noValidate>
      <label htmlFor="organization-name" className="block font-medium text-ink">
        {t.nameLabel}
      </label>
      <p id="organization-name-hint" className="mt-1 text-meta text-ink-faint">
        {t.nameHint}
      </p>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row">
        <input
          id="organization-name"
          name="name"
          required
          minLength={2}
          maxLength={150}
          autoComplete="organization"
          defaultValue={state.name ?? ""}
          aria-describedby={error ? "organization-name-hint organization-error" : "organization-name-hint"}
          aria-invalid={state.error === "invalid" || undefined}
          className="h-11 w-full min-w-0 rounded-control sm:flex-1 border border-line-strong bg-surface px-3.5 text-body text-ink outline-none transition-colors placeholder:text-ink-faint focus:border-signal"
          placeholder={t.namePlaceholder}
        />
        <button
          type="submit"
          disabled={pending}
          className="h-11 shrink-0 rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-signal-deep disabled:cursor-wait disabled:bg-ink-soft"
        >
          {pending ? t.creating : t.create}
        </button>
      </div>
      {error ? (
        <p id="organization-error" role="alert" className="mt-3 text-meta text-danger">
          {error}
        </p>
      ) : null}
    </form>
  );
}
