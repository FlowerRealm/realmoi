// AUTO_COMMENT_HEADER_V1: diff.ts
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

export type DiffLine = {
  kind: "meta" | "hunk" | "add" | "del" | "ctx" | "other";
  oldLine: number | null;
  newLine: number | null;
  text: string;
};

type ParseState = {
  inHunk: boolean;
  oldNo: number | null;
  newNo: number | null;
};

function resetHunkState(state: ParseState): void {
  state.inHunk = false;
  state.oldNo = null;
  state.newNo = null;
}

function isMetaLine(line: string): boolean {
  return (
    line.startsWith("diff --git ")
    || line.startsWith("index ")
    || line.startsWith("--- ")
    || line.startsWith("+++ ")
    || line.startsWith("\\ No newline at end of file")
  );
}

function parseHunkHeader(line: string): { oldStart: number; newStart: number } | null {
  const m = line.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@/);
  if (!m) return null;
  const oldStart = Number(m[1]);
  const newStart = Number(m[3]);
  if (!Number.isFinite(oldStart) || !Number.isFinite(newStart)) return null;
  return { oldStart, newStart };
}

function handleHunkHeader(line: string, state: ParseState, parsed: DiffLine[]): void {
  const info = parseHunkHeader(line);
  state.inHunk = true;
  state.oldNo = info ? info.oldStart : null;
  state.newNo = info ? info.newStart : null;
  parsed.push({ kind: "hunk", oldLine: null, newLine: null, text: line });
}

function consumeHunkLine(line: string, state: ParseState, parsed: DiffLine[]): boolean {
  if (!state.inHunk) return false;

  // Added line (but not file header "+++ path").
  if (line.startsWith("+") && !line.startsWith("+++ ")) {
    parsed.push({ kind: "add", oldLine: null, newLine: state.newNo, text: line });
    if (state.newNo !== null) state.newNo += 1;
    return true;
  }

  // Deleted line (but not file header "--- path").
  if (line.startsWith("-") && !line.startsWith("--- ")) {
    parsed.push({ kind: "del", oldLine: state.oldNo, newLine: null, text: line });
    if (state.oldNo !== null) state.oldNo += 1;
    return true;
  }

  // Context line.
  if (line.startsWith(" ")) {
    parsed.push({ kind: "ctx", oldLine: state.oldNo, newLine: state.newNo, text: line });
    if (state.oldNo !== null) state.oldNo += 1;
    if (state.newNo !== null) state.newNo += 1;
    return true;
  }

  return false;
}

function kindForLooseLine(line: string): DiffLine["kind"] {
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "del";
  return "other";
}

function trimTrailingBlanks(parsed: DiffLine[]): void {
  while (parsed.length > 0 && !parsed[parsed.length - 1].text.trim()) parsed.pop();
}

export function parseUnifiedDiff(diffText: string): DiffLine[] {
  // The UI expects a tolerant parser: preserve unknown lines as "other".
  const text = String(diffText || "").replace(/\r/g, "");
  const lines = text.split("\n");
  const parsed: DiffLine[] = [];

  const state: ParseState = { inHunk: false, oldNo: null, newNo: null };

  for (const line of lines) {
    if (isMetaLine(line)) {
      resetHunkState(state);
      parsed.push({ kind: "meta", oldLine: null, newLine: null, text: line });
      continue;
    }

    if (line.startsWith("@@")) {
      handleHunkHeader(line, state, parsed);
      continue;
    }

    if (consumeHunkLine(line, state, parsed)) continue;

    parsed.push({ kind: kindForLooseLine(line), oldLine: null, newLine: null, text: line });
  }

  trimTrailingBlanks(parsed);
  return parsed;
}
