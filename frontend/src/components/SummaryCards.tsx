import type { Transaction } from "../types";

export default function SummaryCards({ transactions }: { transactions: Transaction[] }) {
  const count = (status: Transaction["status"]) => transactions.filter((tx) => tx.status === status).length;
  const cards = [
    { label: "Total transactions", value: transactions.length, accent: "bg-navy-700" },
    { label: "Suggested", value: count("suggested"), accent: "bg-blue-500" },
    { label: "Needs review", value: count("needs_review"), accent: "bg-amber-500" },
    { label: "Reconciled", value: count("reconciled"), accent: "bg-emerald-500" },
  ];
  return (
    <section aria-label="Transaction summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
      {cards.map((card) => (
        <div key={card.label} className="relative overflow-hidden rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <span className={`absolute inset-y-0 left-0 w-1 ${card.accent}`} aria-hidden />
          <p className="text-sm text-slate-500">{card.label}</p>
          <p className="tabular mt-1 text-2xl font-semibold text-slate-900">{card.value}</p>
        </div>
      ))}
    </section>
  );
}
