"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Backstage } from "@/components/backstage";
import { Chat, type ChatMessage } from "@/components/chat";
import { Badge, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { ConversationDetail } from "@/lib/types";

export default function ConversaPage() {
  const { id } = useParams<{ id: string }>();
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<ConversationDetail>(`/conversations/${id}`)
      .then((c) => {
        setConv(c);
        const lastTom = [...c.messages].reverse().find((m) => m.role === "assistant");
        setSelected(lastTom?.id ?? null);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [id]);

  if (error) return <p className="text-sm text-ember">{error}</p>;
  if (!conv) return <Spinner />;

  const messages: ChatMessage[] = conv.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, receipt: m.receipt, created_at: m.created_at }));
  const receipt = conv.messages.find((m) => m.id === selected)?.receipt ?? null;

  return (
    <div className="flex h-[calc(100vh-7.5rem)] min-h-[560px] flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/conversas" className="inline-flex items-center gap-1 text-sm text-muted hover:text-ivory">
          <ArrowLeft className="h-4 w-4" /> Conversas
        </Link>
        <h1 className="font-display text-xl text-ivory">{conv.title ?? "(sem título)"}</h1>
        <Badge tone="muted" mono>
          {conv.sender_phone ?? "sem número"}
        </Badge>
        {conv.identity_verified ? <Badge tone="sage">{conv.customer_name}</Badge> : <Badge tone="amber">não identificado</Badge>}
        {conv.clock_override && <Badge tone="muted">relógio {fmtDateTime(conv.clock_override)}</Badge>}
      </div>
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="panel flex min-h-0 flex-col px-4 pb-4">
          <Chat messages={messages} live={null} selectedId={selected} onSelect={setSelected} emptyTitle="Conversa vazia" emptyHint="Nenhuma mensagem registrada." />
        </section>
        <Backstage receipt={receipt} live={null} />
      </div>
    </div>
  );
}
