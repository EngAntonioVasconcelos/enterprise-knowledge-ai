import type { Role } from "@/lib/api-types";

// Who may do what with people. The backend decides; these rules only keep
// the interface from offering what it would refuse.

export const ROLES: Role[] = ["owner", "admin", "member", "viewer"];

/** Owners and admins see and manage the people of an organization. */
export function managesPeople(role: Role | undefined): boolean {
  return role === "owner" || role === "admin";
}

/** The roles a person may give: only an owner gives owner or admin. */
export function assignableRoles(actor: Role): Role[] {
  return actor === "owner" ? ROLES : ["member", "viewer"];
}

/** Whether the actor may change or remove someone with this role. */
export function canManage(actor: Role, target: Role): boolean {
  if (actor === "owner") return true;
  return actor === "admin" && (target === "member" || target === "viewer");
}
