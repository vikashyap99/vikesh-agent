import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useRecorder } from '../hooks/useRecorder'

export default function TrainVoice({ onClose, onTrained }) {
  const [voice, setVoice] = useState(null)
  const [script, setScript] = useState('')
  const [scriptQueue, setScriptQueue] = useState([])
  const [blob, setBlob] = useState(null)
  const [ext, setExt] = useState('webm')
  const [previewUrl, setPreviewUrl] = useState(null)
  const [readText, setReadText] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const previewRef = useRef(null)

  const { recording, start, stop } = useRecorder((b, e) => {
    setBlob(b)
    setExt(e)
    setStatus('')
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(URL.createObjectURL(b))
  })

  useEffect(() => {
    refresh()
    loadScripts()
  }, [])

  function refresh() {
    api.voiceStatus().then(setVoice).catch((e) => setError(e.message))
  }

  function loadScripts() {
    api
      .voiceScripts(6)
      .then((d) => {
        setScriptQueue(d.scripts)
        setScript(d.scripts[0] || '')
      })
      .catch((e) => setError(e.message))
  }

  function nextScript() {
    let queue = scriptQueue
    if (queue.length <= 1) {
      api.voiceScripts(6).then((d) => {
        setScriptQueue(d.scripts)
        setScript(d.scripts[0] || '')
        setReadText(d.scripts[0] || '')
      })
      return
    }
    queue = queue.slice(1)
    setScriptQueue(queue)
    setScript(queue[0])
    setReadText('')
  }

  async function handleRecord() {
    if (recording) {
      stop()
      return
    }
    setError('')
    try {
      await start()
    } catch {
      setError('Mic access denied — browser permission check karo.')
    }
  }

  async function save() {
    if (!blob) return
    setSaving(true)
    setError('')
    setStatus('')
    try {
      const d = await api.trainVoice(blob, `sample.${ext}`, readText || script)
      setStatus(
        `Voice improved! Ab ${d.sample_count} samples pe trained hai${
          d.trained_on ? ` (used ${d.trained_on})` : ''
        }.`,
      )
      setBlob(null)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
      setReadText('')
      refresh()
      onTrained?.()
      nextScript()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function removeSample(id) {
    try {
      await api.deleteSample(id)
      refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Train your voice, Vikash</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          <p className="hint">
            Neeche wali line <strong>zabaan se padho</strong> — mic dabao, padho, phir
            stop. Jitne zyada samples, utna better clone. Har line apni natural awaaz
            mein, shaant room mein.
          </p>

          {voice && (
            <div className="chips">
              <span className="chip">
                {voice.sample_count} extra sample{voice.sample_count === 1 ? '' : 's'}
              </span>
              <span className="chip">
                {voice.base_sample ? 'base reference ✓' : 'no base reference'}
              </span>
              <span className={`chip ${voice.state === 'trained' ? 'good' : ''}`}>
                model: {voice.state || 'unknown'}
              </span>
            </div>
          )}

          <div className="script-box">
            <span className="script-label">Read this:</span>
            <p>{script || 'Loading…'}</p>
            <button className="ghost small" onClick={nextScript} disabled={recording}>
              ↻ New line
            </button>
          </div>

          <div className="rec-row">
            <button
              className={`rec-btn ${recording ? 'rec' : ''}`}
              onClick={handleRecord}
              disabled={saving}
            >
              {recording ? '■ Stop recording' : '● Record'}
            </button>
            {previewUrl && !recording && (
              <audio ref={previewRef} controls src={previewUrl} />
            )}
          </div>

          {blob && !recording && (
            <div className="save-row">
              <label className="field">
                <span>Transcript of what you read (auto-filled, edit if needed)</span>
                <textarea
                  value={readText || script}
                  onChange={(e) => setReadText(e.target.value)}
                  rows={2}
                />
              </label>
              <button className="primary" onClick={save} disabled={saving}>
                {saving ? 'Training voice…' : 'Save & improve voice'}
              </button>
            </div>
          )}

          {status && <div className="toast ok">{status}</div>}
          {error && <div className="toast err">{error}</div>}

          {voice?.samples?.length > 0 && (
            <div className="samples">
              <h3>Saved samples</h3>
              {voice.samples.map((s) => (
                <div className="sample" key={s.id}>
                  <span className="sample-text">{s.transcript || s.id}</span>
                  <button className="x small" onClick={() => removeSample(s.id)}>
                    remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
