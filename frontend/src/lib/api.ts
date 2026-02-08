"use client";

import { getToken, clearToken } from "./auth";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000/api";

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
