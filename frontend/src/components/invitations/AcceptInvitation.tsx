"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useActionState, useEffect, useState } from "react";

import { acceptInvitation, type AcceptState } from "@/app/invitations/accept/actions";
import { useI18n } from "@/i18n/client";

export const TOKEN_KEY = "eka_invitation";
export const RETURN_TO = "/invitations/accept";

/**
 * Reads the token from the link (#token=...) and keeps it in this tab while
 * the person signs in. It is taken out of the address at once, so it does
 * not stay in the history or reach anyone through a shared screen.
 */
export function readToken(): string | null {
  const fromLink = new URLSearchParams(window.location.hash.slice(1)).get("token");
  try {
    if (fromLink) {
      sessionStorage.setItem(TOKEN_KEY, fromLink);
      window.history.replaceState(null, "", window.location.pathname);
      return fromLink;
    }
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return fromLink;
  }
}

function forget() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing kept.
  }
}

const button =
  "mt-8 inline-flex h-11 items-center rounded-control bg-ink px-6 text-body font-medium text-white transition-colors hover:bg-cobalt-deep disabled:cursor-wait disabled:bg-ink-soft";
const link = "font-medium text-cobalt underline underline-offset-4 hover:text-cobalt-deep";

export function AcceptInvitation({
  email,
  action = acceptInvitation,
}: {
  /** The signed-in account, or null before signing in. */
  email: string | null;
  action?: (state: AcceptState, form: FormData) => Promise<AcceptState>;
}) {
  const t = useI18n().t.invitation;
  const router = useRouter();
  // undefined: not read yet (first render, on the server too).
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [state, submit, pending] = useActionState(action, {});

  useEffect(() => {
    // The address after # exists only in the browser.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken(readToken());
  }, []);

  useEffect(() => {
    if (state.organizationId) {
      forget();
      router.push(`/assistente?org=${state.organizationId}`);
    }
    if (state.error === "invalid" || state.error === "alreadyMember") forget();
  }, [state, router]);

  if (token === undefined) return null;

  if (!token) {
    return <Message title={t.missingTitle} body={t.missingBody} />;
  }

  if (!email) {
    return (
      <Message title={t.title} body={t.signInBody}>
        <a href={`/auth/login?returnTo=${encodeURIComponent(RETURN_TO)}`} className={button}>
          {t.signIn}
        </a>
      </Message>
    );
  }

  if (state.error === "invalid") return <Message title={t.invalidTitle} body={t.invalidBody} />;
  if (state.error === "alreadyMember") {
    return (
      <Message title={t.alreadyTitle} body={t.alreadyBody}>
        <a href="/assistente" className={button}>
          {t.open}
        </a>
      </Message>
    );
  }
  if (state.organizationId) return <Message title={t.joined} body="" />;

  return (
    <Message title={t.title} body={t.as(email)}>
      <form action={submit}>
        <input type="hidden" name="token" value={token} />
        <button type="submit" disabled={pending} className={button}>
          {pending ? t.accepting : t.accept}
        </button>
      </form>
      {state.error ? (
        <p role="alert" className="mt-4 text-body text-danger text-pretty">
          {t.errors[state.error]}{" "}
          {state.error === "otherEmail" || state.error === "signedOut" || state.error === "unverified" ? (
            <a href="/auth/logout" className={link}>
              {t.signOut}
            </a>
          ) : null}
        </p>
      ) : null}
    </Message>
  );
}

function Message({ title, body, children }: { title: string; body: string; children?: ReactNode }) {
  return (
    <section className="py-20">
      <h1 className="text-question font-semibold tracking-[-0.02em] text-balance">{title}</h1>
      {body ? <p className="mt-4 text-lead text-ink-soft text-pretty">{body}</p> : null}
      {children}
    </section>
  );
}
