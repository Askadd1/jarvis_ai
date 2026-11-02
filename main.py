import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime

import requests

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover - optional dependency for voice input
    sr = None

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover - optional dependency for speech output
    gTTS = None

try:
    import pyttsx3
except ImportError:  # pragma: no cover - optional offline speech output
    pyttsx3 = None

try:
    import playsound
except ImportError:  # pragma: no cover - optional dependency for local audio playback
    playsound = None

import musicLibrary

newsapi = os.environ.get("NEWSAPI_KEY", "")
speech_engine = None
ui_events = None
ui_speech_requests = None
ui_thread_id = None
managed_browser_windows = {}


def find_managed_browser():
    candidates = (
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Google", "Chrome", "Application", "chrome.exe",
        ),
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Google", "Chrome", "Application", "chrome.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google", "Chrome", "Application", "chrome.exe",
        ),
    )
    return next((path for path in candidates if os.path.isfile(path)), None)


def open_managed_site(site, url):
    browser = find_managed_browser()
    if browser is None:
        raise FileNotFoundError(
            "Microsoft Edge or Google Chrome is required to open a Jarvis-managed window."
        )

    profile = tempfile.TemporaryDirectory(prefix="jarvis_browser_")
    try:
        process = subprocess.Popen(
            [
                browser,
                f"--user-data-dir={profile.name}",
                "--no-first-run",
                "--disable-sync",
                f"--app={url}",
            ]
        )
    except Exception:
        profile.cleanup()
        raise

    managed_browser_windows.setdefault(site, []).append((process, profile))


def close_managed_browser(process):
    if process.poll() is None and os.name == "nt":
        import ctypes

        user32 = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_ssize_t
        )
        windows = []

        def find_process_window(hwnd, _):
            process_id = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            if process_id.value == process.pid:
                windows.append(hwnd)
            return True

        callback = callback_type(find_process_window)
        user32.EnumWindows(callback, 0)
        for hwnd in windows:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)

    if process.poll() is None:
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def close_managed_sites(site=None):
    sites = [site] if site is not None else list(managed_browser_windows)
    closed = []
    errors = []

    for site_name in sites:
        windows = managed_browser_windows.get(site_name, [])
        pending = []
        for process, profile in windows:
            try:
                close_managed_browser(process)
                profile.cleanup()
                closed.append(site_name)
            except Exception as exc:
                errors.append(f"{site_name}: {exc}")
                pending.append((process, profile))
        if pending:
            managed_browser_windows[site_name] = pending
        else:
            managed_browser_windows.pop(site_name, None)

    if errors:
        raise RuntimeError("Could not close all Jarvis browser windows: " + "; ".join(errors))
    return closed


def notify_ui(event, value):
    if ui_events is not None:
        ui_events.put((event, value))


def normalize_text(text):
    return (text or "").lower().strip().replace("?", "")


def play_speech(text):
    global speech_engine

    try:
        if pyttsx3 is not None:
            if speech_engine is None:
                speech_engine = pyttsx3.init()
                speech_engine.setProperty("rate", 185)
                speech_engine.setProperty("volume", 1.0)
                voices = speech_engine.getProperty("voices")
                english_voice = next(
                    (
                        voice
                        for voice in voices
                        if "zira" in voice.name.lower()
                    ),
                    None,
                )
                if english_voice is not None:
                    speech_engine.setProperty("voice", english_voice.id)
            speech_engine.say(text)
            speech_engine.runAndWait()
            return
    except Exception as exc:
        print(f" Offline TTS error: {exc}")

    if gTTS is None:
        print(" TTS unavailable; install pyttsx3 or gTTS to enable spoken responses.")
        return

    try:
        filename = "temp_voice.mp3"
        gTTS(text=text, lang="en").save(filename)
        if playsound is not None:
            playsound.playsound(filename)
        else:
            print(" Audio playback unavailable; skipping generated speech file.")
        if os.path.exists(filename):
            os.remove(filename)
    except Exception as exc:
        print(f" TTS error: {exc}")


