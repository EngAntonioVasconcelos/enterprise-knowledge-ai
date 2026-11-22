"use server";

import { revalidatePath } from "next/cache";

import { RETENTION_DAYS, SSL_MODES } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type SettingsState = {
  error?: "invalidName" | "forbidden" | "signedOut" | "unavailable";
  saved?: boolean;
};

/** Saves what changed: the name, and how long questions are kept. */
export async function saveSettings(_previous: SettingsState, form: FormData): Promise<SettingsState> {
  const organizationId = String(form.get("organizationId") ?? "");
  if (!UUID.test(organizationId)) return { error: "unavailable" };

  const name = String(form.get("name") ?? "").trim().replace(/\s+/g, " ");
  const retention = Number(form.get("retention"));
  const changes: Record<string, unknown> = {};
  if (name !== String(form.get("currentName") ?? "")) {
    if (name.length < 2 || name.length > 150) return { error: "invalidName" };
    changes.name = name;
  }
  if (String(retention) !== String(form.get("currentRetention") ?? "")) {
    if (!(RETENTION_DAYS as readonly number[]).includes(retention)) return { error: "unavailable" };
    changes.history_retention_days = retention;
  }
  if (!Object.keys(changes).length) return { saved: true };

  try {
    const response = await backendFetch(`/organizations/${organizationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    });
    if (response.status === 401) return { error: "signedOut" };
    if (response.status === 403) return { error: "forbidden" };
    if (response.status === 422) return { error: "invalidName" };
    if (!response.ok) return { error: "unavailable" };
  } catch (error) {
    return { error: error instanceof SignedOutError ? "signedOut" : "unavailable" };
  }
  revalidatePath("/", "layout");
  return { saved: true };
}

export type DatabaseState = {
  error?: "invalid" | "nameTaken" | "refused" | "forbidden" | "signedOut" | "unavailable";
  done?: "connected" | "refreshing" | "disconnected";
};

const SCHEMA = /^[A-Za-z_][A-Za-z0-9_$]{0,62}$/;

function failure(status: number): DatabaseState | null {
  if (status === 401) return { error: "signedOut" };
  if (status === 403) return { error: "forbidden" };
  if (status === 409) return { error: "nameTaken" };
  if (status === 400) return { error: "refused" };
  if (status === 422) return { error: "invalid" };
  return null;
}

async function run(steps: () => Promise<DatabaseState>): Promise<DatabaseState> {
  try {
    return await steps();
  } catch (error) {
    return { error: error instanceof SignedOutError ? "signedOut" : "unavailable" };
  }
}

/** Connects a PostgreSQL database: the connection, then its login (sealed,
 *  never returned), then a first reading of its tables by the worker. */
export async function connectDatabase(_previous: DatabaseState, form: FormData): Promise<DatabaseState> {
  const organizationId = String(form.get("organizationId") ?? "");
  if (!UUID.test(organizationId)) return { error: "unavailable" };
  const text = (key: string) => String(form.get(key) ?? "").trim();
  const name = text("name").replace(/\s+/g, " ");
  const host = text("host");
  const port = Number(text("port") || "5432");
  const database = text("database");
  const sslmode = text("sslmode") || "require";
  const schemas = (text("schemas") || "public").split(",").map((schema) => schema.trim()).filter(Boolean);
  const username = text("username");
  const password = String(form.get("password") ?? "");
  if (
    !name || name.length > 200 || !host || host.length > 253 || /[\s/\\=?'"]/.test(host) ||
    !Number.isInteger(port) || port < 1 || port > 65535 || !database || database.length > 63 ||
    !(SSL_MODES as readonly string[]).includes(sslmode) || !schemas.length || schemas.length > 50 ||
    !schemas.every((schema) => SCHEMA.test(schema)) || !username || !password
  ) {
    return { error: "invalid" };
  }

  return run(async () => {
    const base = `/organizations/${organizationId}/connections`;
    const created = await backendFetch(`${base}/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "postgresql", name, settings: { host, port, database, sslmode, schemas } }),
    });
    if (!created.ok) return failure(created.status) ?? { error: "unavailable" };
    const { id } = (await created.json()) as { id: string };

    const sealed = await backendFetch(`${base}/${id}/credentials`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret: { username, password } }),
    });
    if (!sealed.ok) {
      // A connection without its login is of no use: take it away again.
      await backendFetch(`${base}/${id}/disconnect`, { method: "POST" });
      return failure(sealed.status) ?? { error: "unavailable" };
    }
    await backendFetch(`${base}/${id}/sync`, { method: "POST" });
    revalidatePath("/definicoes");
    return { done: "connected" };
  });
}

async function onConnection(form: FormData, path: string, done: DatabaseState["done"]): Promise<DatabaseState> {
  const organizationId = String(form.get("organizationId") ?? "");
  const connectionId = String(form.get("connectionId") ?? "");
  if (!UUID.test(organizationId) || !UUID.test(connectionId)) return { error: "unavailable" };
  return run(async () => {
    const response = await backendFetch(`/organizations/${organizationId}/connections/${connectionId}/${path}`, {
      method: "POST",
    });
    if (!response.ok) return failure(response.status) ?? { error: "unavailable" };
    revalidatePath("/definicoes");
    return { done };
  });
}

/** Asks the worker to read the database's tables again. */
export async function refreshDatabase(_previous: DatabaseState, form: FormData): Promise<DatabaseState> {
  return onConnection(form, "sync", "refreshing");
}

/** Disconnects a database for good: the assistant stops querying it. */
export async function disconnectDatabase(_previous: DatabaseState, form: FormData): Promise<DatabaseState> {
  return onConnection(form, "disconnect", "disconnected");
}
