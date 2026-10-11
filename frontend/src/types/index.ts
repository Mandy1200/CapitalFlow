// Monetary amounts arrive as decimal strings (e.g. "25000.00") and are never
// converted to floating point numbers for arithmetic.
export type Money = string;

export interface Organization {
  id: number;
  slug: string;
  name: string;
}

export type TransactionStatus = "suggested" | "needs_review" | "reconciled" | "ignored";
export type MatchStatus = "proposed" | "approved" | "rejected";
export type LineItemStatus = "open" | "partially_funded" | "funded";

export interface Match {
  id: number;
  status: MatchStatus;
  reason: string;
  line_item_id: number;
  investor_name: string;
  expected_wire_reference: string;
  capital_call_number: number;
  amount_called: Money;
  remaining_amount: Money;
  line_item_status: LineItemStatus;
  created_at: string;
}

export interface Transaction {
  id: number;
  transaction_date: string;
  description: string;
  amount: Money;
  type: "credit" | "debit";
  bank_reference: string;
  status: TransactionStatus;
  review_reason: string | null;
  created_at: string;
  can_ignore: boolean;
  matches: Match[];
}

export interface LineItem {
  id: number;
  investor_entity_id: number;
  investor_name: string;
  capital_call: { id: number; call_number: number; call_date: string; due_date: string };
  expected_wire_reference: string;
  amount_called: Money;
  amount_funded: Money;
  remaining_amount: Money;
  status: LineItemStatus;
}

export interface ImportSummary {
  imported_count: number;
  duplicate_count: number;
  error_count: number;
  imported_breakdown: { credits: number; debits: number; suggested: number; needs_review: number };
  errors: { line: number; message: string }[];
  duplicates: { line: number; reference: string; message: string }[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}
