"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, FormCheckbox, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage, type ChargePreview, type Paginated, type TravelInvoice, type TravelPayment } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";
import { RevealText } from "@/components/marketing/RevealText";
import { FloatingNotice, focusRecord } from "@/components/workspace/FloatingNotice";

type Account = {id:string;bank_name:string;account_name:string;account_masked:string};
const STATUS: Record<string,string> = {DRAFT:"Draf",SUBMITTED:"Menunggu verifikasi",VERIFIED:"Terverifikasi",REJECTED:"Ditolak",REVERSED:"Direversal"};

function previewText(preview:ChargePreview){
  if(!preview.charges_applicable)return "";
  const units=preview.participants.filter((row)=>row.will_attempt_charge).length;
  const charged=preview.participants.filter((row)=>row.already_charged).length;
  let text=`\n\nBiaya layanan Umrovia: ${units} jamaah × ${formatIdr(preview.unit_fee_idr??0)} = ${formatIdr(preview.total_fee_idr??0)}.`;
  if(charged)text+=` ${charged} jamaah sudah pernah dikenai biaya dan tidak ditagih lagi.`;
  if(preview.wallet_balance_idr!==undefined){
    text+=`\nSaldo wallet ${formatIdr(preview.wallet_balance_idr)}`;
    if(preview.pending_queue_idr)text+=` (antrean tertunda ${formatIdr(preview.pending_queue_idr)})`;
    text+=preview.sufficient?` → sisa ${formatIdr(preview.balance_after_idr??0)}.`:". Saldo belum cukup: DP tetap terverifikasi, biaya menunggu top-up.";
  }
  return text;
}

function chargeSummary(payment:TravelPayment){
  if(payment.status!=="VERIFIED"||payment.environment!=="production")return null;
  const ids=new Set(payment.allocations.map((row)=>row.booking_participant_id));
  const rows=payment.participants.filter((row)=>ids.has(row.id));
  const pending=rows.filter((row)=>row.saas_charge_status?.startsWith("PENDING")).length;
  const posted=rows.filter((row)=>row.saas_charge_status==="POSTED").length;
  if(pending)return {tone:"text-warning",text:`DP terverifikasi. ${pending} jamaah menunggu saldo SaaS Wallet sebelum terkonfirmasi.`};
  if(posted)return {tone:"text-muted",text:`Biaya layanan tercatat untuk ${posted} jamaah.`};
  return null;
}

