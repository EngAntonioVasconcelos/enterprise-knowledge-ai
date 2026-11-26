"use client";

import { useState } from "react";

/** Up to two initials from a name, or from the e-mail when there is none. */
export function initials(name: string | null | undefined, email = ""): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  const first = words[0] ?? "";
  const last = words.length > 1 ? (words[words.length - 1] ?? "") : "";
  if (last) return (first.charAt(0) + last.charAt(0)).toUpperCase();
  if (first) return first.slice(0, 2).toUpperCase();
  return email.slice(0, 2).toUpperCase() || "?";
}

// The account photo comes from the sign-in (Google or Auth0); without one,
// or if it fails to load, the initials. Decorative: the name is always
// written next to it.
export function Avatar({
  name,
  email,
  picture,
  size = "md",
}: {
  name: string | null | undefined;
  email?: string;
  picture?: string | null;
  size?: "sm" | "md";
}) {
  const [broken, setBroken] = useState(false);
  const box = size === "sm" ? "size-7 text-[0.6875rem]" : "size-9 text-meta";
  if (picture && !broken) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- an outside address, already sized
      <img
        src={picture}
        alt=""
        aria-hidden
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className={`${box} shrink-0 rounded-full bg-line object-cover`}
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`${box} inline-flex shrink-0 items-center justify-center rounded-full bg-signal-wash font-semibold text-signal-deep`}
    >
      {initials(name, email)}
    </span>
  );
}
