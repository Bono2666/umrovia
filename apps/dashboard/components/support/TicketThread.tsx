"use client";

import { useState } from "react";
import { Btn, FormCheckbox, FormTextarea, StatusBadge } from "@/components/workspace/ui";
import type { SupportTicket } from "@/lib/api";

export const TICKET_TONE: Record<string, "neutral" | "success" | "warning" | "danger"> = {
  OPEN: "warning", IN_PROGRESS: "neutral", WAITING_TENANT: "neutral", RESOLVED: "success",
};
const when = (value: string) => new Date(value).toLocaleString("id-ID", {dateStyle: "medium", timeStyle: "short"});

/** Percakapan tiket (S18): dipakai Bantuan travel dan konsol Support platform. */
export function TicketThread({ticket, platform = false, busy, onReply, actions}: {
  ticket: SupportTicket; platform?: boolean; busy: boolean;
  onReply: (body: string, internal: boolean) => Promise<boolean>; actions?: React.ReactNode;
}) {
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);
  return <section data-detail className="card min-w-0 p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs text-muted">{ticket.number} · {ticket.category_label}{platform && ticket.tenant ? ` · ${ticket.tenant.display_name}` : ""}</p>
        <h2 className="mt-1 font-semibold">{ticket.subject}</h2>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {ticket.priority === "HIGH" ? <StatusBadge tone="danger">Prioritas tinggi</StatusBadge> : null}
        <StatusBadge tone={TICKET_TONE[ticket.status] ?? "neutral"}>{ticket.status_label}</StatusBadge>
      </div>
    </div>
    {actions ? <div className="mt-4 flex flex-wrap gap-2">{actions}</div> : null}
    <ol className="mt-5 space-y-3">
      {(ticket.messages ?? []).map((message) => (
        <li key={message.id} className={`border p-4 text-sm ${message.internal ? "border-warning/40 bg-warning/10" : message.from_platform ? "border-primary/30 bg-primary/5" : "border-border"}`}>
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="font-semibold text-foreground">{message.author}</span>
            {message.internal ? <StatusBadge tone="warning">Catatan internal</StatusBadge> : null}
            <span>{when(message.created_at)}</span>
          </p>
          <p className="mt-2 whitespace-pre-wrap break-words">{message.body}</p>
        </li>
      ))}
    </ol>
    <form className="mt-5" onSubmit={async (event) => {
      event.preventDefault();
      if (await onReply(body, internal)) {setBody(""); setInternal(false);}
    }}>
      <FormTextarea label={internal ? "Catatan internal (tidak terlihat travel)" : "Tulis balasan"} htmlFor={`reply-${ticket.id}`} rows={4} maxLength={5000} value={body} onChange={(event) => setBody(event.target.value)}
        hint={platform ? "Balasan dikirim ke travel dan diberitahukan lewat email pembuka tiket." : "Jangan cantumkan NIK, nomor paspor, password atau kode OTP."} />
      <div className="flex flex-wrap items-center gap-4">
        <Btn type="submit" loading={busy} disabled={body.trim().length < 5}>{internal ? "Simpan catatan" : "Kirim balasan"}</Btn>
        {platform ? <FormCheckbox id={`internal-${ticket.id}`} label="Catatan internal" checked={internal} onChange={setInternal} /> : null}
      </div>
    </form>
  </section>;
}
