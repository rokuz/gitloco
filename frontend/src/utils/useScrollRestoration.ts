import { useEffect, type RefObject } from "react";

/**
 * Persist and restore the scroll position of a scroll container, keyed by
 * `key` (e.g. the selected commit), across navigation and browser refresh.
 *
 * Diff content loads asynchronously, so the container often isn't tall enough
 * to reach the saved offset on first paint — restoration retries (via a
 * ResizeObserver) as content grows, then stops once the offset is reachable.
 * A new key with no saved position scrolls to the top.
 */
export function useScrollRestoration(
  ref: RefObject<HTMLElement | null>,
  key: string | null,
): void {
  // Save on scroll (rAF-throttled), keyed by the current selection.
  useEffect(() => {
    const el = ref.current;
    if (!el || !key) return;
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        sessionStorage.setItem(`gitloco:scroll:${key}`, String(el.scrollTop));
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [ref, key]);

  // Restore when the key changes. The diff loads asynchronously, so we poll
  // (rAF) re-applying the saved offset as the content grows tall enough to
  // reach it — independent of the DOM structure — stopping once reached or
  // after a few seconds.
  useEffect(() => {
    const el = ref.current;
    if (!el || !key) return;
    const saved = Number(sessionStorage.getItem(`gitloco:scroll:${key}`) ?? 0);
    if (saved <= 0) {
      el.scrollTop = 0;
      return;
    }
    let raf = 0;
    let done = false;
    const start = performance.now();
    const tick = () => {
      if (done) return;
      const maxTop = el.scrollHeight - el.clientHeight;
      el.scrollTop = Math.min(saved, maxTop);
      if (maxTop >= saved || performance.now() - start > 4000) {
        done = true;
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      done = true;
      cancelAnimationFrame(raf);
    };
  }, [ref, key]);
}
