"use client";

import {
  BookOpenText,
  Clock3,
  Guitar,
  History,
  LogOut,
  Menu,
  MessageSquareText,
  Settings,
  ShieldAlert,
  Ticket,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { Badge, Spinner, cx } from "@/components/ui";
import { api } from "@/lib/api";
import type { Meta } from "@/lib/types";

const NAV = [
  { href: "/simulador", label: "Simulador", icon: MessageSquareText },
  { href: "/conversas", label: "Conversas", icon: History },
  { href: "/tickets", label: "Tickets", icon: Ticket },
  { href: "/qualidade", label: "Qualidade de dados", icon: ShieldAlert },
  { href: "/politicas", label: "Políticas", icon: BookOpenText },
  { href: "/catalogo", label: "Catálogo", icon: Guitar },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    if (!user) return;
    api<Meta>("/meta").then(setMeta).catch(() => setMeta(null));
  }, [user, pathname]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-line bg-ink/95 backdrop-blur transition-transform md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Link href="/simulador" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-brass/40 bg-brass/10 font-display text-lg text-brass-bright">
              R
            </span>
            <span>
              <span className="block font-display text-lg leading-none text-ivory">Roadie</span>
              <span className="block text-[11px] uppercase tracking-[0.2em] text-muted">Empório da Música</span>
            </span>
          </Link>
          <button className="text-muted md:hidden" onClick={() => setOpen(false)} aria-label="Fechar menu">
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => setOpen(false)}
                className={cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active ? "bg-brass/10 text-brass-bright" : "text-parchment hover:bg-hover hover:text-ivory",
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-line px-4 py-4 text-xs text-muted">
          <div className="flex items-center justify-between">
            <span className="truncate">
              <span className="block text-sm text-parchment">{user.name}</span>
              <span className="block truncate">{user.email}</span>
            </span>
            <button onClick={() => void logout()} className="rounded-lg p-2 text-muted hover:bg-hover hover:text-ivory" title="Sair">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-1">
            <Badge tone={user.role === "admin" ? "brass" : "muted"}>{user.role === "admin" ? "admin" : "atendente"}</Badge>
            {meta && <Badge tone="muted">v{meta.version}</Badge>}
          </div>
        </div>
      </aside>

      {open && <div className="fixed inset-0 z-20 bg-black/60 md:hidden" onClick={() => setOpen(false)} />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 md:px-8">
          <div className="flex items-center gap-3">
            <button className="text-muted md:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu">
              <Menu className="h-5 w-5" />
            </button>
            <span className="hidden text-xs uppercase tracking-[0.25em] text-dim sm:block">Console de atendimento</span>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
            {meta && (
              <>
                <Badge tone="muted" className="gap-1.5">
                  <Clock3 className="h-3 w-3" />
                  {meta.clock.label}
                  {meta.clock.simulated && <span className="text-dim">· simulado</span>}
                </Badge>
                <Badge tone={meta.model.configured ? (meta.model.mode === "mock" ? "amber" : "sage") : "ember"} mono>
                  {meta.model.mode === "mock" ? "modelo simulado" : meta.model.configured ? meta.model.primary : "modelo não configurado"}
                </Badge>
              </>
            )}
          </div>
        </header>
        <main className="flex-1 px-4 py-6 md:px-8">{children}</main>
      </div>
    </div>
  );
}
