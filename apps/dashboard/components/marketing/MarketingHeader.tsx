"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { apiFetch, type UserPayload } from "@/lib/api";
import { UmroviaLogo } from "@/components/UmroviaLogo";
import { BtnLink } from "@/components/workspace/ui";

/**
 * Tautan nav dengan animasi teks "berguling" (roll) — pola yang sama dengan
 * template (`.btn__content ~ .btn__content`): dua lapis label setinggi tombol
 * 30px di dalam kotak clip 30px; keduanya bergeser -100% saat hover sehingga
 * tidak ada huruf yang terpotong.
 */
function RollLink({ href, children, active, onClick }: { href: string; children: string; active?: boolean; onClick?: () => void }) {
  const roll =
    "flex h-[30px] items-center transition-transform duration-[600ms] ease-[cubic-bezier(.25,.74,.22,.99)] group-hover:-translate-y-full motion-reduce:transition-none";
  const Component = href.startsWith("#") ? "a" : Link;
  return (
    <Component href={href} onClick={onClick} aria-current={active ? "page" : undefined} className="group relative block h-[30px] overflow-hidden">
      <span className={roll}>{children}</span>
      <span aria-hidden className={roll}>
        {children}
      </span>
    </Component>
  );
}

/**
 * Header halaman marketing — sticky setinggi `--header-height` template:
 * 50px (60px mulai layar xxl ≥1440) dengan hairline bawah `--t-line`
 * (#e8e8e8) ala `header--sticky`. Mengecek sesi lewat GET /me: bila sudah
 * masuk, CTA kanan berubah menjadi "Buka dashboard".
 */
export function MarketingHeader() {
  const headerRef = useRef<HTMLElement>(null);
  const [authed, setAuthed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const links = [
    { href: pathname === "/" ? "#fitur" : "/#fitur", label: "Fitur" },
    { href: pathname === "/" ? "#modul" : "/#modul", label: "Modul" },
    { href: pathname === "/" ? "#mulai" : "/#mulai", label: "Cara mulai" },
    { href: "/pricing", label: "Pricing" },
    { href: "/kontak", label: "Kontak" },
  ];

  useEffect(() => {
    let active = true;
    apiFetch<UserPayload>("/me").then((result) => {
      if (active && result.ok) setAuthed(true);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const header = headerRef.current;
    const page = header?.closest<HTMLElement>("[data-marketing-page]");
    if (!header || !page) return;

    // Include the white padding around the feature sections, and the footer.
    // Scope to this page: Next.js can retain other routes in hidden trees.
    const sections = Array.from(page.querySelectorAll<HTMLElement>(
      "[data-scroll-section], main > section",
    ));
    let frame = 0;
    let disposed = false;
    let activeSection: HTMLElement | undefined;
    const updateTheme = () => {
      frame = 0;
      if (disposed || !header.getClientRects().length) return;
      const edge = header.getBoundingClientRect().bottom + 1;
      // The last matching section is the innermost section at this edge.
      const section = sections.findLast((element) => {
        const rect = element.getBoundingClientRect();
        return rect.height > 0 && rect.top <= edge && rect.bottom > edge;
      }) ?? sections.find((element) => {
        // During virtual scrolling, a wrapper's leading padding stays in
        // layout while its child sections move. Use the upcoming surface.
        const rect = element.getBoundingClientRect();
        return rect.height > 0 && rect.top > edge;
      });
      if (!section || section === activeSection) return;
      activeSection = section;
      const background = getComputedStyle(section).backgroundColor;
      const channels = background.match(/[\d.]+/g)?.slice(0, 3).map(Number);
      if (!channels || channels.length !== 3) return;
      const linear = channels.map((value) => {
        const channel = value / 255;
        return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
      });
      const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
      header.style.setProperty("--marketing-header-background", background);
      header.dataset.tone = luminance < 0.179 ? "dark" : "light";
    };
    const scheduleUpdate = () => {
      if (!disposed && !frame) frame = requestAnimationFrame(updateTheme);
    };
    // Native scroll events do not fire when SectionScroller translates sections.
    page.addEventListener("marketing:scroll", scheduleUpdate);
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    const observer = new ResizeObserver(scheduleUpdate);
    observer.observe(header);
    sections.forEach((section) => observer.observe(section));
    scheduleUpdate();
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      page.removeEventListener("marketing:scroll", scheduleUpdate);
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
      header.style.removeProperty("--marketing-header-background");
      delete header.dataset.tone;
    };
  }, [pathname]);

  return (
    <header ref={headerRef} className="marketing-header sticky top-0 z-50 h-[50px] before:absolute before:inset-x-0 before:bottom-0 before:h-px min-[1440px]:h-[60px]">
      <div className="mkt-container flex h-full items-center justify-between gap-3">
        <Link
          href="/"
          className="marketing-header__brand flex shrink-0 items-center"
          aria-label="Umrovia — beranda"
        >
          <UmroviaLogo className="" />
        </Link>

        <nav
          className="hidden items-center gap-6 min-[1100px]:flex"
          aria-label="Navigasi utama"
        >
          {links.map((link) => <RollLink key={link.label} href={link.href} active={pathname === link.href}>{link.label}</RollLink>)}
        </nav>

        <div className="flex shrink-0 items-center gap-2 sm:gap-4">
          {authed ? (
            <BtnLink href="/dashboard" variant="solid">
              Buka dashboard
            </BtnLink>
          ) : (
            <>
              <BtnLink href="/login" variant="link">
                Masuk
              </BtnLink>
              <BtnLink href="/register" variant="solid">
                Daftar
              </BtnLink>
            </>
          )}
          <button type="button" className="grid h-8 w-8 place-items-center min-[1100px]:hidden" aria-label={menuOpen ? "Tutup menu" : "Buka menu"} aria-expanded={menuOpen} aria-controls="marketing-menu" onClick={() => setMenuOpen(!menuOpen)}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={menuOpen ? "M5 5l10 10M15 5L5 15" : "M3 6h14M3 14h14"} /></svg>
          </button>
        </div>
      </div>
      {menuOpen && <nav id="marketing-menu" aria-label="Navigasi mobile" className="marketing-header__menu absolute inset-x-0 top-full grid gap-3 border-b px-[30px] py-6 min-[1100px]:hidden">
        {links.map((link) => <RollLink key={link.label} href={link.href} active={pathname === link.href} onClick={() => setMenuOpen(false)}>{link.label}</RollLink>)}
        <RollLink href="/kebijakan-privasi" onClick={() => setMenuOpen(false)}>Kebijakan Privasi</RollLink>
      </nav>}
    </header>
  );
}
