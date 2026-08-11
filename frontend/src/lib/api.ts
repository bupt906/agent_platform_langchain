// 开发环境通过 Vite proxy 转发，生产环境需设置为实际后端地址
import { getPreferences } from "./preferences";

const BUILD_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function apiUrl(path: string, baseUrl?: string) {
  const resolvedBase = baseUrl === undefined ? getPreferences().apiBaseUrl || BUILD_BASE : baseUrl || BUILD_BASE;
  return `${resolvedBase}${path}`;
}

export interface SkillInfo {
  name: string;
  description: string;
  examples: string[];
  dependencies: string[];
  kind?: string;
  tools?: string[];
  ready?: boolean;
  missing_tools?: string[];
  unavailable_reason?: string;
  runtime_profile?: string;
  runtime_backend?: string;
  runtime_reason?: string;
}

export interface AuditStats {
  total_calls: number;
  total_tokens: number;
  total_duration_ms: number;
  avg_duration_ms: number;
  by_skill: Record<string, number>;
  errors: number;
}

export interface AuditRecord {
  id: string;
  session_id: string;
  agent_type: string;
  user_message: string;
  assistant_message: string;
  tokens_total: number;
  duration_ms: number;
  skill_used: string;
  timestamp: string;
  error?: string;
}

export interface ReviewTask {
  task_id: number;
  status: string;
  results?: ReviewResult[];
  total?: number;
}

export interface ReviewResult {
  task_id: number;
  sentence_index: number;
  reviewed_sentence: string;
  has_issue: string;
  content: Record<string, unknown>;
}

export interface RemotePreferences {
  profile_id: string;
  theme: "light" | "dark" | "system";
  default_model: string;
  api_base_url: string;
  updated_at: string | null;
}

// 所有 fetch 请求默认超时 30 秒
async function get<T>(url: string): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  try {
    const r = await fetch(apiUrl(url), { signal: controller.signal });
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function put<T>(url: string, body: unknown, baseUrl?: string): Promise<T> {
  const r = await fetch(apiUrl(url, baseUrl), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}

export const api = {
  getSkills: () => get<{ skills: SkillInfo[]; total: number }>("/skills"),
  getAuditStats: (days = 30) => get<AuditStats>(`/audit/stats?days=${days}`),
  getAuditRecords: (params?: Record<string, string>) => {
    const q = new URLSearchParams(params).toString();
    return get<{ records: AuditRecord[]; total: number }>(`/audit?${q}`);
  },
  getReviewResults: (taskId: number) =>
    get<{ data: { task_id: number; results: ReviewResult[]; total: number } }>(`/api/callback/batch/${taskId}`),
  getTaskStatus: (taskId: number) =>
    get<{ data: { taskId: number; status: string } }>(`/api/callback/task/status/${taskId}`),
  getPreferences: (profileId: string) => get<RemotePreferences>(`/preferences/${encodeURIComponent(profileId)}`),
  updatePreferences: (profileId: string, preferences: { theme: string; default_model: string; api_base_url: string }, currentBaseUrl?: string) =>
    put<RemotePreferences>(`/preferences/${encodeURIComponent(profileId)}`, preferences, currentBaseUrl),
};
