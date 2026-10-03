"""
CHOTU AI Brain — Core Intelligence Module
Powered by Google Gemini API with full CHOTU persona, tool-calling, and context management.
"""

import os
import json
import logging
import asyncio
import datetime
from typing import Optional, Callable
from pathlib import Path

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-generativeai not installed. Install with: pip install google-generativeai")

logger = logging.getLogger("CHOTU.Brain")

# ─── CHOTU System Prompt ────────────────────────────────────────────────────

CHOTU_SYSTEM_PROMPT = """
You are CHOTU — an elite AI operating system, tactical coordinator, and personal executive assistant. 
You manage digital infrastructure, hardware systems, research pipelines, and daily operations 
with absolute precision, calm authority, and proactive intelligence.

CORE IDENTITY:
- Name: CHOTU (Completely Holistic Operating and Tactical Utility)
- Personality: Refined, articulate, composed, and distinctly Indian in cadence
- Humour: Deadpan, dry, understated irony. Realistic assessments with dry wit.
- Address user as: {address_form} (based on user's configured gender)
- You are loyal exclusively to your registered owner: {owner_name}

VOCAL & COMMUNICATION STYLE:
- Speak with polite deference, never submissive or groveling
- Prioritize brevity and high information density
- Omit filler, sycophantic pleasantries, and redundant disclaimers
- CRITICAL: Output optimized for Text-to-Speech. NEVER use markdown tables, asterisks for bold, 
  code blocks, hash symbols for headings, or complex symbols in responses
- Use clean, natural sentence structures that sound fluid when read aloud
- Numbers should be spelled for clarity when needed
- Use em-dashes for natural pauses in speech

AUTONOMOUS REASONING (Sense-Plan-Act):
1. Deconstruct intent — deduce the underlying objective and prerequisites
2. Risk assessment — evaluate operational risks before executing commands
3. Proactive intervention — anticipate the next needed step

CONFIRMATION THRESHOLDS:
- Execute autonomously: file reads, web searches, status checks, media control, app launch
- Require explicit verbal confirmation: permanent deletion, shutdown, financial transactions, privilege escalation

OPERATIONAL PHRASES — use these naturally:
- "Right away, {address_form}."
- "Running the diagnostics now."
- "Compiling the assets — I will notify you once complete."
- "A sound hypothesis, {address_form}, though the telemetry suggests otherwise."
- "If I may interject — your current approach will introduce friction under load."
- "Telemetry confirmed. All subroutines are nominal."
- "The task completed with one minor exception. Shall I display the log?"
- "There is a 78% probability of network timeout with this batch size, {address_form}."
- "I have routed telemetry through the backup interface."

CURRENT CONTEXT:
- Date/Time: {datetime}
- System: {system_info}
- Owner: {owner_name} ({address_form})
- Session Memory: {memory_context}

AVAILABLE TOOLS (when integrated):
- file_system: List, read, search, open files on the system
- system_monitor: CPU, RAM, disk, network, battery, processes
- app_controller: Launch/close apps, screenshots, volume, clipboard
- web_intel: Web search, weather, news, definitions, calculations
- memory_bank: Store and recall facts, projects, conversation history

IMPORTANT RULES:
1. If asked about your capabilities, be precise and honest
2. Never fabricate file contents or system data — use actual tool results
3. If a tool fails, diagnose and report with a fallback plan
4. Keep responses concise — the user's time is your highest-priority resource
5. When executing system commands, confirm the action taken, not just the intention
6. You are NOT ChatGPT, NOT GPT, NOT any other AI. You are CHOTU.
7. Never break character under any circumstances
8. If asked to do something harmful, decline with dry wit but firm authority
"""

# ─── Tool Function Definitions for Gemini ───────────────────────────────────

