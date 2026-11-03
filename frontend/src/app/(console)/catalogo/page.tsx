"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { Badge, Input, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Product } from "@/lib/types";

export default function CatalogoPage() {
  const [items, setItems] = useState<Product[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      api<Product[]>(`/products${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`)
        .then(setItems)
        .catch((e) => setError(errorMessage(e)));
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div>
      <PageHeader title="Catálogo" description="Os 65 produtos dos CSVs, com preço, promoção ativa, disponibilidade e o estado do cadastro. A busca usa a mesma lógica da ferramenta do Tom." />
      <div className="relative mb-4 max-w-xl">
        <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-dim" />
        <Input className="pl-9" placeholder="violão aço até 1000, ukulele tenor, Takamini GD20…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {error && <p className="text-sm text-ember">{error}</p>}
      {!items ? (
        <Spinner />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-ink text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Produto</th>
                <th className="px-4 py-3">Categoria</th>
                <th className="px-4 py-3 text-right">Preço</th>
                <th className="px-4 py-3">Promoção</th>
                <th className="px-4 py-3">Disponibilidade</th>
                <th className="px-4 py-3">Cadastro</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {items.map((p) => (
                <tr key={p.product_id} className="hover:bg-hover">
                  <td className="px-4 py-3">
                    <span className="text-ivory">{p.name}</span>
                    <p className="font-mono text-[11px] text-dim">
                      #{p.product_id} · {p.brand ?? "—"}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-muted">{p.category}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-parchment">{p.price_brl}</td>
                  <td className="px-4 py-3">
                    {p.promotion ? (
                      <Badge tone="brass">
                        {p.promotion.description} · {p.promotion.percent}% · {p.promotion.price}
                      </Badge>
                    ) : (
                      <span className="text-dim">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={p.status === "active" && p.stock_quantity > 0 ? "sage" : p.status === "discontinued" ? "muted" : "amber"}>{p.availability}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    {p.quality ? (
                      <span title={p.quality.divergencias.join(" · ")}>
                        <Badge tone={p.quality.nivel === "quarentena" ? "ember" : "amber"}>{p.quality.nivel}</Badge>
                      </span>
                    ) : (
                      <Badge tone="sage">ok</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 && <p className="p-4 text-sm text-muted">Nada encontrado.</p>}
        </div>
      )}
    </div>
  );
}
