"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useState } from "react";

import {
  connectDatabase,
  type DatabaseState,
  disconnectDatabase,
  refreshDatabase,
} from "@/app/(app)/definicoes/actions";
import { useI18n } from "@/i18n/client";
import { type DatabaseSource, SSL_MODES } from "@/lib/api-types";

type Action = (state: DatabaseState, form: FormData) => Promise<DatabaseState>;

// While the worker reads a new database's tables, look again every few
// seconds, for about a minute.
const POLL_MS = 4000;
const POLL_TIMES = 15;

const FIELD =
  "mt-1.5 h-11 w-full rounded-control border border-line-strong bg-surface px-3.5 text-body text-ink outline-none transition-colors focus:border-signal";
const PRIMARY =
  "h-11 rounded-control bg-ink px-5 text-body font-medium text-white transition-colors hover:bg-signal-deep disabled:cursor-wait disabled:bg-ink-soft";
const SECONDARY =
  "h-9 rounded-control border border-line-strong bg-surface px-4 text-body font-medium text-ink transition-colors hover:border-signal hover:text-signal-deep disabled:cursor-wait disabled:opacity-60";

function reading(database: DatabaseSource): boolean {
  return !database.catalog && database.status !== "error";
}

// The databases the assistant may query, for owners and admins: connect one
// (its login is sent once and sealed), see what was read from it, read it
// again, or disconnect it.
export function DatabasesPanel({
  organizationId,
  databases,
  connect = connectDatabase,
  refresh = refreshDatabase,
  disconnect = disconnectDatabase,
}: {
  organizationId: string;
  databases: DatabaseSource[];
  connect?: Action;
  refresh?: Action;
  disconnect?: Action;
}) {
  const t = useI18n().t.databases;
  const router = useRouter();
  const [opened, setOpened] = useState(false);
  const [polls, setPolls] = useState(0);
  const [connectState, connectAction, connecting] = useActionState(
    async (previous: DatabaseState, form: FormData) => {
      const result = await connect(previous, form);
      // Close the form once connected; the new database shows in the list.
      if (result.done === "connected") {
        setOpened(false);
        setPolls(0);
      }
      return result;
    },
    {},
  );
  const pending = databases.some(reading);

  useEffect(() => {
    if (!pending || polls >= POLL_TIMES) return;
    const timer = setTimeout(() => {
      setPolls((count) => count + 1);
      router.refresh();
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [pending, polls, router]);

  return (
    <section aria-labelledby="databases-title" className="mt-16 border-t border-line pt-10">
      <h2 id="databases-title" className="text-lead font-semibold text-ink">
        {t.title}
      </h2>
      <p className="mt-2 max-w-[40rem] text-meta text-ink-soft text-pretty">{t.lead}</p>

      {databases.length ? (
        <ul className="mt-6 border-t border-line">
          {databases.map((database) => (
            <DatabaseRow
              key={database.id}
              organizationId={organizationId}
              database={database}
              refresh={refresh}
              disconnect={disconnect}
            />
          ))}
        </ul>
      ) : (
        <p className="mt-6 text-body text-ink-soft">{t.empty}</p>
      )}

      <div aria-live="polite" className="mt-3 text-meta">
        {connectState.done === "connected" && !opened ? <p className="text-checked">{t.connected}</p> : null}
      </div>

      {opened ? (
        <form action={connectAction} noValidate className="mt-6 max-w-2xl" autoComplete="off">
          <input type="hidden" name="organizationId" value={organizationId} />

          <aside className="border-l-2 border-signal bg-signal-wash px-4 py-3">
            <p className="font-semibold text-ink">{t.readOnlyTitle}</p>
            <p className="mt-1 text-meta text-ink-soft text-pretty">{t.readOnlyBody}</p>
          </aside>

          <div className="mt-6 grid gap-5 sm:grid-cols-6">
            <label className="block sm:col-span-6">
              <span className="font-medium text-ink">{t.name}</span>
              <span className="mt-0.5 block text-meta text-ink-faint">{t.nameHint}</span>
              <input name="name" required maxLength={200} className={FIELD} />
            </label>
            <label className="block sm:col-span-4">
              <span className="font-medium text-ink">{t.host}</span>
              <input name="host" required maxLength={253} spellCheck={false} className={FIELD} />
            </label>
            <label className="block sm:col-span-2">
              <span className="font-medium text-ink">{t.port}</span>
              <input name="port" inputMode="numeric" defaultValue="5432" required className={FIELD} />
            </label>
            <label className="block sm:col-span-3">
              <span className="font-medium text-ink">{t.database}</span>
              <input name="database" required maxLength={63} spellCheck={false} className={FIELD} />
            </label>
            <label className="block sm:col-span-3">
              <span className="font-medium text-ink">{t.schemas}</span>
              <input name="schemas" defaultValue="public" spellCheck={false} className={FIELD} />
              <span className="mt-1 block text-meta text-ink-faint">{t.schemasHint}</span>
            </label>
            <label className="block sm:col-span-6">
              <span className="font-medium text-ink">{t.sslmode}</span>
              <select name="sslmode" defaultValue="require" className={FIELD}>
                {SSL_MODES.map((mode) => (
                  <option key={mode} value={mode}>
                    {t.ssl[mode]}
                  </option>
                ))}
              </select>
            </label>
            <label className="block sm:col-span-3">
              <span className="font-medium text-ink">{t.username}</span>
              <input name="username" required autoComplete="off" spellCheck={false} className={FIELD} />
            </label>
            <label className="block sm:col-span-3">
              <span className="font-medium text-ink">{t.password}</span>
              <input name="password" type="password" required autoComplete="new-password" className={FIELD} />
              <span className="mt-1 block text-meta text-ink-faint">{t.passwordHint}</span>
            </label>
          </div>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <button type="submit" disabled={connecting} className={PRIMARY}>
              {connecting ? t.connecting : t.connect}
            </button>
            <button type="button" onClick={() => setOpened(false)} className="text-body text-ink-soft hover:text-ink">
              {t.cancel}
            </button>
          </div>
          <div aria-live="polite" className="mt-3 text-meta">
            {connectState.error ? (
              <p role="alert" className="text-danger">
                {t.errors[connectState.error]}
              </p>
            ) : null}
          </div>
        </form>
      ) : (
        <button type="button" onClick={() => setOpened(true)} className={"mt-6 " + PRIMARY}>
          {t.add}
        </button>
      )}
    </section>
  );
}

function DatabaseRow({
  organizationId,
  database,
  refresh,
  disconnect,
}: {
  organizationId: string;
  database: DatabaseSource;
  refresh: Action;
  disconnect: Action;
}) {
  const { locale, t: all } = useI18n();
  const t = all.databases;
  const [refreshState, refreshAction, refreshing] = useActionState(refresh, {});
  const [disconnectState, disconnectAction, disconnecting] = useActionState(disconnect, {});
  const [confirming, setConfirming] = useState(false);
  const [showTables, setShowTables] = useState(false);

  const settings = database.settings ?? {};
  const where = `${String(settings.host ?? "")}:${String(settings.port ?? 5432)} / ${String(settings.database ?? "")}`;
  const failed = database.status === "error";
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const tables = database.catalog?.tables ?? [];

  let status: string;
  if (failed) status = t.readFailed;
  else if (!database.catalog) status = t.reading;
  else {
    const when = database.catalogUpdatedAt ?? database.last_synced_at;
    status = t.tablesRead(tables.length, when ? date.format(new Date(when)) : "").trim();
  }

  const error = refreshState.error ?? disconnectState.error;
  const hidden = (
    <>
      <input type="hidden" name="organizationId" value={organizationId} />
      <input type="hidden" name="connectionId" value={database.id} />
    </>
  );

  return (
    <li className="border-b border-line py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{database.name}</p>
          <p className="mt-0.5 truncate text-meta text-ink-faint">{where}</p>
          <p className={"mt-1 text-meta text-pretty " + (failed ? "text-caution" : "text-ink-soft")}>{status}</p>
          {failed && database.last_error ? (
            <p className="mt-0.5 text-meta text-ink-faint break-words">{database.last_error}</p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {tables.length ? (
            <button
              type="button"
              aria-expanded={showTables}
              aria-controls={`tables-${database.id}`}
              onClick={() => setShowTables((value) => !value)}
              className={SECONDARY}
            >
              {showTables ? t.hideTables : t.showTables}
            </button>
          ) : null}
          <form action={refreshAction}>
            {hidden}
            <button type="submit" disabled={refreshing} className={SECONDARY}>
              {t.refresh}
            </button>
          </form>
          {!confirming ? (
            <button type="button" onClick={() => setConfirming(true)} className={SECONDARY}>
              {t.disconnect}
            </button>
          ) : null}
        </div>
      </div>

      {confirming ? (
        <form action={disconnectAction} className="mt-3 border-l-2 border-caution pl-4">
          {hidden}
          <p className="text-meta text-ink text-pretty">{t.confirmDisconnect(database.name)}</p>
          <div className="mt-2 flex gap-4">
            <button
              type="submit"
              disabled={disconnecting}
              className="h-9 rounded-control bg-danger px-4 text-body font-medium text-white disabled:cursor-wait disabled:opacity-60"
            >
              {t.confirm}
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="text-body text-ink-soft hover:text-ink">
              {t.cancel}
            </button>
          </div>
        </form>
      ) : null}

      <div aria-live="polite" className="mt-2 text-meta">
        {error ? (
          <p role="alert" className="text-danger">
            {t.errors[error]}
          </p>
        ) : refreshState.done ? (
          <p className="text-checked">{t.refreshing}</p>
        ) : null}
      </div>

      {showTables ? (
        <div id={`tables-${database.id}`} className="mt-3">
          <p className="text-meta text-ink-soft">{t.tablesHint}</p>
          <ul className="mt-3 grid gap-3 sm:grid-cols-2">
            {tables.map((table) => (
              <li key={`${table.schema}.${table.name}`} className="rounded-control border border-line px-3.5 py-3">
                <p className="font-medium text-ink">
                  {table.schema}.{table.name}
                  {table.kind === "view" ? <span className="ml-2 text-meta text-ink-faint">{t.view}</span> : null}
                </p>
                {table.comment ? <p className="mt-0.5 text-meta text-ink-soft">{table.comment}</p> : null}
                <p className="mt-1.5 text-meta text-ink-faint break-words">
                  {table.columns.map((column) => column.name).join(", ")}
                </p>
              </li>
            ))}
          </ul>
          {database.catalog?.truncated ? <p className="mt-3 text-meta text-caution">{t.truncated}</p> : null}
        </div>
      ) : null}
    </li>
  );
}
