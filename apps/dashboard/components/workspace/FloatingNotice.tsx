"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const TONES = {
  success: {
    box: "border-success/30 border-l-success bg-[color-mix(in_srgb,var(--status-success)_10%,var(--surface))] text-success",
    close: "text-success/70 hover:text-success focus-visible:outline-success",
  },
  danger: {
    box: "border-danger/30 border-l-danger bg-[color-mix(in_srgb,var(--status-danger)_10%,var(--surface))] text-danger",
    close: "text-danger/70 hover:text-danger focus-visible:outline-danger",
  },
} as const;

/**
 * Notifikasi melayang di bawah header (bukan di atas halaman), sehingga tetap terlihat di
 * posisi gulir mana pun. Dipasang lewat portal ke <body> supaya `position: fixed` tidak
 * terpengaruh transform leluhur.
 *
 * - `success`: hilang sendiri setelah `duration` ms; jeda selama kursor/fokus di atasnya.
 * - `danger`: tetap tampil sampai ditutup atau aksi berikutnya mengosongkan pesan (pesan gagal
 *   harus sempat dibaca), lalu halaman digulir ke sumber masalah lewat `focusError`.
 */
export function FloatingNotice({
  message,
  onDismiss,
  tone = "success",
  duration = 6000,
}: {
  message: string | null;
  onDismiss: () => void;
  tone?: keyof typeof TONES;
  duration?: number;
}) {
  const [held, setHeld] = useState(false);
  const dismiss = useRef(onDismiss);
  useEffect(() => {
    dismiss.current = onDismiss;
  });

  useEffect(() => {
    if (!message || held || tone === "danger") return;
    const timer = setTimeout(() => dismiss.current(), duration);
    return () => clearTimeout(timer);
  }, [message, held, duration, tone]);

  useEffect(() => {
    if (message && tone === "danger") focusError();
  }, [message, tone]);

  if (!message) return null;
  const style = TONES[tone];
  return createPortal(
    <div
      role={tone === "danger" ? "alert" : "status"}
      aria-live={tone === "danger" ? "assertive" : "polite"}
      className="floating-notice fixed inset-x-4 top-[4.5rem] z-50 sm:left-auto sm:right-6 sm:w-[26rem]"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <div className={`flex items-start gap-3 border border-l-[3px] py-3 pl-3 pr-2 text-sm shadow-[0_12px_32px_-16px_rgb(0_0_0/0.35)] ${style.box}`}>
        <p className="min-w-0 flex-1">{message}</p>
        <button
          type="button"
          onClick={() => dismiss.current()}
          aria-label="Tutup notifikasi"
          className={`-my-1 shrink-0 p-1 focus-visible:outline-2 ${style.close}`}
        >
          <X aria-hidden="true" className="h-4 w-4" />
        </button>
      </div>
    </div>,
    document.body,
  );
}

/* Elemen yang terakhir memicu aksi (tombol yang diklik / form yang dikirim): tujuan gulir
   pesan gagal yang tidak menunjuk field tertentu. */
let lastTrigger: { element: Element; at: number } | null = null;
if (typeof document !== "undefined") {
  const remember = (element: Element | null) => {
    if (element && !element.closest(".floating-notice")) lastTrigger = { element, at: Date.now() };
  };
  document.addEventListener("click", (event) => remember((event.target as Element | null)?.closest?.("button, a, [role=button], label.btn") ?? null), true);
  document.addEventListener("submit", (event) => remember((event as SubmitEvent).submitter ?? (event.target as Element)), true);
}

/**
 * Gulir ke sumber pesan gagal: field yang ditandai salah (`aria-invalid`) — lalu difokuskan —
 * atau, bila tidak ada, tombol/form yang memicu aksi. Disorot merah sebentar; tidak menggulir
 * bila sumbernya sudah terlihat. Dipanggil otomatis oleh FloatingNotice `danger`, dan oleh
 * form yang hanya menampilkan error per field.
 */
