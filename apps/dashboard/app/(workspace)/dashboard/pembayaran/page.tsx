"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Btn, EmptyState, ErrorState, FormCheckbox, FormField, FormSelect, LoadingState, StatusBadge } from "@/components/workspace/ui";
import { API_BASE, apiFetch, problemMessage, type ChargePreview, type TravelInvoice, type TravelPayment } from "@/lib/api";
import { formatDate, formatIdr } from "@/lib/format";
import { useWorkspacePermissions } from "@/lib/useWorkspacePermissions";

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
  const [message,setMessage] = useState<string|null>(null);
  const [busy,setBusy] = useState(false);
  const keys = useRef(new Map<string,{signature:string;key:string}>());
  const canCreate=can("payments.create");
  const load = useCallback(() => {
    apiFetch<{results:TravelPayment[]}>("/payments").then((result)=>{if(result.ok)setPayments(result.data.results);else setError(problemMessage(result.error));});
    apiFetch<{results:TravelInvoice[]}>("/invoices").then((result)=>{if(result.ok){setInvoices(result.data.results);setInvoiceId((prev)=>prev||new URLSearchParams(window.location.search).get("invoice")||"");}});
    if(canCreate)apiFetch<{bank_accounts:Account[]}>("/payments/options").then((result)=>{if(result.ok)setAccounts(result.data.bank_accounts);});
  },[canCreate]);
  useEffect(()=>{if(!loading)load();},[loading,load]);
  const invoice=invoices.find((row)=>row.id===invoiceId);
  const visiblePayments=payments===null?null:payments.filter((payment)=>!invoiceId||payment.invoice_id===invoiceId);
  const totalAllocated=Object.values(allocations).reduce((sum,value)=>sum+(Number(value)||0),0);

  function operationKey(scope:string,body:unknown){
    const signature=JSON.stringify(body);const existing=keys.current.get(scope);
    if(existing?.signature===signature)return existing.key;
    const key=crypto.randomUUID();keys.current.set(scope,{signature,key});return key;
  }

  async function create(event:React.FormEvent){
    event.preventDefault();setError(null);setMessage(null);
    if(!invoice||!receivedAt)return;
    const entries=Object.entries(allocations).filter(([,value])=>Number(value)>0).map(([booking_participant_id,value])=>({booking_participant_id,amount_idr:Number(value)}));
    const body={invoice:invoice.id,amount_idr:Number(amount),kind,method,received_at:new Date(receivedAt).toISOString(),bank_account:accountId||null,reference,evidence_ref:evidence,allocations:entries,simulate:invoice.environment==="demo"&&simulate};
    setBusy(true);
    const result=await apiFetch<TravelPayment>("/payments",{method:"POST",headers:{"Idempotency-Key":operationKey("record",body)},body:JSON.stringify(body)});
    setBusy(false);
    if(!result.ok){setError(problemMessage(result.error));return;}
    setMessage("Pembayaran tercatat dan diajukan untuk verifikasi.");
    keys.current.delete("record");setAmount("");setAllocations({});setReference("");setEvidence("");load();
  }

  async function act(payment:TravelPayment,action:string){
    if(action==="evidence"){
      const evidenceRef=window.prompt("Referensi bukti penerimaan:",payment.evidence_ref);
      if(evidenceRef===null)return;
      setBusy(true);setError(null);
      const result=await apiFetch<TravelPayment>(`/payments/${payment.id}`,{method:"PATCH",body:JSON.stringify({evidence_ref:evidenceRef})});
      setBusy(false);
      if(!result.ok){setError(problemMessage(result.error));return;}
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
    setMessage(action==="verify"?(pending?"Pembayaran terverifikasi dan kuitansi diterbitkan. Biaya layanan menunggu saldo SaaS Wallet.":"Pembayaran terverifikasi dan kuitansi diterbitkan."):action==="reverse"?"Reversal tercatat; sisa tagihan diperbarui.":action==="reject"?"Pembayaran ditolak dengan alasan.":"Pembayaran diajukan.");load();
  }

  if(loading)return <LoadingState/>;
  if(!can("payments.read"))return <EmptyState title="Anda tidak memiliki akses pembayaran"/>;
  return <div className="workspace-page">
    <h1 className="text-2xl font-bold">Pembayaran</h1>
    <p className="mt-1 text-sm text-muted">Catat DP, cicilan, atau pelunasan dan alokasikan nominal ke masing-masing jamaah. Kuitansi diterbitkan setelah dana diverifikasi.</p>
    {message?<p className="mt-4 border border-success/30 bg-success/10 p-3 text-sm text-success" role="status">{message}</p>:null}
    {error?<div className="mt-4"><ErrorState message={error}/></div>:null}
    <div className="workspace-columns mt-6">
      <section className="card p-6"><h2 className="font-semibold">Riwayat pembayaran</h2>
        {visiblePayments===null?<LoadingState/>:visiblePayments.length===0?<div className="mt-4"><EmptyState title="Belum ada pembayaran"/></div>:<ul className="mt-4 divide-y divide-border">{visiblePayments.map((payment)=><li key={payment.id} className="py-4 text-sm">
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
      </section>
      {canCreate?<section className="card p-6"><h2 className="font-semibold">Catat pembayaran</h2>
        <form onSubmit={create} className="mt-6">
          <FormSelect label="Invoice" htmlFor="payment-invoice" value={invoiceId} required onChange={(event)=>{setInvoiceId(event.target.value);setAllocations({});setSimulate(false);}}><option value="">— pilih invoice —</option>{invoices.map((row)=><option key={row.id} value={row.id} disabled={["VOIDED","PAID"].includes(row.status)}>{row.invoice_number} · sisa {formatIdr(row.balance_idr)}</option>)}</FormSelect>
          <FormField label="Nominal diterima (Rp)" htmlFor="payment-amount" inputMode="numeric" value={amount} required onChange={(event)=>setAmount(event.target.value)}/>
          <FormSelect label="Jenis pembayaran" htmlFor="payment-kind" value={kind} onChange={(event)=>setKind(event.target.value)}><option value="DP">DP</option><option value="INSTALLMENT">Cicilan</option><option value="BALANCE">Pelunasan</option></FormSelect>
          <FormField label="Tanggal penerimaan" htmlFor="payment-received" type="datetime-local" value={receivedAt} required onChange={(event)=>setReceivedAt(event.target.value)}/>
          <FormSelect label="Metode" htmlFor="payment-method" value={method} onChange={(event)=>setMethod(event.target.value)}><option value="TRANSFER">Transfer bank</option><option value="CASH">Tunai</option></FormSelect>
          {method==="TRANSFER"?<FormSelect label="Rekening tujuan" htmlFor="payment-account" value={accountId} required onChange={(event)=>setAccountId(event.target.value)}><option value="">— pilih rekening —</option>{accounts.map((account)=><option key={account.id} value={account.id}>{account.bank_name} · {account.account_name} · {account.account_masked}</option>)}</FormSelect>:null}
          <FormField label="Referensi penerimaan" htmlFor="payment-reference" value={reference} onChange={(event)=>setReference(event.target.value)} hint="Nomor transfer atau referensi penerimaan tunai."/>
          <FormField label="Referensi bukti" htmlFor="payment-evidence" value={evidence} onChange={(event)=>setEvidence(event.target.value)} hint="Salah satu referensi penerimaan atau bukti wajib diisi."/>
          {invoice?<fieldset className="my-6 border-t border-border pt-6"><legend className="text-sm font-semibold">Alokasi per jamaah</legend>{invoice.lines.map((line)=><FormField key={line.participant_id} label={`Alokasi ${line.pilgrim_name}`} htmlFor={`allocation-${line.participant_id}`} inputMode="numeric" value={allocations[line.participant_id]??""} onChange={(event)=>setAllocations((prev)=>({...prev,[line.participant_id]:event.target.value}))} hint={`Nilai tagihan ${formatIdr(line.amount_idr)}`}/>)}<p className={`text-sm ${totalAllocated===Number(amount)&&totalAllocated>0?"text-success":"text-muted"}`}>Total alokasi {formatIdr(Math.max(0,totalAllocated))} dari {formatIdr(Math.max(0,Number(amount)||0))}</p></fieldset>:null}
          {invoice?.environment==="demo"?<div className="mb-6"><FormCheckbox id="payment-simulate" label="Simulasikan pembayaran DEMO tanpa dana nyata" checked={simulate} onChange={setSimulate}/></div>:null}
          <Btn type="submit" disabled={busy||!invoice||["VOIDED","PAID"].includes(invoice.status)||Number(amount)<=0||totalAllocated!==Number(amount)||(invoice.environment==="demo"&&!simulate)}>{busy?"Memproses…":"Catat & ajukan"}</Btn>
        </form>
      </section>:null}
    </div>
  </div>;
}
