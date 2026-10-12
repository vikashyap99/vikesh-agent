async function json(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data
}

export const api = {
  health: () => fetch('/api/health').then(json),
  chat: (text, history) =>
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history }),
    }).then(json),
  voice: (blob, filename, history) => {
    const form = new FormData()
    form.append('audio', blob, filename)
    form.append('history', JSON.stringify(history))
    return fetch('/api/voice', { method: 'POST', body: form }).then(json)
  },
  voiceStatus: () => fetch('/api/voice/status').then(json),
  voiceScripts: (count = 5) =>
    fetch(`/api/voice/scripts?count=${count}`).then(json),
  trainVoice: (blob, filename, text) => {
    const form = new FormData()
    form.append('audio', blob, filename)
    form.append('text', text)
    form.append('retrain', 'true')
    return fetch('/api/voice/train', { method: 'POST', body: form }).then(json)
  },
  deleteSample: (id) =>
    fetch(`/api/voice/samples/${id}`, { method: 'DELETE' }).then(json),
  memory: () => fetch('/api/memory').then(json),
  rate: (id, rating) =>
    fetch('/api/memory/rate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, rating }),
    }).then(json),
  saveNotes: (text) =>
    fetch('/api/memory/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }).then(json),
  reflect: () =>
    fetch('/api/memory/reflect', { method: 'POST' }).then(json),
}
