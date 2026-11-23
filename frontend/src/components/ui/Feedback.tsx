/** Card, page header, status badge and the empty/error states every view needs. */

import type { ReactNode } from "react";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={"rounded-card border border-navy-700 bg-navy-900 p-5 " + (className ?? "")}>
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string | undefined }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold text-ink-50">{title}</h1>
      {subtitle !== undefined && <p className="mt-1 text-sm text-ink-400">{subtitle}</p>}
    </header>
  );
}

export type StatusTone = "ok" | "warn" | "error" | "info";

const TONES: Record<StatusTone, string> = {
  ok: "bg-navy-800 text-status-ok border-status-ok/40",
  warn: "bg-navy-800 text-status-warn border-status-warn/40",
  error: "bg-navy-800 text-status-error border-status-error/40",
  info: "bg-navy-800 text-status-info border-status-info/40",
};

/** Status is ALWAYS text + color (never color alone — accessibility). */
export function StatusBadge({ tone, label }: { tone: StatusTone; label: string }) {
  return (
    <span className={"inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium " + TONES[tone]}>
      {label}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-card border border-dashed border-navy-600 p-8 text-center">
      <p className="font-medium text-ink-200">{title}</p>
      {hint !== undefined && <p className="mt-1 text-sm text-ink-400">{hint}</p>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-card border border-status-error/40 bg-navy-900 p-6">
      <p className="font-medium text-ink-200">{message}</p>
      {onRetry !== undefined && (
        <button
          type="button"
          className="mt-3 rounded-md border border-navy-600 px-3 py-1.5 text-sm text-ink-200 hover:bg-navy-800"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  );
}