def speak(text):
    text = (text or "").strip()
    if not text:
        return
    print(f" Speaking: {text}")
    notify_ui("reply", text)
    notify_ui("status", "Speaking")

    if ui_speech_requests is not None and threading.get_ident() != ui_thread_id:
        completed = threading.Event()
        ui_speech_requests.put((text, completed))
        if not completed.wait(timeout=60):
            print(" TTS error: timed out waiting for the dashboard speech player.")
        return

    play_speech(text)


def processCommand(command):
    command = normalize_text(command)
    command = command.strip(" ,.!?:;")
    if command.startswith("jarvis "):
        command = command[len("jarvis "):].strip()
    print(f" Command: {command}")

    if not command:
        return True

    notify_ui("command", command)

    if command in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        speak("Hello! It's nice to talk with you. What can I do for you?")

    elif command in {"how are you", "how are you doing"}:
        speak("I'm doing well, thanks for asking. How can I help you?")

    elif command in {"what is your name", "who are you", "what are you"}:
        speak("I'm Jarvis, your voice assistant. I can open websites, play music, and share the news.")

    elif command in {"what time is it", "tell me the time", "current time", "time"}:
        speak(f"It's {datetime.now().strftime('%I:%M %p').lstrip('0')}.")

    elif command in {"what is the date", "what's the date", "tell me the date", "today's date", "date"}:
        speak(f"Today is {datetime.now().strftime('%A, %B %d, %Y')}.")

    elif command in {"thank you", "thanks", "thanks jarvis"}:
        speak("You're welcome! I'm happy to help.")

    elif command in {"help", "what can you do", "what can i ask you"}:
        speak(
            "You can ask me to open Google, YouTube, or GitHub; play a song; "
            "read the news; tell you the time or date; or just chat with me."
        )

    elif command in {"goodbye", "bye", "stop", "exit", "quit"}:
        speak("Goodbye! I'll be here when you need me.")
        return False

    elif command.startswith("close "):
        target = command[len("close "):].strip()
        if target.startswith("the "):
            target = target[len("the "):]

        if target in {
            "all", "all sites", "all websites", "all browser windows",
            "browser", "browser windows", "sites", "websites",
        }:
            try:
                closed = close_managed_sites()
            except RuntimeError as exc:
                print(f"Browser close error: {exc}")
                speak("I couldn't close every Jarvis website window.")
            else:
                if closed:
                    speak(f"Closed {len(closed)} Jarvis-opened website window(s).")
                else:
                    speak("There are no Jarvis-opened website windows to close.")
        elif target in {"google", "youtube", "github"}:
            try:
                closed = close_managed_sites(target)
            except RuntimeError as exc:
                print(f"Browser close error: {exc}")
                speak(f"I couldn't close the Jarvis-opened {target} window.")
            else:
                if closed:
                    speak(f"Closed the Jarvis-opened {target} window.")
                else:
                    speak(f"I don't have a Jarvis-opened {target} window to close.")
        elif target in {name.lower() for name in musicLibrary.music}:
            try:
                closed = close_managed_sites(f"music:{target}")
            except RuntimeError as exc:
                print(f"Browser close error: {exc}")
                speak(f"I couldn't close the Jarvis-opened music window for {target}.")
            else:
                if closed:
                    speak(f"Closed the Jarvis-opened music window for {target}.")
                else:
                    speak(f"I don't have a Jarvis-opened music window for {target}.")
        else:
            speak(
                "I can close Google, YouTube, GitHub, a song window, or all "
                "websites opened by Jarvis. I won't close other apps or tabs."
            )

    elif "open google" in command:
        try:
            open_managed_site("google", "https://www.google.com")
        except OSError as exc:
            print(f"Browser launch error: {exc}")
            speak("I couldn't open Google. Please check that Edge or Chrome is installed.")
        else:
            speak("Opening Google")

    elif "open youtube" in command:
        try:
            open_managed_site("youtube", "https://www.youtube.com")
        except OSError as exc:
            print(f"Browser launch error: {exc}")
            speak("I couldn't open YouTube. Please check that Edge or Chrome is installed.")
        else:
            speak("Opening YouTube")

    elif "open github" in command:
        try:
            open_managed_site("github", "https://www.github.com")
        except OSError as exc:
            print(f"Browser launch error: {exc}")
            speak("I couldn't open GitHub. Please check that Edge or Chrome is installed.")
        else:
            speak("Opening GitHub")

    elif command.startswith("play"):
        parts = command.split()
        if len(parts) > 1:
            song = " ".join(parts[1:]).lower()
            music_lower = {k.lower(): v for k, v in musicLibrary.music.items()}

            if song in music_lower:
                try:
                    open_managed_site(f"music:{song}", music_lower[song])
                except OSError as exc:
                    print(f"Browser launch error: {exc}")
                    speak("I couldn't open the music link. Please check that Edge or Chrome is installed.")
                else:
                    speak(f"Playing {song}")
            else:
                speak("Sorry, I don't have that song")
        else:
            speak("Please tell me which song to play")

    elif "news" in command:
        try:
            response = requests.get(
                f"https://newsapi.org/v2/top-headlines?country=us&apiKey={newsapi}",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                articles = data.get("articles", [])
                if not articles:
                    speak("No news found.")
                else:
                    speak("Here are the top headlines")
                    for i, article in enumerate(articles[:5], start=1):
                        title = article.get("title", "No title")
                        print(f"{i}. {title}")
                        speak(title)
                        time.sleep(0.3)
            else:
                speak("Sorry, I couldn't fetch the news")
        except Exception as exc:
            print(f"Error fetching news: {exc}")
            speak("There was a problem fetching the news")
    else:
        speak("I'm not sure how to help with that yet. Say 'help' to hear what I can do.")

    return True


def run_command_mode():
    print("Microphone support is unavailable, so Jarvis is running in terminal command mode.")
    print("Type a command such as 'open google', 'play believer', 'news', or 'exit'.")
    while True:
        try:
            command = input("Jarvis> ")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
        if not processCommand(command):
            break


def listen_for_commands(stop_event, command_queue):
    if sr is None:
        notify_ui("error", "SpeechRecognition is missing. Install it with: python -m pip install SpeechRecognition")
        return

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 0.6
    speak("Jarvis is ready. You can speak a command.")

    try:
        with sr.Microphone() as source:
            print("Calibrating microphone for background noise...")
            notify_ui("status", "Calibrating microphone...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Calibration complete. Speak a command.")
            notify_ui("status", "Listening for a command")

            while not stop_event.is_set():
                try:
                    command = command_queue.get_nowait()
                except queue.Empty:
                    command = None

                if command is not None:
                    if not processCommand(command):
                        stop_event.set()
                        notify_ui("status", "Jarvis stopped")
                        break
                    notify_ui("status", "Listening for a command")
                    continue

                print("Listening for a command...")
                try:
                    audio = recognizer.listen(source, timeout=1, phrase_time_limit=7)
                    command = recognizer.recognize_google(audio)
                    print(f" Heard: {command}")
                    notify_ui("heard", command)
                    if not processCommand(command):
                        stop_event.set()
                        notify_ui("status", "Jarvis stopped")
                        break
                    notify_ui("status", "Listening for a command")
                except sr.UnknownValueError:
                    print("Speech was not clear enough to recognize.")
                    notify_ui("status", "Listening for a command")
                except sr.RequestError as exc:
                    print(f"Speech recognition service error: {exc}")
                    notify_ui("error", f"Speech recognition error: {exc}")
                    time.sleep(2)
                except sr.WaitTimeoutError:
                    continue
    except Exception as exc:
        print(f"Microphone error: {exc}")
        notify_ui("error", f"Microphone error: {exc}")
    finally:
        if stop_event.is_set():
            notify_ui("status", "Jarvis stopped")


def run_visual_assistant():
    global ui_events, ui_speech_requests, ui_thread_id

    try:
        import tkinter as tk
    except ImportError as exc:
        raise SystemExit(f"Tkinter is unavailable; cannot show Jarvis window: {exc}") from exc

    ui_events = queue.Queue()
    ui_speech_requests = queue.Queue()
    ui_thread_id = threading.get_ident()
    stop_event = threading.Event()
    command_queue = queue.Queue()
    root = tk.Tk()
    root.title("Jarvis Assistant")
    root.geometry("900x700")
    root.minsize(760, 620)
    root.configure(bg="#08111f")

    background = "#08111f"
    panel = "#101d2d"
    panel_alt = "#142438"
    text_primary = "#e8f4ff"
    text_muted = "#8298ae"
    accent = "#42d9ff"

    header = tk.Frame(root, bg=background)
    header.pack(fill="x", padx=30, pady=(22, 16))
    brand = tk.Frame(header, bg=background)
    brand.pack(side="left")
    tk.Label(
        brand, text="J", font=("Segoe UI", 22, "bold"),
        fg=accent, bg=background,
    ).pack(side="left", padx=(0, 10))
    title_box = tk.Frame(brand, bg=background)
    title_box.pack(side="left")
    tk.Label(
        title_box, text="JARVIS", font=("Segoe UI", 19, "bold"),
        fg=text_primary, bg=background,
    ).pack(anchor="w")
    tk.Label(
        title_box, text="PERSONAL VOICE ASSISTANT", font=("Segoe UI", 8, "bold"),
        fg=text_muted, bg=background,
    ).pack(anchor="w")

    live_badge = tk.Label(
        header, text="●  STARTING", font=("Segoe UI", 9, "bold"),
        fg="#a6b8ca", bg=panel, padx=14, pady=8,
    )
    live_badge.pack(side="right", pady=6)

    content = tk.Frame(root, bg=background)
    content.pack(fill="both", expand=True, padx=30)
    content.grid_columnconfigure(0, weight=4)
    content.grid_columnconfigure(1, weight=5)
    content.grid_rowconfigure(0, weight=1)

    visual_card = tk.Frame(content, bg=panel)
    visual_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
    tk.Label(
        visual_card, text="VOICE STATUS", font=("Segoe UI", 9, "bold"),
        fg=text_muted, bg=panel,
    ).pack(anchor="w", padx=22, pady=(20, 0))

    canvas = tk.Canvas(
        visual_card, width=300, height=300, bg=panel, highlightthickness=0
    )
    canvas.pack(fill="both", expand=True, padx=10, pady=(0, 0))
    canvas.create_oval(44, 30, 256, 242, outline="#1c4056", width=1)
    canvas.create_oval(61, 47, 239, 225, outline="#1b344a", width=1)
    outer_orb = canvas.create_oval(
        78, 64, 222, 208, fill="#122d43", outline=accent, width=2
    )
    mid_orb = canvas.create_oval(
        91, 77, 209, 195, fill="#10243a", outline="#2584a7", width=2
    )
    inner_orb = canvas.create_oval(
        106, 92, 194, 180, fill="#0b192a", outline="#8cecff", width=1
    )
    canvas.create_text(
        150, 136, text="J", fill="#d5faff", font=("Segoe UI", 38, "bold")
    )

    status_label = tk.Label(
        visual_card, text="Starting Jarvis...", font=("Segoe UI", 13, "bold"),
        fg=accent, bg=panel,
    )
    status_label.pack(pady=(0, 5))
    tk.Label(
        visual_card, text="Speak naturally — no wake word needed",
        font=("Segoe UI", 9), fg=text_muted, bg=panel,
    ).pack(pady=(0, 20))

    conversation_card = tk.Frame(content, bg=panel)
    conversation_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    conversation_card.grid_rowconfigure(1, weight=1)
    conversation_card.grid_columnconfigure(0, weight=1)
    conversation_header = tk.Frame(conversation_card, bg=panel)
    conversation_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 12))
    tk.Label(
        conversation_header, text="CONVERSATION", font=("Segoe UI", 9, "bold"),
        fg=text_muted, bg=panel,
    ).pack(side="left")
    tk.Label(
        conversation_header, text="Live transcript", font=("Segoe UI", 9),
        fg="#59718a", bg=panel,
    ).pack(side="right")

    transcript_frame = tk.Frame(conversation_card, bg=panel_alt)
    transcript_frame.grid(
        row=1, column=0, sticky="nsew", padx=18, pady=(0, 18)
    )
    transcript_frame.grid_rowconfigure(0, weight=1)
    transcript_frame.grid_columnconfigure(0, weight=1)
    transcript = tk.Text(
        transcript_frame, bg=panel_alt, fg=text_primary, insertbackground=accent,
        relief="flat", wrap="word", padx=16, pady=14, state="disabled",
        font=("Segoe UI", 10), spacing1=5, spacing3=9,
    )
    transcript.grid(row=0, column=0, sticky="nsew")
    scrollbar = tk.Scrollbar(
        transcript_frame, command=transcript.yview,
        bg=panel_alt, troughcolor=panel_alt, relief="flat",
    )
    scrollbar.grid(row=0, column=1, sticky="ns")
    transcript.configure(yscrollcommand=scrollbar.set)
    transcript.tag_configure("user", foreground=accent, font=("Segoe UI", 9, "bold"))
    transcript.tag_configure("jarvis", foreground="#c9a7ff", font=("Segoe UI", 9, "bold"))
    transcript.tag_configure("body", foreground=text_primary)
    transcript.tag_configure("system", foreground=text_muted, font=("Segoe UI", 9, "italic"))

    def add_transcript(speaker, message, tag):
        transcript.configure(state="normal")
        transcript.insert("end", f"{speaker}\n", tag)
        transcript.insert("end", f"{message}\n\n", "body")
        transcript.configure(state="disabled")
        transcript.see("end")

    state = {"status": "Starting Jarvis...", "pulse": 0}
    colors = {
        "listening": ("#122d43", "#42d9ff", "#8cecff"),
        "speaking": ("#332748", "#b58cff", "#e0ccff"),
        "error": ("#4a242c", "#ff687d", "#ffc2cb"),
        "default": ("#122d43", "#42d9ff", "#8cecff"),
    }

    controls = tk.Frame(root, bg=background)
    controls.pack(fill="x", padx=30, pady=(16, 24))
    command_entry = tk.Entry(
        controls, font=("Segoe UI", 11), bg=panel_alt, fg=text_primary,
        insertbackground=accent, relief="flat",
    )
    command_entry.pack(side="left", fill="x", expand=True, ipady=12, padx=(0, 10))
    command_entry.insert(0, "Type a command...")
    command_entry.config(fg=text_muted)

    def clear_placeholder(_event=None):
        if command_entry.get() == "Type a command...":
            command_entry.delete(0, "end")
            command_entry.config(fg=text_primary)

    def restore_placeholder(_event=None):
        if not command_entry.get():
            command_entry.insert(0, "Type a command...")
            command_entry.config(fg=text_muted)

    command_entry.bind("<FocusIn>", clear_placeholder)
    command_entry.bind("<FocusOut>", restore_placeholder)

    def submit_text_command(_event=None):
        command = command_entry.get().strip()
        if command and command != "Type a command...":
            command_queue.put(command)
            add_transcript("YOU · TEXT", command, "user")
            command_entry.delete(0, "end")
            command_entry.config(fg=text_primary)
            root.after(100, command_entry.focus_set)

    command_entry.bind("<Return>", submit_text_command)
    send_button = tk.Button(
        controls, text="SEND", command=submit_text_command,
        font=("Segoe UI", 9, "bold"), fg="#06111c", bg=accent,
        activeforeground="#06111c", activebackground="#8cecff",
        relief="flat", cursor="hand2", padx=20, pady=10,
    )
    send_button.pack(side="right")

    quick_actions = tk.Frame(root, bg=background)
    quick_actions.pack(fill="x", padx=30, pady=(0, 22))
    tk.Label(
        quick_actions, text="QUICK COMMANDS", font=("Segoe UI", 8, "bold"),
        fg=text_muted, bg=background,
    ).pack(side="left", padx=(0, 14))
    for label, command in (
        ("Google", "open google"),
        ("YouTube", "open youtube"),
        ("Help", "help"),
        ("Time", "what time is it"),
    ):
        tk.Button(
            quick_actions, text=label,
            command=lambda value=command: command_queue.put(value),
            font=("Segoe UI", 9, "bold"), fg="#c4d5e5", bg=panel,
            activeforeground=text_primary, activebackground=panel_alt,
            relief="flat", cursor="hand2", padx=14, pady=8,
        ).pack(side="left", padx=(0, 8))

    def update_window():
        try:
            while True:
                text, completed = ui_speech_requests.get_nowait()
                try:
                    play_speech(text)
                finally:
                    completed.set()
        except queue.Empty:
            pass

        try:
            while True:
                event, value = ui_events.get_nowait()
                if event == "status":
                    state["status"] = value
                    status_label.config(text=value)
                    if "error" in value.lower():
                        live_badge.config(text="●  ATTENTION", fg="#ff8292")
                    elif "listen" in value.lower():
                        live_badge.config(text="●  LISTENING", fg=accent)
                    elif "speak" in value.lower():
                        live_badge.config(text="●  SPEAKING", fg="#c9a7ff")
                    else:
                        live_badge.config(text="●  ACTIVE", fg="#93e6b4")
                elif event == "heard":
                    add_transcript("YOU · VOICE", value, "user")
                elif event == "command":
                    pass
                elif event == "reply":
                    add_transcript("JARVIS", value, "jarvis")
                elif event == "error":
                    state["status"] = "Microphone error"
                    status_label.config(text=value, fg="#ff687d")
                    live_badge.config(text="●  ATTENTION", fg="#ff8292")
                    add_transcript("SYSTEM", value, "system")
        except queue.Empty:
            pass

        state["pulse"] += 1
        pulse = state["pulse"] % 32
        status = state["status"].lower()
        color_key = (
            "error" if "error" in status else
            "speaking" if "speak" in status else
            "listening" if "listen" in status else
            "default"
        )
        fill, outline, inner = colors[color_key]
        inset = (pulse // 4) if color_key == "listening" else 0
        canvas.coords(outer_orb, 78 - inset, 64 - inset, 222 + inset, 208 + inset)
        canvas.coords(mid_orb, 91 - inset, 77 - inset, 209 + inset, 195 + inset)
        canvas.itemconfig(outer_orb, fill=fill, outline=outline)
        canvas.itemconfig(mid_orb, outline=inner)
        root.after(100, update_window)

    def close_window():
        stop_event.set()
        try:
            close_managed_sites()
        except RuntimeError as exc:
            print(f"Could not close Jarvis browser windows: {exc}")
        while not ui_speech_requests.empty():
            try:
                _, completed = ui_speech_requests.get_nowait()
                completed.set()
            except queue.Empty:
                break
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    threading.Thread(
        target=listen_for_commands, args=(stop_event, command_queue), daemon=True
    ).start()
    update_window()
    root.mainloop()


if __name__ == "__main__":
    if "--terminal" in sys.argv[1:]:
        run_command_mode()
    else:
        try:
            import pyaudio  # noqa: F401
        except ImportError:
            raise SystemExit(
                "PyAudio is missing. Install it with: python -m pip install PyAudio\n"
                "Or run: python main.py --terminal"
            )
        run_visual_assistant()
