"use client";

import { ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge, PageHeader, Spinner, cx } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { SEVERITY_LABEL } from "@/lib/format";
import type { Flag, Quality } from "@/lib/types";

const TONE: Record<Flag["severity"], "ember" | "amber" | "sky"> = { quarantine: "ember", warning: "amber", info: "sky" };
const ORDER: Flag["severity"][] = ["quarantine", "warning", "info"];

export default function QualidadePage() {
  const [data, setData] = useState<Quality | null>(null);
  const [filter, setFilter] = useState<Flag["severity"] | "all">("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Quality>("/quality").then(setData).catch((e) => setError(errorMessage(e)));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const list = filter === "all" ? data.flags : data.flags.filter((f) => f.severity === filter);
    return [...list].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity));
  }, [data, filter]);

  return (
    <div>
      <PageHeader
        title="Qualidade de dados"
        description="O que a ingestão encontrou de errado nos CSVs. Nada foi apagado: cada problema vira uma etiqueta que o Tom lê antes de responder. Em quarentena, ele não afirma preço nem especificação e chama a equipe."
      />
      {error && <p className="text-sm text-ember">{error}</p>}
      {!data ? (
        <Spinner />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <Chip active={filter === "all"} onClick={() => setFilter("all")} label="Todas" count={data.flags.length} />
            {ORDER.map((s) => (
              <Chip key={s} active={filter === s} onClick={() => setFilter(s)} label={SEVERITY_LABEL[s]} count={data.summary[s] ?? 0} tone={TONE[s]} />
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <Legend tone="ember" title="Quarentena" text="Marca contraditória, specs que não batem com a descrição ou preço implausível. O Tom não afirma preço nem specs; oferece confirmar com a equipe." />
            <Legend tone="amber" title="Atenção" text="Inconsistências menores: nome genérico no cadastro, total do pedido que não fecha, e-mail repetido. O Tom responde com ressalva." />
            <Legend tone="sky" title="Info" text="Só registro: categoria vazia, estoque zero em produto ativo, pré-venda em pedido pendente, quase homônimos." />
          </div>
          <div className="panel mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-ink text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-4 py-3">Severidade</th>
                  <th className="px-4 py-3">Entidade</th>
                  <th className="px-4 py-3">Sinalização</th>
                  <th className="px-4 py-3">Detalhe</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((f) => (
                  <tr key={f.id} className="hover:bg-hover">
                    <td className="px-4 py-3">
                      <Badge tone={TONE[f.severity]}>{SEVERITY_LABEL[f.severity]}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-parchment">{f.entity_label ?? `${f.entity} ${f.entity_id}`}</span>
                      <p className="font-mono text-[11px] text-dim">
                        {f.entity}#{f.entity_id}
                      </p>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-parchment">{f.flag}</td>
                    <td className="px-4 py-3 text-muted">{f.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function Chip({ active, onClick, label, count, tone }: { active: boolean; onClick: () => void; label: string; count: number; tone?: "ember" | "amber" | "sky" }) {
  const color = tone === "ember" ? "text-ember" : tone === "amber" ? "text-amber" : tone === "sky" ? "text-sky" : "text-parchment";
  return (
    <button
      onClick={onClick}
      className={cx("rounded-full border px-3 py-1.5 text-xs transition-colors", active ? "border-brass/60 bg-brass/10 text-ivory" : "border-line-strong text-muted hover:text-ivory")}
    >
      <span className={color}>{label}</span> <span className="font-mono text-dim">{count}</span>
    </button>
  );
}

function Legend({ tone, title, text }: { tone: "ember" | "amber" | "sky"; title: string; text: string }) {
  return (
    <div className="panel p-4">
      <div className="mb-1 flex items-center gap-2">
        <ShieldAlert className={cx("h-4 w-4", tone === "ember" ? "text-ember" : tone === "amber" ? "text-amber" : "text-sky")} />
        <span className="text-sm font-medium text-ivory">{title}</span>
      </div>
      <p className="text-xs text-muted">{text}</p>
    </div>
  );
}
