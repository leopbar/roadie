"use client";

import { Plus, Trash2, UserCog } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-provider";
import { Alert, Badge, Button, Card, Input, Label, Select } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import type { User } from "@/lib/types";

export function UsersCard() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "agent" as User["role"] });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "sage" | "ember"; text: string } | null>(null);

  const load = useCallback(() => api<User[]>("/admin/users").then(setUsers), []);
  useEffect(() => {
    load().catch((e) => setNotice({ tone: "ember", text: errorMessage(e) }));
  }, [load]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await api<User>("/admin/users", { method: "POST", json: form });
      setForm({ email: "", name: "", password: "", role: "agent" });
      await load();
      setNotice({ tone: "sage", text: "Usuário criado." });
    } catch (err) {
      setNotice({ tone: "ember", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (u: User) => {
    try {
      await api<User>(`/admin/users/${u.id}`, { method: "PATCH", json: { is_active: !u.is_active } });
      await load();
    } catch (err) {
      setNotice({ tone: "ember", text: errorMessage(err) });
    }
  };

  const remove = async (u: User) => {
    if (!confirm(`Remover ${u.email}?`)) return;
    try {
      await api<void>(`/admin/users/${u.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setNotice({ tone: "ember", text: errorMessage(err) });
    }
  };

  return (
    <Card title="Usuários do console" subtitle="Quem pode entrar. Admin gerencia usuários e o modelo; atendente usa o simulador e as visões.">
      <form onSubmit={create} className="grid gap-3 md:grid-cols-[1.2fr_1fr_1fr_auto_auto] md:items-end">
        <div>
          <Label>E-mail</Label>
          <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div>
          <Label>Nome</Label>
          <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <Label>Senha inicial</Label>
          <Input type="password" required autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="10+ caracteres, maiúscula, minúscula e número" />
        </div>
        <div>
          <Label>Papel</Label>
          <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as User["role"] })}>
            <option value="agent">atendente</option>
            <option value="admin">admin</option>
          </Select>
        </div>
        <Button type="submit" loading={busy}>
          <Plus className="h-4 w-4" />
          Criar
        </Button>
      </form>
      {notice && (
        <div className="mt-3">
          <Alert tone={notice.tone}>{notice.text}</Alert>
        </div>
      )}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
            <tr>
              <th className="py-2 pr-4">Usuário</th>
              <th className="py-2 pr-4">Papel</th>
              <th className="py-2 pr-4">Último acesso</th>
              <th className="py-2 pr-4">Estado</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="py-2 pr-4">
                  <span className="text-ivory">{u.name}</span>
                  <p className="text-xs text-muted">{u.email}</p>
                </td>
                <td className="py-2 pr-4">
                  <Badge tone={u.role === "admin" ? "brass" : "muted"}>{u.role === "admin" ? "admin" : "atendente"}</Badge>
                </td>
                <td className="py-2 pr-4 text-xs text-muted">{fmtDateTime(u.last_login_at)}</td>
                <td className="py-2 pr-4">
                  <Badge tone={u.is_active ? "sage" : "ember"}>{u.is_active ? "ativo" : "inativo"}</Badge>
                </td>
                <td className="py-2 text-right">
                  {u.id !== me?.id && (
                    <span className="inline-flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => toggle(u)} title={u.is_active ? "Desativar" : "Ativar"}>
                        <UserCog className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(u)} title="Remover">
                        <Trash2 className="h-4 w-4 text-ember" />
                      </Button>
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
