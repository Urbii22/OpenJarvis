import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio, fetchSpeechHealth, createSpeechStream } from '../lib/api';

export type SpeechState = 'idle' | 'recording' | 'transcribing';

export function useSpeech() {
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const speechWsRef = useRef<WebSocket | null>(null);

  // Check if speech backend is available on mount
  useEffect(() => {
    fetchSpeechHealth()
      .then((health) => setAvailable(health.available))
      .catch(() => setAvailable(false));
  }, []);

  const startRecording = useCallback(async (): Promise<void> => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microphone not supported in this browser');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setState('recording');
    } catch (err) {
      setError('Microphone access denied');
      setState('idle');
    }
  }, []);

  const startStreamingRecording = useCallback(async (callbacks?: {
    onPartialText?: (text: string) => void;
    onFinalText?: (text: string) => void;
    onInterrupted?: () => void;
  }): Promise<void> => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microphone not supported in this browser');
      return;
    }
    const ws = createSpeechStream({
      onPartialText: callbacks?.onPartialText,
      onFinalText: callbacks?.onFinalText,
      onInterrupted: callbacks?.onInterrupted,
      onError: (detail) => setError(detail),
    });
    speechWsRef.current = ws;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const recorder = new MediaRecorder(stream);
    mediaRecorderRef.current = recorder;
    recorder.ondataavailable = async (e) => {
      if (e.data.size <= 0 || ws.readyState !== WebSocket.OPEN) return;
      const bytes = await e.data.arrayBuffer();
      let binary = '';
      new Uint8Array(bytes).forEach((b) => { binary += String.fromCharCode(b); });
      ws.send(JSON.stringify({ type: 'audio', data: btoa(binary) }));
    };
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'start', format: 'webm' }));
      recorder.start(250);
      setState('recording');
    };
  }, []);

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state !== 'recording') {
        reject(new Error('Not recording'));
        return;
      }

      recorder.onstop = async () => {
        setState('transcribing');

        // Stop all audio tracks
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        try {
          const result = await transcribeAudio(blob);
          setState('idle');
          resolve(result.text);
        } catch (err) {
          setState('idle');
          const msg = err instanceof Error ? err.message : 'Transcription failed';
          setError(msg);
          reject(err);
        }
      };

      recorder.stop();
    });
  }, []);

  const stopStreamingRecording = useCallback((): void => {
    const recorder = mediaRecorderRef.current;
    const ws = speechWsRef.current;
    if (recorder && recorder.state === 'recording') recorder.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'stop' }));
    }
    setState('idle');
  }, []);

  const interruptSpeech = useCallback((): void => {
    const ws = speechWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }));
    }
  }, []);

  return {
    state,
    error,
    available,
    startRecording,
    stopRecording,
    startStreamingRecording,
    stopStreamingRecording,
    interruptSpeech,
    isRecording: state === 'recording',
    isTranscribing: state === 'transcribing',
  };
}
