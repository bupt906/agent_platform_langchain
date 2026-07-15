import { useCallback, useRef, useState } from "react";

export interface SSEMessage {
  type: string;
  content?: string;
  skill?: string;
  mode?: string;
  confidence?: number;
  tool?: string;
  input?: string;
  output?: string;
  error?: string;
  finish_reason?: string;
  tool_calls?: number;
}

export function useSSE() {
  const [messages, setMessages] = useState<SSEMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    (body: { message: string; agent?: string; skill?: string; thinking?: boolean; session_id?: string }) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      setMessages([]);
      setIsStreaming(true);

      fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
        .then(async (res) => {
          if (!res.ok) throw new Error(`${res.status}`);
          const reader = res.body?.getReader();
          if (!reader) return;
          const decoder = new TextDecoder();
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const data = JSON.parse(line.slice(6));
                setMessages((prev) => [...prev, data]);
              } catch { /* skip */ }
            }
          }
        })
        .catch((e) => {
          if (e.name !== "AbortError") {
            setMessages([{ type: "error", error: String(e) }]);
          }
        })
        .finally(() => setIsStreaming(false));
    }, []
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, send, stop };
}
