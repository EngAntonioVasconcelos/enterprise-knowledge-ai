import type { ReactNode } from "react";

import { AppFrame } from "@/components/shell/AppFrame";
import { getMessages } from "@/i18n/server";
import { auth0 } from "@/lib/auth0";
import { loadOrganizations } from "@/lib/organizations";
import { managesPeople } from "@/lib/roles";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const [session, { t }, result] = await Promise.all([auth0.getSession(), getMessages(), loadOrganizations()]);
  const organizations = "organizations" in result ? result.organizations : [];
  return (
    <AppFrame
      t={t}
      organizations={organizations}
      managed={organizations.filter((o) => managesPeople(o.role)).map((o) => o.id)}
      account={{ name: session?.user.name, email: session?.user.email ?? "", picture: session?.user.picture }}
    >
      {children}
    </AppFrame>
  );
}
