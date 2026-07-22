import os, time, pathlib
import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from faster_whisper import WhisperModel

mic = int(os.environ.get('ARTHUR_MIC_DEVICE', '2'))
fs = 16000
seconds = 5
scratch = pathlib.Path(r'C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad')
scratch.mkdir(parents=True, exist_ok=True)
log = scratch / 'arthur_voice_transcript.log'
state = scratch / 'arthur_voice_listener_state.txt'

def emit(line):
    print(line, flush=True)
    with log.open('a', encoding='utf-8') as f:
        f.write(line + '\n')

state.write_text(f'active mic={mic} name={sd.query_devices(mic)["name"]}\n', encoding='utf-8')
emit(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Arthur voice listener active on mic index {mic}: {sd.query_devices(mic)["name"]}')
model = WhisperModel('tiny.en', device='cpu', compute_type='int8')
count = 0
while True:
    count += 1
    audio = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype='int16', device=mic)
    sd.wait()
    arr = audio.astype(np.float32).reshape(-1)
    rms = float(np.sqrt(np.mean(arr * arr)))
    peak = int(np.max(np.abs(arr)))
    if peak < 700 or rms < 100:
        continue
    path = scratch / f'arthur_live_instruction_{count:04d}.wav'
    wavfile.write(str(path), fs, audio)
    segments, info = model.transcribe(str(path), beam_size=1, vad_filter=True)
    text = ' '.join(s.text.strip() for s in segments).strip()
    if text:
        emit(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] Rin said: {text}')
