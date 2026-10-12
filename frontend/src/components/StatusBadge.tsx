import type { LineItemStatus, MatchStatus, TransactionStatus } from "../types";

type AnyStatus = TransactionStatus | MatchStatus | LineItemStatus;

const STYLES: Record<AnyStatus, { label: string; className: string }> = {
  suggested: { label: "Suggested", className: "bg-blue-50 text-blue-700 ring-blue-600/20" },
  needs_review: { label: "Needs review", className: "bg-amber-50 text-amber-800 ring-amber-600/25" },
  reconciled: { label: "Reconciled", className: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
  ignored: { label: "Ignored", className: "bg-slate-100 text-slate-600 ring-slate-500/20" },
  proposed: { label: "Proposed", className: "bg-blue-50 text-blue-700 ring-blue-600/20" },
  approved: { label: "Approved", className: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
  rejected: { label: "Rejected", className: "bg-rose-50 text-rose-700 ring-rose-600/20" },
  open: { label: "Open", className: "bg-slate-100 text-slate-700 ring-slate-500/20" },
  partially_funded: { label: "Partially funded", className: "bg-amber-50 text-amber-800 ring-amber-600/25" },
  funded: { label: "Funded", className: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
};

export default function StatusBadge({ status }: { status: AnyStatus }) {
  const style = STYLES[status];
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style.className}`}
    >
      {style.label}
    </span>
  );
}
