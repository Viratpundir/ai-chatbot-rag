export type CurrentUser = {
  user_id: string;
  name: string;
  email: string;
  role: string;
  department?: string | null;
};

export type DocumentRecord = {
  document_id: string;
  filename: string;
  status: string;
  classification: string;
  department?: string | null;
  created_at: string;
  updated_at?: string | null;
  file_size?: number | null;
  page_count?: number | null;
  chunk_count?: number | null;
  error_message?: string | null;
};

export type Citation = {
  index: number;
  filename: string;
  page?: number | null;
  document_id?: string | null;
  section?: string | null;
  excerpt: string;
};

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at?: string | null;
  message_count: number;
};

export type ConversationDetail = ConversationSummary & {
  messages: Array<{
    message_id: string;
    role: string;
    content: string;
    created_at: string;
    citations?: Citation[] | null;
  }>;
};

export type AdminStats = {
  total_users: number;
  active_users: number;
  total_documents: number;
  processing_documents: number;
  failed_documents: number;
  ready_documents: number;
  total_pages: number;
  total_chunks: number;
  searchable_documents: number;
  total_queries: number;
  queries_today: number;
  average_retrieval_ms?: number | null;
  average_llm_ms?: number | null;
  average_total_ms?: number | null;
  retrieval_top_k: number;
  rerank_top_k: number;
};

export type SystemHealth = {
  status: string;
  database: string;
  redis: string;
  vector_store: string;
  embeddings: string;
  llm: string;
  uptime_seconds?: number | null;
  worker_count?: number | null;
};

export type AdminUser = CurrentUser & {
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
  last_login?: string | null;
};

