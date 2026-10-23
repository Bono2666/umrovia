"use client";

import { useEffect } from "react";

/**
 * Motor paralaks ringan — memakai rumus yang sama dengan locomotive-scroll
 * (mesin gulir web_template): setiap elemen dengan atribut
 * `data-scroll-speed="2"` digeser `translateY = (viewportCenter − middle
 * elemen) × −(speed/10)`. Elemen dengan speed lebih besar naik lebih cepat
 * daripada aliran halaman sehingga tiap section terasa berdimensi.
 *
 * Berjalan di atas scroll native (tanpa peng-hijack gulir), hanya menghitung
 * pada frame saat ada guliran (rAF-on-demand), mengukur ulang saat layout
 * berubah (resize/font), dan menghormati prefers-reduced-motion.
 */
export function Parallax() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    const items: Array<{ el: HTMLElement; speed: number; middle: number }> = [];
    let raf = 0;

    const measure = () => {
      items.length = 0;
      document
        .querySelectorAll<HTMLElement>("[data-scroll-speed]")
        .forEach((el) => {
          const speed = parseFloat(el.dataset.scrollSpeed ?? "0") / 10;
          if (!speed) return;
          // Ukur posisi absolut tanpa transform aktif agar tidak kumulatif.
          const previous = el.style.transform;
          el.style.transform = "";
          const rect = el.getBoundingClientRect();
          items.push({
            el,
            speed,
            middle: rect.top + window.scrollY + rect.height / 2,
          });
          el.style.transform = previous;
          el.style.willChange = "transform";
        });
    };

    const render = () => {
      raf = 0;
      const center = window.scrollY + window.innerHeight / 2;
      for (const item of items) {
        const y = (center - item.middle) * -item.speed;
        item.el.style.transform = `translate3d(0, ${y.toFixed(1)}px, 0)`;
      }
    };

    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(render);
    };

    measure();
    render();

    window.addEventListener("scroll", onScroll, { passive: true });
    const onResize = () => {
      measure();
      onScroll();
    };
    window.addEventListener("resize", onResize);
    // Layout bergeser setelah Poppins selesai dimuat / konten berubah tinggi.
    document.fonts?.ready.then(onResize).catch(() => {});
    const observer = new ResizeObserver(onResize);
    observer.observe(document.body);

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      if (raf) cancelAnimationFrame(raf);
      for (const item of items) {
        item.el.style.transform = "";
        item.el.style.willChange = "";
      }
    };
  }, []);

  return null;
}
