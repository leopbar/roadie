"use client";

import { Clock3, Phone } from "lucide-react";

import { Input, Label, Select, cx } from "@/components/ui";
import type { Customer } from "@/lib/types";

export type Sender = { mode: "customer" | "unknown"; customerId: number | null; phone: string };

export function SenderPicker({ customers, value, onChange, disabled }: { customers: Customer[]; value: Sender; onChange: (s: Sender) => void; disabled?: boolean }) {
  const selected = customers.find((c) => c.customer_id === value.customerId);
  return (
    <div>
      <Label>
        <span className="inline-flex items-center gap-1">
          <Phone className="h-3 w-3" /> Remetente (número do WhatsApp)
        </span>
      </Label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select
          value={value.mode === "unknown" ? "unknown" : String(value.customerId ?? "")}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "unknown") onChange({ mode: "unknown", customerId: null, phone: value.phone || "(67) 90000-0000" });
            else {
              const c = customers.find((x) => String(x.customer_id) === v);
              onChange({ mode: "customer", customerId: c?.customer_id ?? null, phone: c?.phone ?? "" });
            }
          }}
        >
          <option value="unknown">Número não cadastrado</option>
          {customers.map((c) => (
            <option key={c.customer_id} value={c.customer_id}>
              {c.name} · {c.city} · {c.orders} pedido{c.orders === 1 ? "" : "s"}
            </option>
          ))}
        </Select>
        {value.mode === "unknown" ? (
          <Input className="sm:w-48" value={value.phone} disabled={disabled} onChange={(e) => onChange({ ...value, phone: e.target.value })} placeholder="(67) 9...." />
        ) : (
          <div className={cx("flex h-10 items-center rounded-lg border border-line bg-ink px-3 font-mono text-xs text-muted sm:w-48", !selected && "text-dim")}>
            {selected?.phone ?? "—"}
          </div>
        )}
      </div>
    </div>
  );
}

const PRESETS: { label: string; value: string }[] = [
  { label: "Terça 10:00", value: "2026-03-24T10:00" },
  { label: "Sexta 18:30", value: "2026-03-27T18:30" },
  { label: "Sábado 14:00", value: "2026-03-28T14:00" },
  { label: "Domingo", value: "2026-03-29T11:00" },
];

export function ClockControl({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <div>
      <Label>
        <span className="inline-flex items-center gap-1">
          <Clock3 className="h-3 w-3" /> Relógio da loja (simulado)
        </span>
      </Label>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input type="datetime-local" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="sm:w-56" />
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              disabled={disabled}
              onClick={() => onChange(p.value)}
              className={cx(
                "rounded-full border px-2.5 py-1 text-[11px] transition-colors disabled:opacity-50",
                value === p.value ? "border-brass/60 bg-brass/10 text-brass-bright" : "border-line-strong text-muted hover:text-ivory",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
