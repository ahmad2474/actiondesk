import Link from "next/link";
import type { ChoicePage } from "@/lib/api-types";
export function ReadChoices({ choices, label, id, pageHref }: { choices: ChoicePage; label: string; id: string; pageHref: (offset: number) => string }) {
  const items = choices.items ?? [];
  return <div className="read-choices"><label htmlFor={id}>{label} · read-only</label>
    {items.length ? <select id={id} disabled defaultValue=""><option value="">{items.length} choices on this page</option>{items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select> : <p className="caption">No choices on this page.</p>}
    {items.length > 0 && <ul className="choice-labels" aria-label={label}>{items.map(item => <li key={item.id}>{item.name}</li>)}</ul>}
    <nav className="button-group" aria-label={`${label} pagination`}>{choices.offset > 0 && <Link className="button button-secondary" href={pageHref(Math.max(0, choices.offset - choices.limit))}>Previous choices</Link>}{choices.has_more && <Link className="button button-secondary" href={pageHref(choices.offset + choices.limit)}>More choices</Link>}</nav>
  </div>;
}
