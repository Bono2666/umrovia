"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, BtnLink, EmptyState, ErrorState, FormField, FormSelect, FormTextarea, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type Departure, type Lead, type LeadStage, type LeadSummary, type Paginated, type TravelPackage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

const SOURCES: [string, string][] = [
  ["WHATSAPP", "WhatsApp"], ["INSTAGRAM", "Instagram"], ["FACEBOOK", "Facebook"], ["TIKTOK", "TikTok"], ["WEBSITE", "Website"],
  ["REFERRAL", "Referensi jamaah/kerabat"], ["WALK_IN", "Datang ke kantor"], ["EVENT", "Pameran/kajian"], ["OTHER", "Lainnya"],
];
const STAGES: {stage: LeadStage; label: string}[] = [
  {stage: "NEW", label: "Baru"}, {stage: "CONTACTED", label: "Sudah dihubungi"}, {stage: "QUALIFIED", label: "Berminat serius"},
  {stage: "QUOTED", label: "Penawaran dikirim"}, {stage: "WON", label: "Jadi jamaah"}, {stage: "LOST", label: "Tidak jadi"},
];
const OPEN: LeadStage[] = ["NEW", "CONTACTED", "QUALIFIED", "QUOTED"];
const TONE: Record<LeadStage, "neutral" | "success" | "warning" | "danger"> = {NEW: "neutral", CONTACTED: "neutral", QUALIFIED: "warning", QUOTED: "warning", WON: "success", LOST: "danger"};
const ACTIVITY_KINDS: [string, string][] = [["WHATSAPP", "WhatsApp"], ["CALL", "Telepon"], ["MEETING", "Pertemuan"], ["NOTE", "Catatan"]];
const EMPTY_FORM = {name: "", phone: "", email: "", city: "", source: "WHATSAPP", interest_package: "", interest_departure: "", pax: "1", owner: "", next_follow_up_at: "", notes: ""};
type Owner = {id: string; name: string};
type Duplicates = NonNullable<Lead["duplicates"]>;

