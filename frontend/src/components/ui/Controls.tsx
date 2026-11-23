/** Buttons and form fields with consistent focus rings and disabled states. */

import type { ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-gold-500 text-navy-950 hover:bg-gold-400",
  secondary: "border border-navy-600 text-ink-200 hover:bg-navy-800",
  ghost: "text-ink-200 hover:bg-navy-800",
};

export function Button({
  variant = "primary",
  type = "button",
  children,
  ...rest
}: {
  variant?: ButtonVariant;
  type?: "button" | "submit";
  children: ReactNode;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type">) {
  return (
    <button
      type={type}
      className={VARIANTS[variant] + " rounded-md px-4 py-2 text-sm font-medium disabled:opacity-60"}
      {...rest}
    >
      {children}
    </button>
  );
}

export function TextField({
  label,
  error,
  id,
  ...rest
}: {
  label: string;
  error?: string | undefined;
  id: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "id">) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink-200">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error !== undefined}
        aria-describedby={error !== undefined ? `${id}-error` : undefined}
        className={
          "rounded-md border bg-navy-800 px-3 py-2 text-sm text-ink-50 placeholder:text-ink-500 " +
          (error !== undefined ? "border-status-error" : "border-navy-600")
        }
        {...rest}
      />
      {error !== undefined && (
        <p id={`${id}-error`} role="alert" className="text-xs text-status-error">
          {error}
        </p>
      )}
    </div>
  );
}
