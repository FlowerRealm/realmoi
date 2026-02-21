import type { Page } from "@playwright/test";

import type {
  ClipOffender,
  ElementRef,
  LayoutMetrics,
  MisalignedButtonRowOffender,
  OccludedOffender,
  OverlapOffender,
  OverflowOffender,
  TextTruncationOffender,
} from "./report";

/**
 * Collect rough layout diagnostics in the browser context.
 *
 * Goals:
 * - be deterministic and cheap (hard caps on scans)
 * - focus on "high-signal" offenders users feel immediately (overflow, clipping, occlusion, overlap)
 * - keep payload small (top-N offenders only)
 *
 * Notes:
 * - This is a heuristic, not a full accessibility/layout engine.
 * - It intentionally trades completeness for speed.
 */
export async function collectLayoutMetrics(page: Page): Promise<LayoutMetrics> {
  return await page.evaluate(() => {
    const root = document.documentElement;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    const clientWidth = root.clientWidth;
    const scrollWidth = root.scrollWidth;
    const clientHeight = root.clientHeight;
    const scrollHeight = root.scrollHeight;

    // Page-level overflow is a common regression; we keep a cheap global signal plus top offenders.
    const horizontalOverflowPx = Math.max(0, Math.round(scrollWidth - clientWidth));

    // Compact element ref suitable for JSON reports (no DOM nodes).
    const elRef = (el: Element | null): ElementRef => {
      const htmlEl = el as HTMLElement | null;
      const rawText = (el?.textContent || "").replace(/\s+/g, " ").trim();
      const text = rawText ? (rawText.length > 60 ? rawText.slice(0, 60) + "…" : rawText) : null;
      const className = (htmlEl?.className || "").toString().trim() || null;
      const id = htmlEl?.id || null;
      return { tag: (el?.tagName || "unknown").toLowerCase(), id, className, text };
    };

    const offenders: OverflowOffender[] = [];
    if (horizontalOverflowPx > 0 && document.body) {
      const vw = clientWidth || viewportWidth;
      const nodes = Array.from(document.body.querySelectorAll("*"));
      // Cap scanning to avoid pathological pages locking up the audit.
      const maxScan = 2500;
      const cap = Math.min(nodes.length, maxScan);
      const tmp: Array<OverflowOffender & { score: number }> = [];

      for (let i = 0; i < cap; i++) {
        const el = nodes[i];
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) continue;
        const overflowRightPx = Math.max(0, rect.right - vw);
        const overflowLeftPx = Math.max(0, -rect.left);
        const score = Math.max(overflowRightPx, overflowLeftPx);
        if (score <= 1) continue;

        const ref = elRef(el);
        tmp.push({
          tag: ref.tag,
          id: ref.id,
          className: ref.className,
          text: ref.text,
          overflowRightPx: Math.round(overflowRightPx),
          overflowLeftPx: Math.round(overflowLeftPx),
          score,
        });

        if (tmp.length >= 80) break;
      }

      tmp.sort((a, b) => b.score - a.score);
      for (const item of tmp.slice(0, 8)) {
        offenders.push({
          tag: item.tag,
          id: item.id,
          className: item.className,
          text: item.text,
          overflowRightPx: item.overflowRightPx,
          overflowLeftPx: item.overflowLeftPx,
        });
      }
    }

    const isVisible = (el: Element): el is HTMLElement => {
      const h = el as HTMLElement;
      const rect = h.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return false;
      if (rect.right <= 0 || rect.bottom <= 0 || rect.left >= viewportWidth || rect.top >= viewportHeight) {
        return false;
      }
      const style = getComputedStyle(h);
      if (style.display === "none" || style.visibility === "hidden") return false;
      if (Number(style.opacity || 1) < 0.05) return false;
      if (!h.offsetParent && style.position !== "fixed" && style.position !== "sticky") return false;
      const closedDetails = h.closest("details:not([open])");
      if (closedDetails && !h.closest("summary")) return false;
      return true;
    };

    const overflowClips = (style: CSSStyleDeclaration, axis: "x" | "y"): boolean => {
      const v = axis === "x" ? style.overflowX : style.overflowY;
      return v === "hidden" || v === "clip";
    };

    const clipped: ClipOffender[] = [];
    const occluded: OccludedOffender[] = [];
    const overlaps: OverlapOffender[] = [];
    const misalignedButtonRows: MisalignedButtonRowOffender[] = [];
    const textTruncations: TextTruncationOffender[] = [];

    // 1) Candidates: focus on interactive + Semi components; cap for perf.
    const candidates: Element[] = [];
    const seen = new Set<Element>();
    const selectors = [
      "button",
      "a[href]",
      "input",
      "select",
      "textarea",
      "[role='button']",
      "[role='link']",
      ".semi-button",
      ".semi-input-wrapper",
      ".semi-select",
      ".semi-card",
      ".semi-table",
    ];
    for (const sel of selectors) {
      for (const el of Array.from(document.querySelectorAll(sel))) {
        if ((el as HTMLElement).closest?.("[data-app-header]")) continue;
        if (seen.has(el)) continue;
        seen.add(el);
        candidates.push(el);
        if (candidates.length >= 800) break;
      }
      if (candidates.length >= 800) break;
    }

    const visible = candidates.filter(isVisible).slice(0, 220);

    // 2) overflow:hidden/clip ancestor clipping (top offenders).
    for (const el of visible) {
      const rect = el.getBoundingClientRect();
      let p: HTMLElement | null = el.parentElement;
      let depth = 0;
      // Walk a few ancestors only; deep trees can be expensive.
      while (p && depth < 8) {
        const ps = getComputedStyle(p);
        if (overflowClips(ps, "x") || overflowClips(ps, "y")) {
          const pr = p.getBoundingClientRect();
          const clipLeftPx = Math.max(0, Math.round(pr.left - rect.left));
          const clipRightPx = Math.max(0, Math.round(rect.right - pr.right));
          const clipTopPx = Math.max(0, Math.round(pr.top - rect.top));
          const clipBottomPx = Math.max(0, Math.round(rect.bottom - pr.bottom));
          const score = Math.max(clipLeftPx, clipRightPx, clipTopPx, clipBottomPx);
          if (score >= 6) {
            clipped.push({
              el: elRef(el),
              clipBy: elRef(p),
              clipLeftPx,
              clipRightPx,
              clipTopPx,
              clipBottomPx,
            });
            break;
          }
        }
        p = p.parentElement;
        depth++;
      }
      if (clipped.length >= 10) break;
    }

    // 3) Occluded interactive targets (center point not hit).
    for (const el of visible) {
      // Only audit elements that are intended to be clicked or typed into.
      if (
        !(
          el.matches("button") ||
          el.matches("a[href]") ||
          el.matches("input") ||
          el.matches("select") ||
          el.matches("textarea") ||
          el.getAttribute("role") === "button" ||
          el.getAttribute("role") === "link"
        )
      ) {
        continue;
      }
      const h = el as HTMLElement;
      const disabledAttr = h.getAttribute("aria-disabled");
      const style = getComputedStyle(h);
      const isDisabled =
        disabledAttr === "true" ||
        style.pointerEvents === "none" ||
        ("disabled" in h && Boolean((h as unknown as { disabled?: boolean }).disabled));
      if (isDisabled) continue;
      const rect = el.getBoundingClientRect();
      const cx = Math.round(rect.left + rect.width / 2);
      const cy = Math.round(rect.top + rect.height / 2);
      if (cx < 0 || cy < 0 || cx > viewportWidth || cy > viewportHeight) continue;
      const top = document.elementFromPoint(cx, cy);
      if (!top) continue;
      if (top === el || (el as HTMLElement).contains(top)) continue;
      occluded.push({ el: elRef(el), at: { x: cx, y: cy }, top: elRef(top) });
      if (occluded.length >= 10) break;
    }

    // 4) Overlapping interactive targets (strong signal of broken layout).
    const clickTargets = visible.filter((el) =>
      el.matches("button, a[href], input, select, textarea, [role='button'], [role='link']")
    );
    // Keep overlap checks bounded; this is O(n^2).
    const inViewport = clickTargets
      .filter((el) => {
        const r = el.getBoundingClientRect();
        return r.right > 0 && r.bottom > 0 && r.left < viewportWidth && r.top < viewportHeight;
      })
      .slice(0, 36);

    const rects = inViewport.map((el) => ({ el, r: el.getBoundingClientRect() }));
    const tmpOverlaps: Array<OverlapOffender & { score: number }> = [];
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const ix = Math.max(0, Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left));
        const iy = Math.max(0, Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top));
        const area = Math.round(ix * iy);
        if (area < 700) continue;
        tmpOverlaps.push({ a: elRef(a.el), b: elRef(b.el), intersectionAreaPx: area, score: area });
        if (tmpOverlaps.length >= 60) break;
      }
      if (tmpOverlaps.length >= 60) break;
    }
    tmpOverlaps.sort((a, b) => b.score - a.score);
    for (const o of tmpOverlaps.slice(0, 10)) {
      overlaps.push({ a: o.a, b: o.b, intersectionAreaPx: o.intersectionAreaPx });
    }

    // 5) Misaligned buttons within the same flex-row parent.
    const buttons = visible.filter((el) => el.matches("button, .semi-button, [role='button']"));
    const byParent = new Map<HTMLElement, HTMLElement[]>();
    for (const el of buttons) {
      const parent = el.parentElement;
      if (!parent) continue;
      const arr = byParent.get(parent);
      if (arr) arr.push(el);
      else byParent.set(parent, [el]);
    }
    for (const [parent, items] of byParent) {
      if (items.length < 2) continue;
      const ps = getComputedStyle(parent);
      if (ps.display !== "flex" || ps.flexDirection !== "row") continue;
      const rects2 = items.map((b) => ({ el: b, r: b.getBoundingClientRect() }));
      const tops = rects2.map((x) => x.r.top);
      const heights = rects2.map((x) => x.r.height);
      const deltaTopPx = Math.round(Math.max(...tops) - Math.min(...tops));
      const deltaHeightPx = Math.round(Math.max(...heights) - Math.min(...heights));
      if (deltaTopPx <= 3 && deltaHeightPx <= 6) continue;
      misalignedButtonRows.push({
        container: elRef(parent),
        buttonCount: items.length,
        deltaTopPx,
        deltaHeightPx,
        sampleTexts: rects2
          .slice(0, 4)
          .map((x) => (x.el.textContent || "").replace(/\s+/g, " ").trim())
          .filter(Boolean),
      });
      if (misalignedButtonRows.length >= 10) break;
    }

    // 6) Text truncation signals (scrollWidth > clientWidth under overflow hidden).
    for (const el of visible) {
      const h = el as HTMLElement;
      const style = getComputedStyle(h);
      if (!(style.overflowX === "hidden" || style.overflowX === "clip" || style.textOverflow === "ellipsis")) {
        continue;
      }
      const cw = Math.round(h.clientWidth || 0);
      const sw = Math.round(h.scrollWidth || 0);
      if (cw < 24 || sw <= cw + 8) continue;
      textTruncations.push({ el: elRef(el), clientWidth: cw, scrollWidth: sw });
      if (textTruncations.length >= 10) break;
    }

    return {
      viewportWidth,
      viewportHeight,
      clientWidth,
      scrollWidth,
      clientHeight,
      scrollHeight,
      horizontalOverflowPx,
      offenders,
      clipped,
      occluded,
      overlaps,
      misalignedButtonRows,
      textTruncations,
    };
  });
}
