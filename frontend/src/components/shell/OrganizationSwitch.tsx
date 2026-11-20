"use client";

import { useRouter } from "next/navigation";

import { useI18n } from "@/i18n/client";
import type { Organization } from "@/lib/api-types";

export function OrganizationSwitch({
  organizations,
  activeId,
  basePath = "/assistente",
}: {
  organizations: Organization[];
  activeId: string;
  basePath?: string;
}) {
  const router = useRouter();
  const { t } = useI18n();
  return (
    <label className="mb-8 flex items-center gap-3 text-meta text-ink-soft">
      {t.nav.organization}
      <select
        value={activeId}
        aria-label={t.nav.switchOrganization}
        onChange={(event) => router.push(`${basePath}?org=${event.target.value}`)}
        className="rounded-control border border-line bg-surface px-2 py-1 text-body text-ink"
      >
        {organizations.map((organization) => (
          <option key={organization.id} value={organization.id}>
            {organization.name}
          </option>
        ))}
      </select>
    </label>
  );
}
