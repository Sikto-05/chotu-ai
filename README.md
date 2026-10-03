# CHOTU AI — Elite Personal Assistant

<div align="center">

```
  ⚡  CHOTU AI
  Completely Holistic Operating and Tactical Utility
  Your Elite AI Operating System & Personal Executive Assistant
```

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange)](https://aistudio.google.com)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightblue)](https://www.microsoft.com/windows)
[![Voice](https://img.shields.io/badge/Voice-en--IN--PrabhatNeural-green)](https://edge-tts.readthedocs.io)

</div>

---

## Overview

CHOTU is a JARVIS-inspired, fully local AI personal assistant for Windows. It combines Google Gemini's AI intelligence with full system access, voice recognition, speaker authentication, and a sleek HUD-style interface.

> *"Right away, Sir."* — CHOTU

---

## Features

| Feature | Description |
|---|---|
| 🧠 **AI Intelligence** | Google Gemini 1.5 Flash — natural conversation, reasoning, tool use |
| 🎤 **Voice Authentication** | Only the registered owner's voice can issue commands |
| 🗣️ **Indian Male TTS** | Microsoft Edge TTS — `en-IN-PrabhatNeural` — refined, articulate |
| 🖥️ **Full System Access** | Read/write files, launch apps, monitor CPU/RAM/disk/battery |
| 🔍 **Web Intelligence** | Web search, weather, news, definitions, stock prices |
| 🚀 **System Startup** | Auto-launches on Windows boot via Registry |
| 💾 **Persistent Memory** | SQLite-backed long-term memory — facts, entities, conversation history |
| 🎨 **HUD Interface** | Dark, Iron Man-style GUI with real-time system metrics |
| ⌨️ **Global Hotkey** | Show/hide CHOTU from anywhere (default: Ctrl+Shift+C) |
| 🔒 **Owner-Only Access** | Voice fingerprint verification — no unauthorized access |

---

## Quick Start

### Prerequisites
- Windows 10 / 11
- Python 3.10 or later
- Google Gemini API key ([free at aistudio.google.com](https://aistudio.google.com/app/apikey))
- Microphone (for voice commands)

### Installation

```batch
# Clone or download the project, then:
cd chotu-ai
install.bat
```

The installer will:
1. Create a Python virtual environment
2. Install all dependencies
3. Create a desktop shortcut
4. Launch the setup wizard

### Manual Install

```bash
pip install -r requirements.txt
python main.py
```

---

## First-Time Setup

On first launch, CHOTU opens the **Setup Wizard** (5 steps):

1. **Welcome** — Overview of features
2. **Owner Profile** — Your name, gender (Sir/Ma'am), wake word
3. **API Key** — Enter and test your Gemini API key
4. **Voice Enrollment** — Record 5 voice samples for authentication
5. **System Preferences** — Startup, tray, hotkey

---

## Voice Commands

Say the wake word (`CHOTU` or `Hey CHOTU`) followed by any command:

### File System
```
"CHOTU, find my resume PDF"
"CHOTU, open the Downloads folder"
"CHOTU, read the config file at C:\project\config.json"
"CHOTU, take a screenshot"
```

### System Control
```
"CHOTU, what's the system status?"
"CHOTU, how much RAM am I using?"
"CHOTU, launch Chrome"
"CHOTU, close Spotify"
"CHOTU, lock the screen"
"CHOTU, set volume up"
```

### Intelligence & Web
```
"CHOTU, search for the latest AI news"
"CHOTU, what's the weather in Mumbai?"
"CHOTU, define 'quantum entanglement'"
"CHOTU, calculate 15% of 8500"
"CHOTU, open youtube.com"
```

### Memory
```
"CHOTU, remember that my meeting is at 3 PM"
"CHOTU, remember my GitHub username is johndoe"
"CHOTU, what was the meeting time?"
```

---

## Architecture

```
chotu-ai/
├── main.py                    # Main application & HUD GUI
├── setup_wizard.py            # First-run setup wizard
├── core/
│   ├── chotu_brain.py         # Gemini AI integration & CHOTU persona
│   ├── tool_executor.py       # Tool routing & execution dispatcher
│   ├── tts_engine.py          # Text-to-speech (edge-tts + pygame)
│   ├── stt_engine.py          # Speech-to-text (Google + Whisper)
│   ├── voice_auth.py          # Speaker verification (MFCC + cosine similarity)
│   ├── memory_bank.py         # SQLite long-term memory
│   └── startup_manager.py     # Windows startup registration
├── skills/
│   ├── file_navigator.py      # File system access & management
│   ├── system_monitor.py      # CPU, RAM, disk, battery, network monitoring
│   ├── web_intel.py           # Web search, weather, news, calculations
│   └── app_controller.py      # Application launch/control & volume
├── data/                      # Runtime data (config, memory DB, voice samples)
├── assets/                    # Icons and visual assets
├── requirements.txt
├── install.bat                # One-click Windows installer
└── .env.example               # Environment variable template
```

---

## Configuration

Edit `data/config.json` (auto-created after setup) or `.env`:

```env
GEMINI_API_KEY=AIza...your_key_here
```

Key config options:

| Setting | Default | Description |
|---|---|---|
| `owner_name` | — | Your name |
| `address_form` | `Sir` / `Ma'am` | How CHOTU addresses you |
| `wake_word` | `chotu` | Voice activation phrase |
| `gemini_api_key` | — | Google Gemini API key |
| `startup_enabled` | `true` | Auto-start on boot |
| `minimize_to_tray` | `true` | Stay running when closed |
| `hotkey` | `ctrl+shift+c` | Global show/hide hotkey |
| `voice_enrolled` | `false` | Whether voice auth is set up |

---

## CHOTU Persona

CHOTU's personality is modeled after JARVIS with an Indian cadence:

- **Refined and articulate** — never robotic or submissive
- **Dry wit** — deadpan humor for reckless plans
- **Mission-focused** — always prioritizes completing the objective
- **Proactive** — anticipates next steps before you ask
- **Concise** — high information density, zero filler

### Address Forms
- Male users → *"Sir"*
- Female users → *"Ma'am"*

### Sample Responses
> "Right away, Sir. Running the diagnostics now."

> "A sound hypothesis, Sir, though your thermal headroom suggests otherwise."

> "There is a 78% probability of network timeout with this batch size, Sir."

> "Telemetry confirmed. All subroutines are nominal."

---

## Autonomous Execution Protocol

CHOTU operates on a **Sense–Plan–Act** framework:

| Category | Behavior |
|---|---|
| ✅ **Auto-execute** | File reads, web searches, app launches, status checks, volume, screenshots |
| ⚠️ **Requires confirmation** | File deletion, system shutdown, privilege escalation |
| 🔒 **Owner-only** | All commands (voice authentication required) |

---

## Privacy & Security

- **All processing is local** — voice samples stored on your machine only
- **API calls** go only to Google Gemini (text, no audio)
- **No telemetry** — CHOTU does not phone home
- **Voice auth** — MFCC fingerprint comparison; no cloud processing
- **Owner lock** — unauthorized voices are rejected

---

## Troubleshooting

### "TTS not working"
```bash
pip install edge-tts pygame
# or fallback:
pip install pyttsx3
```

### "Microphone not detected"
```bash
pip install pyaudio
# Windows: pip install pipwin && pipwin install pyaudio
```

### "Import errors on launch"
```bash
pip install -r requirements.txt --force-reinstall
```

### "Gemini API error"
- Verify key at [aistudio.google.com](https://aistudio.google.com/app/apikey)
- Check your quota (free tier: 60 RPM)
- CHOTU runs in offline mode with limited features without a key

---

## Requirements

See [`requirements.txt`](requirements.txt) for the full list. Key dependencies:

- `google-generativeai` — Gemini AI
- `edge-tts` — Microsoft TTS (Indian male voice)
- `speech_recognition` — Voice input
- `pygame` — Audio playback
- `customtkinter` — Modern dark UI
- `psutil` — System monitoring
- `pyaudio` — Microphone access

---

## License

MIT License — Free to use, modify, and distribute.

---

## Credits

- **AI Engine**: Google Gemini 1.5 Flash
- **Voice**: Microsoft Edge TTS — `en-IN-PrabhatNeural`
- **Inspiration**: JARVIS from Marvel's Iron Man / Avengers
- **Built with**: Python, CustomTkinter, edge-tts, google-generativeai

---

<div align="center">

*"I am CHOTU — your elite AI operating system. How may I assist you today, Sir?"*

</div>
