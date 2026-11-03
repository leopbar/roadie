"use client";

import { Lock } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Input, Label } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "sage" | "ember"; text: string } | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await api<void>("/auth/password", { method: "POST", json: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      setNotice({ tone: "sage", text: "Senha alterada." });
    } catch (err) {
      setNotice({ tone: "ember", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Minha senha" subtitle="Mínimo de 10 caracteres, com maiúscula, minúscula e número.">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <div>
          <Label>Senha atual</Label>
          <Input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </div>
        <div>
          <Label>Nova senha</Label>
          <Input type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} />
        </div>
        <Button type="submit" loading={busy}>
          <Lock className="h-4 w-4" />
          Alterar
        </Button>
      </form>
      {notice && (
        <div className="mt-3">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}
    </Card>
  );
}
