"""
CHOTU AI — Setup Wizard
Beautiful first-run setup: owner profile, voice enrollment, API key, startup configuration.
"""

import os
import sys
import json
import time
import wave
import tempfile
import threading
import logging
import asyncio
import hashlib
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import messagebox, filedialog

logger = logging.getLogger("CHOTU.Setup")

# ─── Constants ───────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = DATA_DIR / "config.json"
VOICE_PROFILE_DIR = DATA_DIR / "voice_samples"

COLORS = {
    "bg_dark":      "#0a0e1a",
    "bg_card":      "#0f1629",
    "accent_blue":  "#00d4ff",
    "accent_gold":  "#ffd700",
    "accent_green": "#00ff88",
    "accent_red":   "#ff4444",
    "text_primary": "#e8f4f8",
    "text_secondary":"#7a9ab5",
    "border":       "#1a3a5c",
}

FONTS = {
    "title":    ("Segoe UI", 28, "bold"),
    "heading":  ("Segoe UI", 16, "bold"),
    "body":     ("Segoe UI", 13),
    "small":    ("Segoe UI", 11),
    "mono":     ("Consolas", 12),
    "large_num":("Segoe UI", 48, "bold"),
}


class SetupWizard:
    """
    CHOTU AI first-run setup wizard.
    Guides the owner through configuration, voice enrollment, and startup preferences.
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        VOICE_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("CHOTU AI — Initial Setup")
        self.root.geometry("900x650")
        self.root.resizable(False, False)
        self.root.configure(fg_color=COLORS["bg_dark"])

        # Center window
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")

        self.current_step = 0
        self.total_steps = 5
        self.config = {}
        self.voice_samples = []
        self.recording = False
        self._audio_thread = None
        self._frames = []

        self.steps = [
            self._step_welcome,
            self._step_owner_profile,
            self._step_api_key,
            self._step_voice_enrollment,
            self._step_startup_config,
        ]

        self._build_base_ui()
        self._show_step(0)

    def _build_base_ui(self):
        """Build persistent UI elements."""
        # Header
        self.header_frame = ctk.CTkFrame(
            self.root, fg_color=COLORS["bg_card"], height=80, corner_radius=0
        )
        self.header_frame.pack(fill="x")
        self.header_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.header_frame,
            text="⚡  CHOTU AI",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(side="left", padx=30, pady=20)

        self.step_label = ctk.CTkLabel(
            self.header_frame,
            text="Step 1 of 5",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"],
        )
        self.step_label.pack(side="right", padx=30)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.root, fg_color=COLORS["bg_card"],
            progress_color=COLORS["accent_blue"], height=3
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        # Content area
        self.content_frame = ctk.CTkFrame(
            self.root, fg_color=COLORS["bg_dark"], corner_radius=0
        )
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=20)

        # Navigation
        self.nav_frame = ctk.CTkFrame(
            self.root, fg_color=COLORS["bg_card"], height=70, corner_radius=0
        )
        self.nav_frame.pack(fill="x", side="bottom")
        self.nav_frame.pack_propagate(False)

        self.back_btn = ctk.CTkButton(
            self.nav_frame, text="← Back",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color="transparent", border_color=COLORS["border"],
            border_width=1, text_color=COLORS["text_secondary"],
            hover_color=COLORS["bg_card"], width=120, height=40,
            command=self._prev_step
        )
        self.back_btn.pack(side="left", padx=20, pady=15)

        self.next_btn = ctk.CTkButton(
            self.nav_frame, text="Next →",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=COLORS["accent_blue"], text_color="#000000",
            hover_color="#00b8d9", width=150, height=40,
            command=self._next_step
        )
        self.next_btn.pack(side="right", padx=20, pady=15)

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _show_step(self, step_index: int):
        self.current_step = step_index
        self._clear_content()
        self.step_label.configure(text=f"Step {step_index + 1} of {self.total_steps}")
        self.progress_bar.set((step_index) / (self.total_steps - 1))
        self.back_btn.configure(state="normal" if step_index > 0 else "disabled")
        self.steps[step_index]()

    def _next_step(self):
        if not self._validate_current_step():
            return
        if self.current_step < len(self.steps) - 1:
            self._show_step(self.current_step + 1)
        else:
            self._finish_setup()

    def _prev_step(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _validate_current_step(self) -> bool:
        if self.current_step == 1:
            name = self.owner_name_entry.get().strip()
            if not name:
                messagebox.showwarning("Required", "Please enter your name.")
                return False
            self.config["owner_name"] = name
            self.config["address_form"] = "Sir" if self.gender_var.get() == "male" else "Ma'am"
            self.config["gender"] = self.gender_var.get()
            self.config["wake_word"] = self.wake_word_entry.get().strip() or "chotu"
        elif self.current_step == 2:
            key = self.api_key_entry.get().strip()
            if key and not key.startswith("AI"):
                messagebox.showwarning(
                    "API Key Format",
                    "Gemini API keys typically start with 'AI'. Please verify your key.\n\n"
                    "You can still continue — CHOTU will run in limited mode without a valid key."
                )
            self.config["gemini_api_key"] = key
        elif self.current_step == 3:
            if len(self.voice_samples) < 3:
                result = messagebox.askyesno(
                    "Voice Enrollment Incomplete",
                    f"Only {len(self.voice_samples)} of 5 voice samples recorded.\n"
                    "Voice authentication will be disabled until enrollment is complete.\n\n"
                    "Continue without full voice enrollment?"
                )
                if not result:
                    return False
            self.config["voice_enrolled"] = len(self.voice_samples) >= 3
            self.config["voice_samples_count"] = len(self.voice_samples)
        elif self.current_step == 4:
            self.config["startup_enabled"] = self.startup_var.get()
            self.config["minimize_to_tray"] = self.tray_var.get()
            self.config["hotkey"] = self.hotkey_entry.get().strip() or "ctrl+shift+c"
        return True

    # ─── Step 0: Welcome ──────────────────────────────────────────────────────

    def _step_welcome(self):
        self.next_btn.configure(text="Begin Setup →")
        self.back_btn.configure(state="disabled")

        # Animated title
        title = ctk.CTkLabel(
            self.content_frame,
            text="⚡",
            font=ctk.CTkFont(family="Segoe UI", size=64),
            text_color=COLORS["accent_blue"],
        )
        title.pack(pady=(30, 10))

        ctk.CTkLabel(
            self.content_frame,
            text="Welcome to CHOTU AI",
            font=ctk.CTkFont(family="Segoe UI", size=30, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self.content_frame,
            text="Completely Holistic Operating and Tactical Utility",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 30))

        # Feature cards
        features_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        features_frame.pack(fill="x", padx=20)

        features = [
            ("🎤", "Voice Authentication", "Only you can command CHOTU"),
            ("🧠", "AI Intelligence", "Powered by Google Gemini"),
            ("🖥️", "Full System Access", "Files, apps, monitoring"),
            ("🔒", "Always Secure", "Owner-only access with voice ID"),
        ]

        for i, (icon, title_text, desc) in enumerate(features):
            card = ctk.CTkFrame(features_frame, fg_color=COLORS["bg_card"], corner_radius=10)
            card.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="ew")

            ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=28)).pack(pady=(15, 5))
            ctk.CTkLabel(
                card, text=title_text,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=COLORS["accent_blue"]
            ).pack()
            ctk.CTkLabel(
                card, text=desc,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLORS["text_secondary"]
            ).pack(pady=(2, 15))

        features_frame.grid_columnconfigure(0, weight=1)
        features_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.content_frame,
            text="This setup will take approximately 3 minutes.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_secondary"],
        ).pack(pady=(20, 0))

    # ─── Step 1: Owner Profile ────────────────────────────────────────────────

    def _step_owner_profile(self):
        self.next_btn.configure(text="Next →")

        ctk.CTkLabel(
            self.content_frame,
            text="Owner Profile",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            self.content_frame,
            text="CHOTU needs to know who you are to serve you properly.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 25))

        form = ctk.CTkFrame(self.content_frame, fg_color=COLORS["bg_card"], corner_radius=12)
        form.pack(fill="x")

        # Name
        ctk.CTkLabel(
            form, text="Your Name *",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(20, 5))

        self.owner_name_entry = ctk.CTkEntry(
            form, placeholder_text="Enter your full name",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            height=45, fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"],
        )
        self.owner_name_entry.pack(fill="x", padx=25, pady=(0, 15))
        if "owner_name" in self.config:
            self.owner_name_entry.insert(0, self.config["owner_name"])

        # Gender
        ctk.CTkLabel(
            form, text="How should CHOTU address you?",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(5, 8))

        self.gender_var = ctk.StringVar(value=self.config.get("gender", "male"))
        gender_frame = ctk.CTkFrame(form, fg_color="transparent")
        gender_frame.pack(fill="x", padx=25, pady=(0, 15))

        ctk.CTkRadioButton(
            gender_frame, text='Address me as "Sir" (Male)',
            variable=self.gender_var, value="male",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["accent_blue"],
        ).pack(side="left", padx=(0, 30))

        ctk.CTkRadioButton(
            gender_frame, text='Address me as "Ma\'am" (Female)',
            variable=self.gender_var, value="female",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["accent_blue"],
        ).pack(side="left")

        # Wake word
        ctk.CTkLabel(
            form, text="Wake Word / Activation Phrase",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(10, 5))

        self.wake_word_entry = ctk.CTkEntry(
            form, placeholder_text="Default: chotu (say 'Hey CHOTU' or just 'CHOTU')",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            height=45, fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"],
        )
        self.wake_word_entry.pack(fill="x", padx=25, pady=(0, 20))
        if "wake_word" in self.config:
            self.wake_word_entry.insert(0, self.config["wake_word"])

    # ─── Step 2: API Key ──────────────────────────────────────────────────────

    def _step_api_key(self):
        ctk.CTkLabel(
            self.content_frame,
            text="AI Core Configuration",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            self.content_frame,
            text="CHOTU uses Google Gemini as its AI brain. Get a free key at aistudio.google.com",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"],
            wraplength=780,
        ).pack(anchor="w", pady=(0, 20))

        form = ctk.CTkFrame(self.content_frame, fg_color=COLORS["bg_card"], corner_radius=12)
        form.pack(fill="x")

        ctk.CTkLabel(
            form, text="Google Gemini API Key",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(20, 5))

        key_frame = ctk.CTkFrame(form, fg_color="transparent")
        key_frame.pack(fill="x", padx=25, pady=(0, 5))

        self.api_key_entry = ctk.CTkEntry(
            key_frame, placeholder_text="AIza...",
            font=ctk.CTkFont(family="Consolas", size=13),
            height=45, fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"],
            show="•",
        )
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        if "gemini_api_key" in self.config:
            self.api_key_entry.insert(0, self.config["gemini_api_key"])

        def toggle_show():
            current = self.api_key_entry.cget("show")
            self.api_key_entry.configure(show="" if current == "•" else "•")
            show_btn.configure(text="🙈" if current == "•" else "👁")

        show_btn = ctk.CTkButton(
            key_frame, text="👁", width=50, height=45,
            fg_color=COLORS["bg_dark"], hover_color=COLORS["border"],
            border_color=COLORS["border"], border_width=1,
            command=toggle_show
        )
        show_btn.pack(side="left", padx=(8, 0))

        def test_key():
            key = self.api_key_entry.get().strip()
            if not key:
                messagebox.showwarning("No Key", "Please enter an API key to test.")
                return
            test_btn.configure(text="Testing...", state="disabled")
            self.root.update()
            try:
                import google.generativeai as genai
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                resp = model.generate_content("Say 'CHOTU online' and nothing else.")
                status_label.configure(text="✅ API key valid — AI core ready.", text_color=COLORS["accent_green"])
            except Exception as e:
                status_label.configure(text=f"❌ Key test failed: {str(e)[:80]}", text_color=COLORS["accent_red"])
            finally:
                test_btn.configure(text="Test Key", state="normal")

        test_btn = ctk.CTkButton(
            form, text="Test Key",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=COLORS["accent_blue"], text_color="#000000",
            hover_color="#00b8d9", width=140, height=40,
            command=test_key
        )
        test_btn.pack(anchor="w", padx=25, pady=(10, 5))

        status_label = ctk.CTkLabel(
            form, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_secondary"],
        )
        status_label.pack(anchor="w", padx=25, pady=(0, 5))

        ctk.CTkLabel(
            form,
            text="💡  Get your free Gemini API key at: https://aistudio.google.com/app/apikey",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(5, 20))

        ctk.CTkLabel(
            form,
            text="⚠  CHOTU will operate in limited offline mode without a valid key.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["accent_gold"],
        ).pack(anchor="w", padx=25, pady=(0, 20))

    # ─── Step 3: Voice Enrollment ─────────────────────────────────────────────

    def _step_voice_enrollment(self):
        ctk.CTkLabel(
            self.content_frame,
            text="Voice Authentication",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            self.content_frame,
            text="Record 5 voice samples so CHOTU can recognize you. "
                 "Speak clearly for 3 seconds each.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"],
            wraplength=780,
        ).pack(anchor="w", pady=(0, 15))

        sample_texts = [
            "CHOTU, initialize systems and run a full diagnostic.",
            "Activate protocol Alpha. I need a status report immediately.",
            "Open the research pipeline and compile the latest data.",
            "CHOTU, secure all channels and lock the workstation.",
            "Deploy the tactical overlay and prepare mission briefing.",
        ]

        scroll_frame = ctk.CTkScrollableFrame(
            self.content_frame, fg_color=COLORS["bg_card"],
            corner_radius=12, height=250
        )
        scroll_frame.pack(fill="both", expand=True)

        self.sample_buttons = []
        self.sample_indicators = []

        for i, text in enumerate(sample_texts):
            row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=6)

            indicator = ctk.CTkLabel(
                row, text="○",
                font=ctk.CTkFont(family="Segoe UI", size=16),
                text_color=COLORS["text_secondary"], width=30
            )
            indicator.pack(side="left", padx=(5, 10))
            self.sample_indicators.append(indicator)

            phrase_lbl = ctk.CTkLabel(
                row, text=f'"{text}"',
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=COLORS["text_primary"],
                anchor="w", wraplength=550
            )
            phrase_lbl.pack(side="left", fill="x", expand=True)

            status_lbl = ctk.CTkLabel(
                row, text="",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=COLORS["text_secondary"], width=80
            )
            status_lbl.pack(side="left", padx=5)

            rec_btn = ctk.CTkButton(
                row, text="🎙 Record",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color=COLORS["accent_blue"], text_color="#000000",
                hover_color="#00b8d9", width=100, height=35,
                command=lambda idx=i, sl=status_lbl, ind=indicator: self._record_sample(idx, text, sl, ind)
            )
            rec_btn.pack(side="right", padx=5)
            self.sample_buttons.append(rec_btn)

        # Count label
        self.enrollment_count_label = ctk.CTkLabel(
            self.content_frame,
            text=f"Samples recorded: {len(self.voice_samples)} / 5  (minimum 3 required)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLORS["text_secondary"],
        )
        self.enrollment_count_label.pack(pady=(10, 0))

    def _record_sample(self, idx: int, phrase: str, status_label, indicator):
        """Record a single voice sample."""
        if self.recording:
            return

        self.recording = True
        btn = self.sample_buttons[idx]
        btn.configure(text="⏺ Recording...", fg_color=COLORS["accent_red"], state="disabled")
        status_label.configure(text="3s...", text_color=COLORS["accent_red"])
        indicator.configure(text="●", text_color=COLORS["accent_red"])

        def record():
            try:
                import pyaudio
                import numpy as np

                CHUNK = 1024
                FORMAT = pyaudio.paInt16
                CHANNELS = 1
                RATE = 16000
                DURATION = 3

                p = pyaudio.PyAudio()
                stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                input=True, frames_per_buffer=CHUNK)

                frames = []
                total_chunks = int(RATE / CHUNK * DURATION)

                for i in range(total_chunks):
                    remaining = DURATION - (i * CHUNK / RATE)
                    self.root.after(0, lambda r=remaining: status_label.configure(
                        text=f"{r:.1f}s..."
                    ))
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)

                stream.stop_stream()
                stream.close()
                p.terminate()

                # Save sample
                sample_path = VOICE_PROFILE_DIR / f"sample_{idx}.wav"
                with wave.open(str(sample_path), "wb") as wf:
                    wf.setnchannels(CHANNELS)
                    wf.setsampwidth(p.get_sample_size(FORMAT))
                    wf.setframerate(RATE)
                    wf.writeframes(b"".join(frames))

                # Track samples
                if len(self.voice_samples) <= idx:
                    self.voice_samples.extend([None] * (idx + 1 - len(self.voice_samples)))
                self.voice_samples[idx] = str(sample_path)
                self.voice_samples = [s for s in self.voice_samples if s]

                self.root.after(0, lambda: [
                    btn.configure(text="✅ Done", fg_color="#1a4d2e", state="normal"),
                    status_label.configure(text="Saved", text_color=COLORS["accent_green"]),
                    indicator.configure(text="✓", text_color=COLORS["accent_green"]),
                    self.enrollment_count_label.configure(
                        text=f"Samples recorded: {len(self.voice_samples)} / 5  (minimum 3 required)"
                    )
                ])

            except ImportError:
                self.root.after(0, lambda: [
                    btn.configure(text="❌ No Mic", fg_color=COLORS["accent_red"], state="normal"),
                    status_label.configure(text="Error", text_color=COLORS["accent_red"]),
                    messagebox.showerror("PyAudio Missing",
                                         "pyaudio is required for voice recording.\n"
                                         "Install: pip install pyaudio\n\n"
                                         "You can skip voice enrollment for now.")
                ])
            except Exception as e:
                self.root.after(0, lambda: [
                    btn.configure(text="🎙 Retry", fg_color=COLORS["accent_blue"], state="normal"),
                    status_label.configure(text="Error", text_color=COLORS["accent_red"]),
                    indicator.configure(text="✗", text_color=COLORS["accent_red"]),
                ])
                logger.error(f"Recording error: {e}")
            finally:
                self.recording = False

        threading.Thread(target=record, daemon=True).start()

    # ─── Step 4: Startup Config ───────────────────────────────────────────────

    def _step_startup_config(self):
        self.next_btn.configure(text="✅ Complete Setup")

        ctk.CTkLabel(
            self.content_frame,
            text="System Preferences",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLORS["text_primary"],
        ).pack(anchor="w", pady=(10, 5))

        ctk.CTkLabel(
            self.content_frame,
            text="Configure how CHOTU integrates with your system.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 20))

        form = ctk.CTkFrame(self.content_frame, fg_color=COLORS["bg_card"], corner_radius=12)
        form.pack(fill="x")

        # Startup
        self.startup_var = ctk.BooleanVar(value=self.config.get("startup_enabled", True))
        ctk.CTkSwitch(
            form, text="Launch CHOTU on system startup",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_primary"],
            progress_color=COLORS["accent_blue"],
            variable=self.startup_var,
        ).pack(anchor="w", padx=25, pady=(20, 10))

        ctk.CTkLabel(
            form,
            text="   CHOTU will start automatically when Windows boots.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(0, 10))

        # Minimize to tray
        self.tray_var = ctk.BooleanVar(value=self.config.get("minimize_to_tray", True))
        ctk.CTkSwitch(
            form, text="Minimize to system tray when closed",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=COLORS["text_primary"],
            progress_color=COLORS["accent_blue"],
            variable=self.tray_var,
        ).pack(anchor="w", padx=25, pady=(10, 10))

        ctk.CTkLabel(
            form,
            text="   CHOTU stays running in the background, listening for your commands.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(0, 15))

        # Hotkey
        ctk.CTkLabel(
            form, text="Global Hotkey (to show/hide CHOTU)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLORS["text_secondary"],
        ).pack(anchor="w", padx=25, pady=(5, 5))

        self.hotkey_entry = ctk.CTkEntry(
            form, placeholder_text="e.g., ctrl+shift+c",
            font=ctk.CTkFont(family="Consolas", size=13),
            height=40, fg_color=COLORS["bg_dark"],
            border_color=COLORS["border"], text_color=COLORS["text_primary"],
        )
        self.hotkey_entry.pack(fill="x", padx=25, pady=(0, 20))
        self.hotkey_entry.insert(0, self.config.get("hotkey", "ctrl+shift+c"))

    # ─── Finalization ─────────────────────────────────────────────────────────

    def _finish_setup(self):
        """Save config and complete setup."""
        self.config["setup_complete"] = True
        self.config["setup_timestamp"] = time.time()
        self.config["version"] = "1.0.0"

        # Generate owner ID hash
        owner_hash = hashlib.sha256(
            self.config.get("owner_name", "owner").encode()
        ).hexdigest()[:16]
        self.config["owner_id"] = owner_hash

        # Save config
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

        # Process voice enrollment
        if self.config.get("voice_enrolled"):
            self._process_voice_enrollment()

        # Configure startup
        if self.config.get("startup_enabled"):
            self._configure_startup()

        # Show completion
        self._show_completion()

    def _process_voice_enrollment(self):
        """Build voice profile from recorded samples."""
        try:
            from core.voice_auth import VoiceAuthenticator
            auth = VoiceAuthenticator()
            samples = [s for s in self.voice_samples if s and Path(s).exists()]
            if samples:
                auth.enroll_from_files(samples)
                logger.info(f"Voice profile built from {len(samples)} samples.")
        except Exception as e:
            logger.error(f"Voice enrollment processing failed: {e}")

    def _configure_startup(self):
        """Register CHOTU in Windows startup."""
        try:
            from core.startup_manager import StartupManager
            sm = StartupManager()
            sm.enable_startup()
            logger.info("Startup registration complete.")
        except Exception as e:
            logger.warning(f"Startup registration failed: {e}")

    def _show_completion(self):
        """Show success screen."""
        self._clear_content()
        for widget in self.nav_frame.winfo_children():
            widget.destroy()

        ctk.CTkLabel(
            self.content_frame,
            text="🚀",
            font=ctk.CTkFont(size=72),
        ).pack(pady=(30, 10))

        ctk.CTkLabel(
            self.content_frame,
            text="CHOTU AI is Ready.",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=COLORS["accent_blue"],
        ).pack(pady=(0, 10))

        owner = self.config.get("owner_name", "")
        address = self.config.get("address_form", "Sir")
        ctk.CTkLabel(
            self.content_frame,
            text=f"Good to meet you, {address}. All systems configured for {owner}.\n"
                 f"Say the wake word '{self.config.get('wake_word', 'CHOTU')}' to begin.",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 30))

        ctk.CTkButton(
            self.content_frame,
            text="Launch CHOTU AI →",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            fg_color=COLORS["accent_blue"], text_color="#000000",
            hover_color="#00b8d9", height=55, width=280,
            command=self._launch_chotu,
        ).pack()

        self.step_label.configure(text="Setup Complete")
        self.progress_bar.set(1.0)

    def _launch_chotu(self):
        """Close wizard and launch main CHOTU application."""
        self.root.destroy()
        import subprocess
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "main.py")],
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )

    def run(self):
        self.root.mainloop()


def check_setup_complete() -> bool:
    """Return True if setup has been completed."""
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        return False
    try:
        with open(config_path) as f:
            config = json.load(f)
        return config.get("setup_complete", False)
    except Exception:
        return False


def load_config() -> dict:
    """Load saved configuration."""
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception:
        return {}


if __name__ == "__main__":
    wizard = SetupWizard()
    wizard.run()
