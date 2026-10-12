import type { Organization } from "../types";

interface Props {
  organizations: Organization[];
  current: string;
  onChange: (slug: string) => void;
  disabled?: boolean;
}

export default function Header({ organizations, current, onChange, disabled }: Props) {
  return (
    <header className="bg-navy-900 text-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M4 17l5-6 4 4 7-9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <p className="text-xl font-semibold tracking-tight">
              Capital<span className="text-blue-300">Flow</span>
            </p>
            <p className="text-sm text-slate-300">Capital Call Reconciliation</p>
          </div>
        </div>

        <div className="flex flex-col gap-1 sm:items-end">
          <label htmlFor="organization" className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Organization
          </label>
          <select
            id="organization"
            value={current}
            disabled={disabled || organizations.length === 0}
            onChange={(event) => onChange(event.target.value)}
            className="w-full rounded-md border border-white/15 bg-navy-800 px-3 py-2 text-sm text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-400 sm:w-64"
          >
            {organizations.map((org) => (
              <option key={org.slug} value={org.slug}>
                {org.name}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
