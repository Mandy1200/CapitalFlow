import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import Header from "../components/Header";
import ImportPanel from "../components/ImportPanel";
import LineItemPanel from "../components/LineItemPanel";
import { Alert } from "../components/Panel";
import SummaryCards from "../components/SummaryCards";
import TransactionTable, { type ActionKind } from "../components/TransactionTable";
import type { LineItem, Organization, Transaction } from "../types";

const DEFAULT_ORGANIZATION = "northwind";
const STORAGE_KEY = "capitalflow.organization";

function storedOrganization(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_ORGANIZATION;
  } catch {
    return DEFAULT_ORGANIZATION;
  }
}

function message(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

export default function Dashboard() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organization, setOrganization] = useState<string>(storedOrganization);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [lineItems, setLineItems] = useState<LineItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  // Ignore responses that arrive after the user has switched organizations.
  const requestSeq = useRef(0);
  const actionInFlight = useRef(false);

  useEffect(() => {
    api
      .listOrganizations()
      .then((orgs) => {
        setOrganizations(orgs);
        if (orgs.length > 0 && !orgs.some((org) => org.slug === organization)) {
          setOrganization(orgs[0].slug);
        }
      })
      .catch((err) => setLoadError(message(err, "Could not load organizations.")));
  }, []);

  // Quick poll or refresh helper after status updates and actions
  const refresh = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const [txs, items] = await Promise.all([api.listTransactions(organization), api.listLineItems(organization)]);
      if (seq !== requestSeq.current) return;
      setTransactions(txs);
      setLineItems(items);
      setLoadError(null);
    } catch (err) {
      if (seq !== requestSeq.current) return;
      setLoadError(message(err, "Could not load reconciliation data."));
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [organization]);

  useEffect(() => {
    setTransactions([]);
    setLineItems([]);
    setActionError(null);
    void refresh();
  }, [refresh]);

  function changeOrganization(slug: string) {
    try {
      localStorage.setItem(STORAGE_KEY, slug);
    } catch {
      // Remembering the choice is a convenience only.
    }
    setOrganization(slug);
  }

  async function handleAction(kind: ActionKind, id: number) {
    // The backend is the source of truth for financial safety; this only
    // stops accidental double clicks.
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    setPendingAction(`${kind}:${id}`);
    setActionError(null);
    try {
      if (kind === "approve") await api.approveMatch(organization, id);
      else if (kind === "reject") await api.rejectMatch(organization, id);
      else await api.ignoreTransaction(organization, id);
      await refresh();
    } catch (err) {
      setActionError(message(err, "The action failed."));
      await refresh(); // show the current state after a conflict
    } finally {
      actionInFlight.current = false;
      setPendingAction(null);
    }
  }

  const organizationName = organizations.find((org) => org.slug === organization)?.name;

  return (
    <div className="min-h-screen">
      <Header
        organizations={organizations}
        current={organization}
        onChange={changeOrganization}
        disabled={pendingAction !== null}
      />
      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
        {loadError && <Alert>{loadError}</Alert>}
        <SummaryCards transactions={transactions} />
        <ImportPanel organization={organization} organizationName={organizationName} onImported={refresh} />
        {actionError && <Alert>{actionError}</Alert>}
        <TransactionTable
          transactions={transactions}
          loading={loading}
          pendingAction={pendingAction}
          onAction={handleAction}
        />
        <LineItemPanel lineItems={lineItems} loading={loading} />
        <footer className="mt-12 py-6 text-center text-xs text-slate-500">
          CapitalFlow &copy; 2026 &middot; Technical Assessment for Digital Alpha Platforms
        </footer>
      </main>
    </div>
  );
}
