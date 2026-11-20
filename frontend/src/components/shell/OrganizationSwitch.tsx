"use client";

import { useRouter } from "next/navigation";

import { messages } from "@/i18n/pt-PT";
import type { Organization } from "@/lib/api-types";

export function OrganizationSwitch({
  organizations,
  activeId,
}: {
  organizations: Organization[];
  activeId: string;
}) {
  const router = useRouter();
  return (
    <label className="mb-8 flex items-center gap-3 text-meta text-ink-soft">
      {messages.nav.organization}
      <select
        value={activeId}
        aria-label={messages.nav.switchOrganization}
        onChange={(event) => router.push(`/assistente?org=${event.target.value}`)}
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
