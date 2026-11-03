"use client";

import { CheckCircle2, ChevronDown, ChevronRight, Database, Gauge, Receipt as ReceiptIcon, Scale, ShieldAlert, Ticket, UserCheck, Wrench, XCircle } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { LiveState } from "@/components/chat";
import { Badge, cx } from "@/components/ui";
import { TOOL_LABEL, fmtMs, fmtTokens, fmtUsd } from "@/lib/format";
import type { Receipt } from "@/lib/types";

type Props = { receipt: Receipt | null; live: LiveState | null };

export function Backstage({ receipt, live }: Props) {
  const [raw, setRaw] = useState(false);

  if (live) {
    return (
      <Panel title="Bastidores" subtitle="ao vivo">
        <Section icon={<Wrench className="h-4 w-4" />} title="Consultas em andamento">
          {live.tools.length === 0 ? (
            <p className="text-sm text-muted">O Tom está lendo a mensagem…</p>
          ) : (
            <ul className="space-y-2">
              {live.tools.map((t) => (
                <li key={t.id} className="rounded-lg border border-line bg-ink p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-parchment">{t.name}</span>
                    {t.done ? (
                      t.ok === false ? <XCircle className="h-4 w-4 text-ember" /> : <CheckCircle2 className="h-4 w-4 text-sage" />
                    ) : (
                      <span className="h-2 w-2 animate-pulse rounded-full bg-brass" />
                    )}
                  </div>
                  <Args args={t.args} />
                  {t.done && (
                    <p className="mt-1 text-xs text-muted">
                      {t.summary} · {fmtMs(t.duration_ms)}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </Panel>
    );
  }

  if (!receipt) {
    return (
      <Panel title="Bastidores" subtitle="recibo de evidências">
        <div className="flex flex-col items-center gap-2 py-12 text-center">
          <ReceiptIcon className="h-8 w-8 text-dim" />
          <p className="max-w-xs text-sm text-muted">
            Cada resposta do Tom vem com um recibo: quais ferramentas chamou, que linhas leu, que cláusulas do manual sustentam a resposta e quanto custou.
          </p>
        </div>
      </Panel>
    );
  }

  const ident = receipt.identity;
  return (
    <Panel
      title="Bastidores"
      subtitle={receipt.clock.label}
      actions={
        <button onClick={() => setRaw((v) => !v)} className="text-xs text-muted hover:text-ivory">
          {raw ? "visão guiada" : "JSON bruto"}
        </button>
      }
    >
      {raw ? (
        <pre className="max-h-[70vh] overflow-auto rounded-lg border border-line bg-ink p-3 font-mono text-[11px] leading-relaxed text-parchment">
          {JSON.stringify(receipt, null, 2)}
        </pre>
      ) : (
        <div className="space-y-5">
          <Section icon={<UserCheck className="h-4 w-4" />} title="Identidade">
            {ident.verified ? (
              <div className="flex flex-wrap items-center gap-2 text-sm text-parchment">
                <span>{ident.name}</span>
                <Badge tone="sage">verificado · {ident.via}</Badge>
                {ident.city && <Badge tone="muted">{ident.city}</Badge>}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Badge tone="amber">não identificado</Badge>
                <span>ferramentas de pedido bloqueadas</span>
              </div>
            )}
          </Section>

          <Section icon={<Wrench className="h-4 w-4" />} title={`Ferramentas (${receipt.tools.length})`}>
            {receipt.tools.length === 0 ? (
              <p className="text-sm text-muted">Nenhuma consulta: resposta direta da persona.</p>
            ) : (
              <ol className="space-y-2">
                {receipt.tools.map((t, i) => (
                  <li key={t.id ?? i} className="rounded-lg border border-line bg-ink p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-ivory">
                        <span className="mr-2 font-mono text-[11px] text-dim">{i + 1}</span>
                        {TOOL_LABEL[t.name] ?? t.name}
                      </span>
                      {t.result?.ok === false ? <XCircle className="h-4 w-4 text-ember" /> : <CheckCircle2 className="h-4 w-4 text-sage" />}
                    </div>
                    <p className="font-mono text-[11px] text-dim">{t.name}</p>
                    <Args args={t.args} />
                    {t.result && (
                      <p className="mt-1 text-xs text-muted">
                        {t.result.summary} · {fmtMs(t.result.duration_ms)}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Section>

          <Section icon={<Database className="h-4 w-4" />} title="Fontes">
            <Row label="tabelas">
              {receipt.sources.tables.length ? receipt.sources.tables.map((t) => <Badge key={t} tone="sky" mono>{t}</Badge>) : <Muted />}
            </Row>
            <Row label="linhas lidas">
              {receipt.sources.rows.length ? (
                receipt.sources.rows.map((r) => (
                  <Badge key={`${r.table}:${r.id}`} tone="muted" mono>
                    {r.table}#{r.id}
                  </Badge>
                ))
              ) : (
                <Muted />
              )}
            </Row>
          </Section>

          <Section icon={<Scale className="h-4 w-4" />} title="Políticas e regras">
            <Row label="cláusulas">
              {receipt.sources.clauses.length ? receipt.sources.clauses.map((c) => <Badge key={c} tone="brass" mono>§ {c}</Badge>) : <Muted />}
            </Row>
            <Row label="regras determinísticas">
              {receipt.sources.rules.length ? receipt.sources.rules.map((r) => <Badge key={r} tone="sage" mono>{r}</Badge>) : <Muted />}
            </Row>
          </Section>

          {(receipt.flags.length > 0 || receipt.tickets.length > 0) && (
            <Section icon={<ShieldAlert className="h-4 w-4" />} title="Alertas">
              {receipt.flags.map((f) => (
                <Badge key={f} tone="amber" mono className="mr-1 mb-1">
                  {f}
                </Badge>
              ))}
              {receipt.tickets.map((t) => (
                <div key={t.protocolo} className="mt-2 flex items-center gap-2 text-sm text-parchment">
                  <Ticket className="h-4 w-4 text-sky" />
                  <span className="font-mono">{t.protocolo}</span>
                  <span className="text-muted">· {t.categoria}</span>
                </div>
              ))}
            </Section>
          )}

          <Section icon={<Gauge className="h-4 w-4" />} title="Modelo e custo">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-muted">modelo</dt>
              <dd className="font-mono text-parchment">{receipt.model.used.join(", ") || receipt.model.primary}</dd>
              <dt className="text-muted">fallback</dt>
              <dd className={cx(receipt.model.fallback_used ? "text-amber" : "text-parchment")}>{receipt.model.fallback_used ? "acionado" : "não"}</dd>
              <dt className="text-muted">chamadas ao modelo</dt>
              <dd className="text-parchment">{receipt.model.llm_calls}</dd>
              <dt className="text-muted">tokens</dt>
              <dd className="text-parchment">
                {fmtTokens(receipt.tokens.total)} <span className="text-dim">({fmtTokens(receipt.tokens.input)} in · {fmtTokens(receipt.tokens.output)} out)</span>
              </dd>
              <dt className="text-muted">custo estimado</dt>
              <dd className="text-parchment">{fmtUsd(receipt.cost_usd)}</dd>
              <dt className="text-muted">latência</dt>
              <dd className="text-parchment">{fmtMs(receipt.latency_ms)}</dd>
            </dl>
          </Section>
        </div>
      )}
    </Panel>
  );
}

function Panel({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <aside className="panel flex h-full min-h-0 flex-col">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <h2 className="font-display text-base text-ivory">{title}</h2>
          {subtitle && <p className="text-[11px] uppercase tracking-wider text-dim">{subtitle}</p>}
        </div>
        {actions}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
    </aside>
  );
}

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button onClick={() => setOpen((v) => !v)} className="mb-2 flex w-full items-center gap-2 text-left text-xs font-semibold uppercase tracking-wider text-muted hover:text-parchment">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        <span className="text-brass">{icon}</span>
        {title}
      </button>
      {open && <div className="space-y-2">{children}</div>}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[11px] text-dim">{label}</p>
      <div className="flex flex-wrap gap-1">{children}</div>
    </div>
  );
}

function Muted() {
  return <span className="text-xs text-dim">—</span>;
}

function Args({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (entries.length === 0) return null;
  return (
    <p className="mt-1 font-mono text-[11px] leading-relaxed text-muted">
      {entries.map(([k, v]) => (
        <span key={k} className="mr-2">
          <span className="text-dim">{k}=</span>
          <span className="text-parchment">{typeof v === "string" ? v : JSON.stringify(v)}</span>
        </span>
      ))}
    </p>
  );
}
