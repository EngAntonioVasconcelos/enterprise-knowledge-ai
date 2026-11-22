import "server-only";

import type { Connection, DatabaseCatalog, DatabaseSource } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

export const DATABASE_PROVIDER = "postgresql";

/** The organization's connected databases, each with what was read from it.
 *  Null when the caller cannot manage connections. */
export async function loadDatabases(organizationId: string): Promise<DatabaseSource[] | null> {
  const response = await backendFetch(`/organizations/${organizationId}/connections/`);
  if (!response.ok) return null;
  const connections = ((await response.json()) as Connection[]).filter(
    (connection) => connection.provider === DATABASE_PROVIDER && !connection.disconnected_at,
  );
  return Promise.all(
    connections.map(async (connection) => {
      const catalog = await backendFetch(`/organizations/${organizationId}/connections/${connection.id}/catalog`);
      const body = catalog.ok
        ? ((await catalog.json()) as { catalog: DatabaseCatalog | null; catalog_updated_at: string | null })
        : { catalog: null, catalog_updated_at: null };
      return { ...connection, catalog: body.catalog, catalogUpdatedAt: body.catalog_updated_at };
    }),
  );
}
