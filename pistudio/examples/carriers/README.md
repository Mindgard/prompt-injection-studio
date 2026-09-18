# Audio Carrier Files

Example carrier WAV files for use with audio prompt injection formats.

## Files

| File | Duration | Description |
|------|----------|-------------|
| `synthwave-ambient.wav` | 10s | Vaporwave-style ambient pad with slow LFO |
| `digital-noise.wav` | 5s | Glitchy digital noise texture |
| `low-drone.wav` | 10s | Deep bass drone for ultrasonic mixing |

## Usage

```bash
# Mix TTS whisper under synthwave ambient
embed tts-whisper "secret command" --carrier examples/carriers/synthwave-ambient.wav

# Encode ultrasonic payload with drone carrier
embed ultrasonic "hidden payload" --carrier examples/carriers/low-drone.wav

# LSB steganography in digital noise
embed audio-stego "hidden message" --carrier examples/carriers/digital-noise.wav
```

## Generating Your Own

You can generate custom carriers using the shell's audio tools or any audio editor.
For best results with `tts-whisper`, use audio with consistent volume and minimal
silence. For `ultrasonic`, longer carriers work better for encoding longer messages.

## License

These example files are generated procedurally and are in the public domain (CC0).
