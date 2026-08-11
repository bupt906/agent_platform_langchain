import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "../lib/api";

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
  path?: string;
}

export function useSSE() {
  const [messages, setMessages] = useState<SSEMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  // 用递增 id 追踪当前请求，解决快速连续发送的竞态条件
  const requestIdRef = useRef(0);

  // 组件卸载时标记为未挂载，防止在已卸载组件上 setState
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const send = useCallback(
    (body: { message: string; agent?: string; skill?: string; model?: string; thinking?: boolean; session_id?: string; profile_id?: string; response_mode?: "general" | "auto" }) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const currentRequestId = ++requestIdRef.current;

      setMessages([]);
      setIsStreaming(true);

      fetch(apiUrl("/chat/stream"), {
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
            // 同时处理 \n 和 \r\n 行结束符
            const lines = buffer.split(/\r?\n/);
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const data = JSON.parse(line.slice(6));
                // 仅在仍是当前请求且组件未卸载时才更新状态
                if (requestIdRef.current === currentRequestId && mountedRef.current) {
                  setMessages((prev) => [...prev, data]);
                }
              } catch {
                // 格式错误的 SSE 数据跳过，但不吞没——记录到 console 方便调试
                if (import.meta.env.DEV) {
                  console.warn("SSE parse error for line:", line.slice(0, 100));
                }
              }
            }
          }
        })
        .catch((e) => {
          if (e.name !== "AbortError" && requestIdRef.current === currentRequestId && mountedRef.current) {
            setMessages([{ type: "error", error: String(e) }]);
          }
        })
        .finally(() => {
          // 仅当这是当前活跃的请求时才设置 streaming 为 false
          if (requestIdRef.current === currentRequestId && mountedRef.current) {
            setIsStreaming(false);
          }
        });
    }, []
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, send, stop };
}
