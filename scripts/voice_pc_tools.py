from __future__ import annotations

import os
import re
import subprocess
import unicodedata
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NOTES_FILE = REPO_ROOT / "notes" / "voice_notes.md"


@dataclass
class ToolOutcome:
    handled: bool
    spoken: str = ""
    status: str = ""


def handle_pc_command(text: str, *, execute: bool = True) -> ToolOutcome:
    """Handle fast local PC commands before asking the LLM.

    The commands here are intentionally conservative: opening apps/sites,
    media keys, clipboard reads, notes, time/date, and web searches.
    """
    clean = _normalize(text)
    if not clean:
        return ToolOutcome(False)

    for handler in (
        _handle_note,
        _handle_time_date,
        _handle_volume_media,
        _handle_clipboard,
        _handle_search,
        _handle_open,
    ):
        outcome = handler(text, clean, execute)
        if outcome.handled:
            return outcome

    return ToolOutcome(False)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^\w\s:/.-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _strip_command(clean: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if clean == prefix:
            return ""
        if clean.startswith(prefix + " "):
            return clean[len(prefix) + 1 :].strip()
    return None


def _open_target(target: str | Path, *, execute: bool) -> None:
    if not execute:
        return
    os.startfile(str(target))  # type: ignore[attr-defined]


def _run_hidden(args: list[str], *, execute: bool) -> None:
    if not execute:
        return
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _handle_open(original: str, clean: str, execute: bool) -> ToolOutcome:
    target = _strip_command(
        clean,
        (
            "abre",
            "abrir",
            "abreme",
            "lanza",
            "inicia",
            "ejecuta",
            "pon",
            "open",
            "open up",
            "launch",
            "start",
            "run",
        ),
    )
    if target is None:
        return ToolOutcome(False)

    if not target:
        return ToolOutcome(True, "Dime qué quieres que abra.", "open missing target")

    folder_aliases = {
        "jarvis": REPO_ROOT,
        "proyecto": REPO_ROOT,
        "proyecto jarvis": REPO_ROOT,
        "carpeta jarvis": REPO_ROOT,
        "carpeta de jarvis": REPO_ROOT,
        "descargas": Path.home() / "Downloads",
        "documentos": Path.home() / "Documents",
        "escritorio": Path.home() / "Desktop",
    }
    for alias, path in folder_aliases.items():
        if alias in target:
            _open_target(path, execute=execute)
            return ToolOutcome(True, f"Abro {alias}.", f"open folder: {path}")

    sites = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "chatgpt": "https://chatgpt.com",
        "gmail": "https://mail.google.com",
        "whatsapp": "https://web.whatsapp.com",
        "spotify web": "https://open.spotify.com",
    }
    for alias, url in sites.items():
        if alias in target:
            _open_target(url, execute=execute)
            return ToolOutcome(True, f"Abro {alias}.", f"open site: {url}")

    app_protocols = {
        "spotify": ("spotify:", "https://open.spotify.com"),
        "discord": ("discord:", "https://discord.com/app"),
        "steam": ("steam:", "https://store.steampowered.com"),
    }
    for alias, (protocol, fallback_url) in app_protocols.items():
        if alias in target:
            if execute:
                try:
                    _open_target(protocol, execute=True)
                except OSError:
                    _open_target(fallback_url, execute=True)
            return ToolOutcome(True, f"Abro {alias}.", f"open app protocol: {protocol}")

    apps = {
        "bloc de notas": "notepad.exe",
        "notepad": "notepad.exe",
        "notas": "notepad.exe",
        "calculadora": "calc.exe",
        "calculator": "calc.exe",
        "explorador": "explorer.exe",
        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",
        "terminal": "wt.exe",
        "powershell": "powershell.exe",
        "cmd": "cmd.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "visual studio code": "code",
        "vs code": "code",
        "vscode": "code",
    }
    for alias, command in apps.items():
        if alias in target:
            _run_hidden(["cmd", "/c", "start", "", command], execute=execute)
            return ToolOutcome(True, f"Abro {alias}.", f"open app: {command}")

    if "." in target and " " not in target:
        url = target if "://" in target else f"https://{target}"
        _open_target(url, execute=execute)
        return ToolOutcome(True, f"Abro {target}.", f"open url: {url}")

    return ToolOutcome(False)


def _handle_search(original: str, clean: str, execute: bool) -> ToolOutcome:
    youtube_query = _strip_command(
        clean,
        (
            "busca en youtube",
            "buscar en youtube",
            "busca youtube",
            "pon en youtube",
        ),
    )
    if youtube_query is not None:
        if not youtube_query:
            return ToolOutcome(True, "Dime qué quieres buscar en YouTube.", "youtube search missing query")
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(
            youtube_query
        )
        _open_target(url, execute=execute)
        return ToolOutcome(True, f"Busco {youtube_query} en YouTube.", "youtube search")

    google_query = _strip_command(
        clean,
        (
            "busca en google",
            "buscar en google",
            "busca en internet",
            "buscar en internet",
            "busca",
            "buscar",
        ),
    )
    if google_query is None:
        return ToolOutcome(False)
    if not google_query:
        return ToolOutcome(True, "Dime qué quieres buscar.", "search missing query")
    url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(google_query)
    _open_target(url, execute=execute)
    return ToolOutcome(True, f"Busco {google_query}.", "web search")


