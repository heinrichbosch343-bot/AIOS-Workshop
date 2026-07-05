/*
 * app.js — push-to-talk loop for the Johan demo.
 *
 * Hold the orb (mouse/touch) or the spacebar: record -> release: send to /api/ask
 * -> play the spoken answer, driving Orb states throughout, and slide in the
 * visual card (Cards.show) when the answer carries one.
 * Add ?debug=1 to the URL for a text-input fallback.
 */
import { Orb } from './orb3d.js';

const statusEl = document.getElementById('status');
const exchangeEl = document.getElementById('exchange');
const questionEl = document.getElementById('question');
const answerEl = document.getElementById('answer');
const orbHotspot = document.getElementById('orb-space');

const READY_HINT = 'Hold the orb — or hold space — and ask Johan a question';
const MAX_TURNS = 12;

let history = [];          // [{role, content}] text turns only
let recorder = null;
let micStream = null;
let chunks = [];
let recording = false;
let busy = false;
let audioCtx = null;
let meterRaf = null;

function setStatus(text, isError) {
  statusEl.textContent = text;
  statusEl.classList.toggle('error', !!isError);
}

function showExchange(question) {
  questionEl.textContent = '“' + question + '”';
  answerEl.replaceChildren();
  exchangeEl.classList.remove('hidden');
}

// Build one <span class="w"> per word; speak() lights them up in sync with the audio.
function prepareKaraoke(answerText) {
  answerEl.replaceChildren();
  const words = answerText.split(/\s+/).filter(Boolean);
  return words.map((word, i) => {
    const span = document.createElement('span');
    span.className = 'w';
    span.textContent = word + (i < words.length - 1 ? ' ' : '');
    answerEl.appendChild(span);
    return span;
  });
}

function revealAllWords(spans) {
  spans.forEach((s) => { s.classList.add('shown'); s.classList.remove('current'); });
}

function pushHistory(question, answer) {
  history = [...history, { role: 'user', content: question }, { role: 'assistant', content: answer }]
    .slice(-MAX_TURNS);
}

function ensureAudioCtx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

// Drive Orb.setLevel from any WebAudio node until stopped.
function startMeter(sourceNode) {
  const analyser = ensureAudioCtx().createAnalyser();
  analyser.fftSize = 512;
  sourceNode.connect(analyser);
  const buf = new Uint8Array(analyser.frequencyBinCount);
  const tick = () => {
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = (buf[i] - 128) / 128;
      sum += v * v;
    }
    Orb.setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4));
    meterRaf = requestAnimationFrame(tick);
  };
  tick();
  return analyser;
}

function stopMeter() {
  if (meterRaf) cancelAnimationFrame(meterRaf);
  meterRaf = null;
  Orb.setLevel(0);
}

// ---------------------------------------------------------------- recording

async function startRecording() {
  if (recording || busy) return;
  try {
    if (!micStream) {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
  } catch (err) {
    setStatus('Microphone blocked — allow mic access, or add ?debug=1 to the URL to type instead.', true);
    return;
  }
  recording = true;
  chunks = [];
  recorder = new MediaRecorder(micStream, { mimeType: 'audio/webm' });
  recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  recorder.start();

  const source = ensureAudioCtx().createMediaStreamSource(micStream);
  startMeter(source);
  Orb.setState('listening');
  setStatus('Listening…');
}

function stopRecording() {
  if (!recording) return;
  recording = false;
  stopMeter();
  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: 'audio/webm' });
    if (blob.size < 2000) {
      Orb.setState('idle');
      setStatus(READY_HINT);
      return; // accidental tap — too short to be speech
    }
    sendQuestion({ audioBlob: blob });
  };
  recorder.stop();
}

// ------------------------------------------------------------------ asking

async function sendQuestion({ audioBlob, textQuestion }) {
  busy = true;
  Orb.setState('thinking');
  setStatus('Thinking…');

  const form = new FormData();
  if (audioBlob) form.append('audio', audioBlob, 'question.webm');
  if (textQuestion) form.append('text', textQuestion);
  form.append('history', JSON.stringify(history));

  let data;
  try {
    const resp = await fetch('/api/ask', { method: 'POST', body: form });
    data = await resp.json();
  } catch (err) {
    finishError('Lost connection to the Johan server — is the run.bat window still open?');
    return;
  }

  if (data.error) {
    finishError(data.error);
    return;
  }

  showExchange(data.transcript);
  pushHistory(data.transcript, data.answer);
  // A new card replaces the old one; a null card leaves the previous card up
  // (it stays on screen until the next data answer).
  if (data.card) Cards.show(data.card);
  speak(data.audio_b64, data.answer);
}

function finishError(message) {
  busy = false;
  Orb.setState('idle');
  setStatus(message, true);
}

function speak(audioB64, answerText) {
  const audio = new Audio('data:audio/mp3;base64,' + audioB64);
  const spans = prepareKaraoke(answerText || '');
  try {
    const source = ensureAudioCtx().createMediaElementSource(audio);
    source.connect(audioCtx.destination);
    startMeter(source);
  } catch (err) {
    // Metering is cosmetic — if WebAudio balks, still play the answer.
  }

  // Karaoke: reveal words proportionally to playback position — close enough
  // to true word timing for 1-2 sentence answers, with zero extra API calls.
  audio.ontimeupdate = () => {
    if (!isFinite(audio.duration) || audio.duration <= 0) return;
    const progress = Math.min(1, audio.currentTime / audio.duration);
    const count = Math.min(spans.length, Math.ceil(spans.length * progress * 1.06)); // slight lead so text never lags the voice
    spans.forEach((s, i) => {
      s.classList.toggle('shown', i < count);
      s.classList.toggle('current', i === count - 1 && progress < 1);
    });
  };

  Orb.setState('speaking');
  setStatus('');
  audio.onended = () => {
    revealAllWords(spans);
    stopMeter();
    busy = false;
    Orb.setState('idle');
    setStatus(READY_HINT);
  };
  audio.onerror = () => { revealAllWords(spans); finishError('The answer audio failed to play.'); };
  audio.play().catch(() => { revealAllWords(spans); finishError('Click the page once, then try again (browser blocked autoplay).'); });
}

// ------------------------------------------------------------------- input

orbHotspot.addEventListener('mousedown', startRecording);
orbHotspot.addEventListener('touchstart', (e) => { e.preventDefault(); startRecording(); });
window.addEventListener('mouseup', stopRecording);
window.addEventListener('touchend', stopRecording);

window.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !e.repeat && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    startRecording();
  }
});
window.addEventListener('keyup', (e) => {
  if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
    e.preventDefault();
    stopRecording();
  }
});

// Debug text mode: ?debug=1
if (new URLSearchParams(location.search).get('debug') === '1') {
  const panel = document.getElementById('debug-panel');
  const input = document.getElementById('debug-text');
  const send = document.getElementById('debug-send');
  panel.classList.remove('hidden');
  const submit = () => {
    const q = input.value.trim();
    if (!q || busy) return;
    input.value = '';
    sendQuestion({ textQuestion: q });
  };
  send.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
}

Orb.setState('idle');
setStatus(READY_HINT);
