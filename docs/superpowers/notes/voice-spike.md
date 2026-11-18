# Voice spike result (2026-11-18)

- macOS speech output: `say -v Milena` works (verified here, Russian voice present).
- Windows speech output: `pyttsx3` (SAPI) with a Russian voice if installed; NOT verified, the author must run `python scripts/spike_voice.py speak` on the target PC. If no Russian voice, the robot stays silent and text on screen is the only output.
- Speech recognition: the `SpeechRecognition` + Google endpoint needs PyAudio (native build) and sends audio to a third party; rejected for a packaged app. NOT tested.

Decision for v1: `PlatformServices.listen()` returns None, so the UI always shows the big text field
with a hint to use system dictation (Windows: Win+H, which the app presses via pyautogui on the mic button;
macOS: Fn twice, the user presses it). Real in-app recognition is deferred.
