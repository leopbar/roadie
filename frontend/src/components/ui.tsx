"use client";

import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "outline";
  size?: "sm" | "md";
  loading?: boolean;
};

export function Button({ variant = "primary", size = "md", loading, className, children, disabled, ...rest }: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brass/60 disabled:cursor-not-allowed disabled:opacity-50";
  const sizes = size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-sm";
  const variants = {
    primary: "bg-brass text-ebony hover:bg-brass-bright",
    ghost: "text-parchment hover:bg-hover hover:text-ivory",
    outline: "border border-line-strong text-parchment hover:border-brass/60 hover:text-ivory",
    danger: "bg-ember/15 text-ember border border-ember/40 hover:bg-ember/25",
  }[variant];
  return (
    <button className={cx(base, sizes, variants, className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      {children}
    </button>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "h-10 w-full rounded-lg border border-line bg-ink px-3 text-sm text-ivory placeholder:text-dim focus:border-brass/60 focus:outline-none focus:ring-2 focus:ring-brass/20",
        className,
      )}
      {...rest}
    />
  );
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full resize-none rounded-lg border border-line bg-ink px-3 py-2 text-sm text-ivory placeholder:text-dim focus:border-brass/60 focus:outline-none focus:ring-2 focus:ring-brass/20",
        className,
      )}
      {...rest}
    />
  );
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "h-10 w-full rounded-lg border border-line bg-ink px-3 text-sm text-ivory focus:border-brass/60 focus:outline-none focus:ring-2 focus:ring-brass/20",
        className,
      )}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <label className={cx("mb-1 block text-xs font-medium uppercase tracking-wide text-muted", className)}>{children}</label>;
}

export function Card({ title, subtitle, actions, children, className }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("panel p-5", className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="font-display text-lg text-ivory">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

type Tone = "brass" | "sage" | "ember" | "amber" | "sky" | "muted" | "rosewood";

const TONES: Record<Tone, string> = {
  brass: "border-brass/40 bg-brass/10 text-brass-bright",
  sage: "border-sage/40 bg-sage/10 text-sage",
  ember: "border-ember/40 bg-ember/10 text-ember",
  amber: "border-amber/40 bg-amber/10 text-amber",
  sky: "border-sky/40 bg-sky/10 text-sky",
  muted: "border-line-strong bg-raised text-muted",
  rosewood: "border-rosewood-soft/50 bg-rosewood/30 text-parchment",
};

export function Badge({ tone = "muted", children, className, mono }: { tone?: Tone; children: ReactNode; className?: string; mono?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", TONES[tone], mono && "font-mono", className)}>
      {children}
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx("h-5 w-5 animate-spin text-brass", className)} />;
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      {icon && <div className="text-dim">{icon}</div>}
      <p className="font-display text-lg text-parchment">{title}</p>
      {hint && <p className="max-w-md text-sm text-muted">{hint}</p>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl text-ivory md:text-3xl">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Alert({ tone = "ember", children }: { tone?: "ember" | "amber" | "sage" | "sky"; children: ReactNode }) {
  const map = {
    ember: "border-ember/40 bg-ember/10 text-ember",
    amber: "border-amber/40 bg-amber/10 text-amber",
    sage: "border-sage/40 bg-sage/10 text-sage",
    sky: "border-sky/40 bg-sky/10 text-sky",
  }[tone];
  return <div className={cx("rounded-lg border px-3 py-2 text-sm", map)}>{children}</div>;
}
