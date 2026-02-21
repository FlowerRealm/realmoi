// Public exports for Playwright UI audit reporting utilities.
//
// Keeping this file as a small barrel makes it easy for specs/scripts to import
// from `./report` while allowing the implementation to stay modular.

export type {
  AuditRecord,
  AuditScreenshots,
  AuditStatus,
  ClipOffender,
  ElementRef,
  LayoutMetrics,
  MisalignedButtonRowOffender,
  OccludedOffender,
  OverlapOffender,
  OverflowOffender,
  TextTruncationOffender,
} from "./reportTypes";

export { appendRecord, getOutDir, getReportJsonlPath, readJsonl } from "./reportJsonl";
export { renderMarkdown } from "./reportRender";

