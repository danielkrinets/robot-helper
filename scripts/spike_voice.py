"""THROWAWAY spike: which voice approach works per OS. Not shipped."""
import subprocess
import sys


def speak_probe(text="Привет, я ваш робот-помощник"):
    if sys.platform == "darwin":
        subprocess.run(["say", "-v", "Milena", text], check=True)
    elif sys.platform == "win32":
        import pyttsx3  # pip install pyttsx3

        engine = pyttsx3.init()
        ru = [v for v in engine.getProperty("voices") if "ru" in (v.id + v.name).lower()]
        print("Russian voices:", [v.name for v in ru] or "NONE (fallback: no speech)")
        if ru:
            engine.setProperty("voice", ru[0].id)
        engine.say(text)
        engine.runAndWait()


def listen_probe():
    import speech_recognition as sr  # pip install SpeechRecognition pyaudio

    r = sr.Recognizer()
    with sr.Microphone() as src:
        print("Говорите...")
        audio = r.listen(src, timeout=8, phrase_time_limit=10)
    print("Heard:", r.recognize_google(audio, language="ru-RU"))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "speak"
    {"speak": speak_probe, "listen": listen_probe}[which]()
