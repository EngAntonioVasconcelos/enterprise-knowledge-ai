import "server-only";

import { cache } from "react";

import type { Organization } from "@/lib/api-types";
import { backendFetch, SignedOutError } from "@/lib/backend";

// The person's active organizations, or why they could not be loaded. An
// error is never shown as "no organization": that would send the person
// to ask for an invitation when the problem is their session.
export type AccessProblem = "signedOut" | "unverified" | "unavailable";

export type OrganizationsResult =
  | { organizations: Organization[] }
  | { problem: AccessProblem };

// The frame (navigation) and the page both need the list: one call per
// request, shared.
export const loadOrganizations = cache(fetchOrganizations);

async function fetchOrganizations(): Promise<OrganizationsResult> {
  let response: Response;
  try {
    response = await backendFetch("/organizations/");
  } catch (error) {
    return { problem: error instanceof SignedOutError ? "signedOut" : "unavailable" };
  }
  if (response.status === 401) return { problem: "signedOut" };
  if (response.status === 403) return { problem: "unverified" };
  if (!response.ok) return { problem: "unavailable" };
  const all = (await response.json()) as Organization[];
  return { organizations: all.filter((organization) => organization.status === "active") };
}
