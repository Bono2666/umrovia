"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, FormField, FormSelect, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type NotificationDelivery, type NotificationLog, type NotificationStatus, type NotificationTemplate } from "@/lib/api";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice } from "@/components/workspace/FloatingNotice";

const STATUS: Record<NotificationStatus, {label: string; tone: "neutral" | "success" | "warning" | "danger"; hint: string}> = {
  PENDING: {label: "Menunggu", tone: "neutral", hint: "Dalam antrean kirim"},
  SENT: {label: "Terkirim", tone: "success", hint: "Diterima server email"},
  FAILED: {label: "Dicoba ulang", tone: "warning", hint: "Gagal, akan dicoba lagi otomatis"},
  DEAD: {label: "Gagal", tone: "danger", hint: "Percobaan habis, kirim ulang manual"},
};
const dateTime = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"});

function statusBadge(row: NotificationDelivery) {
  if (row.channel === "IN_APP") return <StatusBadge tone="success">{row.read_at ? "Dibaca" : "Masuk portal"}</StatusBadge>;
  const meta = STATUS[row.status];
  return <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>;
}

export default function NotificationsPage() {
  const {can, loading} = useWorkspacePermissions();
  const canRead = can("notifications.read");
  const canManage = can("notifications.manage");
  const [tab, setTab] = useState<"log" | "templates">("log");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses notifikasi" />;

  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Notifikasi</RevealText>
    <p className="mt-1 max-w-3xl text-sm text-muted">Pesan otomatis untuk jamaah saat booking, invoice, pembayaran, dokumen dan jadwal berubah — masuk ke portal jamaah dan dikirim lewat email. Email yang gagal dicoba ulang otomatis; kegagalan email tidak mengubah data pembayaran.</p>
    <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label="Bagian notifikasi">
      {([["log", "Riwayat pengiriman"], ["templates", "Template pesan"]] as const).map(([key, label]) => (
        <Btn key={key} role="tab" aria-selected={tab === key} variant={tab === key ? "solid" : "tint"} onClick={() => {setTab(key); setError(null); setMessage(null);}}>{label}</Btn>
      ))}
    </div>
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    {tab === "log"
      ? <DeliveryLog canManage={canManage} onError={setError} onMessage={setMessage} />
      : <TemplateEditor canManage={canManage} onError={setError} onMessage={setMessage} />}
  </div>;
}