export default function PaymentsPage() {
  const {can, loading} = useWorkspacePermissions();
  const [payments,setPayments] = useState<TravelPayment[] | null>(null);
  const [invoices,setInvoices] = useState<TravelInvoice[]>([]);
  const [accounts,setAccounts] = useState<Account[]>([]);
  const [invoiceId,setInvoiceId] = useState("");
  const [amount,setAmount] = useState("");
  const [kind,setKind] = useState("DP");
  const [method,setMethod] = useState("TRANSFER");
  const [receivedAt,setReceivedAt] = useState("");
  const [accountId,setAccountId] = useState("");
  const [reference,setReference] = useState("");
  const [evidence,setEvidence] = useState("");
  const [allocations,setAllocations] = useState<Record<string,string>>({});
  const [simulate,setSimulate] = useState(false);
  const [error,setError] = useState<string|null>(null);
  const [fieldErrors,setFieldErrors] = useState<Record<string,string>>({});
  const [message,setMessage] = useState<string|null>(null);
  const [busy,setBusy] = useState(false);
  const keys = useRef(new Map<string,{signature:string;key:string}>());
  const canCreate=can("payments.create");
  const [page,setPage] = useState(1);
  const [pageInfo,setPageInfo] = useState<{count:number;next:string|null;previous:string|null}>({count:0,next:null,previous:null});
  // Paginasi server (S19): pembayaran disaring per invoice di server, 50 per halaman.
  const loadPayments = useCallback(() => {
    const params=new URLSearchParams({page:String(page)});
    if(invoiceId)params.set("invoice",invoiceId);
    apiFetch<Paginated<TravelPayment>>(`/payments?${params}`).then((result)=>{if(result.ok){setPayments(result.data.results);setPageInfo({count:result.data.count,next:result.data.next,previous:result.data.previous});}else setError(problemMessage(result.error));});
  },[page,invoiceId]);
  const [invoiceSearch,setInvoiceSearch] = useState("");
  // Pilihan invoice: hanya yang masih terbuka (dicari di server), ditambah invoice dari tautan ?invoice= (walau sudah lunas).
  const loadInvoices = useCallback(() => {
    const wanted=new URLSearchParams(window.location.search).get("invoice")||"";
    apiFetch<{results:TravelInvoice[]}>(`/invoices?open=1${invoiceSearch.trim()?`&q=${encodeURIComponent(invoiceSearch.trim())}`:""}`).then(async (result)=>{
      if(!result.ok)return;
      let rows=result.data.results;
      if(wanted&&!rows.some((row)=>row.id===wanted)){const one=await apiFetch<TravelInvoice>(`/invoices/${wanted}`);if(one.ok)rows=[one.data,...rows];}
      setInvoices(rows);setInvoiceId((prev)=>prev||wanted);
    });
  },[invoiceSearch]);
  const loadOptions = useCallback(() => {
    if(canCreate)apiFetch<{bank_accounts:Account[]}>("/payments/options").then((result)=>{if(result.ok)setAccounts(result.data.bank_accounts);});
  },[canCreate]);
  // Setelah aksi (catat/verifikasi/tolak): muat ulang semuanya.
  const load = useCallback(() => {loadInvoices();loadOptions();loadPayments();},[loadInvoices,loadOptions,loadPayments]);
  useEffect(()=>{if(!loading)loadInvoices();},[loading,loadInvoices]);
  useEffect(()=>{if(!loading)loadOptions();},[loading,loadOptions]);
  useEffect(()=>{if(!loading)loadPayments();},[loading,loadPayments]);
  const invoice=invoices.find((row)=>row.id===invoiceId);
  const visiblePayments=payments;
  const totalAllocated=Object.values(allocations).reduce((sum,value)=>sum+(Number(value)||0),0);

  function operationKey(scope:string,body:unknown){
    const signature=JSON.stringify(body);const existing=keys.current.get(scope);
    if(existing?.signature===signature)return existing.key;
    const key=crypto.randomUUID();keys.current.set(scope,{signature,key});return key;
  }

  async function create(event:React.FormEvent){
    event.preventDefault();setError(null);setMessage(null);setFieldErrors({});
    if(!invoice||!receivedAt)return;
    const entries=Object.entries(allocations).filter(([,value])=>Number(value)>0).map(([booking_participant_id,value])=>({booking_participant_id,amount_idr:Number(value)}));
    const body={invoice:invoice.id,amount_idr:Number(amount),kind,method,received_at:new Date(receivedAt).toISOString(),bank_account:accountId||null,reference,evidence_ref:evidence,allocations:entries,simulate:invoice.environment==="demo"&&simulate};
    setBusy(true);
    const result=await apiFetch<TravelPayment>("/payments",{method:"POST",headers:{"Idempotency-Key":operationKey("record",body)},body:JSON.stringify(body)});
    setBusy(false);
    // Error per field (mis. referensi ganda) ditandai di field-nya; FloatingNotice danger menggulir ke sana.
    if(!result.ok){setFieldErrors(formErrors(result.error));setError(problemMessage(result.error));return;}
    focusRecord(result.data.id);
    setMessage("Pembayaran tercatat dan diajukan untuk verifikasi.");
    resetForm();load();
  }

  // Form kembali kosong setelah dicatat agar pembayaran yang sama tidak terajukan dua kali.
  function resetForm(){
    keys.current.delete("record");setFieldErrors({});
    setInvoiceSearch("");setInvoiceId("");setAmount("");setKind("DP");setMethod("TRANSFER");setReceivedAt("");
    setAccountId("");setReference("");setEvidence("");setAllocations({});setSimulate(false);
    // ?invoice= dari tautan "Lihat pembayaran" akan memilih ulang invoice saat daftar dimuat ulang.
    const url=new URL(window.location.href);
    if(url.searchParams.has("invoice")){url.searchParams.delete("invoice");window.history.replaceState(null,"",url);}
  }

  async function act(payment:TravelPayment,action:string){
    if(action==="evidence"){
      const evidenceRef=window.prompt("Referensi bukti penerimaan:",payment.evidence_ref);
      if(evidenceRef===null)return;
      setBusy(true);setError(null);
      const result=await apiFetch<TravelPayment>(`/payments/${payment.id}`,{method:"PATCH",body:JSON.stringify({evidence_ref:evidenceRef})});
      setBusy(false);
      if(!result.ok){setError(problemMessage(result.error));return;}
      focusRecord(payment.id);
      setMessage("Referensi bukti tersimpan.");load();return;
    }
    const body:Record<string,string>={};
    if(action==="reject"||action==="reverse"){
      const reason=window.prompt(action==="reverse"?"Alasan reversal (wajib). Persetujuan petugas berbeda dari verifikator diperlukan:":"Alasan penolakan (wajib):");
      if(reason===null)return;if(!reason.trim()){setError("Alasan wajib diisi.");return;}body.reason=reason.trim();
    }else if(action==="verify"){
      const preview=await apiFetch<ChargePreview>(`/payments/${payment.id}/charge-preview`);
      if(!window.confirm(`Dana ${formatIdr(payment.amount_idr)} sudah diterima dan cocok dengan bukti?${preview.ok?previewText(preview.data):""}`))return;
    }
    setBusy(true);setError(null);setMessage(null);
    const result=await apiFetch<TravelPayment>(`/payments/${payment.id}/${action}`,{method:"POST",headers:{"Idempotency-Key":operationKey(`${payment.id}:${action}`,body)},body:JSON.stringify(body)});
    setBusy(false);
    if(!result.ok){setError(problemMessage(result.error));return;}
    const pending=action==="verify"&&result.data.participants.some((row)=>row.saas_charge_status?.startsWith("PENDING"));
    focusRecord(result.data.id);
    setMessage(action==="verify"?(pending?"Pembayaran terverifikasi dan kuitansi diterbitkan. Biaya layanan menunggu saldo SaaS Wallet.":"Pembayaran terverifikasi dan kuitansi diterbitkan."):action==="reverse"?"Reversal tercatat; sisa tagihan diperbarui.":action==="reject"?"Pembayaran ditolak dengan alasan.":"Pembayaran diajukan.");load();
  }

  if(loading)return <LoadingState/>;
  if(!can("payments.read"))return <EmptyState title="Anda tidak memiliki akses pembayaran"/>;
  return <div className="workspace-page">
    <RevealText as="h1" variant="title" className="text-2xl font-bold">Pembayaran</RevealText>
    <p className="mt-1 text-sm text-muted">Catat DP, cicilan, atau pelunasan dan alokasikan nominal ke masing-masing jamaah. Kuitansi diterbitkan setelah dana diverifikasi.</p>
    <FloatingNotice message={message} onDismiss={() => setMessage(null)} />
    <FloatingNotice tone="danger" message={error} onDismiss={() => setError(null)} />
    <div className="workspace-columns mt-6">
      <section className="card p-6"><h2 className="font-semibold">Riwayat pembayaran</h2>
        {visiblePayments===null?<LoadingState/>:visiblePayments.length===0?<div className="mt-4"><EmptyState title="Belum ada pembayaran"/></div>:<ul className="mt-4 divide-y divide-border">{visiblePayments.map((payment)=><li key={payment.id} data-record={payment.id} className="py-4 text-sm">
          <div className="flex flex-wrap items-center gap-2"><strong>{formatIdr(payment.amount_idr)}</strong><StatusBadge tone={payment.status==="VERIFIED"?"success":["REJECTED","REVERSED"].includes(payment.status)?"danger":"warning"}>{STATUS[payment.status]}</StatusBadge>{payment.simulated?<StatusBadge tone="warning">DEMO</StatusBadge>:null}</div>
          <p className="mt-1 text-xs text-muted">{payment.booking_code} · {payment.invoice_number} · {payment.kind} · {formatDate(payment.received_at)}</p>
          <p className="mt-1 text-xs text-muted">Referensi: {payment.reference||payment.evidence_ref}</p>
          <ul className="mt-2 space-y-1">{payment.allocations.map((allocation)=><li key={allocation.booking_participant_id} className="flex justify-between gap-3"><span>{allocation.pilgrim_name}</span><span>{formatIdr(allocation.amount_idr)}</span></li>)}</ul>
          {payment.reason?<p className="mt-2 text-danger">{payment.reason}</p>:null}
          {(()=>{const summary=chargeSummary(payment);return summary?<p className={`mt-2 ${summary.tone}`}>{summary.text}</p>:null;})()}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {payment.status==="DRAFT"&&canCreate?<Btn variant="tint" size="xs" disabled={busy} onClick={()=>act(payment,"submit")}>Ajukan</Btn>:null}
            {payment.status==="DRAFT"&&canCreate?<Btn variant="tint" size="xs" disabled={busy} onClick={()=>act(payment,"evidence")}>Lengkapi bukti</Btn>:null}
            {payment.status==="SUBMITTED"&&can("payments.verify")?<Btn size="xs" disabled={busy} onClick={()=>act(payment,"verify")}>Verifikasi dana</Btn>:null}
            {["DRAFT","SUBMITTED"].includes(payment.status)&&can("payments.verify")?<Btn variant="danger" size="xs" disabled={busy} onClick={()=>act(payment,"reject")}>Tolak</Btn>:null}
            {payment.status==="VERIFIED"&&can("payments.reverse")?<Btn variant="danger" size="xs" disabled={busy} onClick={()=>act(payment,"reverse")}>Reversal</Btn>:null}
            {payment.receipt&&can("receipts.read")?<a className="text-primary underline" href={`${API_BASE}/api/v1/receipts/${payment.receipt.id}/pdf`}>{payment.receipt.receipt_no} · PDF{payment.receipt.status==="REVERSED"?" (direversal)":""}</a>:null}
          </div>
        </li>)}</ul>}
        {pageInfo.previous||pageInfo.next?<div className="mt-4 flex flex-wrap items-center gap-3 text-sm"><Btn size="xs" variant="solid" disabled={!pageInfo.previous} onClick={()=>setPage((value)=>value-1)}>Sebelumnya</Btn><span>Halaman {page} · {pageInfo.count} pembayaran</span><Btn size="xs" variant="solid" disabled={!pageInfo.next} onClick={()=>setPage((value)=>value+1)}>Berikutnya</Btn></div>:null}
      </section>
      {canCreate?<section className="card p-6"><h2 className="font-semibold">Catat pembayaran</h2>
        <form onSubmit={create} className="mt-6">
          <FormField label="Cari invoice (nomor, kode booking, pelanggan)" htmlFor="payment-invoice-search" value={invoiceSearch} onChange={(event)=>setInvoiceSearch(event.target.value)} hint="Daftar menampilkan hingga 200 invoice terbuka terbaru."/>
          <FormSelect label="Invoice" htmlFor="payment-invoice" value={invoiceId} required onChange={(event)=>{setInvoiceId(event.target.value);setPage(1);setAllocations({});setSimulate(false);}}><option value="">— pilih invoice —</option>{invoices.map((row)=><option key={row.id} value={row.id} disabled={["VOIDED","PAID"].includes(row.status)}>{row.invoice_number} · sisa {formatIdr(row.balance_idr)}</option>)}</FormSelect>
          <FormField label="Nominal diterima (Rp)" htmlFor="payment-amount" inputMode="numeric" value={amount} required error={fieldErrors.amount_idr} onChange={(event)=>setAmount(event.target.value)}/>
          <FormSelect label="Jenis pembayaran" htmlFor="payment-kind" value={kind} onChange={(event)=>setKind(event.target.value)}><option value="DP">DP</option><option value="INSTALLMENT">Cicilan</option><option value="BALANCE">Pelunasan</option></FormSelect>
          <FormField label="Tanggal penerimaan" htmlFor="payment-received" type="datetime-local" value={receivedAt} required error={fieldErrors.received_at} onChange={(event)=>setReceivedAt(event.target.value)}/>
          <FormSelect label="Metode" htmlFor="payment-method" value={method} onChange={(event)=>setMethod(event.target.value)}><option value="TRANSFER">Transfer bank</option><option value="CASH">Tunai</option></FormSelect>
          {method==="TRANSFER"?<FormSelect label="Rekening tujuan" htmlFor="payment-account" value={accountId} required error={fieldErrors.bank_account} onChange={(event)=>setAccountId(event.target.value)}><option value="">— pilih rekening —</option>{accounts.map((account)=><option key={account.id} value={account.id}>{account.bank_name} · {account.account_name} · {account.account_masked}</option>)}</FormSelect>:null}
          <FormField label="Referensi penerimaan" htmlFor="payment-reference" value={reference} error={fieldErrors.reference} onChange={(event)=>{setReference(event.target.value);setFieldErrors((prev)=>{const next={...prev};delete next.reference;return next;});}} hint="Nomor transfer atau referensi penerimaan tunai."/>
          <FormField label="Referensi bukti" htmlFor="payment-evidence" value={evidence} error={fieldErrors.evidence_ref} onChange={(event)=>setEvidence(event.target.value)} hint="Salah satu referensi penerimaan atau bukti wajib diisi."/>
          {invoice?<fieldset className="my-6 border-t border-border pt-6"><legend className="text-sm font-semibold">Alokasi per jamaah</legend>{invoice.lines.map((line)=><FormField key={line.participant_id} label={`Alokasi ${line.pilgrim_name}`} htmlFor={`allocation-${line.participant_id}`} inputMode="numeric" value={allocations[line.participant_id]??""} onChange={(event)=>setAllocations((prev)=>({...prev,[line.participant_id]:event.target.value}))} hint={`Nilai tagihan ${formatIdr(line.amount_idr)}`}/>)}<p className={`text-sm ${totalAllocated===Number(amount)&&totalAllocated>0?"text-success":"text-muted"}`}>Total alokasi {formatIdr(Math.max(0,totalAllocated))} dari {formatIdr(Math.max(0,Number(amount)||0))}</p></fieldset>:null}
          {invoice?.environment==="demo"?<div className="mb-6"><FormCheckbox id="payment-simulate" label="Simulasikan pembayaran DEMO tanpa dana nyata" checked={simulate} onChange={setSimulate}/></div>:null}
          <Btn type="submit" disabled={busy||!invoice||["VOIDED","PAID"].includes(invoice.status)||Number(amount)<=0||totalAllocated!==Number(amount)||(invoice.environment==="demo"&&!simulate)}>{busy?"Memproses…":"Catat & ajukan"}</Btn>
        </form>
      </section>:null}
    </div>
  </div>;
}
