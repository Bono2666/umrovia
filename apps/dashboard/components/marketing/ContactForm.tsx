"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { apiFetch, problemMessage } from "@/lib/api";
import { Btn, FormCheckbox, FormField, FormSelect, FormTextarea } from "@/components/workspace/ui";

export function ContactForm() {
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [reference, setReference] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState<Record<string, string[]>>({});

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError(""); setFields({});
    const result = await apiFetch<{ reference: string }>("/contact", {
      method: "POST", body: JSON.stringify({ ...values, consent }),
    });
    setBusy(false);
    if (result.ok) setReference(result.data.reference);
    else { setError(problemMessage(result.error)); setFields(result.error.field_errors ?? {}); }
  };

  if (reference) return <div role="status" className="py-12">
    <p className="text--h2">Terima kasih.<br /><span className="text-muted">Pesan Anda tercatat.</span></p>
    <p className="mt-8 text--t3-md text-muted">Balasan dapat ditujukan ke email yang Anda cantumkan. Simpan nomor referensi berikut untuk komunikasi selanjutnya.</p>
    <p className="mt-5 break-all font-mono text-sm">{reference}</p>
    <button type="button" className="mt-10 text-primary hover:text-primary-hover" onClick={() => { setReference(""); setConsent(false); }}>Tulis pesan lain</button>
  </div>;

  return <form onSubmit={submit} className="contact-marketing-form">
    <div className="grid gap-x-8 min-[980px]:grid-cols-2">
      <FormField name="name" htmlFor="contact-name" label="Nama Anda" placeholder="Nama lengkap" autoComplete="name" required maxLength={150} error={fields.name?.[0]} />
      <FormField name="company" htmlFor="contact-company" label="Nama travel / perusahaan" placeholder="Nama perusahaan (opsional)" autoComplete="organization" maxLength={200} error={fields.company?.[0]} />
      <FormField name="email" htmlFor="contact-email" label="Email" placeholder="nama@perusahaan.com" type="email" autoComplete="email" required maxLength={254} error={fields.email?.[0]} />
      <FormField name="phone" htmlFor="contact-phone" label="Nomor telepon" placeholder="Nomor telepon (opsional)" type="tel" autoComplete="tel" maxLength={32} error={fields.phone?.[0]} />
    </div>
    <FormSelect name="topic" htmlFor="contact-topic" label="Saya ingin membahas" defaultValue="product" required error={fields.topic?.[0]}>
      <option value="product">Produk & demo</option><option value="pricing">Harga & pembayaran</option><option value="support">Bantuan penggunaan</option><option value="privacy">Privasi & data pribadi</option>
    </FormSelect>
    <FormTextarea name="message" htmlFor="contact-message" label="Pesan Anda" placeholder="Ceritakan kebutuhan atau pertanyaan Anda" required minLength={20} maxLength={4000} error={fields.message?.[0]} />
    <p className="-mt-6 mb-8 text--t3-sm text-muted">20–4.000 karakter. Cukup ceritakan kebutuhan Anda; hindari mencantumkan paspor, password, atau data jamaah.</p>
    <div className="hidden" aria-hidden="true"><label htmlFor="contact-website">Website</label><input name="website" id="contact-website" tabIndex={-1} autoComplete="off" /></div>
    <FormCheckbox id="contact-consent" checked={consent} onChange={setConsent} required label={<>Saya mengizinkan Umrovia memproses data dalam formulir ini untuk menanggapi pesan saya. Baca <Link href="/kebijakan-privasi" className="text-primary hover:text-primary-hover">Kebijakan Privasi</Link>.</>} />
    {error && <p role="alert" className="mt-6 text-sm text-danger">{error}</p>}
    <div className="mt-10 flex justify-end"><Btn type="submit" size="circle-xl" loading={busy} disabled={!consent}>Kirim pesan</Btn></div>
  </form>;
}
