import "server-only";

import type { DashboardData } from "@/lib/api-types";
import { backendFetch } from "@/lib/backend";

export async function loadDashboard(organizationId: string): Promise<DashboardData | null> {
  try {
    const response = await backendFetch(`/organizations/${organizationId}/dashboard/`);
    return response.ok ? ((await response.json()) as DashboardData) : null;
  } catch {
    return null;
  }
}
