"use client";

import { Check, Copy } from "lucide-react";
import { useActionState, useEffect, useRef, useState } from "react";

import {
  changeRole,
  type ChangeState,
  invitePerson,
  type InviteState,
  removePerson,
  revokeInvitation,
} from "@/app/(app)/pessoas/actions";
import { Avatar } from "@/components/shell/Avatar";
import { useI18n } from "@/i18n/client";
import type { Invitation, Member, Role } from "@/lib/api-types";
import { assignableRoles, canManage } from "@/lib/roles";

type Action<S> = (state: S, form: FormData) => Promise<S>;

export type PeopleActions = {
  invite: Action<InviteState>;
  change: Action<ChangeState>;
  remove: Action<ChangeState>;
  revoke: Action<ChangeState>;
};

const DEFAULT_ACTIONS: PeopleActions = {
  invite: invitePerson,
  change: changeRole,
  remove: removePerson,
  revoke: revokeInvitation,
};

type Props = {
  organizationId: string;
  actorRole: Role;
  /** The signed-in person, to mark their own row and keep it safe. */
  selfEmail: string;
  selfPicture?: string | null;
  members: Member[];
  invitations: Invitation[];
  actions?: PeopleActions;
};

const field =
  "h-11 rounded-control border border-line-strong bg-surface px-3.5 text-body text-ink outline-none transition-colors focus:border-cobalt";
const primary =
  "h-11 shrink-0 rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-cobalt-deep disabled:cursor-wait disabled:bg-ink-soft";
const quiet =
  "text-meta font-medium text-ink-soft underline-offset-4 hover:text-ink hover:underline disabled:cursor-wait disabled:opacity-60";

