"use client";

import { getToken, clearToken } from "./auth";

const DEFAULT_API_BASE = "http://0.0.0.0:8000/api";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

function isLoopbackHost(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1" ||
    hostname === "[::1]" ||
    hostname.endsWith(".localhost")
  );
}

function shouldUseConfiguredBase(configuredBase: string): boolean {
  if (typeof window === "undefined") return true;
  try {
    const configuredHost = new URL(configuredBase, window.location.origin).hostname;
    const currentHost = window.location.hostname;
    if (isLoopbackHost(configuredHost) && !isLoopbackHost(currentHost)) {
      return false;
    }
  } catch {
    return true;
  }
  return true;
}

function resolveRuntimeApiBase(): string {
  if (typeof window === "undefined") {
    return DEFAULT_API_BASE;
  }
  const target = new URL(window.location.origin);
  target.port = process.env.NEXT_PUBLIC_API_PORT?.trim() || "8000";
  target.pathname = "/api";
  target.search = "";
  target.hash = "";
  return trimTrailingSlash(target.toString());
}

export const API_BASE = (() => {
  const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configuredBase) {
    if (shouldUseConfiguredBase(configuredBase)) {
      return trimTrailingSlash(configuredBase);
    }
    return resolveRuntimeApiBase();
  }
  return trimTrailingSlash(DEFAULT_API_BASE);
})();

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(message: string, code: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function readErrorCode(payload: unknown): string {
  if (!payload || typeof payload !== "object") return "http_error";
  const maybeError = (payload as { error?: unknown }).error;
  if (!maybeError || typeof maybeError !== "object") return "http_error";
  const code = (maybeError as { code?: unknown }).code;
  return typeof code === "string" ? code : "http_error";
}

function readErrorMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const maybeError = (payload as { error?: unknown }).error;
  if (!maybeError || typeof maybeError !== "object") return null;
  const message = (maybeError as { message?: unknown }).message;
  return typeof message === "string" ? message : null;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return String(error);
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
  const token = getToken();
  const hasAuthToken = Boolean(token);
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(url, { ...init, headers });
  const text = await resp.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!resp.ok) {
    const code = readErrorCode(data);
    const msg = readErrorMessage(data) ?? resp.statusText;
    if (resp.status === 401 && hasAuthToken && code === "unauthorized") {
      clearToken();
    }
    throw new ApiError(msg, code, resp.status);
  }
  return data as T;
}