def _handle_volume_media(original: str, clean: str, execute: bool) -> ToolOutcome:
    if (
        re.search(r"\b(sube|subir|aumenta|aumentar)\b.{0,16}\bvolumen\b", clean)
        or "mas volumen" in clean
    ):
        _send_media_key(0xAF, count=4, execute=execute)
        return ToolOutcome(True, "Subo el volumen.", "volume up")
    if (
        re.search(r"\b(baja|bajar|reduce|reducir)\b.{0,16}\bvolumen\b", clean)
        or "menos volumen" in clean
    ):
        _send_media_key(0xAE, count=4, execute=execute)
        return ToolOutcome(True, "Bajo el volumen.", "volume down")
    if any(phrase in clean for phrase in ("silencia", "mute", "quita el sonido", "silencio")):
        _send_media_key(0xAD, execute=execute)
        return ToolOutcome(True, "Alterno el silencio.", "volume mute")
    if any(phrase in clean for phrase in ("pausa", "reanuda", "play pause", "play", "continua la musica")):
        _send_media_key(0xB3, execute=execute)
        return ToolOutcome(True, "Hecho.", "media play/pause")
    if any(phrase in clean for phrase in ("siguiente cancion", "siguiente pista", "pasa cancion")):
        _send_media_key(0xB0, execute=execute)
        return ToolOutcome(True, "Paso a la siguiente.", "media next")
    if any(phrase in clean for phrase in ("cancion anterior", "pista anterior", "vuelve cancion")):
        _send_media_key(0xB1, execute=execute)
        return ToolOutcome(True, "Vuelvo a la anterior.", "media previous")
    return ToolOutcome(False)


def _send_media_key(vk: int, *, count: int = 1, execute: bool) -> None:
    if not execute:
        return
    script = (
        "Add-Type -Namespace Win32 -Name Native -MemberDefinition "
        "'[System.Runtime.InteropServices.DllImport(\"user32.dll\")]"
        "public static extern void keybd_event(byte bVk, byte bScan, int dwFlags, int dwExtraInfo);';"
        f"1..{count} | ForEach-Object {{"
        f"[Win32.Native]::keybd_event({vk},0,0,0);"
        f"[Win32.Native]::keybd_event({vk},0,2,0);"
        "Start-Sleep -Milliseconds 35}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )


def _handle_note(original: str, clean: str, execute: bool) -> ToolOutcome:
    note = _strip_command(
        clean,
        (
            "anota",
            "apunta",
            "toma nota",
            "recuerda que",
            "guarda nota",
        ),
    )
    if note is None:
        return ToolOutcome(False)
    if not note:
        return ToolOutcome(True, "Dime qué quieres que anote.", "note missing content")
    if execute:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        NOTES_FILE.write_text(
            (NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else "")
            + f"- {stamp}: {original.strip()}\n",
            encoding="utf-8",
        )
    return ToolOutcome(True, "Lo dejo anotado.", f"note saved: {NOTES_FILE}")


def _handle_time_date(original: str, clean: str, execute: bool) -> ToolOutcome:
    now = datetime.now()
    if "que hora es" in clean or clean in {"hora", "dime la hora"}:
        return ToolOutcome(True, f"Son las {now:%H:%M}.", "time")
    if "que dia es" in clean or "fecha" in clean or clean in {"dia"}:
        return ToolOutcome(True, f"Hoy es {now:%d/%m/%Y}.", "date")
    return ToolOutcome(False)


def _handle_clipboard(original: str, clean: str, execute: bool) -> ToolOutcome:
    if not any(
        phrase in clean
        for phrase in (
            "lee portapapeles",
            "leer portapapeles",
            "que hay en el portapapeles",
            "que tengo en el portapapeles",
            "que tengo copiado",
            "lee lo copiado",
        )
    ):
        return ToolOutcome(False)
    if not execute:
        return ToolOutcome(True, "Leo el portapapeles.", "clipboard read")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        text=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    clip = result.stdout.strip()
    if not clip:
        return ToolOutcome(True, "El portapapeles está vacío.", "clipboard empty")
    clip = re.sub(r"\s+", " ", clip)
    if len(clip) > 180:
        clip = clip[:177].rstrip() + "..."
    return ToolOutcome(True, f"En el portapapeles hay: {clip}", "clipboard read")
