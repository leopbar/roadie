"use client";

import { CheckCircle2, Eye, EyeOff, KeyRound, PlugZap, Save, Trash2, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Alert, Badge, Button, Card, Input, Label } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime, fmtMs } from "@/lib/format";
import type { LLMStatus, LLMTestResult } from "@/lib/types";

export function LLMSettingsCard() {
  const [status, setStatus] = useState<LLMStatus | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [show, setShow] = useState(false);
  const [primary, setPrimary] = useState("");
  const [fallback, setFallback] = useState("");
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<LLMTestResult | null>(null);
  const [notice, setNotice] = useState<{ tone: "sage" | "ember" | "amber"; text: string } | null>(null);

  const load = useCallback(async () => {
    const s = await api<LLMStatus>("/admin/llm");
    setStatus(s);
    setPrimary(s.primary);
    setFallback(s.fallback ?? "");
    setResult(s.last_test);
  }, []);

  useEffect(() => {
    Promise.resolve()
      .then(() => load())
      .catch((e) => setNotice({ tone: "ember", text: errorMessage(e) }));
  }, [load]);

  const test = async () => {
    setTesting(true);
    setNotice(null);
    try {
      const body: Record<string, string> = {};
      if (apiKey.trim()) body.api_key = apiKey.trim();
      if (primary.trim()) body.primary = primary.trim();
      if (fallback.trim()) body.fallback = fallback.trim();
      const r = await api<LLMTestResult>("/admin/llm/test", { method: "POST", json: body });
      setResult(r);
      setNotice(r.ok ? { tone: "sage", text: "Conexão OK. Pode salvar." } : { tone: "ember", text: r.error ?? "O teste falhou." });
    } catch (e) {
      setNotice({ tone: "ember", text: errorMessage(e) });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const body: Record<string, unknown> = { primary: primary.trim() || undefined };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      if (fallback.trim()) body.fallback = fallback.trim();
      else body.clear_fallback = true;
      const s = await api<LLMStatus>("/admin/llm", { method: "PUT", json: body });
      setStatus(s);
      setApiKey("");
      setNotice({ tone: "sage", text: "Configuração salva. O Tom já está usando." });
    } catch (e) {
      setNotice({ tone: "ember", text: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  const removeKey = async () => {
    if (!confirm("Remover a chave guardada no banco? O sistema volta a usar a chave do .env, se houver.")) return;
    try {
      const s = await api<LLMStatus>("/admin/llm/key", { method: "DELETE" });
      setStatus(s);
      setNotice({ tone: "amber", text: "Chave removida do banco." });
    } catch (e) {
      setNotice({ tone: "ember", text: errorMessage(e) });
    }
  };

  return (
    <Card
      title="Modelo de linguagem"
      subtitle="Chave da OpenAI e modelos usados pelo Tom. A chave fica cifrada no banco e prevalece sobre o .env."
      actions={
        status && (
          <div className="flex flex-col items-end gap-1">
            {status.mode === "mock" ? (
              <Badge tone="amber">modo simulado (LLM_MODE=mock)</Badge>
            ) : status.key.configured ? (
              <Badge tone="sage">
                chave ativa · {status.key.source} · …{status.key.suffix}
              </Badge>
            ) : (
              <Badge tone="ember">sem chave</Badge>
            )}
            {status.key.unreadable && <Badge tone="ember">chave do banco ilegível (SECRET_KEY mudou)</Badge>}
          </div>
        )
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <div className="md:col-span-2">
          <Label>Chave da API (OpenAI)</Label>
          <div className="relative">
            <KeyRound className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-dim" />
            <Input
              className="pl-9 pr-10 font-mono"
              type={show ? "text" : "password"}
              autoComplete="off"
              placeholder={status?.key.configured ? `mantida (…${status.key.suffix}); cole uma nova para trocar` : "sk-…"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button type="button" onClick={() => setShow((v) => !v)} className="absolute inset-y-0 right-0 px-3 text-muted hover:text-ivory" aria-label="Mostrar chave">
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="mt-1 text-xs text-dim">A chave nunca é devolvida pela API; só os últimos quatro caracteres.</p>
        </div>
        <div>
          <Label>Modelo principal</Label>
          <Input className="font-mono" value={primary} onChange={(e) => setPrimary(e.target.value)} placeholder={status?.env_defaults.primary} />
        </div>
        <div>
          <Label>Modelo de fallback (opcional)</Label>
          <Input className="font-mono" value={fallback} onChange={(e) => setFallback(e.target.value)} placeholder={status?.env_defaults.fallback ?? "—"} />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={test} loading={testing} disabled={saving}>
          <PlugZap className="h-4 w-4" />
          Testar conexão
        </Button>
        <Button onClick={save} loading={saving} disabled={testing}>
          <Save className="h-4 w-4" />
          Salvar
        </Button>
        {status?.key.source === "banco" && (
          <Button variant="danger" onClick={removeKey} disabled={saving || testing}>
            <Trash2 className="h-4 w-4" />
            Remover chave do banco
          </Button>
        )}
        {notice && (
          <div className="ml-auto">
            <Alert tone={notice.tone}>{notice.text}</Alert>
          </div>
        )}
      </div>

      {result && (
        <div className="mt-4 rounded-lg border border-line bg-ink p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
            {result.ok ? <CheckCircle2 className="h-4 w-4 text-sage" /> : <XCircle className="h-4 w-4 text-ember" />}
            <span className="text-ivory">{result.ok ? "Conexão verificada" : "Falha na conexão"}</span>
            {result.model_used && <Badge tone="muted" mono>{result.model_used}</Badge>}
            {result.latency_ms !== undefined && <Badge tone="muted">{fmtMs(result.latency_ms)}</Badge>}
            {result.tested_at && (
              <span className="ml-auto text-xs text-dim">
                {fmtDateTime(result.tested_at)}
                {result.tested_by ? ` · ${result.tested_by}` : ""}
                {result.tested_saved_config === false ? " · chave não salva" : ""}
              </span>
            )}
          </div>
          <ul className="space-y-1">
            {result.steps.map((s) => (
              <li key={s.step} className="flex items-start gap-2 text-sm">
                {s.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-sage" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-ember" />}
                <span className="font-mono text-xs text-muted">{s.step}</span>
                <span className="text-parchment">{s.detail}</span>
              </li>
            ))}
          </ul>
          {result.warnings?.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-amber">
              {result.warnings.map((w) => (
                <li key={w}>• {w}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
