import { useEffect, useState } from 'react'
import { api } from '../api'

function Stat({ label, value, hint }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
      {hint && <span className="stat-hint">{hint}</span>}
    </div>
  )
}

export default function MemoryPanel({ onClose }) {
  const [data, setData] = useState(null)
  const [notes, setNotes] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    load()
  }, [])

  function load() {
    api
      .memory()
      .then((d) => {
        setData(d)
        setNotes(d.notes || '')
      })
      .catch((e) => setError(e.message))
  }

  async function reflect() {
    setBusy('reflect')
    setError('')
    setStatus('')
    try {
      const d = await api.reflect()
      setNotes(d.notes)
      setData((prev) => ({ ...prev, stats: d.stats, notes: d.notes }))
      setStatus('Notes updated — agent will use these in future replies.')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  async function saveNotes() {
    setBusy('save')
    setError('')
    setStatus('')
    try {
      await api.saveNotes(notes)
      setStatus('Saved.')
      load()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
  }

  const stats = data?.stats
  const trendClass =
    stats?.trend === 'improving'
      ? 'good'
      : stats?.trend === 'declining'
        ? 'bad'
        : ''

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Self-learning memory</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          <p className="hint">
            Har jawab save hota hai. 👍/👎 do, aur &ldquo;Reflect&rdquo; dabao — agent
            apni notes khud update karega aur next replies better karega. Report file
            mein improvement validate hoti hai.
          </p>

          {stats && (
            <div className="stats">
              <Stat label="exchanges" value={stats.total} />
              <Stat label="rated" value={stats.rated} hint={`👍 ${stats.up} · 👎 ${stats.down}`} />
              <Stat
                label="positive"
                value={stats.positive_pct == null ? '—' : `${stats.positive_pct}%`}
              />
              <Stat
                label="trend"
                value={stats.trend}
                hint={
                  stats.trend_delta == null ? 'need 6+ ratings' : `${stats.trend_delta > 0 ? '+' : ''}${stats.trend_delta} pts`
                }
              />
            </div>
          )}

          <div className="reflect-row">
            <button className="primary" onClick={reflect} disabled={!!busy}>
              {busy === 'reflect' ? 'Learning…' : '✨ Reflect & improve'}
            </button>
            <a className="ghost small" href="/api/memory/report" target="_blank" rel="noreferrer">
              Open report.md
            </a>
          </div>

          <label className="field">
            <span>Learned notes (injected into every reply)</span>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={8} />
          </label>
          <button className="ghost small" onClick={saveNotes} disabled={!!busy}>
            {busy === 'save' ? 'Saving…' : 'Save notes'}
          </button>

          {status && <div className="toast ok">{status}</div>}
          {error && <div className="toast err">{error}</div>}

          {data?.history?.length > 0 && (
            <div className="history">
              <h3>Recent exchanges</h3>
              {[...data.history].reverse().map((h) => (
                <div className="hist-item" key={h.id}>
                  <div className="hist-q">Q: {h.question}</div>
                  <div className="hist-a">A: {h.reply}</div>
                  {h.rating && (
                    <span className={`hist-mark ${h.rating}`}>
                      {h.rating === 'up' ? '👍 liked' : '👎 disliked'}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
