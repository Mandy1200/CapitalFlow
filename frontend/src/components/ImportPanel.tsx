import { useRef, useState, type FormEvent } from "react";

import { api, ApiError } from "../api/client";
import type { ImportSummary } from "../types";
import Panel, { Alert, Spinner } from "./Panel";

interface Props {
  organization: string;
  organizationName?: string;
  onImported: () => void;
}

export default function ImportPanel({ organization, organizationName, onImported }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    setSummary(null);
    try {
      const result = await api.importStatement(organization, file);
      setSummary(result);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The upload failed.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <Panel
      id="import-heading"
      title="Import bank statement"
      description={`CSV with columns date, description, amount, type, reference. Imported into ${organizationName ?? organization}.`}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
        <label htmlFor="statement-file" className="sr-only">
          Bank statement CSV file
        </label>
        <input
          ref={inputRef}
          id="statement-file"
          type="file"
          accept=".csv,text/csv"
          disabled={uploading}
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setError(null);
          }}
          className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200 sm:max-w-md"
        />
        <button
          type="submit"
          disabled={!file || uploading}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-navy-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-navy-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading && <Spinner />}
          {uploading ? "Importing…" : "Upload CSV"}
        </button>
      </form>

      {(error || summary) && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-4 sm:px-5" aria-live="polite">
          {error && <Alert>Import failed: {error}</Alert>}
          {summary && <ImportResult summary={summary} />}
        </div>
      )}
    </Panel>
  );
}

function ImportResult({ summary }: { summary: ImportSummary }) {
  const stats = [
    { label: "Imported", value: summary.imported_count, className: "text-emerald-700" },
    { label: "Duplicates skipped", value: summary.duplicate_count, className: "text-slate-700" },
    { label: "Rows with errors", value: summary.error_count, className: "text-rose-700" },
  ];
  const { credits, debits, suggested, needs_review } = summary.imported_breakdown;
  return (
    <div className="space-y-4">
      <Alert tone="success">
        Import complete. {credits} credit{credits === 1 ? "" : "s"} and {debits} debit{debits === 1 ? "" : "s"} imported;{" "}
        {suggested} suggested, {needs_review} need review.
      </Alert>
      <dl className="grid grid-cols-3 gap-3">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-md bg-slate-50 px-3 py-2">
            <dt className="text-xs text-slate-500">{stat.label}</dt>
            <dd className={`tabular text-lg font-semibold ${stat.className}`}>{stat.value}</dd>
          </div>
        ))}
      </dl>

      {summary.errors.length > 0 && (
        <IssueTable
          caption="Rows not imported"
          rows={summary.errors.map((e) => ({ line: e.line, message: e.message }))}
          tone="error"
        />
      )}
      {summary.duplicates.length > 0 && (
        <IssueTable
          caption="Duplicates skipped"
          rows={summary.duplicates.map((d) => ({ line: d.line, message: `${d.reference}: ${d.message}` }))}
          tone="muted"
        />
      )}
    </div>
  );
}

function IssueTable({
  caption,
  rows,
  tone,
}: {
  caption: string;
  rows: { line: number; message: string }[];
  tone: "error" | "muted";
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200">
      <table className="min-w-full text-sm">
        <caption className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide ${tone === "error" ? "text-rose-700" : "text-slate-500"}`}>
          {caption}
        </caption>
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th scope="col" className="w-20 px-3 py-2 font-medium">
              Line
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Message
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((row) => (
            <tr key={`${row.line}-${row.message}`}>
              <td className="tabular px-3 py-2 text-slate-700">{row.line}</td>
              <td className="px-3 py-2 text-slate-700">{row.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
