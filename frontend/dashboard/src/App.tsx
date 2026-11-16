import { useEffect, useState } from 'react';
import './App.css';
import type { LedgerSummary, TransactionRecord } from './types';

const API_BASE = 'http://localhost:8000';

export function App() {
  const [summary, setSummary] = useState<LedgerSummary | null>(null);
  const [transactions, setTransactions] = useState<TransactionRecord[]>([]);
  const [replaying, setReplaying] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string>('');

  const fetchData = async () => {
    try {
      const [sumRes, txRes] = await Promise.all([
        fetch(`${API_BASE}/api/summary`),
        fetch(`${API_BASE}/api/transactions?limit=20`),
      ]);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (txRes.ok) setTransactions(await txRes.json());
    } catch {
      // Worker API offline momentarily
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 2000);
    return () => clearInterval(timer);
  }, []);

  const handleReplayDLQ = async () => {
    setReplaying(true);
    setStatusMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/dlq/replay`, { method: 'POST' });
      const data = await res.json();
      setStatusMsg(`Replayed ${data.replayed_count} message(s) back to SQS.`);
      await fetchData();
    } catch {
      setStatusMsg('Failed to contact replay endpoint.');
    } finally {
      setReplaying(false);
    }
  };

  const formatXAF = (val: string | number | undefined) =>
    `${Number(val ?? 0).toLocaleString()} XAF`;

  return (
    <div className="container">
      <header className="header">
        <div>
          <h1>AfriPay-Pulse Operations Console</h1>
          <p>Event-Driven Mobile Money Settlement & Double-Entry Ledger (Floci Local Cloud)</p>
        </div>
        <span className={`badge ${summary?.ledger_balanced ? 'badge-ok' : 'badge-err'}`}>
          {summary?.ledger_balanced ? 'DOUBLE-ENTRY LEDGER: BALANCED' : 'LEDGER CHECKING...'}
        </span>
      </header>

      <section className="grid">
        <div className="card">
          <div className="card-label">Total Settled Volume</div>
          <div className="card-value">{formatXAF(summary?.total_volume_xaf)}</div>
          <div className="card-sub">{summary?.total_settled ?? 0} settled transactions</div>
        </div>

        <div className="card">
          <div className="card-label">MTN MoMo Volume</div>
          <div className="card-value" style={{ color: '#f59e0b' }}>
            {formatXAF(summary?.mtn_volume_xaf)}
          </div>
          <div className="card-sub">TELCO_CLEARING_MTN</div>
        </div>

        <div className="card">
          <div className="card-label">Orange Money Volume</div>
          <div className="card-value" style={{ color: '#f97316' }}>
            {formatXAF(summary?.orange_volume_xaf)}
          </div>
          <div className="card-sub">TELCO_CLEARING_ORANGE</div>
        </div>

        <div className="card">
          <div className="card-label">SQS Queue Depth</div>
          <div className="card-value">{summary?.sqs_queued_count ?? 0}</div>
          <div className="card-sub">In-flight payment events</div>
        </div>
      </section>

      <section className="dlq-bar">
        <div>
          <strong>Dead-Letter Queue (DLQ) Quarantine: </strong>
          <span style={{ color: (summary?.dlq_quarantined_count ?? 0) > 0 ? '#ef4444' : '#10b981' }}>
            {summary?.dlq_quarantined_count ?? 0} failed event(s)
          </span>
          {statusMsg && <span style={{ marginLeft: '1rem', color: '#9ca3af' }}>{statusMsg}</span>}
        </div>
        <button
          className="btn-replay"
          onClick={handleReplayDLQ}
          disabled={replaying || (summary?.dlq_quarantined_count ?? 0) === 0}
        >
          {replaying ? 'Replaying...' : 'Remediate & Replay DLQ'}
        </button>
      </section>

      <section className="table-card">
        <div className="table-header">Recent Settled Ledger Transactions (Live Auto-Refresh)</div>
        <table>
          <thead>
            <tr>
              <th>Reference</th>
              <th>Provider</th>
              <th>Payer Phone</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Settled At (UTC)</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td><code>{tx.external_reference}</code></td>
                <td className={tx.provider === 'MTN_MOMO' ? 'pill-mtn' : 'pill-orange'}>
                  {tx.provider}
                </td>
                <td>{tx.payer_phone}</td>
                <td><strong>{tx.amount.toLocaleString()} {tx.currency}</strong></td>
                <td><span className="badge badge-ok">{tx.status}</span></td>
                <td>{new Date(tx.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', color: '#9ca3af' }}>
                  No settled transactions yet. Run the telco simulator to generate traffic!
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default App;
