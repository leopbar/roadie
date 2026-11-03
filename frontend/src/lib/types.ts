export type User = {
  id: string;
  email: string;
  name: string;
  role: "admin" | "agent";
  is_active: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
};

export type Customer = {
  customer_id: number;
  name: string;
  phone: string | null;
  city: string | null;
  orders: number;
};

export type ToolCall = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: { ok: boolean; summary: string | null; duration_ms: number | null } | null;
};

export type Receipt = {
  version: number;
  clock: { now: string; label: string };
  identity: { customer_id: number | null; name: string | null; city: string | null; verified: boolean; via: string | null };
  identity_update: Record<string, unknown> | null;
  tools: ToolCall[];
  sources: { tables: string[]; rows: { table: string; id: string | number }[]; clauses: string[]; rules: string[] };
  flags: string[];
  tickets: { protocolo: string; categoria: string; prazo_retorno: string }[];
  model: { mode: string; primary: string; used: string[]; fallback_used: boolean; llm_calls: number };
  tokens: { input: number; output: number; total: number };
  cost_usd: number | null;
  pricing_as_of: string;
  latency_ms: number;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  receipt: Receipt | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  title: string | null;
  channel: string;
  sender_phone: string | null;
  customer_id: number | null;
  customer_name: string | null;
  identity_verified: boolean;
  verified_via: string | null;
  clock_override: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message: string | null;
};

export type ConversationDetail = Conversation & { messages: Message[] };

export type Ticket = {
  id: number;
  protocol: string;
  category: string;
  status: "aberto" | "em_andamento" | "resolvido";
  summary: string;
  customer_id: number | null;
  customer_name: string | null;
  order_id: number | null;
  conversation_id: string | null;
  sla_due_at: string | null;
  created_at: string;
};

export type Flag = {
  id: number;
  entity: string;
  entity_id: string;
  entity_label: string | null;
  flag: string;
  severity: "quarantine" | "warning" | "info";
  detail: string;
};

export type Quality = { summary: Record<string, number>; flags: Flag[] };

export type Clause = { clause_id: string; section: number; title: string; body: string; page: number | null };
export type ClauseHit = { id: string; titulo: string; texto: string; rank: number };

export type Product = {
  product_id: number;
  name: string;
  brand: string | null;
  category: string | null;
  price_brl: string;
  stock_quantity: number;
  status: string;
  availability: string;
  promotion: { description: string | null; percent: string; price: string } | null;
  quality: { nivel: "quarentena" | "atencao"; divergencias: string[]; instrucao: string } | null;
};

export type Meta = {
  version: string;
  env: string;
  clock: { default_now: string; label: string; simulated: boolean; timezone: string };
  model: { mode: string; primary: string; fallback: string | null; configured: boolean; key_source: string | null };
  counts: Record<string, number>;
};

export type LLMTestStep = { step: string; ok: boolean; detail: string };
export type LLMTestResult = {
  ok: boolean;
  steps: LLMTestStep[];
  warnings: string[];
  error?: string;
  latency_ms?: number;
  model_used?: string;
  tokens?: { input: number | null; output: number | null };
  tested_saved_config?: boolean;
  tested_at?: string;
  tested_by?: string;
};

export type LLMStatus = {
  mode: string;
  key: { configured: boolean; source: "banco" | "ambiente" | null; suffix: string | null; unreadable: boolean };
  primary: string;
  fallback: string | null;
  env_defaults: { primary: string; fallback: string | null };
  last_test: LLMTestResult | null;
  updated_at: string | null;
};

export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "tool_start"; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_end"; id: string; name: string; ok: boolean; summary: string | null; duration_ms: number | null }
  | { type: "done"; message_id: string; conversation_id: string; content: string; receipt: Receipt }
  | { type: "error"; detail: string };
