"use client";

import { Eye, EyeOff, KeyRound } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Alert, Button, Input, Label } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api<User>("/auth/login", { method: "POST", json: { email, password }, retry: false });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? next : "/simulador");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-brass/40 bg-brass/10 font-display text-2xl text-brass-bright">
            R
          </span>
          <h1 className="font-display text-3xl text-ivory">Roadie</h1>
          <p className="mt-1 text-xs uppercase tracking-[0.3em] text-muted">Empório da Música</p>
          <p className="mt-4 text-sm text-muted">Console de atendimento do Tom. Acesso restrito à equipe.</p>
        </div>
        <form onSubmit={submit} className="panel space-y-4 p-6">
          <div>
            <Label>E-mail</Label>
            <Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </div>
          <div>
            <Label>Senha</Label>
            <div className="relative">
              <Input type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required className="pr-10" />
              <button type="button" onClick={() => setShow((v) => !v)} className="absolute inset-y-0 right-0 px-3 text-muted hover:text-ivory" aria-label="Mostrar senha">
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          {error && <Alert>{error}</Alert>}
          <Button type="submit" loading={loading} className="w-full">
            <KeyRound className="h-4 w-4" />
            Entrar
          </Button>
        </form>
        <p className="mt-6 text-center text-xs text-dim">Sessão protegida por cookies httpOnly. Nada fica no navegador.</p>
      </div>
    </main>
  );
}
