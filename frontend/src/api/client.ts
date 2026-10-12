import type { ApiErrorBody, ImportSummary, LineItem, Organization, Transaction } from "../types";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  /** Organization slug sent as X-Organization. Omitted only for header-free endpoints. */
  organization?: string;
  body?: FormData;
}

async function request<T>(path: string, { method = "GET", organization, body }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (organization) headers["X-Organization"] = organization;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method, headers, body });
  } catch {
    throw new ApiError("Could not reach the CapitalFlow API. Check that the backend is running.", 0, "network_error");
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const error = (data as ApiErrorBody | null)?.error;
    throw new ApiError(
      error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      error?.code ?? "http_error",
      error?.details,
    );
  }
  return data as T;
}

export const api = {
  listOrganizations: () => request<Organization[]>("/organizations/"),
  listTransactions: (organization: string) => request<Transaction[]>("/transactions/", { organization }),
  listLineItems: (organization: string) => request<LineItem[]>("/line-items/", { organization }),
  importStatement: (organization: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ImportSummary>("/imports/", { method: "POST", organization, body: form });
  },
  approveMatch: (organization: string, matchId: number) =>
    request<unknown>(`/matches/${matchId}/approve/`, { method: "POST", organization }),
  rejectMatch: (organization: string, matchId: number) =>
    request<unknown>(`/matches/${matchId}/reject/`, { method: "POST", organization }),
  ignoreTransaction: (organization: string, transactionId: number) =>
    request<Transaction>(`/transactions/${transactionId}/ignore/`, { method: "POST", organization }),
};
