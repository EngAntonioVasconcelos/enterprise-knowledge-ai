/** The product mark: a page of text with one passage marked, which is
 * what the product does (answers that show the passage they came from). */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg
      aria-hidden
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className="shrink-0"
      focusable="false"
    >
      <rect width="24" height="24" rx="6" fill="var(--color-cobalt)" />
      <rect x="6" y="6.5" width="12" height="2" rx="1" fill="#fff" opacity="0.55" />
      <rect x="6" y="11" width="9" height="2" rx="1" fill="#fff" />
      <rect x="6" y="15.5" width="10.5" height="2" rx="1" fill="#fff" opacity="0.55" />
      <rect x="4" y="10" width="1.5" height="4" rx="0.75" fill="#fff" />
    </svg>
  );
}
