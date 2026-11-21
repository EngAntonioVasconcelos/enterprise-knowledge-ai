import "server-only";

import type { DashboardData, GapsData } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

export async function loadDashboard(organizationId: string): Promise<DashboardData | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/dashboard/`);
    return response.ok ? ((await response.json()) as DashboardData) : null;
  } catch {
    return null;
  }
}

export async function loadGaps(organizationId: string): Promise<GapsData | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/dashboard/gaps`);
    return response.ok ? ((await response.json()) as GapsData) : null;
  } catch {
    return null;
  }
}
