/** ShelfIQ's mark: three shelves, stocked to different levels. Drawn, not a letter in a box. */
export function ShelfMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={className}
    >
      <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3 9h18M3 15h18" stroke="currentColor" strokeWidth="1.6" />
      <rect x="6" y="5.5" width="11" height="2" rx="0.5" fill="currentColor" />
      <rect x="6" y="11.5" width="6" height="2" rx="0.5" fill="currentColor" />
      <rect x="6" y="17.5" width="2.5" height="2" rx="0.5" fill="var(--negative)" />
    </svg>
  );
}
