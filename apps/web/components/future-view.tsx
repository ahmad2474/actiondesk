import { PageHeader, Notice, PreviewLink } from "./ui";
import { FileText } from "lucide-react";
export function FutureView({ title, description, screen }: { title: string; description: string; screen: string }) {
  return <><PageHeader title={title} description={description} /><Notice>Live workflow actions are not enabled in this read-only release.</Notice><section className="preview-intro panel"><FileText size={28} aria-hidden="true" /><h2>Preview the experience</h2><p>Explore a clearly labeled, fictional example of this screen. It does not load a live queue, create requests, or send workflow decisions.</p><PreviewLink screen={screen} /></section></>;
}
