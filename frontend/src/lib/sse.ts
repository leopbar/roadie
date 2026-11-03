import { API_BASE, ApiError, refreshSession } from "./api";
import type { StreamEvent } from "./types";

// EventSource só faz GET; o envio de mensagem é POST, então lemos o corpo
// como stream e interpretamos o formato text/event-stream à mão.
export async function streamPost(
  path: string,
  json: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  retry = true,
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(json),
    signal,
  });
  if (res.status === 401 && retry && (await refreshSession())) {
    return streamPost(path, json, onEvent, signal, false);
  }
  if (!res.ok || !res.body) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json())?.detail ?? detail;
    } catch {
      /* sem corpo */
    }
    throw new ApiError(res.status, detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const flush = () => {
    if (dataLines.length === 0) return;
    const raw = dataLines.join("\n");
    dataLines = [];
    const name = eventName;
    eventName = "message";
    if (name === "ping") return;
    try {
      const parsed = JSON.parse(raw) as StreamEvent;
      onEvent(parsed);
    } catch {
      /* linha de keep-alive ou lixo: ignora */
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).replace(/\r$/, "");
      buffer = buffer.slice(idx + 1);
      if (line === "") {
        flush();
      } else if (line.startsWith(":")) {
        /* comentário / ping */
      } else if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).replace(/^ /, ""));
      }
    }
  }
  flush();
}
