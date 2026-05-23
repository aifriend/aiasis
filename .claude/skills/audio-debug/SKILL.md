# Audio Debug Skill

## Trigger

Use when the user reports audio problems: device not found, no input, can't hear playback, AirPods not working, low quality mic, "no sound", "silence", sounddevice errors.

## Quick Diagnostics

### 1. List all audio devices

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Look for:
- AirPods entries (usually two: one input, one output)
- Built-in Microphone / MacBook Pro Microphone
- Default device markers `>` (input) and `<` (output)

### 2. Test mic capture (5 seconds)

```bash
python -c "
import sounddevice as sd
import numpy as np
print('Recording 5s from default input...')
audio = sd.rec(int(16000 * 5), samplerate=16000, channels=1, dtype='int16', blocking=True)
peak = np.max(np.abs(audio))
rms = np.sqrt(np.mean(audio.astype(float)**2))
print(f'Peak: {peak} | RMS: {rms:.1f}')
if peak < 100:
    print('⚠ Very low levels — mic may be muted or wrong device')
elif peak < 1000:
    print('⚠ Low levels — check mic gain or distance')
else:
    print('✓ Audio levels look good')
"
```

### 3. Test mic on specific device

```bash
python -c "
import sounddevice as sd
import numpy as np
DEVICE_ID = 2  # <-- change this
print(f'Recording 5s from device {DEVICE_ID}...')
audio = sd.rec(int(16000 * 5), samplerate=16000, channels=1, dtype='int16', device=DEVICE_ID, blocking=True)
peak = np.max(np.abs(audio))
print(f'Peak: {peak}')
print('✓ OK' if peak > 1000 else '⚠ Low/silent')
"
```

### 4. Test playback on specific device

```bash
python -c "
import sounddevice as sd
import numpy as np
DEVICE_ID = 4  # <-- change this
t = np.linspace(0, 1, 16000, dtype='float32')
tone = 0.3 * np.sin(2 * np.pi * 440 * t)
print(f'Playing 440Hz tone on device {DEVICE_ID}...')
sd.play(tone, samplerate=16000, device=DEVICE_ID, blocking=True)
print('Done. Did you hear the tone?')
"
```

### 5. Check ffmpeg (required for TTS decode)

```bash
ffmpeg -version 2>/dev/null | head -1 || echo "⚠ ffmpeg not found — install with: brew install ffmpeg"
```

## Common Issues

### AirPods SCO codec (low quality mic)

**Symptom**: AirPods mic works but audio is 8kHz/mono, sounds like a phone call.

**Cause**: When AirPods are used as both input AND output, macOS switches to SCO (Bluetooth hands-free) codec which is low quality.

**Fix**: Use Mac built-in mic for input, AirPods for output only:
```bash
python src/main.py --input-device 0 --output-device 4
```
Where device 0 is the built-in mic and device 4 is AirPods output.

### "Device unavailable" or "Invalid number of channels"

- Device was disconnected. Re-pair AirPods, then re-list devices.
- Device index changed. Always re-check `python -m sounddevice` after reconnecting.

### No audio input detected (peak = 0)

1. Check macOS System Settings → Privacy & Security → Microphone → Terminal must be allowed
2. Try a different input device index
3. Check if another app is holding the mic exclusively

### Playback but no sound

1. Check macOS volume is not muted
2. Verify correct output device index
3. AirPods may have auto-switched to another device — check Bluetooth settings