function DeliveryLog({canManage, onError, onMessage}: {canManage: boolean; onError: (value: string | null) => void; onMessage: (value: string | null) => void}) {
  const [log, setLog] = useState<NotificationLog | null>(null);
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [filters, setFilters] = useState({status: "", channel: "", template: "", q: ""});
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<NotificationDelivery | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const sequence = useRef(0);

  const load = useCallback(() => {
    const current = ++sequence.current;
    const query = new URLSearchParams(Object.entries({...filters, page: String(page)}).filter(([, value]) => value)).toString();
    return apiFetch<NotificationLog>(`/notifications?${query}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) setLog(result.data); else onError(problemMessage(result.error));
    });
  }, [filters, page, onError]);
  useEffect(() => {void load();}, [load]);
  useEffect(() => {void apiFetch<{results: NotificationTemplate[]}>("/notification-templates").then((result) => {if (result.ok) setTemplates(result.data.results);});}, []);

  function update(next: Partial<typeof filters>) {setPage(1); setFilters((value) => ({...value, ...next}));}

  async function view(row: NotificationDelivery) {
    if (open?.id === row.id) {setOpen(null); return;}
    const result = await apiFetch<NotificationDelivery>(`/notifications/${row.id}`);
    if (result.ok) setOpen(result.data); else onError(problemMessage(result.error));
  }

  async function resend(row: NotificationDelivery) {
    setBusy(row.id); onError(null); onMessage(null);
    const result = await apiFetch<NotificationDelivery>(`/notifications/${row.id}/resend`, {method: "POST"});
    setBusy(null);
    if (!result.ok) {onError(problemMessage(result.error)); return;}
    onMessage(`Email untuk ${row.recipient_name} masuk antrean kirim ulang dengan isi yang sama.`);
    void load();
  }

  return <>
    <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {(Object.keys(STATUS) as NotificationStatus[]).map((status) => (
        <button key={status} type="button" aria-pressed={filters.status === status && filters.channel === "EMAIL"}
          className={`card p-5 text-left transition-colors hover:border-primary ${filters.status === status && filters.channel === "EMAIL" ? "border-primary" : ""}`}
          onClick={() => update(filters.status === status && filters.channel === "EMAIL" ? {status: "", channel: ""} : {status, channel: "EMAIL"})}>
          <p className="text-sm text-muted">Email {STATUS[status].label.toLowerCase()}</p>
          <p className="mt-2 text-2xl font-semibold">{log ? log.summary[status] : "—"}</p>
          <p className="mt-1 text-xs text-muted">{STATUS[status].hint}</p>
        </button>
      ))}
    </div>
    <section className="card mt-6 p-6">
      <form className="notification-filters grid items-end gap-x-4 gap-y-8 md:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => {event.preventDefault(); update({q: search.trim()});}}>
        <FormField label="Cari penerima atau subjek" htmlFor="notif-q" value={search} onChange={(event) => setSearch(event.target.value)} onBlur={() => update({q: search.trim()})} />
        <FormSelect label="Jenis pesan" htmlFor="notif-template" value={filters.template} onChange={(event) => update({template: event.target.value})}>
          <option value="">Semua</option>
          {templates.map((template) => <option key={template.key} value={template.key}>{template.label}</option>)}
        </FormSelect>
        <FormSelect label="Kanal" htmlFor="notif-channel" value={filters.channel} onChange={(event) => update({channel: event.target.value})}>
          <option value="">Semua</option><option value="EMAIL">Email</option><option value="IN_APP">Portal jamaah</option>
        </FormSelect>
        <FormSelect label="Status" htmlFor="notif-status" value={filters.status} onChange={(event) => update({status: event.target.value})}>
          <option value="">Semua</option>
          {(Object.keys(STATUS) as NotificationStatus[]).map((status) => <option key={status} value={status}>{STATUS[status].label}</option>)}
        </FormSelect>
      </form>
      {log === null ? <LoadingState /> : log.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada notifikasi" description="Notifikasi muncul otomatis saat booking direservasi, invoice terbit, pembayaran diverifikasi, dokumen ditinjau atau jadwal keberangkatan berubah." /></div> : <>
        <div className="mt-4 overflow-x-auto"><table className="w-full min-w-180 text-left text-sm">
          <thead><tr className="border-b border-border text-muted"><th className="py-3 pr-4">Waktu</th><th className="py-3 pr-4">Pesan</th><th className="py-3 pr-4">Penerima</th><th className="py-3 pr-4">Status</th><th className="py-3 text-right">Aksi</th></tr></thead>
          <tbody>{log.results.map((row) => <NotificationRow key={row.id} row={row} open={open?.id === row.id ? open : null} busy={busy === row.id} canManage={canManage} onView={() => void view(row)} onResend={() => void resend(row)} />)}</tbody>
        </table></div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!log.previous} onClick={() => setPage((value) => value - 1)}>Sebelumnya</Btn><span>Halaman {page} · {log.count} pesan</span><Btn size="xs" variant="solid" disabled={!log.next} onClick={() => setPage((value) => value + 1)}>Berikutnya</Btn></div>
      </>}
    </section>
  </>;
}

function NotificationRow({row, open, busy, canManage, onView, onResend}: {row: NotificationDelivery; open: NotificationDelivery | null; busy: boolean; canManage: boolean; onView: () => void; onResend: () => void}) {
  const retry = row.channel === "EMAIL" && row.status === "FAILED" && row.next_attempt_at;
  return <>
    <tr className="border-b border-border align-top">
      <td className="whitespace-nowrap py-3 pr-4">{dateTime(row.created_at)}</td>
      <td className="py-3 pr-4"><span className="font-medium">{row.template_label}</span><p className="mt-1 max-w-80 text-xs text-muted">{row.subject}</p></td>
      <td className="py-3 pr-4"><span>{row.recipient_name}</span><p className="mt-1 text-xs text-muted">{row.channel === "IN_APP" ? "Portal jamaah" : `Email · ${row.recipient_email}`}{row.recipient_type === "USER" ? " · pengguna travel" : ""}</p></td>
      <td className="py-3 pr-4">{statusBadge(row)}
        {row.channel === "EMAIL" && row.attempts > 0 && row.status !== "SENT" ? <p className="mt-1 text-xs text-muted">{row.attempts}× percobaan{row.last_error ? ` · ${row.last_error}` : ""}</p> : null}
        {retry ? <p className="mt-1 text-xs text-muted">Dicoba lagi {dateTime(row.next_attempt_at!)}</p> : null}
        {row.resend_count ? <p className="mt-1 text-xs text-muted">Dikirim ulang {row.resend_count}×</p> : null}
      </td>
      <td className="py-3 text-right"><div className="flex flex-wrap justify-end gap-2">
        <Btn size="xs" variant="link" aria-expanded={Boolean(open)} onClick={onView}>{open ? "Tutup" : "Lihat isi"}</Btn>
        {canManage && row.channel === "EMAIL" && row.status !== "PENDING" ? <Btn size="xs" variant="tint" loading={busy} onClick={onResend}>Kirim ulang</Btn> : null}
      </div></td>
    </tr>
    {open ? <tr className="border-b border-border"><td colSpan={5} className="pb-4">
      <div className="border border-border bg-surface p-4"><p className="text-sm font-semibold">{open.subject}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">{open.body}</pre>
        <p className="mt-3 text-xs text-muted">Template versi {open.template_version}{open.sent_at ? ` · terkirim ${dateTime(open.sent_at)}` : ""}</p></div>
    </td></tr> : null}
  </>;
}

function TemplateEditor({canManage, onError, onMessage}: {canManage: boolean; onError: (value: string | null) => void; onMessage: (value: string | null) => void}) {
  const [templates, setTemplates] = useState<NotificationTemplate[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [draft, setDraft] = useState({subject: "", body: ""});
  const [preview, setPreview] = useState<{subject: string; body: string} | null>(null);
  const [busy, setBusy] = useState(false);
  const current = templates?.find((template) => template.key === selected) ?? null;
  const dirty = current !== null && (draft.subject !== current.subject || draft.body !== current.body);
  const editable = canManage && Boolean(current?.editable);

  const choose = useCallback((template: NotificationTemplate) => {
    setSelected(template.key); setDraft({subject: template.subject, body: template.body}); setPreview(null);
  }, []);

  useEffect(() => {
    void apiFetch<{results: NotificationTemplate[]}>("/notification-templates").then((result) => {
      if (!result.ok) {onError(problemMessage(result.error)); return;}
      setTemplates(result.data.results);
      if (result.data.results[0]) choose(result.data.results[0]);
    });
  }, [choose, onError]);

  function replace(template: NotificationTemplate) {
    setTemplates((list) => list?.map((item) => item.key === template.key ? template : item) ?? null);
    choose(template);
  }

  function insert(name: string) {
    const token = `{{ ${name} }}`;
    const area = document.getElementById("template-body") as HTMLTextAreaElement | null;
    const start = area?.selectionStart ?? draft.body.length;
    const end = area?.selectionEnd ?? draft.body.length;
    setDraft((value) => ({...value, body: value.body.slice(0, start) + token + value.body.slice(end)}));
    requestAnimationFrame(() => {area?.focus(); area?.setSelectionRange(start + token.length, start + token.length);});
  }

  async function call(path: string, method: "POST" | "PUT" | "DELETE", success?: string) {
    setBusy(true); onError(null); onMessage(null);
    const result = await apiFetch<NotificationTemplate & {subject: string; body: string}>(path, {method, body: method === "DELETE" ? undefined : JSON.stringify(draft)});
    setBusy(false);
    if (!result.ok) {onError(problemMessage(result.error)); return null;}
    if (success) onMessage(success);
    return result.data;
  }

  async function save() {
    const saved = await call(`/notification-templates/${selected}`, "PUT", "Template disimpan. Pesan berikutnya memakai teks ini.");
    if (saved) replace(saved);
  }
  async function reset() {
    if (!window.confirm("Kembalikan template ini ke teks bawaan Umrovia?")) return;
    const saved = await call(`/notification-templates/${selected}`, "DELETE", "Template dikembalikan ke teks bawaan.");
    if (saved) replace(saved);
  }
  async function showPreview() {
    const rendered = await call(`/notification-templates/${selected}/preview`, "POST");
    if (rendered) setPreview({subject: rendered.subject, body: rendered.body});
  }

  if (templates === null) return <div className="mt-6"><LoadingState /></div>;

  return <div className="workspace-columns mt-6">
    <section className="card min-w-0 p-6"><h2 className="font-semibold">Jenis pesan</h2>
      <ul className="mt-3 divide-y divide-border">{templates.map((template) => <li key={template.key}>
        <button type="button" aria-current={template.key === selected} onClick={() => {if (!dirty || window.confirm("Perubahan belum disimpan. Tinggalkan?")) choose(template);}}
          className={`flex w-full flex-wrap items-center justify-between gap-2 py-3 text-left text-sm ${template.key === selected ? "font-semibold text-primary" : ""}`}>
          <span>{template.label}<span className="block text-xs font-normal text-muted">{template.audience === "pilgrim" ? "Untuk jamaah · portal & email" : "Untuk owner travel · email"}</span></span>
          {!template.editable ? <StatusBadge>Platform</StatusBadge> : template.customized ? <StatusBadge tone="success">Disesuaikan</StatusBadge> : <StatusBadge>Bawaan</StatusBadge>}
        </button>
      </li>)}</ul>
    </section>
    {current ? <section className="card min-w-0 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">{current.label}</h2><span className="text-xs text-muted">Versi {current.version}</span></div>
      {!current.editable ? <p className="mt-2 text-sm text-muted">Pesan ini dikirim oleh platform Umrovia dan tidak dapat diubah.</p>
        : !canManage ? <p className="mt-2 text-sm text-muted">Hanya peran dengan izin kelola notifikasi yang dapat mengubah template.</p> : null}
      <div className="mt-5">
        <FormField label="Subjek" htmlFor="template-subject" maxLength={200} value={draft.subject} readOnly={!editable} onChange={(event) => {setDraft({...draft, subject: event.target.value}); setPreview(null);}} />
        <FormTextarea label="Isi pesan" htmlFor="template-body" className="textarea-tall" rows={12} maxLength={4000} value={draft.body} readOnly={!editable} onChange={(event) => {setDraft({...draft, body: event.target.value}); setPreview(null);}}
          hint="Identitas travel dan keterangan pesan otomatis ditambahkan di akhir pesan. Jangan menuliskan NIK, nomor paspor atau data sensitif lain." />
      </div>
      <div className="mt-2"><p className="text-sm font-medium">Variabel</p>
        <p className="mt-1 text-xs text-muted">{editable ? "Klik untuk menyisipkan ke isi pesan. " : ""}Tanda * wajib tetap ada.</p>
        <div className="mt-2 flex flex-wrap gap-2">{current.variables.map((variable) => (
          <button key={variable.name} type="button" disabled={!editable} title={variable.label} onClick={() => insert(variable.name)}
            className="border border-border px-2 py-1 font-mono text-xs transition-colors enabled:hover:border-primary enabled:hover:text-primary disabled:cursor-default">
            {`{{ ${variable.name} }}`}{variable.required ? " *" : ""}
          </button>
        ))}</div>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        <Btn variant="tint" disabled={busy} onClick={() => void showPreview()}>Pratinjau</Btn>
        {editable ? <Btn disabled={busy || !dirty} loading={busy && dirty} onClick={() => void save()}>Simpan</Btn> : null}
        {editable && dirty ? <Btn variant="link" onClick={() => choose(current)}>Batalkan perubahan</Btn> : null}
        {editable && current.customized && !dirty ? <Btn variant="link" disabled={busy} onClick={() => void reset()}>Kembalikan ke bawaan</Btn> : null}
      </div>
      {preview ? <div className="mt-5 border border-border bg-surface p-4"><p className="text-xs uppercase tracking-wide text-muted">Pratinjau dengan data contoh</p>
        <p className="mt-2 text-sm font-semibold">{preview.subject}</p><pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">{preview.body}</pre></div> : null}
    </section> : null}
  </div>;
}
