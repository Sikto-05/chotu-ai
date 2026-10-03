"""
CHOTU AI — Main Application
The HUD-style central interface for CHOTU AI personal assistant.
"""

import os
import sys
import json
import time
import asyncio
import logging
import threading
import datetime
from pathlib import Path

# Configure logging before other imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/chotu.log", mode="a", encoding="utf-8"),
    ]
)

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# ─── Colors & Fonts ──────────────────────────────────────────────────────────

COLORS = {
    "bg_dark":       "#070d1a",
    "bg_card":       "#0c1527",
    "bg_panel":      "#0f1e35",
    "accent_blue":   "#00d4ff",
    "accent_cyan":   "#00ffcc",
    "accent_gold":   "#ffd700",
    "accent_green":  "#00ff88",
    "accent_red":    "#ff4444",
    "accent_orange": "#ff8800",
    "text_primary":  "#ddeeff",
    "text_secondary": "#5a8aaa",
    "text_dim":      "#2a4a6a",
    "border":        "#1a3050",
    "border_bright": "#00d4ff44",
    "glow":          "#00d4ff22",
}

logger = logging.getLogger("CHOTU.Main")


class ChoutuApp:
    """
    Main CHOTU AI application window.
    Iron Man JARVIS-inspired HUD interface with voice control and AI chat.
    """

    def __init__(self, config: dict):
        self.config = config
        self.running = True
        self.is_listening = False
        self.is_speaking = False
        self.conversation_history = []
        self.session_id = None

        # Core modules
        self.brain = None
        self.tts = None
        self.stt = None
        self.voice_auth = None
        self.memory = None
        self.tool_executor = None

        # UI state
        self.pulse_angle = 0
        self.waveform_data = [0] * 60
        self._status_animation_id = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("CHOTU AI — Elite Personal Assistant")
        self.root.geometry("1100x750")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=COLORS["bg_dark"])

        try:
            icon_path = BASE_DIR / "assets" / "chotu.ico"
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
        except Exception:
            pass

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._initialize_systems_async()

        # Hotkey
        hotkey = config.get("hotkey", "ctrl+shift+c")
        self._register_hotkey(hotkey)

    # ─── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        """Construct the full HUD interface."""
        # Top bar
        self._build_topbar()

        # Main area: left sidebar + center + right panel
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # Left sidebar
        self._build_sidebar(main)

        # Center (chat)
        self._build_chat_panel(main)

        # Right panel
        self._build_right_panel(main)

        # Bottom input bar
        self._build_input_bar()

        # Status bar
        self._build_statusbar()

        # Start animations
        self._start_animations()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_card"], height=60, corner_radius=0)
        bar.pack(fill="x", pady=(0, 2))
        bar.pack_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=15, pady=10)

        ctk.CTkLabel(
            logo_frame, text="⚡",
            font=ctk.CTkFont(size=22),
            text_color=COLORS["accent_blue"]
        ).pack(side="left")

        ctk.CTkLabel(
            logo_frame, text=" CHOTU",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=COLORS["accent_blue"]
        ).pack(side="left")

        ctk.CTkLabel(
            logo_frame, text="  AI",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["text_secondary"]
        ).pack(side="left")

        # Center: owner name and time
        center_frame = ctk.CTkFrame(bar, fg_color="transparent")
        center_frame.pack(side="left", expand=True)

        owner = self.config.get("owner_name", "Owner")
        address = self.config.get("address_form", "Sir")
        ctk.CTkLabel(
            center_frame,
            text=f"Reporting to: {owner}  ({address})",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_secondary"]
        ).pack()

        self.time_label = ctk.CTkLabel(
            center_frame, text="",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=COLORS["accent_cyan"]
        )
        self.time_label.pack()

        # Right: controls
        controls = ctk.CTkFrame(bar, fg_color="transparent")
        controls.pack(side="right", padx=15)

        self.voice_toggle_btn = ctk.CTkButton(
            controls, text="🎤 Listening OFF",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
            border_width=1, hover_color=COLORS["bg_panel"],
            text_color=COLORS["text_secondary"], height=36, width=160,
            command=self._toggle_voice_listening
        )
        self.voice_toggle_btn.pack(side="right", padx=5)

        ctk.CTkButton(
            controls, text="⚙",
            font=ctk.CTkFont(size=16), width=36, height=36,
            fg_color="transparent", hover_color=COLORS["bg_panel"],
            text_color=COLORS["text_secondary"],
            command=self._show_settings
        ).pack(side="right")

    def _build_sidebar(self, parent):
        sidebar = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], width=220, corner_radius=10)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 5))
        sidebar.grid_propagate(False)

        # System metrics
        ctk.CTkLabel(
            sidebar, text="SYSTEM TELEMETRY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_dim"]
        ).pack(pady=(15, 8), padx=15, anchor="w")

        # CPU
        self._add_metric_widget(sidebar, "CPU", "cpu_bar", "cpu_label")
        self._add_metric_widget(sidebar, "RAM", "ram_bar", "ram_label")
        self._add_metric_widget(sidebar, "DISK", "disk_bar", "disk_label")

        # Battery
        self.battery_label = ctk.CTkLabel(
            sidebar, text="🔋 Battery: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"]
        )
        self.battery_label.pack(pady=(8, 0), padx=15, anchor="w")

        # Network
        self.network_label = ctk.CTkLabel(
            sidebar, text="🌐 Network: --",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"]
        )
        self.network_label.pack(pady=(4, 0), padx=15, anchor="w")

        # Divider
        ctk.CTkFrame(sidebar, fg_color=COLORS["border"], height=1).pack(fill="x", padx=15, pady=15)

        # Quick actions
        ctk.CTkLabel(
            sidebar, text="QUICK ACTIONS",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_dim"]
        ).pack(pady=(0, 8), padx=15, anchor="w")

        quick_actions = [
            ("📸 Screenshot", lambda: self._send_text_command("take a screenshot")),
            ("📋 Clipboard", lambda: self._send_text_command("read clipboard")),
            ("🌤 Weather", lambda: self._send_text_command("what is the weather in Delhi")),
            ("📰 News", lambda: self._send_text_command("give me top news headlines")),
            ("🖥 System", lambda: self._send_text_command("give me a full system report")),
            ("🔒 Lock", lambda: self._send_text_command("lock the screen")),
        ]

        for label, cmd in quick_actions:
            ctk.CTkButton(
                sidebar, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color="transparent", border_color=COLORS["border"],
                border_width=1, hover_color=COLORS["bg_panel"],
                text_color=COLORS["text_secondary"], height=32,
                anchor="w", command=cmd
            ).pack(fill="x", padx=12, pady=2)

        # CHOTU status orb
        ctk.CTkFrame(sidebar, fg_color=COLORS["border"], height=1).pack(fill="x", padx=15, pady=15)

        self.status_orb = ctk.CTkLabel(
            sidebar, text="◉",
            font=ctk.CTkFont(size=28),
            text_color=COLORS["accent_blue"]
        )
        self.status_orb.pack()

        self.status_text = ctk.CTkLabel(
            sidebar, text="STANDBY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_secondary"]
        )
        self.status_text.pack(pady=(2, 15))

    def _add_metric_widget(self, parent, label: str, bar_attr: str, label_attr: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=3)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x")

        ctk.CTkLabel(
            header, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLORS["text_dim"]
        ).pack(side="left")

        pct_lbl = ctk.CTkLabel(
            header, text="--",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLORS["accent_cyan"]
        )
        pct_lbl.pack(side="right")
        setattr(self, label_attr, pct_lbl)

        bar = ctk.CTkProgressBar(
            frame, height=5,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["accent_blue"]
        )
        bar.pack(fill="x", pady=(2, 0))
        bar.set(0)
        setattr(self, bar_attr, bar)

    def _build_chat_panel(self, parent):
        center = ctk.CTkFrame(parent, fg_color="transparent")
        center.grid(row=0, column=1, sticky="nsew", padx=5)
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # Chat history
        self.chat_display = ctk.CTkTextbox(
            center,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=10,
            wrap="word",
            state="disabled",
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")

        # Configure text tags via tkinter
        self.chat_display._textbox.tag_configure(
            "chotu", foreground=COLORS["accent_cyan"],
            font=("Segoe UI", 13, "bold")
        )
        self.chat_display._textbox.tag_configure(
            "user", foreground=COLORS["accent_gold"],
            font=("Segoe UI", 13, "bold")
        )
        self.chat_display._textbox.tag_configure(
            "system", foreground=COLORS["text_secondary"],
            font=("Segoe UI", 11, "italic")
        )
        self.chat_display._textbox.tag_configure(
            "timestamp", foreground=COLORS["text_dim"],
            font=("Consolas", 10)
        )
        self.chat_display._textbox.tag_configure(
            "error", foreground=COLORS["accent_red"],
            font=("Segoe UI", 12)
        )

        # Welcome message
        self._append_message(
            "CHOTU",
            f"Initializing systems... Good {self._time_greeting()}, "
            f"{self.config.get('address_form', 'Sir')}. "
            f"All subsystems coming online. I am CHOTU — your elite AI operating system. "
            f"How may I assist you today?",
            tag="chotu"
        )

    def _build_right_panel(self, parent):
        right = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], width=230, corner_radius=10)
        right.grid(row=0, column=2, sticky="ns", padx=(5, 0))
        right.grid_propagate(False)

        ctk.CTkLabel(
            right, text="COMMAND LOG",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_dim"]
        ).pack(pady=(15, 8), padx=15, anchor="w")

        self.command_log = ctk.CTkTextbox(
            right, height=200,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["text_secondary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=8, state="disabled"
        )
        self.command_log.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkFrame(right, fg_color=COLORS["border"], height=1).pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            right, text="MEMORY",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_dim"]
        ).pack(pady=(5, 5), padx=15, anchor="w")

        self.memory_display = ctk.CTkLabel(
            right,
            text="No memories stored yet.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLORS["text_secondary"],
            wraplength=200, justify="left"
        )
        self.memory_display.pack(padx=15, anchor="w")

        ctk.CTkFrame(right, fg_color=COLORS["border"], height=1).pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(
            right, text="ACTIVE SESSION",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=COLORS["text_dim"]
        ).pack(pady=(0, 5), padx=15, anchor="w")

        self.session_label = ctk.CTkLabel(
            right, text="Session: --\nCommands: 0\nUptime: 0s",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLORS["text_secondary"],
            justify="left"
        )
        self.session_label.pack(padx=15, anchor="w")

        ctk.CTkFrame(right, fg_color=COLORS["border"], height=1).pack(fill="x", padx=15, pady=10)

        # Clear chat button
        ctk.CTkButton(
            right, text="🗑 Clear Chat",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", border_color=COLORS["border"],
            border_width=1, hover_color=COLORS["bg_panel"],
            text_color=COLORS["text_secondary"], height=30,
            command=self._clear_chat
        ).pack(fill="x", padx=12, pady=3)

        ctk.CTkButton(
            right, text="🔄 New Session",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", border_color=COLORS["border"],
            border_width=1, hover_color=COLORS["bg_panel"],
            text_color=COLORS["text_secondary"], height=30,
            command=self._new_session
        ).pack(fill="x", padx=12, pady=3)

    def _build_input_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_card"], height=70, corner_radius=0)
        bar.pack(fill="x", side="bottom", pady=(2, 0))
        bar.pack_propagate(False)

        input_frame = ctk.CTkFrame(bar, fg_color="transparent")
        input_frame.pack(fill="both", expand=True, padx=15, pady=12)

        self.input_field = ctk.CTkEntry(
            input_frame,
            placeholder_text='Type a command or say "Hey CHOTU"...',
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            height=46,
        )
        self.input_field.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.input_field.bind("<Return>", lambda e: self._on_send())
        self.input_field.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(
            input_frame, text="Send ⏎",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=COLORS["accent_blue"], text_color="#000000",
            hover_color="#00b8d9", width=110, height=46,
            command=self._on_send
        )
        self.send_btn.pack(side="left")

        self.mic_btn = ctk.CTkButton(
            input_frame, text="🎤",
            font=ctk.CTkFont(size=20),
            fg_color=COLORS["bg_panel"], border_color=COLORS["border"],
            border_width=1, hover_color=COLORS["bg_panel"],
            text_color=COLORS["text_secondary"], width=50, height=46,
            command=self._toggle_voice_listening
        )
        self.mic_btn.pack(side="left", padx=(8, 0))

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self.root, fg_color="#050b15", height=22, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.status_bar_label = ctk.CTkLabel(
            bar, text="● CHOTU AI — All systems nominal",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLORS["accent_green"]
        )
        self.status_bar_label.pack(side="left", padx=10)

        self.model_label = ctk.CTkLabel(
            bar, text="Engine: Initializing...",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLORS["text_dim"]
        )
        self.model_label.pack(side="right", padx=10)

    # ─── System Initialization ────────────────────────────────────────────────

    def _initialize_systems_async(self):
        """Initialize all CHOTU subsystems in background thread."""
        thread = threading.Thread(target=self._initialize_systems, daemon=True)
        thread.start()

    def _initialize_systems(self):
        """Load all AI and system modules."""
        self._set_status("LOADING", COLORS["accent_orange"])
        self._log_command("Initializing CHOTU subsystems...")
        start_time = time.time()

        # 1. Memory Bank
        try:
            from core.memory_bank import MemoryBank
            self.memory = MemoryBank()
            self.session_id = self.memory.new_session_id()
            self._log_command("✓ Memory bank online")
        except Exception as e:
            self._log_command(f"✗ Memory: {e}")

        # 2. Tool Executor
        try:
            from core.tool_executor import ToolExecutor
            self.tool_executor = ToolExecutor(self.config)
            if self.memory:
                self.tool_executor.set_memory_bank(self.memory)
            self._log_command("✓ Tool executor ready")
        except Exception as e:
            self._log_command(f"✗ Tools: {e}")

        # 3. AI Brain
        try:
            from core.chotu_brain import ChoutuBrain
            api_key = self.config.get("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
            self.brain = ChoutuBrain(
                api_key=api_key,
                owner_name=self.config.get("owner_name", "Owner"),
                address_form=self.config.get("address_form", "Sir"),
                memory_bank=self.memory,
                tool_executor=self.tool_executor.execute if self.tool_executor else None,
            )
            status = self.brain.get_status()
            model_str = status.get("model", "offline")
            self.root.after(0, lambda: self.model_label.configure(
                text=f"Engine: {model_str}"
            ))
            self._log_command(f"✓ AI Brain: {model_str}")
        except Exception as e:
            self._log_command(f"✗ Brain: {e}")

        # 4. TTS Engine
        try:
            from core.tts_engine import TTSEngine
            self.tts = TTSEngine()
            self._log_command("✓ TTS engine online (en-IN-PrabhatNeural)")
        except Exception as e:
            self._log_command(f"✗ TTS: {e}")

        # 5. STT Engine
        try:
            from core.stt_engine import STTEngine
            wake_word = self.config.get("wake_word", "chotu")
            self.stt = STTEngine(wake_word=wake_word)
            self.stt.on_command = self._on_voice_command
            self._log_command("✓ STT engine online")
        except Exception as e:
            self._log_command(f"✗ STT: {e}")

        # 6. Voice Auth
        try:
            from core.voice_auth import VoiceAuthenticator
            self.voice_auth = VoiceAuthenticator()
            enrolled = self.voice_auth.is_enrolled()
            self._log_command(f"✓ Voice auth: {'enrolled' if enrolled else 'not enrolled'}")
        except Exception as e:
            self._log_command(f"✗ Voice auth: {e}")

        elapsed = time.time() - start_time
        self._log_command(f"Boot complete in {elapsed:.2f}s")
        self._set_status("READY", COLORS["accent_green"])

        # Update status bar
        self.root.after(0, lambda: self.status_bar_label.configure(
            text=f"● CHOTU AI — All systems nominal  |  Session: {(self.session_id or '')[:8]}",
            text_color=COLORS["accent_green"]
        ))

        # Start system monitor loop
        self._start_system_monitor()

        # Start session timer
        self._start_session_timer()

        # Speak greeting
        self._speak_async(
            f"All systems online, {self.config.get('address_form', 'Sir')}. "
            f"CHOTU is at your service. How may I assist you today?"
        )

    # ─── Command Processing ───────────────────────────────────────────────────

    def _on_send(self):
        """Handle text input submission."""
        text = self.input_field.get().strip()
        if not text:
            return
        self.input_field.delete(0, "end")
        self._process_command(text)

    def _send_text_command(self, command: str):
        """Programmatically send a command."""
        self._process_command(command)

    def _on_voice_command(self, text: str):
        """Callback for voice commands from STT engine."""
        logger.info(f"Voice command received: {text}")
        self.root.after(0, lambda: self._process_command(text))

    def _process_command(self, text: str):
        """Process a command from text or voice."""
        if not text:
            return

        address = self.config.get("address_form", "Sir")
        self._append_message(f"You", text, tag="user")
        self._log_command(f"CMD: {text[:50]}...")
        self._set_status("PROCESSING", COLORS["accent_blue"])
        self.send_btn.configure(state="disabled")

        def _run():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                if self.brain:
                    response = loop.run_until_complete(
                        self.brain.process_command(text)
                    )
                else:
                    response = (
                        f"I'm operating in offline mode, {address}. "
                        f"The AI core is not initialized. Please check your API configuration."
                    )
            except Exception as e:
                logger.error(f"Command processing error: {e}")
                response = f"I encountered an anomaly, {address}: {str(e)[:100]}"
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

            self.root.after(0, lambda: self._display_response(response))

        threading.Thread(target=_run, daemon=True).start()

    def _display_response(self, response: str):
        """Display CHOTU's response and speak it."""
        self._append_message("CHOTU", response, tag="chotu")
        self._set_status("SPEAKING", COLORS["accent_cyan"])
        self.send_btn.configure(state="normal")
        self._speak_async(response)

    def _speak_async(self, text: str):
        """Speak text in background."""
        def _do_speak():
            try:
                if self.tts:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.tts.speak(text))
                    loop.close()
            except Exception as e:
                logger.error(f"TTS error: {e}")
            finally:
                self.root.after(0, lambda: self._set_status("READY", COLORS["accent_green"]))

        threading.Thread(target=_do_speak, daemon=True).start()

    # ─── Voice Listening ──────────────────────────────────────────────────────

    def _toggle_voice_listening(self):
        """Toggle continuous voice listening."""
        if not self.stt:
            messagebox.showinfo("STT Unavailable", "Speech-to-text engine not initialized.")
            return

        if self.is_listening:
            self.stt.stop_listening()
            self.is_listening = False
            self.voice_toggle_btn.configure(
                text="🎤 Listening OFF",
                text_color=COLORS["text_secondary"],
                fg_color=COLORS["bg_panel"]
            )
            self.mic_btn.configure(text_color=COLORS["text_secondary"])
            self._log_command("Voice listening stopped.")
        else:
            self.stt.start_listening()
            self.is_listening = True
            self.voice_toggle_btn.configure(
                text="🔴 Listening ON",
                text_color=COLORS["accent_red"],
                fg_color="#2a0808"
            )
            self.mic_btn.configure(text_color=COLORS["accent_red"])
            self._log_command(f"Listening for wake word: '{self.config.get('wake_word', 'chotu')}'")

    # ─── UI Helpers ───────────────────────────────────────────────────────────

    def _append_message(self, sender: str, text: str, tag: str = ""):
        """Add a message to the chat display."""
        self.chat_display.configure(state="normal")
        tb = self.chat_display._textbox

        ts = datetime.datetime.now().strftime("%H:%M")
        tb.insert("end", f"[{ts}] ", "timestamp")
        tb.insert("end", f"{sender}: ", tag)
        tb.insert("end", f"{text}\n\n")

        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _log_command(self, text: str):
        """Add entry to command log."""
        def _update():
            self.command_log.configure(state="normal")
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.command_log.insert("end", f"[{ts}] {text}\n")
            self.command_log.configure(state="disabled")
            self.command_log.see("end")
        try:
            self.root.after(0, _update)
        except Exception:
            pass

    def _set_status(self, status: str, color: str):
        """Update the status orb and text."""
        def _update():
            try:
                self.status_orb.configure(text_color=color)
                self.status_text.configure(text=status)
            except Exception:
                pass
        self.root.after(0, _update)

    def _clear_chat(self):
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        address = self.config.get("address_form", "Sir")
        self._append_message("CHOTU", f"Chat history cleared. Ready for new commands, {address}.", tag="chotu")

    def _new_session(self):
        if self.brain:
            self.brain.reset_chat()
        if self.memory:
            self.session_id = self.memory.new_session_id()
        self._clear_chat()
        address = self.config.get("address_form", "Sir")
        self._append_message("CHOTU", f"New session initiated. All context reset, {address}.", tag="chotu")

    # ─── System Monitor ───────────────────────────────────────────────────────

    def _start_system_monitor(self):
        """Start background system metrics collection."""
        def _monitor():
            while self.running:
                try:
                    import psutil
                    cpu = psutil.cpu_percent(interval=1)
                    mem = psutil.virtual_memory()
                    disk = psutil.disk_usage("C:\\")
                    bat = psutil.sensors_battery()

                    def _update_metrics():
                        self.cpu_bar.set(cpu / 100)
                        self.cpu_label.configure(text=f"{cpu:.0f}%")
                        self.ram_bar.set(mem.percent / 100)
                        self.ram_label.configure(text=f"{mem.percent:.0f}%")
                        self.disk_bar.set(disk.percent / 100)
                        self.disk_label.configure(text=f"{disk.percent:.0f}%")

                        if bat:
                            plug = "⚡" if bat.power_plugged else "🔋"
                            self.battery_label.configure(text=f"{plug} Battery: {bat.percent:.0f}%")
                        else:
                            self.battery_label.configure(text="🖥 Desktop")

                    self.root.after(0, _update_metrics)
                except Exception:
                    pass

                # Check internet
                try:
                    import socket
                    socket.create_connection(("8.8.8.8", 53), timeout=2)
                    net_status = "🌐 Online"
                    net_color = COLORS["accent_green"]
                except Exception:
                    net_status = "❌ Offline"
                    net_color = COLORS["accent_red"]

                self.root.after(0, lambda s=net_status, c=net_color: self.network_label.configure(
                    text=s, text_color=c
                ))

                time.sleep(5)

        threading.Thread(target=_monitor, daemon=True).start()

    def _start_session_timer(self):
        self._session_start = time.time()
        self._command_count = 0

        def _update():
            if not self.running:
                return
            elapsed = int(time.time() - self._session_start)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            uptime = f"{h:02d}:{m:02d}:{s:02d}"
            sid = (self.session_id or "----")[:8]
            self.session_label.configure(
                text=f"Session: {sid}\nCommands: {self._command_count}\nUptime: {uptime}"
            )
            self.root.after(1000, _update)

        self.root.after(1000, _update)

    # ─── Animations ───────────────────────────────────────────────────────────

    def _start_animations(self):
        """Start clock and status animations."""
        self._update_clock()
        self._pulse_status_orb()

    def _update_clock(self):
        if not self.running:
            return
        now = datetime.datetime.now()
        self.time_label.configure(
            text=now.strftime("%A, %B %d  |  %I:%M:%S %p")
        )
        self.root.after(1000, self._update_clock)

    def _pulse_status_orb(self):
        if not self.running:
            return
        orb_chars = ["◉", "◎", "○", "◎"]
        self.pulse_angle = (self.pulse_angle + 1) % len(orb_chars)
        try:
            current_color = self.status_orb.cget("text_color")
            self.status_orb.configure(text=orb_chars[self.pulse_angle])
        except Exception:
            pass
        self.root.after(600, self._pulse_status_orb)

    # ─── Settings ─────────────────────────────────────────────────────────────

    def _show_settings(self):
        """Show settings dialog."""
        win = ctk.CTkToplevel(self.root)
        win.title("CHOTU Settings")
        win.geometry("500x400")
        win.configure(fg_color=COLORS["bg_dark"])
        win.grab_set()

        ctk.CTkLabel(
            win, text="⚙ Settings",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=COLORS["accent_blue"]
        ).pack(pady=20)

        info = (
            f"Owner: {self.config.get('owner_name', '--')}\n"
            f"Address: {self.config.get('address_form', '--')}\n"
            f"Wake Word: {self.config.get('wake_word', '--')}\n"
            f"Voice Enrolled: {self.config.get('voice_enrolled', False)}\n"
            f"API Key: {'Configured' if self.config.get('gemini_api_key') else 'Not set'}\n"
            f"Startup: {self.config.get('startup_enabled', False)}\n"
        )

        ctk.CTkTextbox(
            win, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=COLORS["bg_card"], text_color=COLORS["text_primary"],
            height=180
        ).pack(fill="x", padx=20)

        info_box = win.children[list(win.children.keys())[-1]]
        info_box.insert("end", info)
        info_box.configure(state="disabled")

        ctk.CTkButton(
            win, text="Re-run Setup Wizard",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["accent_blue"], text_color="#000000",
            command=lambda: [win.destroy(), self._rerun_setup()]
        ).pack(pady=10)

    def _rerun_setup(self):
        """Re-run the setup wizard."""
        import subprocess
        subprocess.Popen([sys.executable, str(BASE_DIR / "setup_wizard.py")])

    # ─── Utilities ────────────────────────────────────────────────────────────

    def _time_greeting(self) -> str:
        h = datetime.datetime.now().hour
        if h < 12:
            return "morning"
        elif h < 17:
            return "afternoon"
        else:
            return "evening"

    def _register_hotkey(self, hotkey: str):
        try:
            import keyboard
            keyboard.add_hotkey(hotkey, self._toggle_window)
            logger.info(f"Global hotkey registered: {hotkey}")
        except Exception as e:
            logger.warning(f"Hotkey registration failed: {e}")

    def _toggle_window(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
        else:
            self.root.withdraw()

    def _on_close(self):
        if self.config.get("minimize_to_tray", True):
            self.root.withdraw()
        else:
            self._shutdown()

    def _shutdown(self):
        self.running = False
        if self.stt and self.is_listening:
            self.stt.stop_listening()
        if self.tts:
            self.tts.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    """Main entry point — checks setup, then launches CHOTU."""
    from setup_wizard import check_setup_complete, load_config

    # Ensure data dir exists for logging
    Path("data").mkdir(exist_ok=True)

    if not check_setup_complete():
        logger.info("First run detected — launching setup wizard.")
        from setup_wizard import SetupWizard
        wizard = SetupWizard()
        wizard.run()
        # After wizard, reload config and launch
        config = load_config()
        if not config.get("setup_complete"):
            logger.warning("Setup not completed. Exiting.")
            return
    else:
        config = load_config()

    # Apply any env overrides
    if not config.get("gemini_api_key") and os.getenv("GEMINI_API_KEY"):
        config["gemini_api_key"] = os.getenv("GEMINI_API_KEY")

    app = ChoutuApp(config)
    app.run()


if __name__ == "__main__":
    main()
