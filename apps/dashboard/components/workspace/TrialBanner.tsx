"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, problemMessage, type TrialStatus } from "@/lib/api";
import { formatDate, formatRemaining } from "@/lib/format";

/**
 * Banner masa uji coba (S06, Spec §4.3 + §8.7): countdown absolut ke
 * `ends_at` + jumlah booking/user terpakai + tombol konversi (Owner,
 * `trial.convert`). Disembunyikan otomatis saat 403 (peran tanpa
 * `trial.read`) atau setelah workspace terkonversi — server tetap otoritas.
 */
export function TrialBanner({
  canConvert,
  onConverted,
}: {
  canConvert: boolean;
  onConverted: () => void;
}) {
  const [status, setStatus] = useState<TrialStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(() => {
    apiFetch<TrialStatus>("/trial/status").then((result) => {
      setStatus(result.ok ? result.data : null);
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  if (!status || status.converted_at) return null;

  async function onConvert() {
    const confirmed = window.confirm(
      "Konversi workspace ke mode produksi sekarang? " +
        "Setelah ini data uji coba (booking dummy) dinonaktifkan dan workspace " +
        "berstatus aktif — tanpa biaya otomatis.",
    );
    if (!confirmed) return;
    setBusy(true);
    setError(null);
    const result = await apiFetch<{ trial_status: string }>("/trial/convert", {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(problemMessage(result.error));
      return;
    }
    onConverted();
  }

  return (
    <div className="card border-warning/30 bg-warning/10 p-4 text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="font-semibold">
          Masa uji coba — berakhir {formatDate(status.ends_at)}{" "}
          <span className="font-normal text-muted">
            ({formatRemaining(status.ends_at, now)})
          </span>
        </p>
        <p className="text-muted">
          Booking dummy: {status.dummy_bookings_used}/{status.dummy_bookings_limit} ·
          Pengguna internal: {status.internal_users_used}/{status.internal_users_limit}
        </p>
        {canConvert ? (
          <button
            type="button"
            onClick={onConvert}
            disabled={busy || !status.can_convert_now}
            className="btn btn--solid ml-auto"
          >
            {busy ? "Mengonversi…" : "Konversi ke Produksi"}
          </button>
        ) : null}
      </div>
      {error ? (
        <p className="mt-2 text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
