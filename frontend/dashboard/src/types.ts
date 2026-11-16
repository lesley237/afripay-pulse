export interface LedgerSummary {
  total_settled: number;
  total_volume_xaf: string;
  mtn_volume_xaf: string;
  orange_volume_xaf: string;
  ledger_balanced: boolean;
  total_debits_xaf: string;
  total_credits_xaf: string;
  sqs_queued_count: number;
  dlq_quarantined_count: number;
}

export interface TransactionRecord {
  id: string;
  external_reference: string;
  provider: 'MTN_MOMO' | 'ORANGE_MONEY';
  payer_phone: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
}
