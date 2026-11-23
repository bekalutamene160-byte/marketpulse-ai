/** Accessible spinner: labelled for screen readers, respects reduced motion. */

export function Spinner({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-ink-400">
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-navy-600 border-t-gold-500"
      />
      {label}
    </span>
  );
}
