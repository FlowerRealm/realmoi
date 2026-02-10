"use client";

import { API_BASE } from "./api";
import { getToken } from "./auth";

export type JsonRpcError = { code: number; message: string };

export type McpToolCallResult<TStructured = unknown> = {
  content?: unknown;
  structuredContent?: TStructured;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
};

type NotificationHandler = (method: string, params: unknown) => void;

function buildMcpWsUrl(): string {
  const httpUrl = new URL(API_BASE);
  httpUrl.pathname = `${httpUrl.pathname.replace(/\/$/, "")}/mcp/ws`;
  httpUrl.search = "";
  httpUrl.hash = "";

  if (httpUrl.protocol === "https:") httpUrl.protocol = "wss:";
  else httpUrl.protocol = "ws:";

  const token = getToken();
  if (token) httpUrl.searchParams.set("token", token);
  return httpUrl.toString();
}

export class McpWsClient {
  private ws: WebSocket | null = null;
  private nextId = 0;
  private pending = new Map<number, PendingRequest>();
  private notificationHandlers = new Set<NotificationHandler>();
  private connectPromise: Promise<void> | null = null;
  private disconnectWaiters = new Set<() => void>();

  onNotification(handler: NotificationHandler): () => void {
    this.notificationHandlers.add(handler);
    return () => {
      this.notificationHandlers.delete(handler);
    };
  }

  waitForDisconnect(): Promise<void> {
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING) {
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const fn = () => resolve();
      this.disconnectWaiters.add(fn);
    });
  }

  private notifyDisconnected(): void {
    for (const fn of Array.from(this.disconnectWaiters)) fn();
    this.disconnectWaiters.clear();
  }

  private rejectAllPending(reason: unknown): void {
    for (const [id, pending] of Array.from(this.pending.entries())) {
      this.pending.delete(id);
      pending.reject(reason);
    }
  }

  private attachWs(ws: WebSocket, onClose?: () => void): void {
    ws.onmessage = (ev) => {
      let msg: unknown;
      try {
        msg = JSON.parse(String(ev.data));
      } catch {
        return;
      }

      if (isRecord(msg) && typeof msg.id === "number") {
        const pending = this.pending.get(msg.id);
        if (!pending) return;
        this.pending.delete(msg.id);
        if ("error" in msg && msg.error) pending.reject(msg.error);
        else pending.resolve(msg.result);
        return;
      }

      if (isRecord(msg) && typeof msg.method === "string") {
        const params = msg.params;
        for (const handler of Array.from(this.notificationHandlers)) {
          try {
            handler(msg.method, params);
          } catch {
            // ignore
          }
        }
      }
    };

    ws.onclose = () => {
      this.rejectAllPending({ code: "ws_closed" });
      this.notifyDisconnected();
      onClose?.();
    };

    ws.onerror = () => {
      // Errors are surfaced via onclose or pending rejections.
    };
  }

  private requestRaw(method: string, params: unknown): Promise<unknown> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return Promise.reject(new Error("mcp_ws_not_open"));

    this.nextId += 1;
    const id = this.nextId;
    const req = { jsonrpc: "2.0", id, method, params };
    const body = JSON.stringify(req);
    const ws = this.ws;

    const p = new Promise<unknown>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try {
        ws.send(body);
      } catch (e) {
        this.pending.delete(id);
        reject(e);
      }
    });
    return p;
  }

  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    if (this.connectPromise) return this.connectPromise;

    this.connectPromise = new Promise<void>((resolve, reject) => {
      const url = buildMcpWsUrl();
      const ws = new WebSocket(url);
      this.ws = ws;
      let settled = false;
      this.attachWs(ws, () => {
        if (settled) return;
        settled = true;
        this.connectPromise = null;
        reject({ code: "ws_closed" });
      });

      ws.onopen = async () => {
        try {
          await this.requestRaw("initialize", {});
          settled = true;
          resolve();
        } catch (e) {
          try {
            ws.close();
          } catch {}
          if (!settled) {
            settled = true;
            reject(e);
          }
        } finally {
          this.connectPromise = null;
        }
      };
    });

    return this.connectPromise;
  }

  async request(method: string, params: unknown): Promise<unknown> {
    await this.connect();
    return this.requestRaw(method, params);
  }

  async callTool<TStructured = unknown>(name: string, args: Record<string, unknown>): Promise<TStructured> {
    const result = (await this.request("tools/call", { name, arguments: args })) as McpToolCallResult<TStructured>;
    if (result && typeof result === "object" && "structuredContent" in result) {
      return (result as McpToolCallResult<TStructured>).structuredContent as TStructured;
    }
    return result as unknown as TStructured;
  }
}

let _CLIENT: McpWsClient | null = null;

export function getMcpClient(): McpWsClient {
  if (_CLIENT) return _CLIENT;
  _CLIENT = new McpWsClient();
  return _CLIENT;
}
