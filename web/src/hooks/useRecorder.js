import { useRef, useState } from 'react'

export function useRecorder(onDone) {
  const [recording, setRecording] = useState(false)
  const recorderRef = useRef(null)
  const chunksRef = useRef([])

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const rec = new MediaRecorder(stream)
    chunksRef.current = []
    rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop())
      const type = rec.mimeType || 'audio/webm'
      const blob = new Blob(chunksRef.current, { type })
      const ext = type.includes('mp4')
        ? 'm4a'
        : type.includes('ogg')
          ? 'ogg'
          : type.includes('wav')
            ? 'wav'
            : 'webm'
      onDone(blob, ext)
    }
    recorderRef.current = rec
    rec.start()
    setRecording(true)
  }

  function stop() {
    recorderRef.current?.stop()
    setRecording(false)
  }

  return { recording, start, stop }
}