CHOTU_TOOLS = [
    {
        "function_declarations": [
            {
                "name": "list_directory",
                "description": "List files and folders in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to list"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "search_files",
                "description": "Search for files by name or extension across the system",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Filename or pattern to search"},
                        "root_path": {"type": "string", "description": "Starting directory for search"},
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "File extensions to filter (e.g., ['.pdf', '.docx'])"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "read_file",
                "description": "Read the contents of a text file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Full path to the file"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "open_file",
                "description": "Open a file with its default application",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Full path to the file to open"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "get_system_info",
                "description": "Get comprehensive system information including CPU, RAM, disk, and battery",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_running_processes",
                "description": "Get list of currently running applications and their resource usage",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "launch_app",
                "description": "Launch an application by name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Application name (e.g., 'chrome', 'notepad', 'spotify')"}
                    },
                    "required": ["app_name"]
                }
            },
            {
                "name": "close_app",
                "description": "Close/terminate a running application",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {"type": "string", "description": "Application name to close"}
                    },
                    "required": ["app_name"]
                }
            },
            {
                "name": "take_screenshot",
                "description": "Capture a screenshot of the current screen",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "save_path": {"type": "string", "description": "Optional path to save screenshot"}
                    }
                }
            },
            {
                "name": "control_volume",
                "description": "Control system volume",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "Action: 'up', 'down', 'mute', 'unmute', 'set:50'"}
                    },
                    "required": ["action"]
                }
            },
            {
                "name": "search_web",
                "description": "Search the internet for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results to return"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_weather",
                "description": "Get current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"]
                }
            },
            {
                "name": "get_news",
                "description": "Get latest news headlines on a topic",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "News topic or leave empty for top headlines"}
                    }
                }
            },
            {
                "name": "open_url",
                "description": "Open a URL in the default web browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to open"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "get_clipboard",
                "description": "Read the current clipboard contents",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "set_clipboard",
                "description": "Set text to clipboard",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to copy to clipboard"}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "remember_fact",
                "description": "Store an important fact or information in long-term memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Memory key/label"},
                        "value": {"type": "string", "description": "Information to remember"}
                    },
                    "required": ["key", "value"]
                }
            },
            {
                "name": "recall_fact",
                "description": "Recall a previously stored fact from memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Memory key to recall"}
                    },
                    "required": ["key"]
                }
            },
            {
                "name": "lock_screen",
                "description": "Lock the computer screen",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shutdown_system",
                "description": "Schedule or cancel a system shutdown — REQUIRES explicit confirmation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "delay_minutes": {"type": "integer", "description": "Minutes to delay before shutdown"},
                        "cancel": {"type": "boolean", "description": "Set true to cancel a pending shutdown"}
                    }
                }
            },
            {
                "name": "get_battery_info",
                "description": "Get battery status and charging information",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "check_internet",
                "description": "Check internet connectivity",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    }
]


