"use client";

import { BookOpenText, ChevronDown, ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge, Input, PageHeader, Spinner, cx } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Clause, ClauseHit } from "@/lib/types";

export default function PoliticasPage() {
  const [clauses, setClauses] = useState<Clause[] | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<ClauseHit[] | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Clause[]>("/policies").then(setClauses).catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 3) return;
    const t = setTimeout(() => {
      api<ClauseHit[]>(`/policies/search?q=${encodeURIComponent(term)}`).then(setHits).catch((e) => setError(errorMessage(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const onQuery = (value: string) => {
    setQ(value);
    if (value.trim().length < 3) setHits(null);
  };

  const sections = useMemo(() => {
    const map = new Map<number, Clause[]>();
    (clauses ?? []).forEach((c) => {
      const list = map.get(c.section) ?? [];
      list.push(c);
      map.set(c.section, list);
    });
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [clauses]);

  return (
    <div>
      <PageHeader
        title="Políticas"
        description="O manual da loja, extraído do PDF em cláusulas numeradas. É isto que o Tom cita e que o motor de regras usa para prazos, parcelas e frete. A busca abaixo é a mesma que o Tom usa."
      />
      <div className="relative mb-4 max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-dim" />
        <Input className="pl-9" placeholder="Pergunte como o cliente: 'posso devolver?', 'garantia', 'frete para Dourados'…" value={q} onChange={(e) => onQuery(e.target.value)} />
      </div>
      {error && <p className="text-sm text-ember">{error}</p>}
      {hits ? (
        hits.length === 0 ? (
          <p className="text-sm text-muted">Nada encontrado para “{q}”.</p>
        ) : (
          <div className="space-y-3">
            {hits.map((h) => (
              <article key={h.id} className="panel p-4">
                <div className="mb-2 flex items-center gap-2">
                  <Badge tone="brass" mono>
                    § {h.id}
                  </Badge>
                  <h3 className="font-display text-base text-ivory">{h.titulo}</h3>
                  <span className="ml-auto font-mono text-[11px] text-dim">relevância {h.rank.toFixed(3)}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-parchment">{h.texto}</p>
              </article>
            ))}
          </div>
        )
      ) : !clauses ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {sections.map(([section, list]) => {
            const head = list.find((c) => !c.clause_id.includes("."));
            const children = list.filter((c) => c !== head);
            const key = String(section);
            const isOpen = open[key] ?? section <= 2;
            return (
              <div key={key} className="panel overflow-hidden">
                <button onClick={() => setOpen((o) => ({ ...o, [key]: !isOpen }))} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-hover">
                  {isOpen ? <ChevronDown className="h-4 w-4 text-muted" /> : <ChevronRight className="h-4 w-4 text-muted" />}
                  <Badge tone="brass" mono>
                    § {head?.clause_id ?? section}
                  </Badge>
                  <span className="font-display text-base text-ivory">{head?.title ?? `Seção ${section}`}</span>
                  <span className="ml-auto text-[11px] text-dim">
                    {children.length} subseç{children.length === 1 ? "ão" : "ões"}
                    {head?.page ? ` · p.${head.page}` : ""}
                  </span>
                </button>
                {isOpen && (
                  <div className="space-y-4 border-t border-line px-4 py-4">
                    {head && head.body && !head.body.startsWith("Seção com as subseções") && <p className="whitespace-pre-wrap text-sm leading-relaxed text-parchment">{head.body}</p>}
                    {children.map((c) => (
                      <div key={c.clause_id} className={cx("rounded-lg border border-line bg-ink p-3")}>
                        <div className="mb-1 flex items-center gap-2">
                          <Badge tone="muted" mono>
                            {c.clause_id}
                          </Badge>
                          <span className="text-sm font-medium text-ivory">{c.title}</span>
                        </div>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-parchment">{c.body}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          {sections.length === 0 && <p className="text-sm text-muted"><BookOpenText className="mr-1 inline h-4 w-4" /> Nenhuma cláusula carregada; rode a carga de dados.</p>}
        </div>
      )}
    </div>
  );
}
