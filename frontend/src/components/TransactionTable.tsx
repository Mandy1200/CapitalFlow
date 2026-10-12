import { useState } from "react";

import { formatDate, formatMoney } from "../lib/format";
import type { Match, Transaction, TransactionStatus } from "../types";
import Panel, { Spinner } from "./Panel";
import StatusBadge from "./StatusBadge";

export type ActionKind = "approve" | "reject" | "ignore";

interface Props {
  transactions: Transaction[];
  loading: boolean;
  /** Key of the action currently running, e.g. "approve:12", or null. */
  pendingAction: string | null;
  onAction: (kind: ActionKind, id: number) => void;
}

type Filter = "all" | TransactionStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "suggested", label: "Suggested" },
  { value: "needs_review", label: "Needs review" },
  { value: "reconciled", label: "Reconciled" },
  { value: "ignored", label: "Ignored" },
];

export default function TransactionTable({ transactions, loading, pendingAction, onAction }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const visible = filter === "all" ? transactions : transactions.filter((tx) => tx.status === filter);

  return (
    <Panel
      id="transactions-heading"
      title="Bank transactions"
      description="Newest first. Approve a specific proposed match to fund its line item."
      actions={
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-1">
          {FILTERS.map((option) => {
            const count =
              option.value === "all" ? transactions.length : transactions.filter((tx) => tx.status === option.value).length;
            const active = filter === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(option.value)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  active ? "bg-navy-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {option.label} <span className="tabular opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      }
    >
      {loading && transactions.length === 0 ? (
        <p className="flex items-center gap-2 px-5 py-10 text-sm text-slate-500">
          <Spinner /> Loading transactions…
        </p>
      ) : transactions.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <p className="text-sm font-medium text-slate-700">No transactions yet</p>
          <p className="mt-1 text-sm text-slate-500">Upload a bank statement CSV above to start reconciling.</p>
        </div>
      ) : visible.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-slate-500">No transactions with this status.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium sm:pl-5">Date</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Description</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Amount</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Bank reference</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Suggested investor</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Expected ref</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Match reason</th>
                <th scope="col" className="px-4 py-2.5 font-medium sm:pr-5">Actions</th>
              </tr>
            </thead>
            {visible.map((tx) => (
              <TransactionRows key={tx.id} tx={tx} pendingAction={pendingAction} onAction={onAction} />
            ))}
          </table>
        </div>
      )}
    </Panel>
  );
}

function TransactionRows({
  tx,
  pendingAction,
  onAction,
}: {
  tx: Transaction;
  pendingAction: string | null;
  onAction: Props["onAction"];
}) {
  const rows: (Match | null)[] = tx.matches.length > 0 ? tx.matches : [null];
  const span = rows.length;
  const busy = pendingAction !== null;
  const proposedCount = tx.matches.filter((m) => m.status === "proposed").length;

  return (
    <tbody className="border-t border-slate-200 first:border-t-0">
      {rows.map((match, index) => (
        <tr key={match?.id ?? "none"} className="align-top">
          {index === 0 && (
            <>
              <td rowSpan={span} className="whitespace-nowrap px-4 py-3 text-slate-700 sm:pl-5">
                {formatDate(tx.transaction_date)}
              </td>
              <td rowSpan={span} className="max-w-[16rem] px-4 py-3 text-slate-900">
                {tx.description}
                {tx.type === "debit" && <span className="ml-1 text-xs text-slate-400">(debit)</span>}
              </td>
              <td
                rowSpan={span}
                className={`tabular whitespace-nowrap px-4 py-3 text-right font-medium ${tx.type === "debit" ? "text-rose-700" : "text-slate-900"}`}
              >
                {formatMoney(tx.amount)}
              </td>
              <td rowSpan={span} className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-600">
                {tx.bank_reference}
              </td>
              <td rowSpan={span} className="px-4 py-3">
                <StatusBadge status={tx.status} />
                {tx.status === "needs_review" && proposedCount > 1 && (
                  <p className="mt-1 text-xs text-amber-800">Choose one of {proposedCount} candidates.</p>
                )}
              </td>
            </>
          )}

          {match ? (
            <>
              <td className="px-4 py-3">
                <span className={match.status === "rejected" ? "text-slate-400 line-through" : "text-slate-900"}>
                  {match.investor_name}
                </span>
                <span className="mt-1 block">
                  <StatusBadge status={match.status} />
                </span>
              </td>
              <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-700">
                {match.expected_wire_reference}
                <span className="mt-0.5 block font-sans text-slate-400">
                  {formatMoney(match.remaining_amount)} left
                </span>
              </td>
              <td className="max-w-[18rem] px-4 py-3 text-slate-600">
                {match.reason}
                {index === 0 && tx.review_reason && tx.status === "needs_review" && (
                  <p className="mt-1 text-xs text-amber-800">{tx.review_reason}</p>
                )}
              </td>
            </>
          ) : (
            <>
              <td className="px-4 py-3 text-slate-400">—</td>
              <td className="px-4 py-3 text-slate-400">—</td>
              <td className="max-w-[18rem] px-4 py-3 text-slate-600">
                {tx.review_reason ?? <span className="text-slate-400">—</span>}
              </td>
            </>
          )}

          <td className="px-4 py-3 sm:pr-5">
            <div className="flex flex-wrap gap-1.5">
              {match?.status === "proposed" && (
                <>
                  <ActionButton
                    label="Approve"
                    ariaLabel={`Approve match to ${match.investor_name} (${match.expected_wire_reference})`}
                    tone="primary"
                    pending={pendingAction === `approve:${match.id}`}
                    disabled={busy}
                    onClick={() => onAction("approve", match.id)}
                  />
                  <ActionButton
                    label="Reject"
                    ariaLabel={`Reject match to ${match.investor_name} (${match.expected_wire_reference})`}
                    tone="secondary"
                    pending={pendingAction === `reject:${match.id}`}
                    disabled={busy}
                    onClick={() => onAction("reject", match.id)}
                  />
                </>
              )}
              {index === 0 && tx.can_ignore && (
                <ActionButton
                  label="Ignore"
                  ariaLabel={`Ignore transaction ${tx.bank_reference}`}
                  tone="ghost"
                  pending={pendingAction === `ignore:${tx.id}`}
                  disabled={busy}
                  onClick={() => onAction("ignore", tx.id)}
                />
              )}
            </div>
          </td>
        </tr>
      ))}
    </tbody>
  );
}

function ActionButton({
  label,
  ariaLabel,
  tone,
  pending,
  disabled,
  onClick,
}: {
  label: string;
  ariaLabel: string;
  tone: "primary" | "secondary" | "ghost";
  pending: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const styles = {
    primary: "bg-navy-900 text-white hover:bg-navy-800",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    ghost: "text-slate-500 hover:bg-slate-100 hover:text-slate-700",
  }[tone];
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 ${styles}`}
    >
      {pending && <Spinner className="h-3 w-3" />}
      {label}
    </button>
  );
}
