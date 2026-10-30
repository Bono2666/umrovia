"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Video tur aplikasi Umrovia (data demo fiktif, infra/marketing/record_tour.py).
 *
 * Diputar tanpa suara dan berulang hanya selama terlihat di layar. Pengunjung dengan
 * prefers-reduced-motion melihat poster diam dan memutar sendiri lewat kontrol video.
 */
export function ProductVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    video.muted = true; // React tidak menyetel properti muted; tanpa ini autoplay ditolak browser
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let visible = false;
    const sync = () => {
      setReduced(motion.matches);
      if (visible && !motion.matches) void video.play().catch(() => undefined);
      else video.pause();
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      sync();
    }, { threshold: 0.15 });
    observer.observe(video);
    motion.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", sync);
    };
  }, []);

  return (
    <video
      ref={ref}
      className="block h-auto w-full"
      width={1600}
      height={1000}
      poster="/marketing/tur-aplikasi-poster.webp"
      muted
      loop
      playsInline
      preload="metadata"
      controls={reduced}
      aria-label="Tur aplikasi Umrovia: Ringkasan, Leads, Jamaah, Booking, Invoice, Manifest, dan Laporan"
    >
      <source src="/marketing/tur-aplikasi.webm" type="video/webm" />
      <source src="/marketing/tur-aplikasi.mp4" type="video/mp4" />
    </video>
  );
}
