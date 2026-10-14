"use client";
import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, Copy } from "lucide-react";
import { identifier } from "@/lib/display";

/** Abbreviation is presentation only; the original identifier is exposed/copied unchanged. */
export function Identifier({ value, label }: { value: string; label: string }) {
  const [feedback, setFeedback] = useState("");
  async function copy() {
    try { await navigator.clipboard.writeText(value); setFeedback("Copied full identifier."); }
    catch { setFeedback("Copy unavailable. Select the full identifier above to copy it manually."); }
  }
  return <span className="identifier"><Dialog.Root onOpenChange={() => setFeedback("")}><Dialog.Trigger className="identifier-trigger" aria-label={`Show full ${label.toLowerCase()} (${identifier(value)})`}>{identifier(value)}<ChevronDown size={11} aria-hidden="true" /></Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="dialog-overlay" /><Dialog.Content className="action-dialog identifier-dialog"><Dialog.Title>{label}</Dialog.Title><Dialog.Description className="dialog-description">Full identifier from the recorded evidence.</Dialog.Description><textarea rows={2} className="identifier-value" aria-label={`Full ${label.toLowerCase()}`} readOnly value={value} onFocus={event => event.currentTarget.select()} /><p className="caption identifier-feedback" role="status">{feedback}</p><div className="button-group"><Dialog.Close className="button button-secondary">Close</Dialog.Close><button type="button" className="button button-primary" onClick={() => void copy()}><Copy size={15} aria-hidden="true" />Copy full identifier</button></div></Dialog.Content></Dialog.Portal></Dialog.Root><noscript><span className="full-id">{value}</span></noscript></span>;
}
