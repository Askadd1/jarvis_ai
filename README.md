<div align="center">

# ◈ J.A.R.V.I.S. AI
### PERSONAL VOICE ASSISTANT · PYTHON · DESKTOP

**Your desktop. Your voice. Your assistant.**

A Python-powered assistant with a live dashboard, voice controls, browser automation, music search, and real-time headlines.

</div>

---

## ⟡ What it can do

| MODULE | CAPABILITY |
| --- | --- |
| **VOICE** | Listen for commands and respond aloud |
| **DASHBOARD** | Use the graphical interface or type commands |
| **BROWSER** | Open and close managed Google, YouTube, and GitHub windows |
| **MUSIC** | Launch YouTube searches for tracks in your library |
| **NEWS** | Fetch top US headlines with NewsAPI |
| **UTILITY** | Ask for the time, date, or help |

## ⌘ Quick start

### 1 · Create your environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2 · Install the packages

```powershell
python -m pip install requests SpeechRecognition PyAudio pyttsx3 gTTS playsound
```

### 3 · Launch Jarvis

**Dashboard + voice input**

```powershell
python main.py
```

**Terminal mode · no microphone required**

```powershell
python main.py --terminal
```

> If PowerShell blocks environment activation, install and run with `.venv\Scripts\python.exe` instead.

## ◉ Command deck

```text
hello                 Start a conversation
what time is it       Get the current time
what is the date      Get today's date
open google           Open Google in a Jarvis window
open youtube          Open YouTube in a Jarvis window
open github           Open GitHub in a Jarvis window
play believer         Search the music library
news                  Fetch top US headlines
close youtube         Close a Jarvis-managed window
help                  See available commands
exit                  Quit terminal mode
```

Add tracks in [`musicLibrary.py`](musicLibrary.py) by adding a song name and its YouTube search URL to the `music` dictionary.

## ⚙ News module setup

The `news` command uses a NewsAPI key. Set it in PowerShell before launching Jarvis:

```powershell
$env:NEWSAPI_KEY = "your-newsapi-key"
python main.py
```

Keep your key private. Never commit it to the repository.

## ⌬ System requirements

- **Python 3.10+**
- **Windows** for the managed browser windows
- **Microsoft Edge or Google Chrome** for opening sites
- **Microphone + PyAudio** for voice input
- **SpeechRecognition** for speech recognition
- **pyttsx3** for offline speech, or **gTTS + playsound** for online speech output

## ◌ Notes

- Terminal mode accepts typed commands and does not need a microphone.
- The graphical voice mode requires PyAudio and a working microphone.
- `pyttsx3` speaks offline on supported systems. The `gTTS` fallback needs an internet connection.
- Browser commands open separate managed windows; use `close <site>` to close one opened by Jarvis.

---

<div align="center">

**BUILT WITH PYTHON · READY FOR YOUR NEXT COMMAND**

</div>