export function PeopleView({
  organizationId,
  actorRole,
  selfEmail,
  selfPicture = null,
  members,
  invitations,
  actions = DEFAULT_ACTIONS,
}: Props) {
  const { locale, t: all } = useI18n();
  const t = all.people;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });
  const sorted = [...members].sort((a, b) => {
    const self = Number(b.email.toLowerCase() === selfEmail) - Number(a.email.toLowerCase() === selfEmail);
    return self || (a.full_name ?? a.email).localeCompare(b.full_name ?? b.email, locale);
  });

  return (
    <div>
      <h1 className="text-question font-semibold tracking-[-0.02em]">{t.title}</h1>
      <p className="mt-3 max-w-[40rem] text-lead text-ink-soft text-pretty">{t.lead}</p>

      <InviteForm organizationId={organizationId} actorRole={actorRole} action={actions.invite} />

      <section aria-labelledby="members-heading" className="mt-12">
        <h2 id="members-heading" className="text-lead font-semibold">
          {t.membersTitle(members.length)}
        </h2>
        <ul className="mt-4 border-t border-line">
          {sorted.map((member) => {
            const self = member.email.toLowerCase() === selfEmail;
            return (
              <MemberRow
                key={member.id}
                organizationId={organizationId}
                actorRole={actorRole}
                member={member}
                self={self}
                picture={self ? selfPicture : null}
                actions={actions}
              />
            );
          })}
        </ul>
      </section>

      {invitations.length ? (
        <section aria-labelledby="invitations-heading" className="mt-12">
          <h2 id="invitations-heading" className="text-lead font-semibold">
            {t.invitationsTitle}
          </h2>
          <ul className="mt-4 border-t border-line">
            {invitations.map((invitation) => (
              <InvitationRow
                key={invitation.id}
                organizationId={organizationId}
                invitation={invitation}
                expires={date.format(new Date(invitation.expires_at))}
                action={actions.revoke}
                allowed={canManage(actorRole, invitation.role)}
              />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function InviteForm({
  organizationId,
  actorRole,
  action,
}: {
  organizationId: string;
  actorRole: Role;
  action: Action<InviteState>;
}) {
  const t = useI18n().t.people;
  const [state, submit, pending] = useActionState(action, {});
  const [role, setRole] = useState<Role>("member");
  const form = useRef<HTMLFormElement>(null);
  const error = state.error ? t.errors[state.error] : null;

  // A sent invitation clears the field for the next one.
  useEffect(() => {
    if (state.invited) form.current?.reset();
  }, [state.invited]);

  return (
    <section aria-labelledby="invite-heading" className="mt-8 rounded-panel border border-line-strong bg-surface p-6">
      <h2 id="invite-heading" className="font-semibold text-ink">
        {t.inviteTitle}
      </h2>
      <form ref={form} action={submit} noValidate className="mt-4">
        <input type="hidden" name="organizationId" value={organizationId} />
        <div className="flex flex-col gap-3 md:flex-row">
          <label className="min-w-0 md:flex-1">
            <span className="sr-only">{t.emailLabel}</span>
            <input
              name="email"
              type="email"
              required
              autoComplete="off"
              spellCheck={false}
              defaultValue={state.email ?? ""}
              placeholder={t.emailPlaceholder}
              aria-invalid={state.error === "invalidEmail" || undefined}
              aria-describedby={error ? "invite-error" : "invite-role-hint"}
              className={`${field} w-full`}
            />
          </label>
          <label className="md:w-48">
            <span className="sr-only">{t.roleLabel}</span>
            <select
              name="role"
              value={role}
              onChange={(event) => setRole(event.target.value as Role)}
              aria-describedby="invite-role-hint"
              className={`${field} w-full`}
            >
              {assignableRoles(actorRole).map((value) => (
                <option key={value} value={value}>
                  {t.roles[value]}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={pending} className={primary}>
            {pending ? t.inviting : t.invite}
          </button>
        </div>
        <p id="invite-role-hint" className="mt-2 text-meta text-ink-faint">
          {t.roleHints[role]}
        </p>
      </form>
      <div aria-live="polite">
        {error ? (
          <p id="invite-error" role="alert" className="mt-3 text-meta text-danger">
            {error}
          </p>
        ) : null}
        {state.invited ? <Invited email={state.invited.email} token={state.invited.token} /> : null}
      </div>
    </section>
  );
}

/** After inviting: who, and, while e-mails are not sent, the link to pass on. */
function Invited({ email, token }: { email: string; token: string | null }) {
  const t = useI18n().t.people;
  const [copied, setCopied] = useState(false);
  if (!token) return <p className="mt-4 border-l-2 border-checked pl-4 text-body text-checked">{t.sent(email)}</p>;

  const link = `${window.location.origin}/invitations/accept#token=${token}`;
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="mt-4 border-l-2 border-caution pl-4">
      <p className="text-body text-ink">{t.created(email)}</p>
      <p className="mt-1 text-meta text-ink-soft text-pretty">{t.noEmail}</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          readOnly
          value={link}
          aria-label={t.linkLabel}
          onFocus={(event) => event.currentTarget.select()}
          className={`${field} min-w-0 font-mono text-meta sm:flex-1`}
        />
        <button
          type="button"
          onClick={() => void copy()}
          className="inline-flex h-11 shrink-0 items-center gap-2 rounded-control border border-line-strong bg-surface px-4 text-body font-medium text-ink transition-colors hover:border-ink"
        >
          {copied ? <Check aria-hidden className="size-4 text-checked" /> : <Copy aria-hidden className="size-4" />}
          {copied ? t.copied : t.copy}
        </button>
      </div>
    </div>
  );
}

function MemberRow({
  organizationId,
  actorRole,
  member,
  self,
  picture,
  actions,
}: {
  organizationId: string;
  actorRole: Role;
  member: Member;
  self: boolean;
  picture: string | null;
  actions: PeopleActions;
}) {
  const t = useI18n().t.people;
  const role = member.membership.role;
  const name = member.full_name || member.email;
  // Your own access is not changed from here: no locking yourself out.
  const editable = !self && canManage(actorRole, role);
  const [changeState, change, changing] = useActionState(actions.change, {});
  const [removeState, remove, removing] = useActionState(actions.remove, {});
  const [confirming, setConfirming] = useState(false);
  const roleForm = useRef<HTMLFormElement>(null);
  const error = removeState.error ?? changeState.error;

  // A refused change puts the menu back on the role the person still has.
  useEffect(() => {
    if (changeState.error) roleForm.current?.reset();
  }, [changeState]);

  return (
    <li className="flex flex-col gap-3 border-b border-line py-4 sm:flex-row sm:flex-wrap sm:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <Avatar name={member.full_name} email={member.email} picture={picture} />
        <div className="min-w-0">
          <p className="truncate font-medium text-ink" title={name}>
            {name}
            {self ? <span className="font-normal text-ink-faint"> {t.you}</span> : null}
          </p>
          {member.full_name ? (
            <p className="truncate text-meta text-ink-soft" title={member.email}>
              {member.email}
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-4 pl-12 sm:pl-0">
        {editable ? (
          <form ref={roleForm} action={change}>
            <input type="hidden" name="organizationId" value={organizationId} />
            <input type="hidden" name="userId" value={member.id} />
            <label>
              <span className="sr-only">{t.roleOf(name)}</span>
              <select
                name="role"
                defaultValue={role}
                disabled={changing}
                onChange={() => roleForm.current?.requestSubmit()}
                className="h-9 w-36 rounded-control border border-line bg-surface px-2 text-meta text-ink outline-none focus:border-cobalt disabled:cursor-wait"
              >
                {assignableRoles(actorRole).map((value) => (
                  <option key={value} value={value}>
                    {t.roles[value]}
                  </option>
                ))}
              </select>
            </label>
          </form>
        ) : (
          <span className="w-36 px-2 text-meta text-ink-soft">{t.roles[role]}</span>
        )}

        <span className="w-20 text-right">
          {editable && !confirming ? (
            <button type="button" onClick={() => setConfirming(true)} className={quiet}>
              {t.remove}
            </button>
          ) : null}
        </span>
      </div>

      {confirming ? (
        <form action={remove} className="flex flex-wrap items-center gap-3 pl-12 sm:basis-full sm:justify-end">
          <input type="hidden" name="organizationId" value={organizationId} />
          <input type="hidden" name="userId" value={member.id} />
          <p className="text-meta text-ink">{t.removeConfirm(name)}</p>
          <button
            type="submit"
            disabled={removing}
            className="h-9 rounded-control bg-danger px-3 text-meta font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-wait disabled:opacity-60"
          >
            {removing ? t.removing : t.removeYes}
          </button>
          <button type="button" onClick={() => setConfirming(false)} className={quiet}>
            {t.cancel}
          </button>
        </form>
      ) : null}

      {error ? (
        <p role="alert" className="pl-12 text-meta text-danger sm:basis-full">
          {t.errors[error]}
        </p>
      ) : null}
    </li>
  );
}

function InvitationRow({
  organizationId,
  invitation,
  expires,
  action,
  allowed,
}: {
  organizationId: string;
  invitation: Invitation;
  expires: string;
  action: Action<ChangeState>;
  allowed: boolean;
}) {
  const t = useI18n().t.people;
  const [state, submit, pending] = useActionState(action, {});
  return (
    <li className="flex flex-col gap-2 border-b border-line py-4 sm:flex-row sm:flex-wrap sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1">
        <p className="truncate text-ink" title={invitation.email}>
          {invitation.email}
        </p>
        <p className="text-meta text-ink-soft">
          {t.roles[invitation.role]}, {t.expires(expires)}
        </p>
      </div>
      {allowed ? (
        <form action={submit}>
          <input type="hidden" name="organizationId" value={organizationId} />
          <input type="hidden" name="invitationId" value={invitation.id} />
          <button type="submit" disabled={pending} className={quiet}>
            {pending ? t.revoking : t.revoke}
          </button>
        </form>
      ) : null}
      {state.error ? (
        <p role="alert" className="text-meta text-danger sm:basis-full">
          {t.errors[state.error]}
        </p>
      ) : null}
    </li>
  );
}
