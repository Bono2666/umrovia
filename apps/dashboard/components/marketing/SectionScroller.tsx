"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

const clamp = (value: number, max: number) => Math.max(0, Math.min(value, max));

/**
 * web_template: smooth scroll lerp .06 and the clamped `section-out` pattern.
 * Short sections animate from top=0 to bottom=0; tall sections animate from
 * bottom=viewport-bottom to bottom=0. The inner layer shifts from 0 to 30vh.
 */
function startScroller(page: HTMLElement, resetPosition = false) {
  const html = document.documentElement;
  const sections = Array.from(
    page.querySelectorAll<HTMLElement>(".mkt-scroll-section[data-scroll-section]"),
    (element) => ({
      element,
      layer: element.querySelector<HTMLElement>('[data-parallax-pattern="section-out"]'),
      top: 0,
      height: 0,
    }),
  );
  const previousRestoration = history.scrollRestoration;
  let current = resetPosition ? 0 : window.scrollY;
  let target = current;
  let limit = 0;
  let raf = 0;
  let resizeRaf = 0;
  let disposed = false;
  let hideTimer: ReturnType<typeof setTimeout> | undefined;

  html.classList.add("has-scroll-smooth");
  history.scrollRestoration = "manual";
  window.scrollTo(0, 0);
  const scrollbar = document.createElement("div");
  scrollbar.className = "c-scrollbar";
  scrollbar.setAttribute("aria-hidden", "true");
  const thumb = document.createElement("span");
  thumb.className = "c-scrollbar_thumb";
  scrollbar.append(thumb);
  document.body.append(scrollbar);

  const paint = () => {
    const viewport = window.innerHeight;
    for (const { element, layer, top, height } of sections) {
      element.style.transform = `translate3d(0, ${-current}px, 0)`;
      if (layer) {
        const start = top + Math.max(0, height - viewport);
        const progress = clamp((current - start) / Math.max(1, Math.min(height, viewport)), 1);
        layer.style.transform = `translate3d(0, ${progress * viewport * 0.3}px, 0)`;
      }
    }
    const height = Math.max(24, (viewport * viewport) / (limit + viewport));
    thumb.style.height = `${height}px`;
    thumb.style.transform = `translate3d(0, ${(current / Math.max(1, limit)) * (viewport - height - 4)}px, 0)`;
    page.dispatchEvent(new Event("marketing:scroll"));
  };
  const measure = () => {
    let bottom = 0;
    for (const section of sections) {
      section.top = section.element.getBoundingClientRect().top + current;
      section.height = section.element.offsetHeight;
      bottom = Math.max(bottom, section.top + section.height);
    }
    limit = Math.max(0, bottom - window.innerHeight);
    current = clamp(current, limit);
    target = clamp(target, limit);
    paint();
  };
  const tick = () => {
    current += (target - current) * 0.06;
    if (Math.abs(target - current) < 0.25) current = target;
    paint();
    raf = current === target ? 0 : requestAnimationFrame(tick);
  };
  const setTarget = (value: number) => {
    target = clamp(value, limit);
    html.classList.add("has-scroll-scrolling");
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => html.classList.remove("has-scroll-scrolling"), 600);
    if (!raf) raf = requestAnimationFrame(tick);
  };

  const onWheel = (event: WheelEvent) => {
    if (event.ctrlKey || event.defaultPrevented) return;
    // Preserve zoom gestures and independently scrollable controls.
    for (let el = event.target instanceof Element ? event.target : null;
      el && el !== document.body; el = el.parentElement) {
      if (/(auto|scroll)/.test(getComputedStyle(el).overflowY) &&
        el.scrollHeight > el.clientHeight &&
        ((event.deltaY < 0 && el.scrollTop > 0) ||
          (event.deltaY > 0 && el.scrollTop + el.clientHeight < el.scrollHeight))) return;
    }
    event.preventDefault();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? window.innerHeight : 1;
    setTarget(target + event.deltaY * unit);
  };
  let touchY: number | null = null;
  const onTouchStart = (event: TouchEvent) => {
    touchY = event.touches.length === 1 ? event.touches[0].clientY : null;
  };
  const onTouchMove = (event: TouchEvent) => {
    if (touchY === null || event.touches.length !== 1) return;
    const y = event.touches[0].clientY;
    setTarget(target + (touchY - y) * 2);
    touchY = y;
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey ||
      (document.activeElement instanceof HTMLElement &&
        document.activeElement.closest('input, textarea, select, button, [contenteditable]:not([contenteditable="false"])'))) return;
    switch (event.key) {
      case "ArrowUp": setTarget(target - 240); break;
      case "ArrowDown": setTarget(target + 240); break;
      case "PageUp": setTarget(target - window.innerHeight); break;
      case "PageDown": setTarget(target + window.innerHeight); break;
      case "Home": setTarget(0); break;
      case "End": setTarget(limit); break;
      case " ": setTarget(target + (event.shiftKey ? -0.9 : 0.9) * window.innerHeight); break;
      default: return;
    }
    event.preventDefault();
  };

  const hashTarget = () => {
    let id: string;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return null; }
    if (!id) return 0;
    const element = page.querySelector<HTMLElement>(`#${CSS.escape(id)}`);
    if (!element) return null;
    const headerHeight = page.querySelector("header")?.getBoundingClientRect().height ?? 64;
    return element.getBoundingClientRect().top + current - headerHeight;
  };
  const onHashChange = () => {
    const value = hashTarget();
    if (value !== null) setTarget(value);
  };
  const onClick = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href^="#"]') : null;
    if (!anchor || (anchor.target && anchor.target !== "_self")) return;
    const hash = anchor.getAttribute("href")!;
    let id: string;
    try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
    if (id && !page.querySelector(`#${CSS.escape(id)}`)) return;
    event.preventDefault();
    if (location.hash !== hash) history.pushState(null, "", hash);
    onHashChange();
  };
  const onFocusIn = (event: FocusEvent) => {
    const element = event.target;
    if (!(element instanceof HTMLElement) || !element.closest("[data-scroll-section]")) return;
    const rect = element.getBoundingClientRect();
    if (rect.top < 64 || rect.bottom > window.innerHeight) {
      setTarget(rect.top + current - window.innerHeight / 3);
    }
  };

  let dragging = false;
  let dragOffset = 0;
  const onThumbDown = (event: PointerEvent) => {
    event.preventDefault();
    dragging = true;
    dragOffset = event.clientY - thumb.getBoundingClientRect().top;
    thumb.setPointerCapture(event.pointerId);
    html.classList.add("has-scroll-dragging");
  };
  const onDragMove = (event: PointerEvent) => {
    if (!dragging) return;
    const travel = window.innerHeight - thumb.offsetHeight - 4;
    setTarget(((event.clientY - dragOffset - 2) / Math.max(1, travel)) * limit);
  };
  const onDragUp = () => {
    dragging = false;
    html.classList.remove("has-scroll-dragging");
  };
  const onResize = () => {
    if (disposed || resizeRaf) return;
    resizeRaf = requestAnimationFrame(() => {
      resizeRaf = 0;
      measure();
    });
  };
  window.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("touchstart", onTouchStart, { passive: true });
  window.addEventListener("touchmove", onTouchMove, { passive: true });
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("hashchange", onHashChange);
  window.addEventListener("popstate", onHashChange);
  window.addEventListener("resize", onResize);
  page.addEventListener("click", onClick);
  page.addEventListener("focusin", onFocusIn);
  thumb.addEventListener("pointerdown", onThumbDown);
  thumb.addEventListener("pointermove", onDragMove);
  thumb.addEventListener("pointerup", onDragUp);
  thumb.addEventListener("pointercancel", onDragUp);
  const observer = new ResizeObserver(onResize);
  for (const { element } of sections) observer.observe(element);
  document.fonts.ready.then(onResize).catch(() => {});

  // Apply the scroll transform before reading absolute section positions.
  paint();
  measure();
  if (location.hash) {
    const value = hashTarget();
    if (value !== null) current = target = clamp(value, limit);
    paint();
  }
  return (restorePosition = true) => {
    disposed = true;
    window.removeEventListener("wheel", onWheel);
    window.removeEventListener("touchstart", onTouchStart);
    window.removeEventListener("touchmove", onTouchMove);
    window.removeEventListener("keydown", onKeyDown);
    window.removeEventListener("hashchange", onHashChange);
    window.removeEventListener("popstate", onHashChange);
    window.removeEventListener("resize", onResize);
    page.removeEventListener("click", onClick);
    page.removeEventListener("focusin", onFocusIn);
    thumb.removeEventListener("pointerdown", onThumbDown);
    thumb.removeEventListener("pointermove", onDragMove);
    thumb.removeEventListener("pointerup", onDragUp);
    thumb.removeEventListener("pointercancel", onDragUp);
    observer.disconnect();
    clearTimeout(hideTimer);
    cancelAnimationFrame(raf);
    cancelAnimationFrame(resizeRaf);
    html.classList.remove("has-scroll-smooth", "has-scroll-scrolling", "has-scroll-dragging");
    scrollbar.remove();
    for (const { element, layer } of sections) {
      element.style.removeProperty("transform");
      layer?.style.removeProperty("transform");
    }
    history.scrollRestoration = previousRestoration;
    window.scrollTo(0, restorePosition ? current : 0);
  };
}

export function SectionScroller() {
  const pathname = usePathname();
  const marker = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    // Cache Components retains hidden routes. Measure this page only.
    const page = marker.current?.closest<HTMLElement>("[data-marketing-page]");
    if (!page) return;
    const desktop = window.matchMedia("(min-width: 980px)");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let stop: ((restorePosition?: boolean) => void) | undefined;
    let initial = true;
    const updateMode = () => {
      stop?.();
      stop = desktop.matches && !reduced.matches ? startScroller(page, initial) : undefined;
      initial = false;
    };
    updateMode();
    desktop.addEventListener("change", updateMode);
    reduced.addEventListener("change", updateMode);
    return () => {
      desktop.removeEventListener("change", updateMode);
      reduced.removeEventListener("change", updateMode);
      stop?.(false);
    };
  }, [pathname]);
  return <span ref={marker} hidden aria-hidden="true" />;
}
