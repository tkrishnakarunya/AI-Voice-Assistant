"""
AIVA Agent — fully-featured AI voice assistant backend.

Tool dispatch order:
  1.  Deterministic rules  (time, date, quit, reset)
  2.  File-system tools    (create/delete files & folders, notes)
  3.  URL/site opening     (smart: known alias → heuristic → LLM → Google)
  4.  App launcher         (Windows apps, browsers, music, etc.)
  5.  Web actions          (search, weather, Wikipedia, news, maps, translate)
  6.  AI archiver          ("using artificial intelligence …")
  7.  LLM chat fallback    (Groq LLaMA 70B)
  8.  Google search        (if LLM refuses or errors)
"""

import os
import re
import datetime
import webbrowser
import subprocess
import glob
import random
import pathlib
from typing import Optional
from llama_index.core.chat_engine.types import BaseChatEngine
from src.device_control import handle_device_command


# ──────────────────────────────────────────────────────────────────────────────

class VoiceAssistantResponse:
    def __init__(self, text: str):
        self.response_text = text

    def __str__(self):
        return self.response_text


# ──────────────────────────────────────────────────────────────────────────────

class VoiceAssistantAgent:
    """Hybrid rule + LLM agent powering AIVA."""

    REFUSAL_PHRASES = [
        "sorry, but i can't", "i'm sorry, i can't", "i cannot assist",
        "i can't assist with that", "i am unable to", "i'm unable to",
        "i don't have the ability", "i cannot", "cannot help",
    ]

    WIN_APPS = {
        "task manager":  "taskmgr",
        "control panel": "control",
        "settings":      "ms-settings:",
        "paint":         "mspaint",
        "word":          "winword",
        "excel":         "excel",
        "powerpoint":    "powerpnt",
        "cmd":           "cmd",
        "command prompt":"cmd",
        "terminal":      "wt",
        "powershell":    "powershell",
        "snipping tool": "snippingtool",
        "camera":        "microsoft.windows.camera:",
        "clock":         "ms-clock:",
        "store":         "ms-windows-store:",
        "photos":        "ms-photos:",
        "calendar":      "outlookcal:",
        "sticky notes":  "ms-stickynotes:",
        "spotify":       "spotify",
        "vlc":           "vlc",
        "chrome":        "chrome",
        "firefox":       "firefox",
        "edge":          "msedge",
        "notepad":       "notepad",
        "wordpad":       "wordpad",
        "calculator":    "calc",
        "file explorer": "explorer",
        "explorer":      "explorer",
    }

    # Sites that should NOT trigger the site opener
    NON_SITE_KEYWORDS = (
        "file explorer", " drive", " disk", " folder", " directory",
        "desktop", "downloads", "documents", "pictures", "music folder",
        "videos", "notepad", "calculator", "task manager", "control panel",
        "settings", "cmd", "terminal", "powershell", "paint",
        "word", "excel", "powerpoint", "chrome", "firefox", "edge",
        "vlc", "spotify", "snipping", "camera", "clock", "store",
    )

    def __init__(self, chat_engine: BaseChatEngine):
        self.chat_engine = chat_engine

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _R(self, text: str) -> VoiceAssistantResponse:
        return VoiceAssistantResponse(text)

    def _is_refusal(self, text: str) -> bool:
        lower = text.lower().strip()
        return any(p in lower for p in self.REFUSAL_PHRASES)

    def _google_search(self, query: str):
        webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")

    def _open_in_explorer(self, path: str):
        if os.name == "nt":
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", path])

    def _resolve_path(self, raw: str) -> str:
        """Convert natural-language location hints to absolute paths."""
        raw = raw.strip().strip('"').strip("'")

        if re.match(r"^[A-Za-z]:[\\\/]", raw):
            return raw

        lower = raw.lower()
        MAP = {
            "desktop":    str(pathlib.Path.home() / "Desktop"),
            "documents":  str(pathlib.Path.home() / "Documents"),
            "downloads":  str(pathlib.Path.home() / "Downloads"),
            "pictures":   str(pathlib.Path.home() / "Pictures"),
            "music":      str(pathlib.Path.home() / "Music"),
            "videos":     str(pathlib.Path.home() / "Videos"),
            "current":    os.getcwd(),
            "this folder":os.getcwd(),
            "home":       str(pathlib.Path.home()),
        }
        for key, val in MAP.items():
            if key in lower:
                return val

        # Single letter like "D", "D drive", "D folder", "D:"
        m = re.match(r"^([a-zA-Z])\s*(?:drive|folder|disk|:)?$", raw.strip())
        if m:
            return f"{m.group(1).upper()}:\\"

        return str(pathlib.Path.home() / raw)

    def _llm_resolve_url(self, phrase: str) -> Optional[str]:
        """Ask Groq LLM to return the best URL for an unknown phrase."""
        prompt = (
            f'The user said: "open {phrase}".\n'
            "Return ONLY the most likely website URL starting with https://. "
            "No explanation. If unknown, reply: UNKNOWN"
        )
        try:
            resp = self.chat_engine.chat(prompt)
            text = str(resp).strip().split()[0]
            if text.startswith("http") and "." in text:
                return text
        except Exception:
            pass
        return None

    # ── Tool: Universal site opener ───────────────────────────────────────────

    def _tool_open_site(self, raw_target: str) -> VoiceAssistantResponse:
        phrase = raw_target.strip()
        lower = phrase.lower()

        # Strip trailing noise words
        for noise in (" website", " site", " web", " page", " portal", " url", " homepage", " link"):
            if lower.endswith(noise):
                lower = lower[:-len(noise)].strip()
                phrase = phrase[:-len(noise)].strip()

        KNOWN = {
            "youtube": "https://www.youtube.com",
            "yt": "https://www.youtube.com",
            "google": "https://www.google.com",
            "gmail": "https://mail.google.com",
            "github": "https://github.com",
            "stackoverflow": "https://stackoverflow.com",
            "wikipedia": "https://www.wikipedia.org",
            "netflix": "https://www.netflix.com",
            "instagram": "https://www.instagram.com",
            "twitter": "https://twitter.com",
            "x": "https://x.com",
            "linkedin": "https://www.linkedin.com",
            "reddit": "https://www.reddit.com",
            "chatgpt": "https://chat.openai.com",
            "openai": "https://openai.com",
            "groq": "https://groq.com",
            "amazon": "https://www.amazon.in",
            "flipkart": "https://www.flipkart.com",
            "hotstar": "https://www.hotstar.com",
            "prime": "https://www.primevideo.com",
            "maps": "https://maps.google.com",
            "meet": "https://meet.google.com",
            "drive": "https://drive.google.com",
            "docs": "https://docs.google.com",
            "sheets": "https://sheets.google.com",
            "slides": "https://slides.google.com",
            "classroom": "https://classroom.google.com",
            "cmrec": "https://cmrec.ac.in",
            "whatsapp": "https://web.whatsapp.com",
            "telegram": "https://web.telegram.org",
            "discord": "https://discord.com/app",
            "spotify": "https://open.spotify.com",
            "twitch": "https://www.twitch.tv",
            "canva": "https://www.canva.com",
            "figma": "https://www.figma.com",
            "notion": "https://www.notion.so",
            "vercel": "https://vercel.com",
            "netlify": "https://app.netlify.com",
            "heroku": "https://dashboard.heroku.com",
            "aws": "https://console.aws.amazon.com",
            "azure": "https://portal.azure.com",
            "gcp": "https://console.cloud.google.com",
        }
        if lower in KNOWN:
            webbrowser.open(KNOWN[lower])
            return self._R(f"Opening {phrase.capitalize()} for you.")

        # Already a valid domain/URL
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", lower):
            url = phrase if phrase.startswith("http") else f"https://{lower}"
            webbrowser.open(url)
            return self._R(f"Opening {lower} in your browser.")

        # Single clean word → try www.word.com
        if re.match(r"^[\w-]+$", lower):
            url = f"https://www.{lower}.com"
            webbrowser.open(url)
            return self._R(f"Trying {lower}.com for you.")

        # Multi-word: ask LLM to resolve
        url = self._llm_resolve_url(phrase)
        if url:
            webbrowser.open(url)
            return self._R(f"Opening {url} as requested.")

        # Final fallback: Google search
        self._google_search(phrase)
        return self._R(f"Couldn't find a direct link, so I've searched Google for '{phrase}'.")

    # ── Tool: Create file ─────────────────────────────────────────────────────

    def _tool_create_file(self, message: str, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        pattern = re.search(
            r"(?:create|make|new)\s+(?:a\s+)?(?:new\s+)?file\s+"
            r"(?:named?\s+|called?\s+)?([^\s,]+)"
            r"(?:\s+(?:in|on|at|inside)\s+(?:the\s+)?(.+))?",
            msg_lower
        )
        if not pattern:
            return None

        filename = pattern.group(1).strip()
        location_hint = (pattern.group(2) or "desktop").strip()
        folder = self._resolve_path(location_hint)

        try:
            os.makedirs(folder, exist_ok=True)
            full_path = os.path.join(folder, filename)
            open(full_path, "w").close()
            self._open_in_explorer(folder)
            return self._R(
                f"Created '{filename}' in {folder}. "
                f"File Explorer is now open."
            )
        except Exception as e:
            return self._R(f"Failed to create file: {e}")

    # ── Tool: Create folder ───────────────────────────────────────────────────

    def _tool_create_folder(self, message: str, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        pattern = re.search(
            r"(?:create|make|new)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+"
            r"(?:named?\s+|called?\s+)?([^\s,]+)"
            r"(?:\s+(?:in|on|at|inside)\s+(?:the\s+)?(.+))?",
            msg_lower
        )
        if not pattern:
            return None

        folder_name = pattern.group(1).strip()
        location_hint = (pattern.group(2) or "desktop").strip()
        parent = self._resolve_path(location_hint)

        try:
            full_path = os.path.join(parent, folder_name)
            os.makedirs(full_path, exist_ok=True)
            self._open_in_explorer(full_path)
            return self._R(
                f"Created folder '{folder_name}' in {parent}. "
                f"File Explorer is now open."
            )
        except Exception as e:
            return self._R(f"Failed to create folder: {e}")

    # ── Tool: Open folder in Explorer ─────────────────────────────────────────

    def _tool_open_folder(self, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        # File Explorer directly
        if "file explorer" in msg_lower or "open explorer" in msg_lower:
            self._open_in_explorer(str(pathlib.Path.home()))
            return self._R("Opening File Explorer.")

        # Explicit drive letter: "open D drive", "open D:", "open D folder"
        drive_m = re.search(
            r"\bopen\s+([A-Za-z])\s*(?:drive|disk|:|folder)\b",
            msg_lower
        )
        if drive_m:
            letter = drive_m.group(1).upper()
            path = f"{letter}:\\"
            if os.path.exists(path):
                self._open_in_explorer(path)
                return self._R(f"Opening {letter}: drive in File Explorer.")

        # Named system folders
        NAMED = {
            "desktop":   str(pathlib.Path.home() / "Desktop"),
            "documents": str(pathlib.Path.home() / "Documents"),
            "downloads": str(pathlib.Path.home() / "Downloads"),
            "pictures":  str(pathlib.Path.home() / "Pictures"),
            "music":     str(pathlib.Path.home() / "Music"),
            "videos":    str(pathlib.Path.home() / "Videos"),
        }
        for kw, path in NAMED.items():
            if re.search(rf"\bopen\s+(?:the\s+|my\s+)?{kw}\b", msg_lower):
                self._open_in_explorer(path)
                return self._R(f"Opening {kw.capitalize()} folder.")

        return None

    # ── Tool: Delete file ─────────────────────────────────────────────────────

    def _tool_delete_file(self, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        pattern = re.search(
            r"(?:delete|remove|trash)\s+(?:the\s+)?(?:file\s+)?([^\s,]+\.[a-zA-Z0-9]+)"
            r"(?:\s+(?:from|in|at)\s+(.+))?",
            msg_lower
        )
        if not pattern:
            return None

        filename = pattern.group(1).strip()
        location_hint = (pattern.group(2) or "desktop").strip()
        folder = self._resolve_path(location_hint)
        full_path = os.path.join(folder, filename)

        if not os.path.exists(full_path):
            return self._R(f"I couldn't find '{filename}' in {folder}.")
        try:
            os.remove(full_path)
            return self._R(f"Deleted '{filename}' from {folder}.")
        except Exception as e:
            return self._R(f"Failed to delete: {e}")

    # ── Tool: Note-taking ─────────────────────────────────────────────────────

    def _tool_write_note(self, message: str, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        pattern = re.search(
            r"(?:write|save|take|add)\s+(?:a\s+)?note[:\s]+(.+)",
            msg_lower
        )
        if not pattern and not msg_lower.startswith("note:"):
            return None

        content = pattern.group(1).strip() if pattern else msg_lower[5:].strip()
        notes_dir = str(pathlib.Path.home() / "Documents" / "AIVA Notes")
        os.makedirs(notes_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(notes_dir, f"note_{ts}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            f.write(f"[AIVA Note — {now}]\n\n{content}\n")
        return self._R(f"Note saved to Documents/AIVA Notes/{os.path.basename(filename)}.")

    # ── Tool: Windows app launcher ────────────────────────────────────────────

    def _tool_open_app(self, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        if not msg_lower.startswith("open "):
            return None
        phrase = msg_lower[5:].strip()
        for name, cmd in self.WIN_APPS.items():
            if name in phrase:
                try:
                    if cmd.endswith(":"):
                        os.startfile(cmd)
                    else:
                        subprocess.Popen(cmd, shell=True)
                    return self._R(f"Opening {name.title()}.")
                except Exception as e:
                    return self._R(f"Couldn't open {name}: {e}")
        return None

    # ── Tool: Music ───────────────────────────────────────────────────────────

    def _tool_music(self, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        if not any(t in msg_lower for t in ("open music", "play music", "play song", "play a song")):
            return None
        mp3_files = glob.glob("**/*.mp3", recursive=True)
        if mp3_files:
            path = os.path.abspath(mp3_files[0])
            try:
                if os.name == "nt":
                    os.startfile(path)
                else:
                    subprocess.Popen(["open", path])
                return self._R(f"Playing '{os.path.basename(path)}'.")
            except Exception:
                pass
        webbrowser.open("https://www.youtube.com/watch?v=jfKfPfyJRdk")
        return self._R("No local tracks found. Opened Lofi Girl on YouTube.")

    # ── Tool: Web actions ─────────────────────────────────────────────────────

    def _tool_web_actions(self, message: str, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        # 1. Compound Search patterns: "open X and search for Y" or "search for Y on X"
        # Match "open {site} and search/play {query}"
        m_compound = re.search(
            r"\bopen\s+([\w\.-]+)\s+and\s+(?:search\s+for|play|lookup|look\s+up)\s+(.+)$",
            msg_lower
        )
        # Match "search/play {query} on {site}"
        m_on = re.search(
            r"\b(?:search\s+for|play|lookup|look\s+up)\s+(.+)\s+on\s+([\w\.-]+)\b",
            msg_lower
        )

        site_name = None
        query = None

        if m_compound:
            site_name = m_compound.group(1).strip().lower()
            query = message[m_compound.start(2):].strip()
        elif m_on:
            site_name = m_on.group(2).strip().lower()
            query = message[m_on.start(1):m_on.end(1)].strip()

        if site_name and query:
            # Strip noise from site name
            for noise in (" website", " site", " web", " portal"):
                if site_name.endswith(noise):
                    site_name = site_name[:-len(noise)].strip()

            if site_name in ("youtube", "yt"):
                webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
                return self._R(f"Searching YouTube for '{query}'.")
            elif site_name in ("google", "browser"):
                self._google_search(query)
                return self._R(f"Searching Google for '{query}'.")
            elif site_name == "wikipedia":
                webbrowser.open(f"https://en.wikipedia.org/w/index.php?search={query.replace(' ', '+')}")
                return self._R(f"Searching Wikipedia for '{query}'.")
            elif site_name == "amazon":
                webbrowser.open(f"https://www.amazon.in/s?k={query.replace(' ', '+')}")
                return self._R(f"Searching Amazon for '{query}'.")
            elif site_name == "flipkart":
                webbrowser.open(f"https://www.flipkart.com/search?q={query.replace(' ', '+')}")
                return self._R(f"Searching Flipkart for '{query}'.")
            elif site_name in ("github", "git"):
                webbrowser.open(f"https://github.com/search?q={query.replace(' ', '+')}")
                return self._R(f"Searching GitHub for '{query}'.")
            else:
                domain = site_name if "." in site_name else f"{site_name}.com"
                webbrowser.open(f"https://www.google.com/search?q=site%3A{domain}+{query.replace(' ', '+')}")
                return self._R(f"Searching for '{query}' on {domain}.")

        # 2. General searches: "search for X" / "look up X"
        for trigger in ("search for", "look up", "google for", "find me", "search google"):
            if msg_lower.startswith(trigger):
                q = message[len(trigger):].strip()
                self._google_search(q)
                return self._R(f"Searching Google for '{q}'.")

        # Wikipedia search directly
        if "wikipedia" in msg_lower and any(t in msg_lower for t in ("search", "look up", "about")):
            q = re.sub(r"(wikipedia|search|look up|about|on)", "", msg_lower).strip()
            webbrowser.open(f"https://en.wikipedia.org/w/index.php?search={q.replace(' ', '+')}")
            return self._R(f"Searching Wikipedia for '{q}'.")

        # Weather
        if "weather" in msg_lower:
            loc_m = re.search(r"(?:weather in|weather for|weather at)\s+(.+)", msg_lower)
            loc = loc_m.group(1).strip() if loc_m else "my location"
            webbrowser.open(f"https://www.google.com/search?q=weather+{loc.replace(' ', '+')}")
            return self._R(f"Checking weather for {loc}.")

        # News
        if "news" in msg_lower and any(t in msg_lower for t in ("open", "show", "latest", "get")):
            webbrowser.open("https://news.google.com")
            return self._R("Opening Google News.")

        # Maps / directions
        if any(t in msg_lower for t in ("directions to", "navigate to", "take me to")):
            dest = re.sub(r"(directions to|navigate to|take me to)", "", msg_lower).strip()
            webbrowser.open(f"https://maps.google.com/maps?q={dest.replace(' ', '+')}")
            return self._R(f"Opening Maps directions to '{dest}'.")

        if any(t in msg_lower for t in ("find on map", "show on map", "locate on map")):
            place = re.sub(r"(find on map|show on map|locate on map)", "", msg_lower).strip()
            webbrowser.open(f"https://maps.google.com/maps?q={place.replace(' ', '+')}")
            return self._R(f"Showing '{place}' on Google Maps.")

        # Play on YouTube directly
        if "play on youtube" in msg_lower or ("youtube" in msg_lower and "search" in msg_lower):
            q = re.sub(r"(play on youtube|youtube|search)", "", msg_lower).strip()
            webbrowser.open(f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}")
            return self._R(f"Searching YouTube for '{q}'.")

        # Translate
        if "translate" in msg_lower:
            q = re.sub(r"(translate|please)", "", msg_lower).strip()
            webbrowser.open(f"https://translate.google.com/?text={q.replace(' ', '+')}")
            return self._R(f"Opening Google Translate.")

        return None

    # ── Tool: AI archiver ─────────────────────────────────────────────────────

    def _tool_ai_archiver(self, message: str, msg_lower: str) -> Optional[VoiceAssistantResponse]:
        if "using artificial intelligence" not in msg_lower:
            return None
        llm_resp = self.chat_engine.chat(message)
        response_text = str(llm_resp)
        try:
            os.makedirs("Openai", exist_ok=True)
            parts = msg_lower.split("artificial intelligence")
            suffix = re.sub(r"[^\w\s-]", "", parts[1].strip() if len(parts) > 1 else "query")[:60] or "query"
            fname = f"Openai/{suffix}_{random.randint(1000, 9999)}.txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"Prompt: {message}\n{'-'*40}\n{response_text}\n")
            return self._R(f"Saved to '{fname}'.\n\n{response_text}")
        except Exception as e:
            return self._R(f"Query done but save failed: {e}\n\n{response_text}")

    # ── Main router ───────────────────────────────────────────────────────────

    def chat(self, message: str) -> VoiceAssistantResponse:
        msg_lower = message.lower().strip()

        # Device Control (Settings, Volume, Brightness, Bluetooth, Wi-Fi, Dark/Light Mode)
        device_resp = handle_device_command(msg_lower)
        if device_resp:
            return self._R(device_resp)

        # 1. Time & Date
        if any(t in msg_lower for t in ("the time", "current time", "what time", "tell me the time")):
            now = datetime.datetime.now()
            return self._R(
                f"the time is {now.strftime('%I:%M %p')} "
                f"({now.strftime('%H')} bajke {now.strftime('%M')} minutes)."
            )

        if any(t in msg_lower for t in ("today's date", "current date", "what date", "what day", "which day")):
            now = datetime.datetime.now()
            return self._R(f"Today is {now.strftime('%A, %d %B %Y')}.")

        # 2. Quit / Reset
        if any(t in msg_lower for t in ("quit aiva", "jarvis quit", "goodbye aiva", "bye aiva")):
            return self._R("Goodbye. Standby mode activated.")

        if any(t in msg_lower for t in ("reset chat", "clear chat history")):
            self.reset()
            return self._R("Chat history cleared.")

        # 3. File-system tools
        if any(t in msg_lower for t in ("create", "make", "new")):
            if "file" in msg_lower and "folder" not in msg_lower and "directory" not in msg_lower:
                r = self._tool_create_file(message, msg_lower)
                if r: return r
            if any(t in msg_lower for t in ("folder", "directory")):
                r = self._tool_create_folder(message, msg_lower)
                if r: return r

        if any(t in msg_lower for t in ("delete", "remove", "trash")):
            r = self._tool_delete_file(msg_lower)
            if r: return r

        if any(t in msg_lower for t in ("write a note", "save a note", "take a note", "add a note")):
            r = self._tool_write_note(message, msg_lower)
            if r: return r
        if msg_lower.startswith("note:"):
            r = self._tool_write_note(message, msg_lower)
            if r: return r

        # 4. Folder / Explorer (before site opener — but only for explicit drive/folder words)
        if any(t in msg_lower for t in ("open", "show", "navigate")):
            r = self._tool_open_folder(msg_lower)
            if r: return r

        # 5. Windows apps (before site opener)
        r = self._tool_open_app(msg_lower)
        if r: return r

        # 6. Music
        r = self._tool_music(msg_lower)
        if r: return r

        # 7. Web actions (search, weather, news, maps, YouTube, translate)
        r = self._tool_web_actions(message, msg_lower)
        if r: return r

        # 8. Universal site opener — runs for ANY "open X" that hasn't been
        #    caught by an earlier tool
        if msg_lower.startswith("open "):
            raw_target = message[5:].strip()
            # Skip if it looks like a non-site intent that slipped through
            if not any(kw in msg_lower for kw in self.NON_SITE_KEYWORDS):
                return self._tool_open_site(raw_target)

        # 9. AI archiver
        r = self._tool_ai_archiver(message, msg_lower)
        if r: return r

        # 10. LLM chat fallback (Groq LLaMA 70B)
        try:
            llm_resp = self.chat_engine.chat(message)
            response_text = str(llm_resp).strip()
        except Exception as e:
            response_text = ""
            print(f"[AIVA] LLM error: {e}")

        if not response_text or self._is_refusal(response_text):
            self._google_search(message)
            return self._R(
                f"I couldn't answer that directly, so I've searched Google for '{message}'."
            )

        return self._R(response_text)

    def reset(self):
        if hasattr(self.chat_engine, "reset"):
            self.chat_engine.reset()
