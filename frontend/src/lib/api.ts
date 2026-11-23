/**
 * Typed API client (Phase 2).
 *
 * Every call goes through `apiFetch`, which:
 *  - talks to RELATIVE /api paths (the Vite dev proxy forwards them to the API, so
 *    the browser sees one origin and cookies just work — blueprint 19.2 shape);
 *  - sends cookies (`credentials: "include"`) and echoes the CSRF token cookie in
 *    the `X-CSRF-Token` header on every state-changing request;
 *  - parses the one error envelope (blueprint 14.2) into `ApiError{code, message,
 *    requestId, status}` so screens can branch on stable codes;
 *  - validates response shapes at runtime: TypeScript types vanish at build time,
 *    so a type alone cannot protect the UI from an unexpected payload.
 *
 * No credentials, tokens or secrets are stored anywhere but the cookies the server
 * sets (HttpOnly session + readable CSRF). There is nothing in localStorage.
 */

export type ProbeStatus = "ok" | "failed" | "not_configured";

export interface LiveResponse {
  status: "alive";
  service: string;
  version: string;
  environment: string;
}

export interface CheckResponse {
  status: ProbeStatus;
  required: boolean;
  latency_ms: number | null;
}

export interface ReadyResponse {
  status: "ready" | "not_ready";
  checks: Record<string, CheckResponse>;
}

// --- Phase 2 domain types (mirror backend api/v1/schemas) ---
export interface UserDto {
  id: string;
  email: string;
  created_at: string;
}

export interface OrganizationBrief {
  id: string;
  slug: string;
  display_name: string;
  is_demo: boolean;
}

export interface MembershipBrief {
  organization_id: string;
  slug: string;
  display_name: string;
  role: string;
}

export interface MeResponse {
  user: UserDto;
  active_organization: OrganizationBrief | null;
  memberships: MembershipBrief[];
}

export interface Organization {
  id: string;
  slug: string;
  display_name: string;
  default_market: string | null;
  timezone: string;
  base_currency: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface Workspace {
  id: string;
  organization_id: string;
  name: string;
  is_read_only: boolean;
  created_at: string;
  updated_at: string;
}

export interface Member {
  membership_id: string;
  user_id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
}

export interface WorkspaceCreated {
  id: string;
  organization_id: string;
  name: string;
  is_read_only: boolean;
}

/** The stable error envelope every failure uses (blueprint 14.2). */
export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string;
  readonly status: number;

  constructor(code: string, message: string, status: number, requestId: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

const CSRF_COOKIE = "mp_csrf";
const CSRF_HEADER = "X-CSRF-Token";

function csrfToken(): string | null {
  const entry = document.cookie
    .split("; ")
    .find((pair) => pair.startsWith(`${CSRF_COOKIE}=`));
  return entry === undefined ? null : decodeURIComponent(entry.slice(CSRF_COOKIE.length + 1));
}

interface ApiInit {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal | undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseEnvelope(body: unknown): ApiError {
  if (isRecord(body) && isRecord(body["error"])) {
    const error = body["error"];
    return new ApiError(
      typeof error["code"] === "string" ? error["code"] : "UNKNOWN",
      typeof error["message"] === "string" ? error["message"] : "Request failed",
      0, // status is set by the caller
      typeof error["request_id"] === "string" ? error["request_id"] : "-",
    );
  }
  return new ApiError("UNKNOWN", "Request failed", 0, "-");
}

export async function apiFetch<T>(path: string, init: ApiInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers: Record<string, string> = {};
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const token = csrfToken();
    if (token !== null) headers[CSRF_HEADER] = token;
  }
  const requestInit: RequestInit = { method, headers, credentials: "include" };
  if (init.signal !== undefined) requestInit.signal = init.signal;
  if (init.body !== undefined) requestInit.body = JSON.stringify(init.body);
  let response: Response;
  try {
    response = await fetch(path, requestInit);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("NETWORK", "Could not reach the API. Is the backend running?", 0, "-");
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const apiError = parseEnvelope(payload);
    throw new ApiError(apiError.code, apiError.message, response.status, apiError.requestId);
  }
  return payload as T;
}

// --- Health (Phase 0 contract, unchanged) ---
export async function fetchLive(signal?: AbortSignal): Promise<LiveResponse> {
  const data = await apiFetch<unknown>("/api/v1/health/live", { signal });
  if (!isRecord(data) || data["status"] !== "alive") throw new Error("Unexpected /health/live response");
  return data as unknown as LiveResponse;
}

export async function fetchReady(signal?: AbortSignal): Promise<ReadyResponse> {
  const data = await apiFetch<unknown>("/api/v1/health/ready", { signal });
  if (!isRecord(data) || !isRecord(data["checks"])) throw new Error("Unexpected /health/ready response");
  if (data["status"] !== "ready" && data["status"] !== "not_ready") {
    throw new Error("Unexpected /health/ready status");
  }
  return data as unknown as ReadyResponse;
}

// --- Authentication (Phase 2) ---
export interface RegisterInput {
  email: string;
  password: string;
  organization_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export const authApi = {
  async register(input: RegisterInput): Promise<{ user: UserDto; organization: OrganizationBrief }> {
    return apiFetch("/api/v1/auth/register", { method: "POST", body: input });
  },
  async login(input: LoginInput): Promise<{ user: UserDto; organization_id: string | null }> {
    return apiFetch("/api/v1/auth/login", { method: "POST", body: input });
  },
  async logout(): Promise<null> {
    return apiFetch<null>("/api/v1/auth/logout", { method: "POST" });
  },
  async me(signal?: AbortSignal): Promise<MeResponse> {
    return apiFetch<MeResponse>("/api/v1/auth/me", { signal });
  },
  async switchOrganization(organizationId: string): Promise<{ organization: OrganizationBrief }> {
    return apiFetch("/api/v1/auth/switch-organization", {
      method: "POST",
      body: { organization_id: organizationId },
    });
  },
};

// --- Tenant reads (Phase 1 endpoints, now session-authenticated) ---
export const tenantApi = {
  async currentOrganization(signal?: AbortSignal): Promise<Organization> {
    return apiFetch<Organization>("/api/v1/organizations/current", { signal });
  },
  async workspaces(signal?: AbortSignal): Promise<Workspace[]> {
    const data = await apiFetch<unknown[]>("/api/v1/workspaces", { signal });
    return data as Workspace[];
  },
  async createWorkspace(name: string): Promise<WorkspaceCreated> {
    return apiFetch("/api/v1/workspaces", { method: "POST", body: { name } });
  },
  async members(signal?: AbortSignal): Promise<Member[]> {
    const data = await apiFetch<unknown[]>("/api/v1/organizations/members", { signal });
    return data as Member[];
  },
};

/** True when the error means "no valid session" (used by the protected route). */
export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "UNAUTHORIZED" || error.status === 401);
}

export function isValidationError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}