export type AuditLogRecord = {
  log_id: string;
  user_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  timestamp: string;
  ip_address?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type AdminDocument = {
  document_id: string;
  filename: string;
  owner_id: string;
  owner_name: string;
  owner_email: string;
  page_count?: number | null;
  chunk_count?: number | null;
  status: string;
  created_at: string;
  file_size: number;
  error_message?: string | null;
};

export type ChatResult = {
  answer: string;
  citations: Citation[];
  conversation_id: string;
  message_id?: string;
  model: string;
  total_time_ms: number;
  retrieval_time_ms?: number;
  embedding_time_ms?: number;
  reranking_time_ms?: number;
  llm_time_ms?: number;
  llm_first_token_ms?: number | null;
  has_answer?: boolean;
};

const API_BASE = "";
const REQUEST_TIMEOUT_MS = 30_000;

async function fetchApi(url: string, init: RequestInit) {
  try {
    return await fetch(url, {
      ...init,
      signal: init.signal || AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("The server took too long to respond. Please try again.");
    }
    if (error instanceof TypeError) {
      throw new Error("Unable to reach the knowledge service. Please try again.");
    }
    throw error;
  }
}

export function saveSession(accessToken: string, refreshToken: string) {
  sessionStorage.setItem("access_token", accessToken);
  sessionStorage.setItem("refresh_token", refreshToken);
}

export function clearSession() {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
}

async function readError(response: Response, path: string) {
  if (response.status === 401 && !path.endsWith("/auth/login")) {
    return "Your session has expired. Please sign in again.";
  }
  if (response.status === 403) return "You do not have permission to perform this action.";
  if (response.status === 404) return "The requested API endpoint was not found.";
  if (response.status === 503) return "The AI service is temporarily unavailable. Please try again.";
  if (response.status === 504) return "The AI service took too long to respond. Please try again.";
  if (response.status >= 500) return "Something went wrong on the server. Please try again.";
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item: { msg?: string }) => item.msg).join("; ");
    if (body.error?.message) return body.error.message;
  } catch {
    // Keep the status-based message when the response is not JSON.
  }
  return `Request failed (${response.status})`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const makeRequest = (token: string | null) => {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return fetchApi(`${API_BASE}${path}`, { ...init, headers });
  };

  let token = sessionStorage.getItem("access_token");
  let response = await makeRequest(token);

  if (response.status === 401 && !path.endsWith("/auth/refresh")) {
    const refreshToken = sessionStorage.getItem("refresh_token");
    if (refreshToken) {
      const refreshed = await fetchApi(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshed.ok) {
        const tokens = (await refreshed.json()) as { access_token: string };
        token = tokens.access_token;
        sessionStorage.setItem("access_token", token);
        response = await makeRequest(token);
      } else {
        clearSession();
      }
    }
  }

  if (!response.ok) throw new Error(await readError(response, path));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function streamApi<T>(
  path: string,
  body: unknown,
  onToken: (token: string) => void,
  signal?: AbortSignal,
): Promise<T> {
  const streamTimeout = AbortSignal.timeout(120_000);
  const requestSignal = signal ? AbortSignal.any([signal, streamTimeout]) : streamTimeout;
  const makeRequest = (token: string | null) => {
    const headers = new Headers({
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    });
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetchApi(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: requestSignal,
    });
  };

  let token = sessionStorage.getItem("access_token");
  let response = await makeRequest(token);
  if (response.status === 401) {
    const refreshToken = sessionStorage.getItem("refresh_token");
    if (refreshToken) {
      const refreshed = await fetchApi(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshed.ok) {
        const tokens = (await refreshed.json()) as { access_token: string };
        token = tokens.access_token;
        sessionStorage.setItem("access_token", token);
        response = await makeRequest(token);
      } else {
        clearSession();
      }
    }
  }

  if (!response.ok) throw new Error(await readError(response, path));
  if (!response.body) throw new Error("The knowledge service returned an empty stream. Please retry.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];
  let result: T | undefined;

  function dispatchEvent() {
    if (!dataLines.length) {
      eventName = "message";
      return;
    }
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      throw new Error("The AI response was interrupted. Please retry.");
    }
    if (eventName === "token" && typeof payload.token === "string") {
      onToken(payload.token);
    } else if (eventName === "complete") {
      result = payload as T;
    } else if (eventName === "error") {
      throw new Error(typeof payload.message === "string" ? payload.message : "The response was interrupted. Please retry.");
    }
    eventName = "message";
    dataLines = [];
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
        }
        dispatchEvent();
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("The AI service took too long to respond. Please retry.");
    }
    if (error instanceof TypeError) {
      throw new Error("The AI response was interrupted. Please retry.");
    }
    throw error;
  }

  if (buffer.trim()) {
    for (const line of buffer.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    dispatchEvent();
  }
  if (result === undefined) throw new Error("The response stream ended before completion. Please retry.");
  return result;
}

export async function downloadDocument(documentId: string, filename: string) {
  const url = `${API_BASE}/api/v1/documents/${documentId}/download`;
  const request = () => fetchApi(url, {
    headers: { Authorization: `Bearer ${sessionStorage.getItem("access_token") || ""}` },
  });
  let response = await request();
  if (response.status === 401) {
    await api("/api/v1/auth/me");
    response = await request();
  }
  if (!response.ok) throw new Error(await readError(response, `/api/v1/documents/${documentId}/download`));
  const href = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 30_000);
}

export async function listDocuments() {
  const documents: DocumentRecord[] = [];
  let total = 0;
  let page = 1;
  do {
    const result = await api<{ documents: DocumentRecord[]; total: number }>(`/api/v1/documents?page=${page}&page_size=100`);
    documents.push(...result.documents);
    total = result.total;
    page += 1;
  } while (documents.length < total && page <= Math.ceil(total / 100) + 1);
  return { documents, total };
}

export async function downloadApiFile(path: string, filename: string) {
  const makeRequest = () => {
    const headers = new Headers({ Accept: "text/csv,application/octet-stream" });
    const token = sessionStorage.getItem("access_token");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetchApi(`${API_BASE}${path}`, { headers });
  };
  let response = await makeRequest();
  if (response.status === 401) {
    await api("/api/v1/auth/me");
    response = await makeRequest();
  }
  if (!response.ok) throw new Error(await readError(response, path));
  const href = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 30_000);
}