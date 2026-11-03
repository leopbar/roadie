import { Suspense } from "react";

import { AuthProvider } from "@/components/auth-provider";
import { Shell } from "@/components/shell";

function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-brass border-t-transparent" />
    </div>
  );
}

// Painel dinâmico por natureza (sessão, relógio, streaming): opta fora da
// validação de navegação instantânea do Next, que só gera ruído aqui.
export const instant = false;

// O console é todo dinâmico (hooks de rota e sessão). O Suspense permite ao
// Next prerenderizar a casca estática e transmitir o resto em tempo de execução.
export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<Loading />}>
      <AuthProvider>
        <Shell>{children}</Shell>
      </AuthProvider>
    </Suspense>
  );
}
