"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Btn, FormField, FormSelect, StatusBadge } from "@/components/workspace/ui";
import { apiFetch, problemMessage, type ChangeRequest, type FamilyGroup, type Pilgrim, type PilgrimHistory } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";

const RELATIONS = ["Kepala keluarga", "Suami", "Istri", "Anak", "Orang tua", "Saudara", "Mahram", "Lainnya"];
const BOOKING_LABEL: Record<string, string> = {DRAFT: "Draf", RESERVED: "Direservasi", CONFIRMED: "Terkonfirmasi", DOCUMENT_PROCESS: "Proses dokumen", READY_TO_DEPART: "Siap berangkat", DEPARTED: "Berangkat", COMPLETED: "Selesai", CANCELED: "Dibatalkan", EXPIRED: "Kedaluwarsa"};

/** MOD-04/POR-06 pada detail jamaah: keluarga, riwayat perjalanan, dan verifikasi koreksi identitas dari portal. */
export function PilgrimExtras({pilgrim, canWrite, onChanged, notify}: {pilgrim: Pilgrim; canWrite: boolean; onChanged: () => void; notify: (message: string | null, error?: string | null) => void}) {
  const [history, setHistory] = useState<PilgrimHistory | null>(null);
  const [families, setFamilies] = useState<FamilyGroup[]>([]);
  const [familyId, setFamilyId] = useState("");
  const [relation, setRelation] = useState("Anak");
  const [newFamily, setNewFamily] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    void apiFetch<PilgrimHistory>(`/pilgrims/${pilgrim.id}/history`).then((r) => {if (r.ok) setHistory(r.data);});
  }, [pilgrim.id]);
  useEffect(() => {
    load();
    if (canWrite) void apiFetch<{results: FamilyGroup[]}>("/families").then((r) => {if (r.ok) setFamilies(r.data.results);});
  }, [load, canWrite]);

  async function join(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); notify(null, null);
    let target = familyId;
    if (!target && newFamily.trim()) {
      const created = await apiFetch<FamilyGroup>("/families", {method: "POST", body: JSON.stringify({name: newFamily.trim()})});
      if (!created.ok) {setBusy(false); notify(null, problemMessage(created.error)); return;}
      target = created.data.id;
    }
    const result = await apiFetch<FamilyGroup>(`/families/${target}/members`, {method: "POST", body: JSON.stringify({pilgrim: pilgrim.id, relation})});
    setBusy(false);
    if (!result.ok) {notify(null, problemMessage(result.error)); return;}
    notify(`${pilgrim.name} masuk ${result.data.name} sebagai ${relation.toLowerCase()}.`); setNewFamily(""); load(); onChanged();
  }

  async function leave() {
    if (!history?.family) return;
    setBusy(true);
    const result = await apiFetch<FamilyGroup>(`/families/${history.family.id}/members?pilgrim=${pilgrim.id}`, {method: "DELETE"});
    setBusy(false);
    if (!result.ok) {notify(null, problemMessage(result.error)); return;}
    notify(`${pilgrim.name} dikeluarkan dari ${result.data.name}.`); load(); onChanged();
  }

  async function decide(request: ChangeRequest, approve: boolean) {
    let note = "";
    if (!approve) {
      const input = window.prompt("Alasan menolak koreksi (terlihat oleh jamaah):");
      if (input === null) return;
      note = input;
    } else if (!window.confirm(`Terapkan koreksi berikut ke data jamaah?\n${request.changes.map((c) => `${c.label}: ${c.value}`).join("\n")}\n\nPastikan sudah dicocokkan dengan dokumen asli.`)) return;
    setBusy(true);
    const result = await apiFetch<ChangeRequest>(`/pilgrim-change-requests/${request.id}/${approve ? "approve" : "reject"}`, {method: "POST", body: JSON.stringify({note})});
    setBusy(false);
    if (!result.ok) {notify(null, problemMessage(result.error)); return;}
    notify(approve ? "Koreksi identitas diterapkan." : "Koreksi identitas ditolak."); load(); onChanged();
  }

  if (!history) return null;
  const pending = history.change_requests.filter((r) => r.status === "PENDING");
  return <>
    {pending.length ? <>
      <h4 className="mt-6 text-sm font-semibold">Permintaan koreksi dari portal</h4>
      {pending.map((r) => <div key={r.id} className="mt-2 border border-warning/40 bg-warning/5 p-3 text-sm">
        <p>{r.changes.map((c) => `${c.label}: ${c.value}`).join(" · ")}</p>
        <p className="mt-1 text-xs text-muted">Alasan: {r.reason} · {formatDate(r.created_at)}</p>
        {canWrite ? <div className="mt-2 flex gap-2"><Btn size="xs" disabled={busy} onClick={() => void decide(r, true)}>Setujui & terapkan</Btn><Btn size="xs" variant="danger" disabled={busy} onClick={() => void decide(r, false)}>Tolak</Btn></div> : null}
      </div>)}
    </> : null}

    <h4 className="mt-6 text-sm font-semibold">Keluarga</h4>
    {history.family ? <div className="mt-2 text-sm">
      <p className="font-medium">{history.family.name}</p>
      <ul className="mt-1 space-y-0.5 text-xs text-muted">{history.family.members.map((m) => <li key={m.id}>{m.name} · {m.relation || "-"}{m.id === pilgrim.id ? " (jamaah ini)" : ""}</li>)}</ul>
      {canWrite ? <Btn size="xs" variant="link" disabled={busy} onClick={() => void leave()}>Keluarkan dari keluarga</Btn> : null}
    </div> : <p className="mt-2 text-sm text-muted">Belum masuk kelompok keluarga.</p>}
    {canWrite && !history.family ? <form className="mt-2" onSubmit={join}>
      <FormSelect label="Keluarga" htmlFor={`family-${pilgrim.id}`} value={familyId} onChange={(e) => setFamilyId(e.target.value)}>
        <option value="">+ Keluarga baru</option>{families.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.members.length} anggota)</option>)}
      </FormSelect>
      {!familyId ? <FormField label="Nama keluarga baru" htmlFor={`family-new-${pilgrim.id}`} value={newFamily} maxLength={160} onChange={(e) => setNewFamily(e.target.value)} placeholder="Keluarga Bp. Ahmad" /> : null}
      <FormSelect label="Hubungan" htmlFor={`family-rel-${pilgrim.id}`} value={relation} onChange={(e) => setRelation(e.target.value)}>{RELATIONS.map((r) => <option key={r}>{r}</option>)}</FormSelect>
      <Btn size="xs" type="submit" disabled={busy || (!familyId && !newFamily.trim())}>Simpan keluarga</Btn>
    </form> : null}

    <h4 className="mt-6 text-sm font-semibold">Riwayat perjalanan <span className="font-normal text-muted">· {history.completed_trips} selesai</span></h4>
    {history.trips.length === 0 ? <p className="mt-2 text-sm text-muted">Belum pernah didaftarkan ke keberangkatan.</p> :
      <ul className="mt-2 divide-y divide-border/60 text-sm">{history.trips.map((t) => <li key={t.booking.id} className="py-2">
        <p className="flex flex-wrap items-center gap-2"><Link className="font-medium text-primary hover:underline" href={`/dashboard/booking?q=${t.booking.code}`}>{t.booking.code}</Link><StatusBadge tone={t.booking.status === "CANCELED" ? "danger" : t.booking.status === "COMPLETED" ? "neutral" : "success"}>{BOOKING_LABEL[t.booking.status] ?? t.booking.status}</StatusBadge></p>
        <p className="text-xs text-muted">{t.package} · {t.departure.code} · {formatDate(t.departure.start_at)}{t.price_idr !== null ? ` · ${formatIdr(t.price_idr)} (dibayar ${formatIdr(t.paid_idr)})` : ""}</p>
      </li>)}</ul>}
  </>;
}
