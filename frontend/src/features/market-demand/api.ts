import type { AgentState, ChatMessage, StreamEvent } from "./types";
import api from "@/services/api";

const DEFAULT_PROD_API_URL = "https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io";
const DEV_HOST = typeof window !== "undefined" ? window.location.hostname : "localhost";
const DEFAULT_DEV_API_URL = `http://${DEV_HOST}:8000`;
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : DEFAULT_DEV_API_URL);

function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

interface StreamChatArgs {
  message: string;
  threadId: string | null;
  onEvent: (event: StreamEvent) => void;
  onThreadId?: (threadId: string) => void;
  onError?: (err: unknown) => void;
  signal?: AbortSignal;
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;
  try {
    const { authApi } = await import("@/features/auth/api");
    const tokens = await authApi.refresh(refreshToken);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return tokens.access_token;
  } catch {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    return null;
  }
}

async function fetchWithAuth(
  url: string,
  body: string,
  token: string,
  signal?: AbortSignal,
): Promise<Response> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body,
    signal,
  });

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${newToken}`,
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body,
        signal,
      });
    }
  }

  return res;
}

export async function streamMarketDemandChat({
  message,
  threadId,
  onEvent,
  onThreadId,
  onError,
  signal,
}: StreamChatArgs): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const url = `${API_URL}/market-demand/chat`;
  const body = JSON.stringify({ message, thread_id: threadId });
  const res = await fetchWithAuth(url, body, token, signal);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Market demand chat failed (${res.status})`);
  }

  // Capture thread_id from response header
  const returnedThreadId = res.headers.get("X-Thread-Id");
  if (returnedThreadId && onThreadId) {
    onThreadId(returnedThreadId);
  }

  if (!res.body) {
    throw new Error("Streaming not supported by the browser");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const rawMessage = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const lines = rawMessage.split("\n").map((l) => l.trimEnd());
        let eventType: string | null = null;
        let eventData: string | null = null;

        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith("event:")) {
            eventType = line.slice("event:".length).trim();
          } else if (line.startsWith("data:")) {
            eventData = line.slice("data:".length).trim();
          }
        }

        if (eventData) {
          try {
            const parsed = JSON.parse(eventData);
            if (!parsed.type && eventType) {
              parsed.type = eventType;
            }
            onEvent(parsed as StreamEvent);
          } catch (e) {
            onError?.(e);
          }
        }
      }
    }
  } catch (e) {
    const isAbort =
      typeof e === "object" &&
      e !== null &&
      "name" in e &&
      (e as { name: string }).name === "AbortError";
    if (!isAbort) {
      onError?.(e);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}

export interface HistoryResponse {
  messages: ChatMessage[];
  threadId: string;
}

export async function fetchConversationHistory(): Promise<HistoryResponse> {
  const { data } = await api.get<HistoryResponse>("/market-demand/history");
  return data;
}

export async function fetchAgentState(): Promise<AgentState> {
  const { data } = await api.get<AgentState>("/market-demand/state");
  return data;
}

export async function deleteConversation(): Promise<void> {
  await api.delete("/market-demand/history");
}
