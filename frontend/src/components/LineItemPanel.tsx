import { formatDate, formatMoney, sumMoney, toCents } from "../lib/format";
import type { LineItem } from "../types";
import Panel, { Spinner } from "./Panel";
import StatusBadge from "./StatusBadge";

interface Props {
  lineItems: LineItem[];
  loading: boolean;
}

export default function LineItemPanel({ lineItems, loading }: Props) {
  return (
    <Panel id="line-items-heading" title="Capital call line items" description="Expected wires, funding and remaining balances.">
      {loading && lineItems.length === 0 ? (
        <p className="flex items-center gap-2 px-5 py-8 text-sm text-slate-500">
          <Spinner /> Loading line items…
        </p>
      ) : lineItems.length === 0 ? (
        <p className="px-5 py-8 text-sm text-slate-500">This organization has no capital call line items yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium sm:px-5">Investor</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Capital call</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Reference</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Called</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Funded</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Remaining</th>
                <th scope="col" className="px-4 py-2.5 font-medium sm:pr-5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lineItems.map((item) => (
                <tr key={item.id} className="align-top">
                  <td className="px-4 py-3 font-medium text-slate-900 sm:px-5">{item.investor_name}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                    Call #{item.capital_call.call_number}
                    <span className="block text-xs text-slate-400">
                      {formatDate(item.capital_call.call_date)} · due {formatDate(item.capital_call.due_date)}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-700">{item.expected_wire_reference}</td>
                  <td className="tabular whitespace-nowrap px-4 py-3 text-right text-slate-700">{formatMoney(item.amount_called)}</td>
                  <td className="tabular whitespace-nowrap px-4 py-3 text-right text-slate-700">
                    {formatMoney(item.amount_funded)}
                    <FundingBar funded={item.amount_funded} called={item.amount_called} />
                  </td>
                  <td className="tabular whitespace-nowrap px-4 py-3 text-right font-medium text-slate-900">
                    {formatMoney(item.remaining_amount)}
                  </td>
                  <td className="px-4 py-3 sm:pr-5">
                    <StatusBadge status={item.status} />
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t border-slate-200 bg-slate-50 font-medium text-slate-900">
              <tr>
                <th scope="row" colSpan={3} className="px-4 py-2.5 text-left sm:px-5">
                  Total
                </th>
                <td className="tabular whitespace-nowrap px-4 py-2.5 text-right">{formatMoney(sumMoney(lineItems.map((i) => i.amount_called)))}</td>
                <td className="tabular whitespace-nowrap px-4 py-2.5 text-right">{formatMoney(sumMoney(lineItems.map((i) => i.amount_funded)))}</td>
                <td className="tabular whitespace-nowrap px-4 py-2.5 text-right">{formatMoney(sumMoney(lineItems.map((i) => i.remaining_amount)))}</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </Panel>
  );
}

function FundingBar({ funded, called }: { funded: string; called: string }) {
  const calledCents = toCents(called);
  const percent = calledCents > 0n ? Number((toCents(funded) * 100n) / calledCents) : 0;
  return (
    <span
      className="mt-1.5 ml-auto block h-1 w-20 overflow-hidden rounded-full bg-slate-200"
      role="progressbar"
      aria-label="Funded"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span className="block h-full rounded-full bg-emerald-500" style={{ width: `${percent}%` }} />
    </span>
  );
}
