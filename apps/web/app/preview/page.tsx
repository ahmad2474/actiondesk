export const metadata = { title: "Synthetic design preview · ActionDesk" };
import { AppShell } from "@/components/shell";
import { PreviewContent } from "@/components/preview";
import { previewUser } from "@/lib/preview-fixtures";
export default async function Preview({ searchParams }: { searchParams: Promise<{ screen?: string; variant?: string; role?: string }> }) {
  const { screen = "home", variant = "current", role } = await searchParams;
  const requester = screen === "revision" || screen === "create" || (screen === "detail" && ["changes", "reversed", "service"].includes(variant));
  const persona = requester ? { ...previewUser, id: "00000001-0000-4000-8000-000000000001", name: "Noor Malik", email: "noor@actiondesk.ahmad", roles: ["employee" as const] } : previewUser;
  const user = { ...persona, roles: role === "employee" ? ["employee" as const] : role === "admin" ? ["admin" as const] : persona.roles };
  return <AppShell user={user} preview screen={screen}><PreviewContent screen={screen} variant={variant} /></AppShell>;
}
