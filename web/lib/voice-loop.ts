// Hands-free voice for the assistant: the mic stays open, each utterance is cut where the shopper pauses, and replies
// are played through the same audio context. Audio is captured as raw PCM and sent as 16 kHz WAV, so speech-to-text
// never depends on what MediaRecorder container a browser produces (Safari's caused "Invalid file format" errors).

const TARGET_RATE = 16000;
const FRAME = 2048; // ~43 ms at 48 kHz
const PREROLL_MS = 400; // keep the start of the first word, which arrives before speech is detected
const START_MS = 120; // this much loud audio in a row starts an utterance
const END_SILENCE_MS = 1100; // a pause this long ends it
const MIN_SPEECH_MS = 300; // shorter is a click or a cough
const MAX_UTTERANCE_MS = 30000;
const ECHO_TAIL_MS = 350; // after a reply, wait for the room to go quiet before listening again

export interface Mic {
  /** Mic level 0..1 for the orb. */
  level(): number;
  /** Stops listening (while the assistant thinks or talks) without closing the mic. */
  pause(): void;
  resume(): void;
  /** Plays a reply. Resolves when it ends or is cut off. */
  play(audio: ArrayBuffer): Promise<void>;
  /** Cuts off the reply that is playing. */
  hush(): void;
  close(): void;
}

export interface MicEvents {
  /** The shopper started talking (used to cut the assistant off mid-sentence). */
  onSpeechStart?: () => void;
  /** One finished utterance as WAV. */
  onUtterance: (wav: Blob) => void;
}

export const canListen = () =>
  typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && !!(window.AudioContext ?? webkitAudio());

function webkitAudio(): typeof AudioContext | undefined {
  return (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
}

/** Opens the mic. Call from a click: browsers only allow audio to start after a user gesture. */
export async function openMic(events: MicEvents): Promise<Mic> {
  const Ctx = window.AudioContext ?? webkitAudio()!;
  const ctx = new Ctx();
  await ctx.resume();
  const stream = await navigator.mediaDevices
    // No echo cancellation: the mic is paused while the assistant talks, and on macOS Chrome's echo canceller runs
    // the speakers through voice processing too, which makes replies sound robotic (worst in the first second).
    .getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true, channelCount: 1 } })
    .catch((err) => {
      ctx.close();
      throw err;
    });
  const source = ctx.createMediaStreamSource(stream);
  // ScriptProcessor is deprecated but runs everywhere (AudioWorklet needs a separate module file); it only reads.
  const proc = ctx.createScriptProcessor(FRAME, 1, 1);
  const mute = ctx.createGain();
  mute.gain.value = 0;
  source.connect(proc);
  proc.connect(mute);
  mute.connect(ctx.destination);

  const frameMs = (FRAME / ctx.sampleRate) * 1000;
  const preroll: Float32Array[] = [];
  let speech: Float32Array[] | null = null;
  let loudRun = 0;
  let quietMs = 0;
  let voicedMs = 0;
  let floor = 0.005;
  let level = 0;
  let paused = false;
  let resumeTimer: ReturnType<typeof setTimeout> | undefined;
  let playing: AudioBufferSourceNode | null = null;
  let endPlay: (() => void) | null = null;

  const finish = () => {
    const frames = speech;
    speech = null;
    loudRun = 0;
    if (frames && voicedMs >= MIN_SPEECH_MS) events.onUtterance(toWav(frames, ctx.sampleRate));
    voicedMs = 0;
  };

  proc.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    const rms = Math.sqrt(sum / input.length);
    level = Math.min(1, rms * 12);
    if (paused) return;
    const frame = new Float32Array(input);
    // Hysteresis: it takes a clearly loud frame to start, and less to keep going between words.
    const loud = rms > Math.max(0.012, floor * 3);
    const voiced = rms > Math.max(0.007, floor * 1.8);
    if (!speech) {
      floor = floor * 0.95 + Math.min(rms, 0.05) * 0.05; // room noise, learned while nobody talks
      preroll.push(frame);
      while (preroll.length * frameMs > PREROLL_MS) preroll.shift();
      loudRun = loud ? loudRun + 1 : 0;
      if (loudRun * frameMs >= START_MS) {
        speech = preroll.splice(0);
        quietMs = 0;
        voicedMs = loudRun * frameMs;
        events.onSpeechStart?.();
      }
      return;
    }
    speech.push(frame);
    if (voiced) {
      quietMs = 0;
      voicedMs += frameMs;
    } else quietMs += frameMs;
    if (quietMs >= END_SILENCE_MS || speech.length * frameMs >= MAX_UTTERANCE_MS) finish();
  };

  const hush = () => {
    try {
      playing?.stop();
    } catch {
      // already stopped
    }
    playing = null;
    endPlay?.();
    endPlay = null;
  };

  return {
    level: () => level,
    pause() {
      clearTimeout(resumeTimer);
      paused = true;
      speech = null;
      loudRun = 0;
      preroll.length = 0;
    },
    resume() {
      // Without echo cancellation the reply's last syllable is still in the room: drop it, then listen.
      clearTimeout(resumeTimer);
      resumeTimer = setTimeout(() => (paused = false), ECHO_TAIL_MS);
    },
    async play(audio) {
      hush();
      const buffer = await ctx.decodeAudioData(audio.slice(0));
      await new Promise<void>((resolve) => {
        const node = ctx.createBufferSource();
        node.buffer = buffer;
        node.connect(ctx.destination);
        node.onended = () => {
          if (playing === node) playing = null;
          resolve();
        };
        playing = node;
        endPlay = resolve;
        node.start();
      });
    },
    hush,
    close() {
      clearTimeout(resumeTimer);
      hush();
      proc.onaudioprocess = null;
      source.disconnect();
      proc.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
    },
  };
}

/** Mono 16-bit WAV at 16 kHz: what speech-to-text wants, and about 32 KB per second. */
function toWav(frames: Float32Array[], rate: number): Blob {
  const total = frames.reduce((n, f) => n + f.length, 0);
  const ratio = rate / TARGET_RATE;
  const length = Math.floor(total / ratio);
  const pcm = new Int16Array(length);
  // Average the samples that fall into each output sample: a cheap low-pass that keeps speech clear.
  let frame = 0;
  let offset = 0;
  const read = () => {
    while (frame < frames.length && offset >= frames[frame].length) {
      frame++;
      offset = 0;
    }
    return frame < frames.length ? frames[frame][offset++] : 0;
  };
  let consumed = 0;
  for (let i = 0; i < length; i++) {
    const until = Math.round((i + 1) * ratio);
    let sum = 0;
    let n = 0;
    for (; consumed < until; consumed++, n++) sum += read();
    const s = Math.max(-1, Math.min(1, n ? sum / n : 0));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const header = new DataView(new ArrayBuffer(44));
  const text = (at: number, s: string) => [...s].forEach((c, i) => header.setUint8(at + i, c.charCodeAt(0)));
  text(0, "RIFF");
  header.setUint32(4, 36 + pcm.byteLength, true);
  text(8, "WAVE");
  text(12, "fmt ");
  header.setUint32(16, 16, true);
  header.setUint16(20, 1, true); // PCM
  header.setUint16(22, 1, true); // mono
  header.setUint32(24, TARGET_RATE, true);
  header.setUint32(28, TARGET_RATE * 2, true);
  header.setUint16(32, 2, true);
  header.setUint16(34, 16, true);
  text(36, "data");
  header.setUint32(40, pcm.byteLength, true);
  return new Blob([header.buffer, pcm.buffer], { type: "audio/wav" });
}
