import fs from "node:fs";
import path from "node:path";

export type RouteDef = {
  pattern: string;
  filePath: string;
  dynamicSegments: string[];
};

function isRouteGroup(seg: string): boolean {
  return seg.startsWith("(") && seg.endsWith(")");
}

function listPageFiles(dir: string): string[] {
  const out: string[] = [];
  const stack: string[] = [dir];
  while (stack.length > 0) {
    const cur = stack.pop()!;
    const entries = fs.readdirSync(cur, { withFileTypes: true });
    for (const ent of entries) {
      const full = path.join(cur, ent.name);
      if (ent.isDirectory()) {
        if (ent.name.startsWith(".")) continue;
        stack.push(full);
        continue;
      }
      if (!ent.isFile()) continue;
      if (ent.name === "page.tsx" || ent.name === "page.ts" || ent.name === "page.jsx" || ent.name === "page.js") {
        out.push(full);
      }
    }
  }
  out.sort((a, b) => a.localeCompare(b));
  return out;
}

function toRoutePattern(appDir: string, pageFile: string): { pattern: string; dynamic: string[] } {
  const rel = path.relative(appDir, pageFile).replace(/\\/g, "/");
  const dir = rel.replace(/(^|\/)page\.(t|j)sx?$/, "");
  const segsRaw = dir ? dir.split("/").filter(Boolean) : [];
  const segs = segsRaw.filter((s) => !isRouteGroup(s));

  const dynamic: string[] = [];
  for (const seg of segs) {
    const m = seg.match(/^\[(.+)\]$/);
    if (m) dynamic.push(m[1]);
  }

  if (segs.length === 0) return { pattern: "/", dynamic };
  return { pattern: "/" + segs.join("/"), dynamic };
}

export function discoverRoutes(opts?: { appDir?: string }): RouteDef[] {
  const appDir = opts?.appDir?.trim()
    ? path.resolve(opts.appDir.trim())
    : path.resolve(__dirname, "..", "src", "app");
  const pageFiles = listPageFiles(appDir);
  const map = new Map<string, RouteDef>();
  for (const pageFile of pageFiles) {
    const { pattern, dynamic } = toRoutePattern(appDir, pageFile);
    if (!map.has(pattern)) {
      map.set(pattern, { pattern, filePath: pageFile, dynamicSegments: dynamic });
    }
  }
  return Array.from(map.values()).sort((a, b) => a.pattern.localeCompare(b.pattern));
}

export function hasDynamicSegments(pattern: string): boolean {
  return /\[[^\]]+\]/.test(pattern);
}

export function slugFromRoute(route: string): string {
  if (route === "/") return "root";
  return route
    .replace(/^\//, "")
    .replaceAll("/", "__")
    .replaceAll("[", "")
    .replaceAll("]", "");
}
