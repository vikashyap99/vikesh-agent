import { useEffect, useRef, useState } from 'react'
import './App.css'
import { api } from './api'
import TrainVoice from './components/TrainVoice'
import MemoryPanel from './components/MemoryPanel'

const GREETING = {
  id: 'greeting',
  role: 'assistant',
  content: 'Hey everyone! Main Vikash hoon — poochho, kya scene hai?',
  audioUrl: null,
}

function historyOf(messages, excludeId) {
  return messages
    .filter((m) => m.id !== 'greeting' && m.id !== excludeId && m.content)
    .map(({ role, content }) => ({ role, content }))
}

export default function App() {
  const [messages, setMessages] = useState([GREETING])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [recording, setRecording] = useState(false)
  const [autoPlay, setAutoPlay] = useState(true)
  const [voiceReady, setVoiceReady] = useState(null)
  const [panel, setPanel] = useState(null)

  const bottomRef = useRef(null)
  const mediaRecorder = useRef(null)
  const chunks = useRef([])
  const audioRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  useEffect(() => {
    api
      .health()
      .then((d) => setVoiceReady(d.voice_enrolled))
      .catch(() => setVoiceReady(null))
  }, [])

  function play(url) {
    if (!url) return
    if (audioRef.current) audioRef.current.pause()
    const audio = new Audio(url)
    audioRef.current = audio
    audio.play().catch(() => {})
  }

  function push(msg) {
    setMessages((prev) => [...prev, msg])
  }

  function addReply(data) {
    const id = crypto.randomUUID()
    push({
      id,
      role: 'assistant',
      content: data.reply,
      audioUrl: data.audio_url,
      memoryId: data.id,
      rating: null,
    })
    if (autoPlay) play(data.audio_url)
  }

  async function sendText(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    push({ id: crypto.randomUUID(), role: 'user', content: text, audioUrl: null })
    setBusy(true)
    setError(null)
    try {
      addReply(await api.chat(text, historyOf(messages)))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function toggleRecord() {
    if (recording) {
      mediaRecorder.current?.stop()
      setRecording(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const rec = new MediaRecorder(stream)
      chunks.current = []
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, {
          type: rec.mimeType || 'audio/webm',
        })
        sendVoice(blob)
      }
      mediaRecorder.current = rec
      rec.start()
      setRecording(true)
    } catch {
      setError('Mic access denied bhai — browser permission check karo.')
    }
  }

  async function sendVoice(blob) {
    const history = historyOf(messages)
    setBusy(true)
    setError(null)
    try {
      const data = await api.voice(blob, 'question.webm', history)
      if (data.heard) {
        push({
          id: crypto.randomUUID(),
          role: 'user',
          content: data.heard,
          audioUrl: null,
        })
      }
      addReply(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function sendFile(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || busy) return
    await sendVoice(file)
  }

  async function rate(msg, value) {
    if (!msg.memoryId) return
    const next = msg.rating === value ? null : value
    setMessages((prev) =>
      prev.map((m) => (m.id === msg.id ? { ...m, rating: next } : m)),
    )
    try {
      await api.rate(msg.memoryId, next)
    } catch (e) {
      setError(e.message)
    }
  }

  function clearChat() {
    setMessages([GREETING])
    setError(null)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">V</span>
          <div>
            <h1>Vik Agent</h1>
            <p>Ask me anything — Hindi ya English, dono chalega</p>
          </div>
        </div>
        <div className="actions">
          <button className="ghost" onClick={() => setPanel('train')}>
            🎙 Train voice
          </button>
          <button className="ghost" onClick={() => setPanel('memory')}>
            🧠 Memory
          </button>
          <label className="toggle">
            <input
              type="checkbox"
              checked={autoPlay}
              onChange={(e) => setAutoPlay(e.target.checked)}
            />
            Auto-play
          </label>
          <button className="ghost" onClick={clearChat} disabled={busy}>
            New chat
          </button>
        </div>
      </header>

      <main className="chat">
        {messages.map((m) => (
          <div key={m.id} className={`row ${m.role}`}>
            {m.role === 'assistant' && <span className="avatar">V</span>}
            <div className="bubble">
              <p>{m.content}</p>
              {m.audioUrl && (
                <div className="audio">
                  <button className="play" onClick={() => play(m.audioUrl)}>
                    ▶ Play voice
                  </button>
                  <audio controls src={m.audioUrl} preload="none" />
                </div>
              )}
              {m.memoryId && (
                <div className="rate">
                  <button
                    className={`thumb ${m.rating === 'up' ? 'on' : ''}`}
                    onClick={() => rate(m, 'up')}
                    title="Good reply"
                  >
                    👍
                  </button>
                  <button
                    className={`thumb ${m.rating === 'down' ? 'on' : ''}`}
                    onClick={() => rate(m, 'down')}
                    title="Needs work"
                  >
                    👎
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="row assistant">
            <span className="avatar">V</span>
            <div className="bubble typing">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {error && (
          <div className="error" onClick={() => setError(null)}>
            {error} (tap to dismiss)
          </div>
        )}

        {voiceReady === false && (
          <div className="notice">
            Voice clone enroll nahi hua — run: <code>python cli.py --enroll</code>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      <form className="composer" onSubmit={sendText}>
        <button
          type="button"
          className={`mic ${recording ? 'rec' : ''}`}
          onClick={toggleRecord}
          disabled={busy}
          title="Speak your question"
        >
          {recording ? '■' : '🎤'}
        </button>
        <label className="attach" title="Upload audio file">
          📎
          <input type="file" accept="audio/*" onChange={sendFile} hidden />
        </label>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Bhai, AI tools pe kya scene hai?"
          disabled={busy}
        />
        <button type="submit" className="send" disabled={busy || !input.trim()}>
          {busy ? '…' : 'Send'}
        </button>
      </form>

      {panel === 'train' && (
        <TrainVoice
          onClose={() => setPanel(null)}
          onTrained={async () => {
            const d = await api.health().catch(() => null)
            if (d) setVoiceReady(d.voice_enrolled)
          }}
        />
      )}
      {panel === 'memory' && <MemoryPanel onClose={() => setPanel(null)} />}
    </div>
  )
}
