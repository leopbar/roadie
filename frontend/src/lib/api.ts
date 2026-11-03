// Cliente HTTP do console. Fala só com /api/* (mesma origem), cookies httpOnly
// vão sozinhos. Em 401 tenta renovar a sessão uma vez e repete a chamada.

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Erro ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

let refreshing: Promise<boolean> | null = null;

export async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit | null; retry?: boolean };

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { json, retry = true, headers, ...rest } = options;
  const init: RequestInit = {
    ...rest,
    credentials: "include",
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(headers ?? {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body ?? null,
  };
  const res = await fetch(`${API_BASE}${path}`, init);
  if (res.status === 401 && retry && !path.startsWith("/auth/login") && !path.startsWith("/auth/refresh")) {
    if (await refreshSession()) return api<T>(path, { ...options, retry: false });
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? body;
    } catch {
      /* corpo vazio */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === "string") return err.detail;
    if (Array.isArray(err.detail)) {
      return err.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    }
    return `Erro ${err.status}`;
  }
  if (err instanceof Error) return err.message;
  return "Erro inesperado";
}
