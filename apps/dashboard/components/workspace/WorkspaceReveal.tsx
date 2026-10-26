"use client";

import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, type ReactNode } from "react";

/** Blok yang dianimasikan: paragraf pembuka halaman dan setiap kartu. */
const TARGETS = ".workspace-page > p, .workspace-page .card";
/** Sama dengan RevealText marketing: layar kecil dan reduced motion tetap statis. */
const SCREEN = "(min-width: 568px) and (max-aspect-ratio: 13/9), (min-width: 668px) and (min-height: 416px), (min-width: 980px)";
const REDUCED = "(prefers-reduced-motion: reduce), (update: slow)";
const STAGGER_MS = 70;
const MAX_STAGGER = 6;

/**
 * Animasi masuk ala web marketing untuk halaman workspace: blok naik dan
 * memudar (0.7s, easing editorial) saat masuk layar, bertahap per batch.
 * Kartu yang baru dirender setelah data dimuat ikut teranimasi sekali.
 * Elemen ditandai di layout effect/MutationObserver sebelum browser melukis
 * sehingga tidak berkedip; kelas dilepas setelah transisi agar transisi
 * bawaan kartu tidak tertimpa.
 */
export function WorkspaceReveal({ children }: { children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useLayoutEffect(() => {
    const element = root.current;
    if (!element) return;
    const screen = window.matchMedia(SCREEN);
    const reduced = window.matchMedia(REDUCED);
    let stop: (() => void) | undefined;
    // Per halaman, bukan per restart: perubahan media query (resize, rotasi)
    // tidak boleh menyembunyikan ulang blok yang sudah tampil.
    const seen = new WeakSet<Element>();

    const finish = (target: HTMLElement) => {
      target.classList.remove("ws-reveal");
      delete target.dataset.revealReady;
      delete target.dataset.revealVisible;
      target.style.removeProperty("--ws-reveal-delay");
    };

    const start = () => {
      stop?.();
      stop = undefined;
      if (!screen.matches || reduced.matches) return;

      const pending = new Set<HTMLElement>();
      const queue: HTMLElement[] = [];
      let frame = 0;
      const visible = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const target = entry.target as HTMLElement;
          target.dataset.revealVisible = "true";
          visible.unobserve(target);
        }
      }, { rootMargin: "0px 0px -60px 0px", threshold: 0 });
      const onEnd = (event: TransitionEvent) => {
        const target = event.target as HTMLElement;
        if (event.propertyName === "transform" && target.classList.contains("ws-reveal")) {
          pending.delete(target);
          finish(target);
        }
      };
      element.addEventListener("transitionend", onEnd);

      const scan = () => {
        const batch: HTMLElement[] = [];
        element.querySelectorAll<HTMLElement>(TARGETS).forEach((target) => {
          if (seen.has(target)) return;
          // Halaman sebelumnya disimpan Next dalam keadaan tersembunyi
          // (display: none); biarkan sampai benar-benar dirender.
          if (target.getClientRects().length === 0) return;
          seen.add(target);
          target.classList.add("ws-reveal");
          target.style.setProperty("--ws-reveal-delay", `${Math.min(batch.length, MAX_STAGGER) * STAGGER_MS}ms`);
          target.dataset.revealReady = "true";
          pending.add(target);
          batch.push(target);
        });
        if (!batch.length) return;
        // Pose tersembunyi dilukis dulu, baru transisi dimulai saat terlihat.
        queue.push(...batch);
        if (!frame) {
          frame = requestAnimationFrame(() => {
            frame = 0;
            queue.splice(0).forEach((target) => visible.observe(target));
          });
        }
      };

      scan();
      const mutations = new MutationObserver(scan);
      mutations.observe(element, { childList: true, subtree: true });
      stop = () => {
        cancelAnimationFrame(frame);
        mutations.disconnect();
        visible.disconnect();
        element.removeEventListener("transitionend", onEnd);
        pending.forEach(finish);
        pending.clear();
      };
    };

    start();
    screen.addEventListener("change", start);
    reduced.addEventListener("change", start);
    return () => {
      screen.removeEventListener("change", start);
      reduced.removeEventListener("change", start);
      stop?.();
    };
  }, [pathname]);

  return <div ref={root}>{children}</div>;
}
