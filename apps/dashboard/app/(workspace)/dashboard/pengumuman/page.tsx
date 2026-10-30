"use client";

import { useCallback, useEffect, useState } from "react";
import { Btn, EmptyState, FormField, FormSelect, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Departure } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

type Announcement = {id: string; title: string; body: string; published_at: string | null; expires_at: string | null; status: "DRAFT" | "PUBLISHED" | "EXPIRED"; departure: {id: string; code: string} | null; created_by: string | null; created_at: string};
const STATUS = {DRAFT: {label: "Draf", tone: "neutral"}, PUBLISHED: {label: "Tayang", tone: "success"}, EXPIRED: {label: "Selesai", tone: "warning"}} as const;
const EMPTY = {title: "", body: "", departure: "", expires: ""};

/** POR-05: pengumuman travel yang tampil di portal jamaah (semua jamaah atau satu keberangkatan). */
export default function AnnouncementsPage() {
  const {can, loading} = useWorkspacePermissions();
  const [rows, setRows] = useState<Announcement[] | null>(null);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => apiFetch<{results: Announcement[]}>("/announcements").then((r) => {if (r.ok) setRows(r.data.results); else setError(problemMessage(r.error));}), []);
  useEffect(() => {
    if (loading || !can("announcements.manage")) return;
    void load();
    void apiFetch<{results: Departure[]}>("/departures").then((r) => {if (r.ok) setDepartures(r.data.results);});
  }, [loading, can, load]);

  async function create(publish: boolean) {
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<Announcement>("/announcements", {method: "POST", body: JSON.stringify({
      title: form.title, body: form.body, departure: form.departure || null, publish, expires_at: form.expires ? new Date(`${form.expires}T23:59:00`).toISOString() : null,
    })});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(result.data.id);
    setMessage(publish ? `"${result.data.title}" tayang di portal jamaah.` : `"${result.data.title}" disimpan sebagai draf.`);
    setForm(EMPTY); void load();
  }

  async function act(row: Announcement, action: "publish" | "unpublish" | "archive") {
    setError(null); setMessage(null);
    const result = await apiFetch<Announcement>(`/announcements/${row.id}`, {method: "PATCH", body: JSON.stringify({action})});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    focusRecord(row.id);
    setMessage({publish: "Pengumuman ditayangkan.", unpublish: "Pengumuman ditarik ke draf.", archive: "Pengumuman diakhiri."}[action]); void load();
  }

  if (loading) return <LoadingState />;
  if (!can("announcements.manage")) return <EmptyState title="Anda tidak memiliki akses pengumuman" />;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Pengumuman Portal</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Informasi untuk jamaah di portal: jadwal manasik, perlengkapan, perubahan jadwal. Pilih keberangkatan agar hanya jamaah rombongan tersebut yang melihat.</p>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <h2 className="font-semibold">Daftar pengumuman</h2>
        {rows === null ? <LoadingState /> : rows.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada pengumuman" /></div> :
          <ul className="mt-4 divide-y divide-border">{rows.map((row) => <li key={row.id} data-record={row.id} className="py-4 text-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-2"><span className="font-medium">{row.title}</span><StatusBadge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</StatusBadge></p>
                <p className="mt-1 whitespace-pre-line text-muted">{row.body}</p>
                <p className="mt-1 text-xs text-muted">{row.departure ? `Rombongan ${row.departure.code}` : "Semua jamaah"}{row.published_at ? ` · tayang ${formatDate(row.published_at)}` : ""}{row.expires_at ? ` · s.d. ${formatDate(row.expires_at)}` : ""}{row.created_by ? ` · ${row.created_by}` : ""}</p>
              </div>
              <div className="flex shrink-0 gap-3">
                {row.status === "DRAFT" ? <Btn size="xs" onClick={() => void act(row, "publish")}>Tayangkan</Btn> : null}
                {row.status === "PUBLISHED" ? <><Btn size="xs" variant="link" onClick={() => void act(row, "unpublish")}>Tarik</Btn><Btn size="xs" variant="link" onClick={() => void act(row, "archive")}>Akhiri</Btn></> : null}
              </div>
            </div>
          </li>)}</ul>}
      </section>
      <section className="card min-w-0 p-6"><h2 className="font-semibold">Buat pengumuman</h2>
        <form className="mt-6" onSubmit={(e) => {e.preventDefault(); void create(true);}}>
          <FormField label="Judul" htmlFor="announcement-title" maxLength={160} value={form.title} onChange={(e) => setForm({...form, title: e.target.value})} required />
          <FormTextarea label="Isi" htmlFor="announcement-body" rows={5} maxLength={5000} value={form.body} onChange={(e) => setForm({...form, body: e.target.value})} required />
          <FormSelect label="Untuk" htmlFor="announcement-departure" value={form.departure} onChange={(e) => setForm({...form, departure: e.target.value})}>
            <option value="">Semua jamaah</option>{departures.map((d) => <option key={d.id} value={d.id}>Rombongan {d.code} · {d.package_name} · {formatDate(d.start_at)}</option>)}
          </FormSelect>
          <FormField label="Tayang sampai (opsional)" htmlFor="announcement-expires" type="date" value={form.expires} onChange={(e) => setForm({...form, expires: e.target.value})} />
          <div className="flex flex-wrap gap-3">
            <Btn type="submit" loading={busy} disabled={!form.title.trim() || !form.body.trim()}>Tayangkan</Btn>
            <Btn type="button" variant="tint" disabled={busy || !form.title.trim() || !form.body.trim()} onClick={() => void create(false)}>Simpan draf</Btn>
          </div>
        </form>
      </section>
    </div>
  </div>;
}
