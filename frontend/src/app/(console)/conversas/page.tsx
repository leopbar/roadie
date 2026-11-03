"use client";

import { History } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { Conversation } from "@/lib/types";

export default function ConversasPage() {
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Conversation[]>("/conversations?limit=100").then(setItems).catch((e) => setError(errorMessage(e)));
  }, []);

  return (
    <div>
      <PageHeader title="Conversas" description="Histórico de atendimentos do simulador, com recibos de evidências por resposta." />
      {error && <p className="text-sm text-ember">{error}</p>}
      {!items ? (
        <Spinner />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhuma conversa ainda" hint="Use o simulador para conversar com o Tom." icon={<History className="h-8 w-8" />} />
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink text-left text-[11px] uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Assunto</th>
                <th className="px-4 py-3">Remetente</th>
                <th className="px-4 py-3">Identidade</th>
                <th className="px-4 py-3 text-right">Mensagens</th>
                <th className="px-4 py-3">Atualizada</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {items.map((c) => (
                <tr key={c.id} className="hover:bg-hover">
                  <td className="px-4 py-3">
                    <Link href={`/conversas/${c.id}`} className="text-ivory hover:text-brass-bright">
                      {c.title ?? "(sem título)"}
                    </Link>
                    {c.last_message && <p className="mt-0.5 line-clamp-1 text-xs text-muted">{c.last_message}</p>}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-parchment">{c.sender_phone ?? "—"}</td>
                  <td className="px-4 py-3">
                    {c.identity_verified ? <Badge tone="sage">{c.customer_name}</Badge> : <Badge tone="amber">não identificado</Badge>}
                  </td>
                  <td className="px-4 py-3 text-right text-parchment">{c.message_count}</td>
                  <td className="px-4 py-3 text-xs text-muted">{fmtDateTime(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
