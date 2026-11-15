"""Shared test setup.

`sounddevice` initialises PortAudio when it is imported and raises on machines
with no sound server (for example CI runners). No test opens a real audio
stream, so fall back to a stub module when the real one cannot be imported.
"""

import sys
import types

try:
    import sounddevice  # noqa: F401
except Exception:  # PortAudioError / OSError when no audio backend exists
    stub = types.ModuleType("sounddevice")
    stub.InputStream = type("InputStream", (), {})
    stub.query_devices = lambda *a, **k: []
    sys.modules["sounddevice"] = stub
