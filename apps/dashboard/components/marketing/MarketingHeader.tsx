"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, type UserPayload } from "@/lib/api";
import { UmroviaMark } from "@/components/UmroviaMark";
import { BtnLink } from "@/components/workspace/ui";

/**
 * Tautan nav dengan animasi teks "berguling" (roll) — pola yang sama dengan
 * sidebar workspace: dua lapis label, keduanya bergeser -100% saat hover.
 */
function RollLink({ href, children }: { href: string; children: string }) {
  const roll =
    "block transition-transform duration-[600ms] ease-[cubic-bezier(.25,.74,.22,.99)] group-hover:-translate-y-full motion-reduce:transition-none";
  return (
    <a href={href} className="group relative block h-4 overflow-hidden">
      <span className={roll}>{children}</span>
      <span aria-hidden className={roll}>
        {children}
      </span>
    </a>
  );
}

/**
 * Header halaman marketing — sticky setinggi 48px dengan hairline bawah
 * (ala `header--sticky` template). Mengecek sesi lewat GET /me: bila sudah
 * masuk, CTA kanan berubah menjadi "Buka dashboard".
 */
export function MarketingHeader() {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch<UserPayload>("/me").then((result) => {
      if (active && result.ok) setAuthed(true);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <header className="sticky top-0 z-50 border-b border-black/10 bg-white">
      <div className="mkt-container flex h-12 items-center justify-between gap-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5"
          aria-label="Umrovia — beranda"
        >
          <UmroviaMark className="h-7 w-7" />
          <span className="text-lg font-semibold tracking-[-0.04em]">
            Umrovia
          </span>
        </Link>

        <nav
          className="hidden items-center gap-8 min-[980px]:flex"
          aria-label="Navigasi utama"
        >
          <RollLink href="#fitur">Fitur</RollLink>
          <RollLink href="#modul">Modul</RollLink>
          <RollLink href="#mulai">Cara mulai</RollLink>
        </nav>

        <div className="flex shrink-0 items-center gap-4">
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
        </div>
      </div>
    </header>
  );
}