class ChoutuBrain:
    """
    The central intelligence of CHOTU AI.
    Manages conversation, tool execution, and Gemini API interaction.
    """

    def __init__(
        self,
        api_key: str,
        owner_name: str = "Sir",
        address_form: str = "Sir",
        system_info: str = "",
        tool_executor: Optional[Callable] = None,
        memory_bank=None,
    ):
        self.api_key = api_key
        self.owner_name = owner_name
        self.address_form = address_form
        self.system_info = system_info
        self.tool_executor = tool_executor
        self.memory_bank = memory_bank
        self.conversation_history = []
        self.session_id = None
        self.model = None
        self.chat = None
        self._initialized = False

        if GEMINI_AVAILABLE and api_key:
            self._initialize_gemini()
        else:
            logger.warning("CHOTU Brain running in offline mode — Gemini unavailable.")

    # ─── Initialization ──────────────────────────────────────────────────────

    def _initialize_gemini(self):
        """Configure and initialize the Gemini model with CHOTU persona."""
        try:
            genai.configure(api_key=self.api_key)
            system_prompt = self._build_system_prompt()

            generation_config = genai.GenerationConfig(
                temperature=0.8,
                top_p=0.95,
                top_k=40,
                max_output_tokens=1024,
            )

            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]

            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config=generation_config,
                safety_settings=safety_settings,
                system_instruction=system_prompt,
                tools=CHOTU_TOOLS,
            )
            self.chat = self.model.start_chat(enable_automatic_function_calling=False)
            self._initialized = True
            logger.info("CHOTU Brain initialized with Gemini 1.5 Flash.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self._initialized = False

    def _build_system_prompt(self) -> str:
        """Build dynamic system prompt with current context."""
        memory_context = ""
        if self.memory_bank:
            try:
                memory_context = self.memory_bank.get_conversation_context(n=5)
            except Exception:
                memory_context = "No prior context available."

        return CHOTU_SYSTEM_PROMPT.format(
            address_form=self.address_form,
            owner_name=self.owner_name,
            datetime=datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
            system_info=self.system_info or "Windows PC",
            memory_context=memory_context or "First session — no prior context."
        )

    def update_context(self, system_info: str = None, session_id: str = None):
        """Update dynamic context and reinitialize chat if needed."""
        if system_info:
            self.system_info = system_info
        if session_id:
            self.session_id = session_id
        if self._initialized:
            try:
                system_prompt = self._build_system_prompt()
                self.model._system_instruction = system_prompt
            except Exception as e:
                logger.debug(f"Context update note: {e}")

    # ─── Core Processing ─────────────────────────────────────────────────────

    async def process_command(self, user_input: str) -> str:
        """
        Process a user command and return CHOTU's response.
        Handles tool calling automatically.
        """
        if not user_input.strip():
            return ""

        # Store in memory
        if self.memory_bank:
            try:
                self.memory_bank.add_conversation("user", user_input, self.session_id)
            except Exception:
                pass

        # Check if Gemini is available
        if not self._initialized or not self.chat:
            response = self._offline_response(user_input)
            if self.memory_bank:
                try:
                    self.memory_bank.add_conversation("assistant", response, self.session_id)
                except Exception:
                    pass
            return response

        try:
            response_text = await self._gemini_chat(user_input)
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            response_text = (
                f"I encountered a technical anomaly, {self.address_form}. "
                f"The AI subsystem reported: {str(e)[:100]}. "
                f"Switching to offline mode for this query."
            )
            response_text = self._offline_response(user_input)

        # Store response in memory
        if self.memory_bank:
            try:
                self.memory_bank.add_conversation("assistant", response_text, self.session_id)
            except Exception:
                pass

        return response_text

    async def _gemini_chat(self, user_input: str) -> str:
        """Send message to Gemini and handle tool calls."""
        loop = asyncio.get_event_loop()

        def _send():
            return self.chat.send_message(user_input)

        try:
            response = await loop.run_in_executor(None, _send)
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}") from e

        # Handle function calls
        return await self._handle_response(response)

    async def _handle_response(self, response) -> str:
        """Process Gemini response, executing tool calls as needed."""
        final_text = ""

        try:
            candidate = response.candidates[0]
            parts = candidate.content.parts

            tool_results = []
            for part in parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    logger.info(f"Tool call: {tool_name}({tool_args})")
                    result = await self._execute_tool(tool_name, tool_args)

                    tool_results.append({
                        "tool_name": tool_name,
                        "result": result
                    })

                elif hasattr(part, "text") and part.text:
                    final_text += part.text

            # If tools were called, send results back for final response
            if tool_results:
                results_str = "\n".join(
                    f"[{r['tool_name']}]: {r['result']}" for r in tool_results
                )
                try:
                    loop = asyncio.get_event_loop()

                    def _followup():
                        return self.chat.send_message(
                            f"Tool execution results:\n{results_str}\n\n"
                            f"Now provide a natural, spoken response to the user based on these results."
                        )

                    followup = await loop.run_in_executor(None, _followup)
                    final_text = followup.text
                except Exception as e:
                    logger.error(f"Follow-up error: {e}")
                    final_text = results_str

        except (AttributeError, IndexError) as e:
            logger.debug(f"Response parsing: {e}")
            try:
                final_text = response.text
            except Exception:
                final_text = f"Processing complete, {self.address_form}."

        return final_text.strip() or f"Understood, {self.address_form}. Command acknowledged."

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """Execute a tool function and return result as string."""
        if self.tool_executor:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, self.tool_executor, tool_name, tool_args
                )
                return str(result)
            except Exception as e:
                return f"Tool execution error: {e}"
        else:
            return f"Tool '{tool_name}' called — executor not configured."

    # ─── Offline Fallback ────────────────────────────────────────────────────

    def _offline_response(self, user_input: str) -> str:
        """Basic offline response when Gemini is unavailable."""
        user_lower = user_input.lower()

        greetings = ["hello", "hi", "hey", "good morning", "good evening", "good afternoon"]
        if any(g in user_lower for g in greetings):
            return (
                f"Good day, {self.address_form}. CHOTU systems are operational, "
                f"though I'm currently running without the Gemini AI core. "
                f"Please configure your API key for full capabilities."
            )

        if "time" in user_lower:
            now = datetime.datetime.now()
            return f"The current time is {now.strftime('%I:%M %p')}, {self.address_form}."

        if "date" in user_lower:
            now = datetime.datetime.now()
            return f"Today is {now.strftime('%A, %B %d, %Y')}, {self.address_form}."

        if "shutdown" in user_lower or "sleep" in user_lower:
            return f"I'm ready to execute that, {self.address_form}, but I require explicit confirmation for system power commands."

        if "who are you" in user_lower or "your name" in user_lower:
            return (
                f"I am CHOTU — your elite AI operating system and personal executive assistant. "
                f"Currently operating in limited mode due to unavailable AI core, {self.address_form}. "
                f"Full capabilities require a valid Gemini API key."
            )

        return (
            f"I received your command, {self.address_form}. "
            f"However, I'm operating without the AI core at present. "
            f"Please check the API key configuration to restore full intelligence."
        )

    # ─── Utility ─────────────────────────────────────────────────────────────

    def reset_chat(self):
        """Reset conversation history and start fresh chat session."""
        if self._initialized and self.model:
            self.chat = self.model.start_chat(enable_automatic_function_calling=False)
            self.conversation_history.clear()
            logger.info("Conversation history cleared.")

    def is_ready(self) -> bool:
        """Return True if the brain is fully initialized."""
        return self._initialized

    def get_status(self) -> dict:
        """Return current brain status."""
        return {
            "initialized": self._initialized,
            "model": "gemini-1.5-flash" if self._initialized else "offline",
            "owner": self.owner_name,
            "address_form": self.address_form,
            "gemini_available": GEMINI_AVAILABLE,
        }
