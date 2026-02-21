export function normalizeTerminalChunk(chunkText: string): string {
  const withoutAnsi = chunkText.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "");
  const withoutCtrl = withoutAnsi.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
  return withoutCtrl.replace(/\r/g, "");
}

