// Shared type definitions for UI audit report.
//
// Note: keep this module dependency-free so it can be imported from both Node
// scripts and Playwright tests without side effects.

export type AuditStatus = "ok" | "error" | "skipped";

export type ElementRef = {
  tag: string;
  id: string | null;
  className: string | null;
  text: string | null;
};

export type OverflowOffender = {
  tag: string;
  id: string | null;
  className: string | null;
  text: string | null;
  overflowRightPx: number;
  overflowLeftPx: number;
};

export type ClipOffender = {
  el: ElementRef;
  clipBy: ElementRef;
  clipLeftPx: number;
  clipRightPx: number;
  clipTopPx: number;
  clipBottomPx: number;
};

export type OccludedOffender = {
  el: ElementRef;
  at: { x: number; y: number };
  top: ElementRef;
};

export type OverlapOffender = {
  a: ElementRef;
  b: ElementRef;
  intersectionAreaPx: number;
};

export type MisalignedButtonRowOffender = {
  container: ElementRef;
  buttonCount: number;
  deltaTopPx: number;
  deltaHeightPx: number;
  sampleTexts: string[];
};

export type TextTruncationOffender = {
  el: ElementRef;
  clientWidth: number;
  scrollWidth: number;
};

export type LayoutMetrics = {
  viewportWidth: number;
  viewportHeight: number;
  clientWidth: number;
  scrollWidth: number;
  clientHeight: number;
  scrollHeight: number;
  horizontalOverflowPx: number;
  offenders: OverflowOffender[];
  clipped: ClipOffender[];
  occluded: OccludedOffender[];
  overlaps: OverlapOffender[];
  misalignedButtonRows: MisalignedButtonRowOffender[];
  textTruncations: TextTruncationOffender[];
};

export type AuditScreenshots = {
  viewport: string;
  fullPage: string;
};

export type AuditRecord = {
  ts: string;
  project: string;
  routePattern: string;
  routeResolved: string | null;
  url: string | null;
  finalUrl: string | null;
  status: AuditStatus;
  reason?: string;
  durationMs?: number;
  metrics?: LayoutMetrics;
  screenshots?: AuditScreenshots;
  error?: string;
};