const when = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"});
/** ISO → nilai input datetime-local (waktu lokal browser). */
const toLocalInput = (value: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const fromLocalInput = (value: string) => (value ? new Date(value).toISOString() : null);

export default function LeadsPage() {
  const {can, loading, canEditEnvironment, writableEnvironments} = useWorkspacePermissions();
  const canRead = can("leads.manage");
  const canConvert = can("pilgrims.write");
  const writable = writableEnvironments.length > 0;
  const [summary, setSummary] = useState<LeadSummary | null>(null);
  const [list, setList] = useState<Paginated<Lead> | null>(null);
  const [filters, setFilters] = useState({stage: "open", source: "", owner: "", follow_up: "", q: ""});
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Lead | null>(null);
  const [mode, setMode] = useState<"view" | "create" | "edit">("view");
  const [form, setForm] = useState(EMPTY_FORM);
  const [duplicates, setDuplicates] = useState<Duplicates | null>(null);
  const [packages, setPackages] = useState<TravelPackage[]>([]);
  const [departures, setDepartures] = useState<Departure[]>([]);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [activity, setActivity] = useState({kind: "WHATSAPP", body: "", next_follow_up_at: ""});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const sequence = useRef(0);

  const loadList = useCallback(() => {
    const current = ++sequence.current;
    const params = new URLSearchParams({page: String(page)});
    for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
    apiFetch<Paginated<Lead>>(`/leads?${params}`).then((result) => {
      if (current !== sequence.current) return;
      if (result.ok) setList(result.data); else setError(problemMessage(result.error));
    });
    apiFetch<LeadSummary>("/leads/summary").then((result) => {if (result.ok) setSummary(result.data);});
  }, [filters, page]);
  useEffect(() => {if (!loading && canRead) loadList();}, [loading, canRead, loadList]);
  useEffect(() => {
    if (loading || !canRead) return;
    apiFetch<{results: TravelPackage[]}>("/packages").then((r) => {if (r.ok) setPackages(r.data.results);});
    apiFetch<{results: Departure[]}>("/departures?status=OPEN").then((r) => {if (r.ok) setDepartures(r.data.results);});
    apiFetch<{results: Owner[]}>("/leads/owners").then((r) => {if (r.ok) setOwners(r.data.results);});
  }, [loading, canRead]);

  function filter(next: Partial<typeof filters>) {setPage(1); setFilters((value) => ({...value, ...next}));}
  function done(text: string, lead?: Lead) {setMessage(text); setError(null); if (lead) setSelected(lead); loadList(); focusRecord(lead?.id);}

  async function open(id: string) {
    setMode("view"); setMessage(null); setError(null); setDuplicates(null);
    const result = await apiFetch<Lead>(`/leads/${id}`);
    if (result.ok) setSelected(result.data); else setError(problemMessage(result.error));
  }

  function startCreate() {setMode("create"); setSelected(null); setForm(EMPTY_FORM); setDuplicates(null); setMessage(null); setError(null);}
  function startEdit(lead: Lead) {
    setMode("edit"); setDuplicates(null);
    setForm({name: lead.name, phone: lead.phone, email: lead.email, city: lead.city, source: lead.source, interest_package: lead.interest_package?.id ?? "",
      interest_departure: lead.interest_departure?.id ?? "", pax: String(lead.pax), owner: lead.owner?.id ?? "", next_follow_up_at: toLocalInput(lead.next_follow_up_at), notes: lead.notes});
  }

  async function save(event: React.FormEvent, allowDuplicate = false) {
    event.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const body = {...form, pax: Number(form.pax) || 1, interest_package: form.interest_package || null, interest_departure: form.interest_departure || null,
      owner: form.owner || null, next_follow_up_at: fromLocalInput(form.next_follow_up_at), ...(allowDuplicate ? {allow_duplicate: true} : {})};
    const result = mode === "edit" && selected
      ? await apiFetch<Lead>(`/leads/${selected.id}`, {method: "PATCH", body: JSON.stringify(body)})
      : await apiFetch<Lead>("/leads", {method: "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {
      const found = result.error.field_errors?.duplicates?.[0] as unknown as Duplicates | undefined;
      if (found && typeof found === "object") {setDuplicates(found); return;}
      setError(problemMessage(result.error)); return;
    }
    setMode("view"); setDuplicates(null);
    done(mode === "edit" ? "Data lead diperbarui." : `Lead ${result.data.code} tersimpan.`, result.data);
  }

  async function act(path: string, body: object, success: string) {
    if (!selected) return false;
    setBusy(true); setError(null); setMessage(null);
    const result = await apiFetch<Lead & {pilgrim?: {id: string; code: string}}>(`/leads/${selected.id}${path}`, {method: "POST", body: JSON.stringify(body)});
    setBusy(false);
    if (!result.ok) {setError(problemMessage(result.error)); return false;}
    done(success, result.data);
    return true;
  }

  async function markLost() {
    const reason = window.prompt("Alasan tidak jadi (mis. memilih travel lain, biaya, jadwal):");
    if (reason === null) return;
    if (reason.trim().length < 3) {setError("Alasan tidak jadi wajib diisi."); return;}
    await act("/stage", {stage: "LOST", lost_reason: reason.trim()}, "Lead ditandai tidak jadi.");
  }

  async function remove() {
    if (!selected || !window.confirm(`Hapus lead ${selected.name}? Riwayat aktivitasnya ikut terhapus.`)) return;
    const result = await apiFetch(`/leads/${selected.id}`, {method: "DELETE"});
    if (!result.ok) {setError(problemMessage(result.error)); return;}
    setSelected(null); done("Lead dihapus.");
  }

  if (loading) return <LoadingState />;
  if (!canRead) return <EmptyState title="Anda tidak memiliki akses Leads" description="Leads tersedia untuk peran Owner, Admin dan Sales." />;

  const editable = selected ? canEditEnvironment(selected.environment) : writable;
  return <div className="workspace-page">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <RevealText as="h1" variant="title" className="text-2xl font-bold">Leads</RevealText>
      {writable ? <Btn onClick={startCreate}>Tambah lead</Btn> : null}
    </div>
    <p className="mt-1 max-w-3xl text-sm text-muted">Kelola calon jamaah dari pertama menghubungi hingga terdaftar. Lead gratis — biaya layanan hanya untuk jamaah dengan DP terverifikasi.</p>
    {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />

    {summary ? <>
      <div className="mt-6 grid gap-3 sm:grid-cols-3 xl:grid-cols-6" aria-label="Funnel lead">
        {summary.stages.map((item) => (
          <button key={item.stage} type="button" aria-pressed={filters.stage === item.stage} onClick={() => filter({stage: filters.stage === item.stage ? "open" : item.stage, follow_up: ""})}
            className={`card p-4 text-left transition-colors hover:border-primary ${filters.stage === item.stage ? "border-primary" : ""}`}>
            <span className="text-xs text-muted">{item.label}</span>
            <span className="mt-1 block text-2xl font-semibold">{item.count}</span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted">
        <span>Konversi: <strong className="text-foreground">{summary.conversion_rate === null ? "—" : `${summary.conversion_rate.toLocaleString("id-ID")}%`}</strong> <span className="text-xs">(jadi ÷ jadi + tidak jadi)</span></span>
        <button type="button" className={`underline ${summary.follow_up_overdue ? "text-danger" : ""}`} onClick={() => filter({follow_up: "overdue", stage: ""})}>{summary.follow_up_overdue} follow-up terlambat</button>
        <button type="button" className="underline" onClick={() => filter({follow_up: "due", stage: ""})}>{summary.follow_up_today} follow-up hari ini</button>
        {summary.sources.length ? <span>Sumber teratas: {summary.sources.slice().sort((a, b) => b.count - a.count).slice(0, 3).map((s) => `${s.label} ${s.count}`).join(" · ")}</span> : null}
      </div>
    </> : null}

    <div className="workspace-columns mt-6">
      <section className="card min-w-0 p-6">
        <form className="notification-filters grid items-end gap-x-4 gap-y-8 sm:grid-cols-2" onSubmit={(event) => {event.preventDefault(); filter({q: search.trim()});}}>
          <FormField label="Cari nama, kode, telepon, kota" htmlFor="lead-q" value={search} onChange={(event) => setSearch(event.target.value)} onBlur={() => filter({q: search.trim()})} />
          <FormSelect label="Tahap" htmlFor="lead-stage" value={filters.stage} onChange={(event) => filter({stage: event.target.value})}>
            <option value="open">Masih berjalan</option><option value="">Semua</option>
            {STAGES.map((s) => <option key={s.stage} value={s.stage}>{s.label}</option>)}
          </FormSelect>
          <FormSelect label="Sumber" htmlFor="lead-source" value={filters.source} onChange={(event) => filter({source: event.target.value})}>
            <option value="">Semua</option>{SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormSelect label="Pemilik" htmlFor="lead-owner" value={filters.owner} onChange={(event) => filter({owner: event.target.value})}>
            <option value="">Semua</option><option value="me">Lead saya</option>
          </FormSelect>
        </form>
        {filters.follow_up ? <p className="mt-4 text-sm">Menampilkan follow-up {filters.follow_up === "overdue" ? "terlambat" : "jatuh tempo hari ini"}. <button type="button" className="text-primary underline" onClick={() => filter({follow_up: "", stage: "open"})}>Tampilkan semua</button></p> : null}
        {list === null ? <LoadingState /> : list.results.length === 0 ? <div className="mt-4"><EmptyState title="Belum ada lead" description="Tambahkan calon jamaah dari WhatsApp, media sosial, referensi atau kunjungan kantor." /></div> : <>
          <ul className="mt-4 divide-y divide-border">{list.results.map((lead) => <li key={lead.id} data-record={lead.id}>
            <button type="button" aria-current={selected?.id === lead.id} onClick={() => void open(lead.id)} className={`w-full py-3 text-left text-sm ${selected?.id === lead.id ? "text-primary" : ""}`}>
              <span className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{lead.name}{lead.pax > 1 ? ` · ${lead.pax} orang` : ""}</span><StatusBadge tone={TONE[lead.stage]}>{lead.stage_label}</StatusBadge></span>
              <span className="mt-1 block text-xs text-muted">{lead.code} · {lead.source_label}{lead.phone ? ` · ${lead.phone}` : ""}{lead.owner?.name ? ` · ${lead.owner.name}` : ""}</span>
              {lead.next_follow_up_at && OPEN.includes(lead.stage) ? <span className={`mt-1 block text-xs ${lead.follow_up_overdue ? "font-semibold text-danger" : "text-muted"}`}>Follow-up {when(lead.next_follow_up_at)}{lead.follow_up_overdue ? " · terlambat" : ""}</span> : null}
            </button>
          </li>)}</ul>
          {list.previous || list.next ? <div className="mt-3 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!list.previous} onClick={() => setPage((v) => v - 1)}>Sebelumnya</Btn><span>Halaman {page} · {list.count} lead</span><Btn size="xs" variant="solid" disabled={!list.next} onClick={() => setPage((v) => v + 1)}>Berikutnya</Btn></div> : null}
        </>}
      </section>

      {mode !== "view" ? <section className="card min-w-0 p-6"><h2 className="font-semibold">{mode === "edit" ? "Ubah lead" : "Lead baru"}</h2>
        <form className="mt-5" onSubmit={(event) => void save(event)}>
          <FormField label="Nama" htmlFor="lead-name" maxLength={160} value={form.name} onChange={(event) => setForm({...form, name: event.target.value})} required />
          <FormField label="Telepon / WhatsApp" htmlFor="lead-phone" inputMode="tel" value={form.phone} onChange={(event) => setForm({...form, phone: event.target.value})} hint="Format bebas, disimpan sebagai +62…" />
          <FormField label="Email (opsional)" htmlFor="lead-email" type="email" value={form.email} onChange={(event) => setForm({...form, email: event.target.value})} />
          <FormField label="Kota" htmlFor="lead-city" maxLength={100} value={form.city} onChange={(event) => setForm({...form, city: event.target.value})} />
          <FormSelect label="Sumber" htmlFor="lead-form-source" value={form.source} onChange={(event) => setForm({...form, source: event.target.value})}>
            {SOURCES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </FormSelect>
          <FormSelect label="Paket diminati" htmlFor="lead-package" value={form.interest_package} onChange={(event) => setForm({...form, interest_package: event.target.value, interest_departure: ""})}>
            <option value="">Belum menentukan</option>{packages.map((pkg) => <option key={pkg.id} value={pkg.id}>{pkg.name}</option>)}
          </FormSelect>
          <FormSelect label="Keberangkatan diminati" htmlFor="lead-departure" value={form.interest_departure} onChange={(event) => setForm({...form, interest_departure: event.target.value})}>
            <option value="">Belum menentukan</option>
            {departures.filter((dep) => !form.interest_package || dep.package_id === form.interest_package).map((dep) => <option key={dep.id} value={dep.id}>{dep.code} · {formatDate(dep.start_at)} · {dep.package_name}</option>)}
          </FormSelect>
          <FormField label="Jumlah orang" htmlFor="lead-pax" inputMode="numeric" value={form.pax} onChange={(event) => setForm({...form, pax: event.target.value.replace(/\D/g, "")})} />
          <FormSelect label="Pemilik lead" htmlFor="lead-form-owner" value={form.owner} onChange={(event) => setForm({...form, owner: event.target.value})}>
            <option value="">Saya</option>{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}
          </FormSelect>
          <FormField label="Follow-up berikutnya" htmlFor="lead-follow-up" type="datetime-local" value={form.next_follow_up_at} onChange={(event) => setForm({...form, next_follow_up_at: event.target.value})} />
          <FormTextarea label="Catatan" htmlFor="lead-notes" rows={3} maxLength={2000} value={form.notes} onChange={(event) => setForm({...form, notes: event.target.value})} hint="Jangan menuliskan NIK atau nomor paspor di catatan lead." />
          {duplicates ? <div className="mb-4 border border-warning/40 bg-warning/10 p-4 text-sm" role="alert">
            <p className="font-semibold">Telepon/email ini sudah terdaftar</p>
            <ul className="mt-2 space-y-1">
              {duplicates.leads.map((row) => <li key={row.id} data-record={row.id}><button type="button" className="text-primary underline" onClick={() => void open(row.id)}>{row.name}</button> <span className="text-xs text-muted">lead {row.code}</span></li>)}
              {duplicates.pilgrims.map((row) => <li key={row.id} data-record={row.id}>{row.name} <span className="text-xs text-muted">jamaah {row.code} — cari di menu Jamaah</span></li>)}
            </ul>
            <Btn className="mt-3" size="xs" variant="tint" disabled={busy} onClick={(event) => void save(event as unknown as React.FormEvent, true)}>Tetap simpan sebagai lead baru</Btn>
          </div> : null}
          <div className="flex flex-wrap gap-2"><Btn type="submit" loading={busy} disabled={!form.name.trim()}>Simpan</Btn><Btn variant="link" onClick={() => {setMode("view"); setDuplicates(null);}}>Batal</Btn></div>
        </form>
      </section> : selected ? <section className="card min-w-0 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="text-xs text-muted">{selected.code} · {selected.source_label} · dibuat {formatDate(selected.created_at)}</p><h2 className="mt-1 text-lg font-semibold">{selected.name}</h2></div>
          <StatusBadge tone={TONE[selected.stage]}>{selected.stage_label}</StatusBadge>
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-muted">Telepon</dt><dd>{selected.phone ? <a className="text-primary underline" href={`https://wa.me/${selected.phone.replace("+", "")}`} target="_blank" rel="noopener noreferrer">{selected.phone}</a> : "—"}</dd></div>
          <div><dt className="text-muted">Email</dt><dd className="break-all">{selected.email || "—"}</dd></div>
          <div><dt className="text-muted">Kota</dt><dd>{selected.city || "—"}</dd></div>
          <div><dt className="text-muted">Jumlah orang</dt><dd>{selected.pax}</dd></div>
          <div><dt className="text-muted">Minat</dt><dd>{selected.interest_package?.name ?? "—"}{selected.interest_departure ? ` · ${selected.interest_departure.code}` : ""}</dd></div>
          <div><dt className="text-muted">Pemilik</dt><dd>{selected.owner?.name ?? "—"}</dd></div>
          <div className="col-span-2"><dt className="text-muted">Follow-up berikutnya</dt><dd className={selected.follow_up_overdue ? "font-semibold text-danger" : ""}>{selected.next_follow_up_at ? when(selected.next_follow_up_at) : "Belum dijadwalkan"}</dd></div>
          {selected.notes ? <div className="col-span-2"><dt className="text-muted">Catatan</dt><dd className="whitespace-pre-wrap">{selected.notes}</dd></div> : null}
          {selected.lost_reason ? <div className="col-span-2"><dt className="text-muted">Alasan tidak jadi</dt><dd>{selected.lost_reason}</dd></div> : null}
        </dl>
        {selected.duplicates && (selected.duplicates.leads.length || selected.duplicates.pilgrims.length) ? <p className="mt-3 border border-warning/40 bg-warning/10 p-3 text-xs">Kemungkinan duplikat: {[...selected.duplicates.leads.map((r) => `lead ${r.code} (${r.name})`), ...selected.duplicates.pilgrims.map((r) => `jamaah ${r.code} (${r.name})`)].join(", ")}</p> : null}

        {selected.converted_pilgrim ? <div className="mt-5 border border-success/30 bg-success/10 p-4 text-sm">
          <p>Sudah menjadi jamaah <strong>{selected.converted_pilgrim.name}</strong> ({selected.converted_pilgrim.code}).</p>
          {can("bookings.create") ? <BtnLink className="mt-3" size="xs" href={`/dashboard/booking?pilgrim=${selected.converted_pilgrim.id}${selected.interest_departure ? `&departure=${selected.interest_departure.id}` : ""}`}>Buat booking</BtnLink> : null}
        </div> : editable ? <>
          <div className="mt-5"><p className="text-sm font-medium">Tahap</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {OPEN.map((stage) => <Btn key={stage} size="xs" variant={selected.stage === stage ? "solid" : "tint"} disabled={busy || selected.stage === stage}
                onClick={() => void act("/stage", {stage}, `Tahap: ${STAGES.find((s) => s.stage === stage)?.label}.`)}>{STAGES.find((s) => s.stage === stage)?.label}</Btn>)}
              {selected.stage !== "LOST" ? <Btn size="xs" variant="danger" disabled={busy} onClick={() => void markLost()}>Tidak jadi</Btn> : null}
            </div>
            {canConvert && selected.stage !== "LOST" ? <Btn className="mt-3" disabled={busy} onClick={() => void act("/convert", {}, "Lead menjadi data jamaah. Lanjutkan dengan membuat booking.")}>Jadikan jamaah</Btn> : null}
          </div>
          <form className="mt-6 border-t border-border pt-5" onSubmit={async (event) => {
            event.preventDefault();
            if (await act("/activities", {kind: activity.kind, body: activity.body, next_follow_up_at: fromLocalInput(activity.next_follow_up_at)}, "Aktivitas tercatat.")) setActivity({kind: activity.kind, body: "", next_follow_up_at: ""});
          }}>
            <p className="text-sm font-medium">Catat aktivitas</p>
            <div className="notification-filters mt-3 grid items-end gap-x-4 gap-y-8 sm:grid-cols-2">
              <FormSelect label="Jenis" htmlFor="activity-kind" value={activity.kind} onChange={(event) => setActivity({...activity, kind: event.target.value})}>
                {ACTIVITY_KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </FormSelect>
              <FormField label="Follow-up berikutnya (opsional)" htmlFor="activity-follow-up" type="datetime-local" value={activity.next_follow_up_at} onChange={(event) => setActivity({...activity, next_follow_up_at: event.target.value})} />
            </div>
            <FormTextarea label="Hasil/catatan" htmlFor="activity-body" rows={3} maxLength={2000} value={activity.body} onChange={(event) => setActivity({...activity, body: event.target.value})} />
            <Btn type="submit" size="xs" loading={busy} disabled={!activity.body.trim() && !activity.next_follow_up_at}>Simpan aktivitas</Btn>
          </form>
        </> : <p className="mt-5 text-sm text-muted">Workspace ini hanya-baca.</p>}

        <div className="mt-6 border-t border-border pt-5"><p className="text-sm font-medium">Riwayat</p>
          <ol className="mt-3 space-y-3">{(selected.activities ?? []).map((item) => <li key={item.id} data-record={item.id} className="text-sm">
            <p className="text-xs text-muted"><span className="font-semibold text-foreground">{item.kind_label}</span> · {item.actor ?? "sistem"} · {when(item.created_at)}</p>
            {item.body ? <p className="mt-1 whitespace-pre-wrap">{item.body}</p> : null}
          </li>)}</ol>
        </div>
        {editable && !selected.converted_pilgrim ? <div className="mt-6 flex flex-wrap gap-3 border-t border-border pt-5">
          <Btn size="xs" variant="tint" onClick={() => startEdit(selected)}>Ubah data</Btn>
          {selected.deletable ? <Btn size="xs" variant="link" onClick={() => void remove()}>Hapus lead</Btn> : null}
        </div> : null}
      </section> : <section className="card min-w-0 p-6 text-sm text-muted">Pilih lead untuk melihat detail, atau tambahkan lead baru.</section>}
    </div>
  </div>;
}
