const API_BASE = import.meta.env.VITE_API_BASE || "";
const SKIP_AUTH_KEY = "skip_auth";

let authEnabledCache: boolean | null = null;

export function getToken(): string | null {
  return localStorage.getItem("auth_token");
}

export function setToken(token: string): void {
  localStorage.setItem("auth_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("auth_token");
}

export function getSkipAuthPreference(): boolean {
  return localStorage.getItem(SKIP_AUTH_KEY) === "1";
}

export function setSkipAuthPreference(skip: boolean): void {
  if (skip) {
    localStorage.setItem(SKIP_AUTH_KEY, "1");
  } else {
    localStorage.removeItem(SKIP_AUTH_KEY);
  }
}

export async function fetchAuthConfig(): Promise<{
  auth_enabled: boolean;
  backend_ok: boolean;
}> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/config`);
    if (!res.ok) {
      return { auth_enabled: true, backend_ok: false };
    }
    const data = (await res.json()) as { auth_enabled: boolean };
    authEnabledCache = data.auth_enabled;
    return { auth_enabled: data.auth_enabled, backend_ok: true };
  } catch {
    return { auth_enabled: true, backend_ok: false };
  }
}

export function isAuthEnabledCached(): boolean {
  return authEnabledCache !== false;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401 && authEnabledCache !== false) {
    clearToken();
    window.location.href = "/";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export function oauthLoginUrl(provider: "google" | "apple" | "facebook"): string {
  return `${API_BASE}/api/auth/${provider}/login`;
}

export interface UserProfile {
  user_id: string;
  email: string;
  display_name: string;
  provider: string;
  avatar_url?: string;
}

export interface BookSummary {
  book_id: string;
  title: string;
  total_pages?: number;
}

export interface UploadJobResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface UploadStatusResponse {
  job_id: string;
  status: string;
  message: string;
  book?: BookSummary;
  error?: string;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function uploadBookWithProgress(
  file: File,
  onProgress: (message: string) => void
): Promise<BookSummary> {
  const form = new FormData();
  form.append("file", file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const startRes = await fetch(`${API_BASE}/api/books/upload`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!startRes.ok) {
    const err = await startRes.json().catch(() => ({ detail: startRes.statusText }));
    throw new Error(err.detail || "Upload failed");
  }

  const started = (await startRes.json()) as UploadJobResponse;
  onProgress(started.message || "Processing PDF...");

  for (let i = 0; i < 600; i += 1) {
    await sleep(2000);
    const status = await apiFetch<UploadStatusResponse>(`/api/books/upload/${started.job_id}`);
    onProgress(status.message || status.status);

    if (status.status === "done" && status.book) {
      return status.book;
    }
    if (status.status === "error") {
      throw new Error(status.error || "Ingestion failed");
    }
  }

  throw new Error("Upload timed out after 20 minutes. Check backend logs.");
}

export interface ConversationSummary {
  conversation_id: string;
  book_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  export_id?: string;
  metadata?: {
    docx_available?: boolean;
    docx_download_url?: string;
  };
  created_at: string;
}

export interface StreamStatus {
  stage: string;
  detail?: Record<string, unknown> | null;
}

export interface ChatStreamResult {
  assistant_message: Message;
  docx_available: boolean;
  docx_download_url?: string;
}

const STATUS_LABELS: Record<string, string> = {
  received: "Message received",
  parsing_intent: "Understanding your request",
  answering_question: "Searching the book and drafting answer",
  rewriting_book: "Rewriting full book (this may take a while)",
  exporting_word: "Preparing Word file",
  preparing_word: "Generating Word download",
  done: "Done",
};

export function statusLabel(stage: string): string {
  return STATUS_LABELS[stage] || stage.replace(/_/g, " ");
}

export async function sendMessageStream(
  conversationId: string,
  content: string,
  onStatus: (status: StreamStatus) => void
): Promise<ChatStreamResult> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/conversations/${conversationId}/messages/stream`, {
    method: "POST",
    headers: {
      Authorization: token ? `Bearer ${token}` : "",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ content }),
  });

  if (res.status === 401 && authEnabledCache !== false) {
    clearToken();
    window.location.href = "/";
    throw new Error("Unauthorized");
  }
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Stream failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: ChatStreamResult | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;

      if (event === "status") {
        const parsed = JSON.parse(data) as StreamStatus;
        onStatus(parsed);
      } else if (event === "error") {
        const parsed = JSON.parse(data) as { detail?: string };
        throw new Error(parsed.detail || "Stream error");
      } else if (event === "done") {
        finalResult = JSON.parse(data) as ChatStreamResult;
      }
    }
  }

  if (!finalResult) {
    throw new Error("Stream ended without a response");
  }
  return finalResult;
}
