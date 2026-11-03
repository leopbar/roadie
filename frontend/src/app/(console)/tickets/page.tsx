"use client";

import { Ticket as TicketIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, EmptyState, PageHeader, Select, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { TICKET_STATUS_LABEL, fmtDateTime } from "@/lib/format";
import type { Ticket } from "@/lib/types";

const TONE: Record<Ticket["status"], "amber" | "sky" | "sage"> = { aberto: "amber", em_andamento: "sky", resolvido: "sage" };

export default function TicketsPage() {
  const [items, setItems] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api<Ticket[]>("/tickets").then(setItems).catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    void load();
  }, []);

  const update = async (t: Ticket, status: Ticket["status"]) => {
    try {
      const updated = await api<Ticket>(`/tickets/${t.id}`, { method: "PATCH", json: { status } });
      setItems((list) => (list ? list.map((x) => (x.id === t.id ? updated : x)) : list));
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div>
      <PageHeader title="Tickets" description="Passagens para a equipe humana registradas pelo Tom: reclamações, cancelamentos, devoluções, cadastro e exceções do manual. Prazo de retorno de 24 horas úteis." />
      {error && <p className="mb-3 text-sm text-ember">{error}</p>}
      {!items ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhum ticket" hint="Quando o Tom registrar uma reclamação ou uma exceção, ela aparece aqui com protocolo e prazo." icon={<TicketIcon className="h-8 w-8" />} />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-ink text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Protocolo</th>
                <th className="px-4 py-3">Categoria</th>
                <th className="px-4 py-3">Cliente</th>
                <th className="px-4 py-3">Resumo</th>
                <th className="px-4 py-3">Prazo</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {items.map((t) => (
                <tr key={t.id} className="align-top hover:bg-hover">
                  <td className="px-4 py-3 font-mono text-xs text-brass-bright">
                    {t.protocol}
                    {t.conversation_id && (
                      <Link href={`/conversas/${t.conversation_id}`} className="mt-1 block text-[11px] text-muted hover:text-ivory">
                        ver conversa
                      </Link>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone="muted">{t.category}</Badge>
                    {t.order_id && <p className="mt-1 text-xs text-muted">pedido {t.order_id}</p>}
                  </td>
                  <td className="px-4 py-3 text-parchment">{t.customer_name ?? <span className="text-dim">não identificado</span>}</td>
                  <td className="max-w-md px-4 py-3 text-parchment">{t.summary}</td>
                  <td className="px-4 py-3 text-xs text-muted">{fmtDateTime(t.sla_due_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Badge tone={TONE[t.status]}>{TICKET_STATUS_LABEL[t.status]}</Badge>
                      <Select className="h-8 w-36 text-xs" value={t.status} onChange={(e) => update(t, e.target.value as Ticket["status"])}>
                        <option value="aberto">Aberto</option>
                        <option value="em_andamento">Em andamento</option>
                        <option value="resolvido">Resolvido</option>
                      </Select>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
