"use client";

import { useAuth } from "@/components/auth-provider";
import { LLMSettingsCard } from "@/components/llm-settings-card";
import { PasswordCard } from "@/components/password-card";
import { PageHeader } from "@/components/ui";
import { UsersCard } from "@/components/users-card";

export default function ConfiguracoesPage() {
  const { isAdmin } = useAuth();
  return (
    <div className="space-y-6">
      <PageHeader title="Configurações" description={isAdmin ? "Modelo de linguagem, usuários e sua senha." : "Sua senha. Modelo e usuários são gerenciados por um administrador."} />
      {isAdmin && <LLMSettingsCard />}
      {isAdmin && <UsersCard />}
      <PasswordCard />
    </div>
  );
}
