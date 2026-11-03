const dateTime = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Campo_Grande",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const timeOnly = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Campo_Grande",
  hour: "2-digit",
  minute: "2-digit",
});

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : dateTime.format(d);
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : timeOnly.format(d);
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}

export function fmtUsd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `US$ ${value.toFixed(5)}`;
}

export function fmtTokens(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("pt-BR").format(n);
}

/** Converte um instante para o valor de um <input type="datetime-local"> no fuso da loja. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "America/Campo_Grande",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
  return parts.replace(" ", "T");
}

export const TICKET_STATUS_LABEL: Record<string, string> = {
  aberto: "Aberto",
  em_andamento: "Em andamento",
  resolvido: "Resolvido",
};

export const SEVERITY_LABEL: Record<string, string> = {
  quarantine: "Quarentena",
  warning: "Atenção",
  info: "Info",
};

export const TOOL_LABEL: Record<string, string> = {
  buscar_produtos: "Busca no catálogo",
  detalhar_produto: "Detalhe do produto",
  promocoes_ativas: "Promoções ativas",
  verificar_identidade: "Verificação de identidade",
  meus_pedidos: "Pedidos do cliente",
  consultar_pedido: "Consulta de pedido",
  avaliar_devolucao: "Avaliação de devolução",
  calcular_parcelas: "Parcelamento",
  calcular_frete: "Frete",
  horario_loja: "Horário da loja",
  informacoes_loja: "Informações da loja",
  consultar_politicas: "Consulta às políticas",
  abrir_ticket: "Abertura de ticket",
};
