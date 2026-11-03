"use client";

import { RotateCcw, Settings } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Backstage } from "@/components/backstage";
import { Chat, SUGGESTIONS, type ChatMessage, type LiveState } from "@/components/chat";
import { ClockControl, SenderPicker, type Sender } from "@/components/simulator-controls";
import { Alert, Badge, Button } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { toLocalInput } from "@/lib/format";
import { streamPost } from "@/lib/sse";
import type { Conversation, Customer, Meta } from "@/lib/types";

const SHOWCASE_CUSTOMER = 10; // Camila: tem um pedido pendente recente

export default function SimuladorPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sender, setSender] = useState<Sender>({ mode: "customer", customerId: null, phone: "" });
  const [clock, setClock] = useState("");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [live, setLive] = useState<LiveState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    Promise.all([api<Customer[]>("/customers"), api<Meta>("/meta")])
      .then(([cs, m]) => {
        setCustomers(cs);
        setMeta(m);
        setClock(toLocalInput(m.clock.default_now));
        const showcase = cs.find((c) => c.customer_id === SHOWCASE_CUSTOMER) ?? cs[0];
        if (showcase) setSender({ mode: "customer", customerId: showcase.customer_id, phone: showcase.phone ?? "" });
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const startConversation = useCallback(async (): Promise<Conversation> => {
    const conv = await api<Conversation>("/conversations", {
      method: "POST",
      json: { sender_phone: sender.phone || null, clock_override: clock ? `${clock}:00` : null },
    });
    setConversation(conv);
    setMessages([]);
    setSelected(null);
    setLive(null);
    return conv;
  }, [sender.phone, clock]);

  const reset = async () => {
    setError(null);
    setBusy(true);
    try {
      await startConversation();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const send = async (text: string) => {
    setError(null);
    setBusy(true);
    const tempId = `tmp-${Date.now()}`;
    setMessages((m) => [...m, { id: tempId, role: "user", content: text, created_at: new Date().toISOString() }]);
    setLive({ text: "", tools: [] });
    try {
      const conv = conversation ?? (await startConversation());
      if (!conversation) {
        // startConversation limpa a lista; recoloca a mensagem do cliente
        setMessages([{ id: tempId, role: "user", content: text, created_at: new Date().toISOString() }]);
        setLive({ text: "", tools: [] });
      }
      abortRef.current = new AbortController();
      await streamPost(
        `/conversations/${conv.id}/messages/stream`,
        { text },
        (ev) => {
          if (ev.type === "token") {
            setLive((l) => (l ? { ...l, text: l.text + ev.text } : { text: ev.text, tools: [] }));
          } else if (ev.type === "tool_start") {
            setLive((l) => ({ text: l?.text ?? "", tools: [...(l?.tools ?? []), { id: ev.id, name: ev.name, args: ev.args, done: false }] }));
          } else if (ev.type === "tool_end") {
            setLive((l) =>
              l
                ? { ...l, tools: l.tools.map((t) => (t.id === ev.id ? { ...t, done: true, ok: ev.ok, summary: ev.summary, duration_ms: ev.duration_ms } : t)) }
                : l,
            );
          } else if (ev.type === "done") {
            setMessages((m) => [...m, { id: ev.message_id, role: "assistant", content: ev.content, receipt: ev.receipt, created_at: new Date().toISOString() }]);
            setSelected(ev.message_id);
            setLive(null);
            setConversation((c) => (c && ev.receipt.identity.verified ? { ...c, identity_verified: true, customer_name: ev.receipt.identity.name, verified_via: ev.receipt.identity.via } : c));
          } else if (ev.type === "error") {
            setLive(null);
            setMessages((m) => [...m, { id: `err-${Date.now()}`, role: "assistant", content: `Falha ao responder: ${ev.detail}`, error: true }]);
          }
        },
        abortRef.current.signal,
      );
    } catch (err) {
      setLive(null);
      const msg = err instanceof ApiError && err.status === 503 ? `${errorMessage(err)}` : errorMessage(err);
      setMessages((m) => [...m, { id: `err-${Date.now()}`, role: "assistant", content: msg, error: true }]);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const selectedReceipt = messages.find((m) => m.id === selected)?.receipt ?? null;
  const unconfigured = meta && !meta.model.configured;

  return (
    <div className="flex h-[calc(100vh-7.5rem)] min-h-[560px] flex-col gap-4">
      <section className="panel p-4">
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_auto] lg:items-end">
          <SenderPicker customers={customers} value={sender} onChange={setSender} disabled={busy} />
          <ClockControl value={clock} onChange={setClock} disabled={busy} />
          <Button variant="outline" onClick={reset} loading={busy} className="lg:mb-0">
            <RotateCcw className="h-4 w-4" />
            Nova conversa
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
          {conversation ? (
            <>
              <Badge tone="muted" mono>
                conversa {conversation.id.slice(0, 8)}
              </Badge>
              {conversation.identity_verified ? (
                <Badge tone="sage">identificado: {conversation.customer_name}</Badge>
              ) : (
                <Badge tone="amber">remetente não identificado</Badge>
              )}
              <span>Mudanças de remetente ou relógio valem para a próxima conversa.</span>
            </>
          ) : (
            <span>A conversa começa na primeira mensagem, com o remetente e o relógio acima.</span>
          )}
        </div>
        {unconfigured && (
          <div className="mt-3">
            <Alert tone="amber">
              <span className="inline-flex flex-wrap items-center gap-2">
                Nenhuma chave da OpenAI configurada: o Tom não consegue responder.
                <Link href="/configuracoes" className="inline-flex items-center gap-1 underline">
                  <Settings className="h-3 w-3" /> Configurar agora
                </Link>
              </span>
            </Alert>
          </div>
        )}
        {error && (
          <div className="mt-3">
            <Alert>{error}</Alert>
          </div>
        )}
      </section>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
        <section className="panel flex min-h-0 flex-col px-4 pb-4">
          <Chat messages={messages} live={live} onSend={send} disabled={busy} selectedId={selected} onSelect={setSelected} suggestions={SUGGESTIONS} />
        </section>
        <Backstage receipt={selectedReceipt} live={live} />
      </div>
    </div>
  );
}
