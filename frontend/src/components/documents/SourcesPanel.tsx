"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect } from "react";

import {
  connectGoogleDrive,
  type SourceActionState,
  syncSource,
} from "@/app/(app)/documentos/actions";
import { useI18n } from "@/i18n/client";
import type { Connection } from "@/lib/api-types";

type Action = (state: SourceActionState, form: FormData) => Promise<SourceActionState>;

// Where documents come from, besides the files sent here: for now, the
// organization's Google Drive. Connecting opens Google's own consent page.
export function SourcesPanel({
  organizationId,
  drive,
  connect = connectGoogleDrive,
  sync = syncSource,
}: {
  organizationId: string;
  drive: Connection | null;
  connect?: Action;
  sync?: Action;
}) {
  const { locale, t: all } = useI18n();
  const t = all.documents.sources;
  const router = useRouter();
  const [connectState, connectAction, connecting] = useActionState(connect, {});
  const [syncState, syncAction, syncing] = useActionState(sync, {});
  const synced = Boolean(syncState.done);

  // Each queued sync: look again, so the new state and documents show.
  useEffect(() => {
    if (syncState.done) router.refresh();
  }, [syncState, router]);

  const error = connectState.error ?? syncState.error;
  const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const refused = drive?.status === "error";

  let status: string;
  if (!drive) status = t.driveBody;
  else if (refused) status = t.refused;
  else if (!drive.last_synced_at) status = t.firstSync;
  else status = t.lastSynced(date.format(new Date(drive.last_synced_at)));

  return (
    <section aria-labelledby="sources-title" className="mt-10">
      <h2 id="sources-title" className="text-meta font-semibold text-ink-soft">
        {t.title}
      </h2>
      <div className="mt-3 flex flex-col gap-4 border-t border-b border-line py-4 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{t.drive}</p>
          <p className={"mt-0.5 text-meta text-pretty " + (refused ? "text-caution" : "text-ink-soft")}>
            {status}
          </p>
        </div>
        <div className="flex shrink-0 gap-3">
          {!drive || refused ? (
            <form action={connectAction}>
              <input type="hidden" name="organizationId" value={organizationId} />
              <button
                type="submit"
                disabled={connecting}
                className="h-9 rounded-control bg-ink px-4 text-body font-medium text-white transition-colors hover:bg-cobalt-deep disabled:cursor-wait disabled:bg-ink-soft"
              >
                {connecting ? t.connecting : refused ? t.reconnect : t.connect}
              </button>
            </form>
          ) : (
            <form action={syncAction}>
              <input type="hidden" name="organizationId" value={organizationId} />
              <input type="hidden" name="connectionId" value={drive.id} />
              <button
                type="submit"
                disabled={syncing}
                className="h-9 rounded-control border border-line-strong bg-surface px-4 text-body font-medium text-ink transition-colors hover:border-cobalt hover:text-cobalt-deep disabled:cursor-wait disabled:opacity-60"
              >
                {t.syncNow}
              </button>
            </form>
          )}
        </div>
      </div>
      <div aria-live="polite" className="mt-2 text-meta">
        {error ? (
          <p role="alert" className="text-danger">
            {t.errors[error]}
          </p>
        ) : synced ? (
          <p className="text-checked">{t.syncRequested}</p>
        ) : null}
      </div>
    </section>
  );
}