export function focusError() {
  reveal(() => {
    const field = document.querySelector('[aria-invalid="true"]');
    if (field) return field.closest(".form-group") ?? field;
    const trigger = lastTrigger && Date.now() - lastTrigger.at < 15000 && lastTrigger.element.isConnected ? lastTrigger.element : null;
    return trigger?.closest(".form-group, li, tr") ?? trigger;
  }, "center", "danger", (element) => {
    const control = element.matches("input, select, textarea") ? element : element.querySelector('[aria-invalid="true"]');
    (control as HTMLElement | null)?.focus({ preventScroll: true });
  });
}

/**
 * Gulir halus ke baris data `[data-record="<id>"]` lalu sorot sebentar, agar pengguna melihat
 * data yang baru dibuat/diubah (hijau) atau data yang menjadi penyebab penolakan (`danger`,
 * merah). Bila baris tidak tampil (mis. tersaring filter atau di halaman lain), tidak terjadi apa-apa.
 */
export function focusRecord(id: string | number | null | undefined, tone: "success" | "danger" = "success") {
  if (id === null || id === undefined) return;
  const selector = `[data-record="${CSS.escape(String(id))}"]`;
  reveal(() => document.querySelector(selector), "center", tone);
}

/**
 * Gulir halus ke panel detail `[data-detail]` yang baru dibuka (mis. tombol Detail jamaah),
 * sehingga panel yang muncul di bawah daftar atau di kolom lain langsung terlihat.
 * `fieldId` opsional: kursor langsung ke isian yang harus dilengkapi berikutnya.
 */
export function focusDetail(fieldId?: string) {
  reveal(() => document.querySelector("[data-detail]"), "start", false, fieldId
    ? (panel) => panel.querySelector<HTMLElement>(`#${CSS.escape(fieldId)}`)?.focus({ preventScroll: true })
    : undefined);
}

/**
 * Elemen biasanya baru dirender setelah data dimuat, jadi ditunggu hingga 5 detik dan baru
 * dipakai setelah stabil (simpul yang sama dua kali berturut-turut, bukan elemen lama yang
 * segera diganti saat daftar dirender ulang). Tidak menggulir bila elemen sudah terlihat.
 */
function reveal(find: () => Element | null, block: "start" | "center", highlight: false | "success" | "danger", after?: (element: Element) => void) {
  if (typeof document === "undefined") return;
  const deadline = Date.now() + 5000;
  let previous: Element | null = null;
  const poll = () => {
    const element = find();
    if (element && element === previous) {
      const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const box = element.getBoundingClientRect();
      const visible = block === "start"
        ? box.top >= 72 && box.top <= window.innerHeight * 0.6
        : box.top >= 72 && box.bottom <= window.innerHeight;
      const done = () => {
        if (highlight) flash(element, highlight);
        after?.(element);
      };
      if (visible) {
        done();
        return;
      }
      // Hitung sendiri (bukan scrollIntoView) agar elemen tidak berhenti di balik header sticky 56px.
      const top = block === "start"
        ? box.top - 80
        : box.top - (window.innerHeight - Math.min(box.height, window.innerHeight - 160)) / 2;
      window.scrollBy({ top, behavior: reduce ? "auto" : "smooth" });
      // Sorot setelah guliran selesai, bukan saat mulai bergulir (guliran jauh butuh ±1 detik).
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        // Panel detail bisa bertambah tinggi saat datanya menyusul (dokumen, keluarga), sehingga
        // guliran pertama mentok di batas bawah halaman lama: koreksi sekali ke posisi semestinya.
        const rest = element.getBoundingClientRect().top - 80;
        if (block === "start" && Math.abs(rest) > 24) window.scrollBy({ top: rest, behavior: reduce ? "auto" : "smooth" });
        done();
      };
      window.addEventListener("scrollend", finish, { once: true });
      setTimeout(finish, reduce ? 0 : 1200); // browser tanpa event scrollend
      return;
    }
    previous = element;
    if (Date.now() < deadline) setTimeout(poll, 120);
  };
  setTimeout(poll, 120);
}

function flash(element: Element, tone: "success" | "danger") {
  const name = tone === "danger" ? "error-flash" : "record-flash";
  element.classList.remove(name);
  void (element as HTMLElement).offsetWidth; // mulai ulang animasi bila elemen yang sama disorot lagi
  element.classList.add(name);
  element.addEventListener("animationend", () => element.classList.remove(name), { once: true });
}
