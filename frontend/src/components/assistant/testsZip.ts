import JSZip from "jszip";
import type { TestCase } from "./types";

function ensureCrLfNormalized(s: string): string {
  // Keep user content, but normalize Windows newlines for consistency with typical test files.
  return s.replace(/\r\n/g, "\n");
}

function caseBaseName(i: number): string {
  // 01, 02, ... ensures stable lexicographic order.
  return String(i + 1).padStart(2, "0");
}

export async function buildTestsZip(testCases: TestCase[]): Promise<File | null> {
  const cases = testCases.filter((tc) => tc.input.trim() || tc.output.trim());
  if (cases.length === 0) return null;

  const zip = new JSZip();
  for (let i = 0; i < cases.length; i++) {
    const base = caseBaseName(i);
    zip.file(`${base}.in`, ensureCrLfNormalized(cases[i].input ?? ""));

    const out = ensureCrLfNormalized(cases[i].output ?? "");
    // If expected output is empty, treat as "no expected" and omit .out.
    if (out.trim().length > 0) zip.file(`${base}.out`, out);
  }

  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], "tests.zip", { type: "application/zip" });
}

