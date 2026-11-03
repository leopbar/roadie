"use client";

import { Bot, Send, Sparkles, User as UserIcon, Wrench, XCircle } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button, Textarea, cx } from "@/components/ui";
import { TOOL_LABEL, fmtMs, fmtTime } from "@/lib/format";
import type { Receipt } from "@/lib/types";

export type LiveTool = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  done: boolean;
  ok?: boolean;
  summary?: string | null;
  duration_ms?: number | null;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  receipt?: Receipt | null;
  created_at?: string;
  error?: boolean;
};

export type LiveState = { text: string; tools: LiveTool[] };

type Props = {
  messages: ChatMessage[];
  live: LiveState | null;
  onSend?: (text: string) => void;
  disabled?: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  suggestions?: string[];
  placeholder?: string;
  emptyTitle?: string;
  emptyHint?: string;
};

export const SUGGESTIONS = [
  "Quais opções de violões vocês têm até R$ 1.000?",
  "Quanto custa o Takamine GD20? Dá pra parcelar?",
  "Me arrependi da minha compra, posso devolver meu pedido?",
  "Qual o endereço e o horário da loja?",
  "Vocês vendem cordas e cabos?",
  "Quanto custa o Korg Synth 1 Pro?",
  "Tem saxofone?",
  "Tem alguma promoção rolando?",
];

export function Chat({ messages, live, onSend, disabled, selectedId, onSelect, suggestions, placeholder, emptyTitle, emptyHint }: Props) {
  const [text, setText] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, live?.text, live?.tools.length]);

  const submit = () => {
    const value = text.trim();
    if (!value || disabled || !onSend) return;
    onSend(value);
    setText("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const empty = messages.length === 0 && !live;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-1 py-4">
        {empty && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-brass/40 bg-brass/10">
              <Bot className="h-7 w-7 text-brass-bright" />
            </div>
            <div>
              <p className="font-display text-xl text-ivory">{emptyTitle ?? "Fale com o Tom"}</p>
              <p className="mt-1 max-w-md text-sm text-muted">
                {emptyHint ?? "Escreva como se fosse o cliente no WhatsApp. O painel ao lado mostra o que o Tom consultou para responder."}
              </p>
            </div>
            {suggestions && onSend && (
              <div className="flex max-w-2xl flex-wrap justify-center gap-2">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => onSend(s)}
                    disabled={disabled}
                    className="rounded-full border border-line-strong bg-raised px-3 py-1.5 text-xs text-parchment transition-colors hover:border-brass/60 hover:text-ivory disabled:opacity-50"
                  >
                    <Sparkles className="mr-1 inline h-3 w-3 text-brass" />
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m) => (
          <Bubble key={m.id} message={m} selected={m.id === selectedId} onSelect={() => m.role === "assistant" && !m.error && onSelect(m.id)} />
        ))}

        {live && (
          <div className="fade-in flex items-end gap-3">
            <Avatar role="assistant" />
            <div className="bubble-tom max-w-[78%] rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed text-ivory">
              {live.tools.length > 0 && (
                <ul className="mb-2 space-y-1">
                  {live.tools.map((t) => (
                    <li key={t.id} className="flex items-center gap-2 text-xs text-muted">
                      {t.done ? (
                        t.ok === false ? <XCircle className="h-3.5 w-3.5 text-ember" /> : <Wrench className="h-3.5 w-3.5 text-sage" />
                      ) : (
                        <Wrench className="h-3.5 w-3.5 animate-pulse text-brass" />
                      )}
                      <span className="font-mono text-[11px] text-parchment">{TOOL_LABEL[t.name] ?? t.name}</span>
                      {t.done ? <span className="truncate">{t.summary} · {fmtMs(t.duration_ms)}</span> : <span>consultando…</span>}
                    </li>
                  ))}
                </ul>
              )}
              {live.text ? <span className="caret whitespace-pre-wrap">{live.text}</span> : live.tools.length === 0 ? <span className="caret text-muted">pensando</span> : null}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {onSend && (
        <div className="border-t border-line pt-3">
          <div className="flex items-end gap-2">
            <Textarea
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKey}
              placeholder={placeholder ?? "Mensagem do cliente… (Enter envia, Shift+Enter quebra linha)"}
              disabled={disabled}
            />
            <Button onClick={submit} disabled={disabled || !text.trim()} className="h-[58px] px-4" aria-label="Enviar">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  return role === "assistant" ? (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-brass/40 bg-brass/10 text-brass-bright">
      <Bot className="h-4 w-4" />
    </span>
  ) : (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-rosewood-soft/50 bg-rosewood/40 text-parchment">
      <UserIcon className="h-4 w-4" />
    </span>
  );
}

function Bubble({ message, selected, onSelect }: { message: ChatMessage; selected: boolean; onSelect: () => void }) {
  const isTom = message.role === "assistant";
  const receipt = message.receipt;
  return (
    <div className={cx("fade-in flex items-end gap-3", !isTom && "flex-row-reverse")}>
      <Avatar role={message.role} />
      <div className={cx("max-w-[78%]", !isTom && "text-right")}>
        <button
          type="button"
          onClick={onSelect}
          className={cx(
            "whitespace-pre-wrap rounded-2xl px-4 py-3 text-left text-sm leading-relaxed text-ivory transition-shadow",
            isTom ? "bubble-tom rounded-bl-md" : "bubble-cliente rounded-br-md",
            message.error && "border-ember/60 text-ember",
            selected && "shadow-glow",
            isTom && !message.error && "cursor-pointer hover:shadow-glow",
          )}
        >
          {message.content}
        </button>
        <div className={cx("mt-1 flex flex-wrap items-center gap-2 text-[11px] text-dim", !isTom && "justify-end")}>
          {message.created_at && <span>{fmtTime(message.created_at)}</span>}
          {receipt && (
            <>
              <span>· {receipt.tools.length} consulta{receipt.tools.length === 1 ? "" : "s"}</span>
              <span>· {fmtMs(receipt.latency_ms)}</span>
              {receipt.model.fallback_used && <span className="text-amber">· fallback</span>}
              {receipt.flags.length > 0 && <span className="text-amber">· quarentena</span>}
              {receipt.tickets.length > 0 && <span className="text-sky">· ticket {receipt.tickets[0].protocolo}</span>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
