"""Level 5 PowerPoint Exact-Slide Presenter & Active Slide Controller.

Zero external dependencies: uses Python standard library `zipfile` + `xml.etree.ElementTree`
for .pptx XML slide parsing, and Windows COM automation (pywin32 or PowerShell COM fallback)
for active presentation slide navigation.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import atexit
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from typing import TYPE_CHECKING
import zipfile
import xml.etree.ElementTree as ET

from .file_navigator import SecurityBlockError, find_files, get_allowed_roots

if TYPE_CHECKING:
    from .audit import Audit

logger = logging.getLogger("nightmare.ppt_controller")

PPT_EXTENSIONS = {".pptx", ".ppt"}


# ==============================================================================
# 1. Zero-dependency XML Slide Parser (.pptx)
# ==============================================================================

def extract_slide_info(xml_bytes: bytes, slide_num: int) -> dict:
    """Parses a single slide XML and extracts title, body, and full text."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as exc:
        logger.debug("Failed to parse slide XML %d: %s", slide_num, exc)
        return {
            "slide_number": slide_num,
            "title": f"Slide {slide_num}",
            "body": "",
            "full_text": f"Slide {slide_num}",
        }

    title_parts: list[str] = []
    body_parts: list[str] = []

    # Iterate through all shapes
    for sp in root.iter():
        if not sp.tag.endswith("}sp") and sp.tag != "sp":
            continue

        # Check if shape has a title placeholder
        is_title = False
        for ph in sp.iter():
            if ph.tag.endswith("}ph") or ph.tag == "ph":
                ph_type = ph.attrib.get("type", "").lower()
                if ph_type in {"title", "ctrtitle"}:
                    is_title = True
                    break

        # Collect text fragments in shape
        shape_texts = [
            elem.text for elem in sp.iter()
            if (elem.tag.endswith("}t") or elem.tag == "t") and elem.text
        ]
        text_joined = " ".join(" ".join(shape_texts).split())
        if not text_joined:
            continue

        if is_title:
            title_parts.append(text_joined)
        else:
            body_parts.append(text_joined)

    # Fallback to first text run if no explicit title shape was flagged
    if not title_parts and body_parts:
        title = body_parts.pop(0)
    elif title_parts:
        title = " - ".join(title_parts)
    else:
        title = f"Slide {slide_num}"

    body = "\n".join(body_parts)
    full_text = f"{title}\n{body}".strip()

    return {
        "slide_number": slide_num,
        "title": title,
        "body": body,
        "full_text": full_text,
    }


def parse_ppt_slides(file_path: Path | str) -> list[dict]:
    """Parses a .pptx file and extracts slide numbers, titles, and body texts.

    Returns list of dicts: [{'slide_number': int, 'title': str, 'body': str, 'full_text': str}]
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"PowerPoint file not found: {p}")

    slides: list[dict] = []
    with zipfile.ZipFile(p, "r") as zf:
        names = zf.namelist()

        # Attempt to discover slide order via presentation relationships
        slide_names: list[str] = []
        if "ppt/presentation.xml" in names and "ppt/_rels/presentation.xml.rels" in names:
            try:
                rels_root = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
                id_to_target: dict[str, str] = {}
                for rel in rels_root.iter():
                    if rel.tag.endswith("}Relationship") or rel.tag == "Relationship":
                        rid = rel.attrib.get("Id")
                        target = rel.attrib.get("Target", "")
                        if "slide" in target.lower():
                            if not target.startswith("ppt/"):
                                if target.startswith("slides/"):
                                    target = f"ppt/{target}"
                                elif target.startswith("/ppt/"):
                                    target = target.lstrip("/")
                            if rid:
                                id_to_target[rid] = target

                pres_root = ET.fromstring(zf.read("ppt/presentation.xml"))
                for sld_id in pres_root.iter():
                    if sld_id.tag.endswith("}sldId") or sld_id.tag == "sldId":
                        for attr_name, attr_val in sld_id.attrib.items():
                            if attr_name.endswith("id") and attr_val in id_to_target:
                                slide_names.append(id_to_target[attr_val])
                                break
            except Exception as exc:
                logger.debug("Failed parsing presentation.xml order: %s", exc)
                slide_names = []

        # Fallback: scan and sort slide XMLs numerically (ppt/slides/slideN.xml)
        if not slide_names:
            slide_pattern = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
            matched: list[tuple[int, str]] = []
            for name in names:
                m = slide_pattern.match(name)
                if m:
                    matched.append((int(m.group(1)), name))
            matched.sort(key=lambda x: x[0])
            slide_names = [item[1] for item in matched]

        for idx, slide_name in enumerate(slide_names, start=1):
            if slide_name in names:
                data = zf.read(slide_name)
                slide_info = extract_slide_info(data, idx)
                slides.append(slide_info)

    return slides


def find_slide_by_topic(file_path: Path | str, topic: str) -> int | None:
    """Finds the 1-based slide number matching the given topic or keywords."""
    slides = parse_ppt_slides(file_path)
    if not slides:
        return None

    clean_topic = topic.lower().strip()
    topic_tokens = [w for w in re.split(r"[^a-z0-9]+", clean_topic) if len(w) >= 2]
    if not topic_tokens:
        return None

    best_slide: int | None = None
    best_score = 0.0

    for s in slides:
        title_lower = s["title"].lower()
        body_lower = s["body"].lower()

        score = 0.0
        # Exact topic match in title
        if clean_topic in title_lower:
            score = 1.0
        # Exact topic match in body
        elif clean_topic in body_lower:
            score = 0.8
        else:
            title_tokens = [w for w in re.split(r"[^a-z0-9]+", title_lower) if len(w) >= 2]
            body_tokens = [w for w in re.split(r"[^a-z0-9]+", body_lower) if len(w) >= 2]

            title_matches = sum(1 for t in topic_tokens if t in title_tokens)
            body_matches = sum(1 for t in topic_tokens if t in body_tokens)

            title_ratio = title_matches / len(topic_tokens) if topic_tokens else 0
            body_ratio = body_matches / len(topic_tokens) if topic_tokens else 0

            score = (title_ratio * 0.7) + (body_ratio * 0.3)

            # SequenceMatcher fuzzy title fallback
            if score < 0.4:
                fuzzy = SequenceMatcher(None, clean_topic, title_lower).ratio()
                if fuzzy > 0.6:
                    score = max(score, fuzzy * 0.7)

        if score > best_score and score >= 0.3:
            best_score = score
            best_slide = s["slide_number"]

    return best_slide


# ==============================================================================
# 2. COM Automation Adapter (Persistent PowerShell / pywin32 Worker)
# ==============================================================================

class PowerShellWorker:
    """Persistent PowerShell COM worker process communicating over stdin/stdout pipes."""

    def __init__(self, script_path: Path):
        self.script_path = script_path
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _ensure_proc(self) -> subprocess.Popen | None:
        if sys.platform != "win32":
            return None
        if self._proc is not None and self._proc.poll() is None:
            return self._proc

        if not self.script_path.is_file():
            logger.error("PowerPoint worker script not found at %s", self.script_path)
            return None

        try:
            self._proc = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.script_path),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            return self._proc
        except Exception as exc:
            logger.debug("Failed spawning PowerPoint worker process: %s", exc)
            self._proc = None
            return None

    def send_command(self, cmd: str) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "PowerPoint COM automation is only supported on Windows."

        with self._lock:
            proc = self._ensure_proc()
            if not proc or proc.poll() is not None:
                return False, "PowerPoint automation worker is unavailable."

            try:
                proc.stdin.write(cmd.strip() + "\n")
                proc.stdin.flush()

                line = proc.stdout.readline()
                if not line:
                    self.close()
                    return False, "PowerPoint worker process disconnected."

                clean = line.strip()
                if clean.startswith("OK:"):
                    return True, clean[3:].strip() or "OK"
                elif clean.startswith("ERROR:"):
                    return False, clean[6:].strip() or "PowerPoint command failed."
                return True, clean
            except Exception as exc:
                logger.debug("PowerPoint worker command error: %s", exc)
                self.close()
                return False, f"PowerPoint command error: {exc}"

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.poll() is None and self._proc.stdin:
                    self._proc.stdin.write("__EXIT__\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            finally:
                self._proc = None


class PPTCOMAdapter:
    """Handles PowerPoint COM automation via persistent PowerShell/COM worker."""

    def __init__(self, worker: PowerShellWorker | None = None):
        if worker is None:
            script_file = Path(__file__).parent / "ppt_worker.ps1"
            self._worker: PowerShellWorker | None = PowerShellWorker(script_file)
        else:
            self._worker = worker

    def open_presentation_at_slide(self, file_path: str, slide_number: int = 1) -> tuple[bool, str]:
        # Try win32com first if available
        try:
            import win32com.client
            try:
                ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            except Exception:
                ppt = win32com.client.Dispatch("PowerPoint.Application")
            ppt.Visible = True
            pres = ppt.Presentations.Open(os.path.abspath(file_path))
            ss = pres.SlideShowSettings.Run()
            if hasattr(ss, "View") and ss.View:
                ss.View.GotoSlide(int(slide_number))
            elif hasattr(ppt, "ActiveWindow") and ppt.ActiveWindow and hasattr(ppt.ActiveWindow, "View"):
                ppt.ActiveWindow.View.GotoSlide(int(slide_number))
            return True, "OK"
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("win32com failed, falling back to persistent PowerShell worker: %s", exc)

        if not self._worker:
            return False, "PowerPoint automation worker not configured."
        escaped_path = os.path.abspath(file_path).replace("|", "")
        return self._worker.send_command(f"OPEN|{escaped_path}|{int(slide_number)}")

    def start_slideshow(self) -> tuple[bool, str]:
        try:
            import win32com.client
            ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            if ppt.Presentations.Count > 0:
                ppt.ActivePresentation.SlideShowSettings.Run()
                return True, "Slide show started."
            return False, "No presentation is open in PowerPoint."
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("win32com start_slideshow failed: %s", exc)

        if not self._worker:
            return False, "PowerPoint automation worker not configured."
        return self._worker.send_command("START")

    def goto_slide(self, slide_number: int) -> tuple[bool, str]:
        try:
            import win32com.client
            ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            if ppt.Presentations.Count == 0:
                return False, "No presentation is open in PowerPoint."
            if ppt.SlideShowWindows.Count == 0:
                try:
                    ppt.ActivePresentation.SlideShowSettings.Run()
                except Exception:
                    pass
            if ppt.SlideShowWindows.Count > 0:
                ppt.SlideShowWindows(1).View.GotoSlide(int(slide_number))
            elif hasattr(ppt, "ActiveWindow") and ppt.ActiveWindow:
                ppt.ActiveWindow.View.GotoSlide(int(slide_number))
            return True, "OK"
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("win32com goto_slide failed, falling back to persistent worker: %s", exc)

        if not self._worker:
            return False, "PowerPoint automation worker not configured."
        return self._worker.send_command(f"GOTO|{int(slide_number)}")

    def next_slide(self) -> tuple[bool, str]:
        try:
            import win32com.client
            ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            if ppt.Presentations.Count == 0:
                return False, "No presentation is open in PowerPoint."
            if ppt.SlideShowWindows.Count == 0:
                try:
                    ppt.ActivePresentation.SlideShowSettings.Run()
                except Exception:
                    pass
            if ppt.SlideShowWindows.Count > 0:
                ppt.SlideShowWindows(1).View.Next()
            elif hasattr(ppt, "ActiveWindow") and ppt.ActiveWindow:
                try:
                    cur = ppt.ActiveWindow.View.Slide.SlideIndex
                    if cur < ppt.ActivePresentation.Slides.Count:
                        ppt.ActiveWindow.View.GotoSlide(cur + 1)
                except Exception:
                    ppt.ActiveWindow.View.Next()
            return True, "OK"
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("win32com next_slide failed, falling back to persistent worker: %s", exc)

        if not self._worker:
            return False, "PowerPoint automation worker not configured."
        return self._worker.send_command("NEXT")

    def previous_slide(self) -> tuple[bool, str]:
        try:
            import win32com.client
            ppt = win32com.client.GetActiveObject("PowerPoint.Application")
            if ppt.Presentations.Count == 0:
                return False, "No presentation is open in PowerPoint."
            if ppt.SlideShowWindows.Count == 0:
                try:
                    ppt.ActivePresentation.SlideShowSettings.Run()
                except Exception:
                    pass
            if ppt.SlideShowWindows.Count > 0:
                ppt.SlideShowWindows(1).View.Previous()
            elif hasattr(ppt, "ActiveWindow") and ppt.ActiveWindow:
                try:
                    cur = ppt.ActiveWindow.View.Slide.SlideIndex
                    if cur > 1:
                        ppt.ActiveWindow.View.GotoSlide(cur - 1)
                except Exception:
                    ppt.ActiveWindow.View.Previous()
            return True, "OK"
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("win32com previous_slide failed, falling back to persistent worker: %s", exc)

        if not self._worker:
            return False, "PowerPoint automation worker not configured."
        return self._worker.send_command("PREV")

    def close(self) -> None:
        if self._worker:
            self._worker.close()


_global_adapter: PPTCOMAdapter = PPTCOMAdapter()
atexit.register(lambda: _global_adapter.close())


def get_com_adapter() -> PPTCOMAdapter:
    """Returns active PowerPoint COM adapter."""
    return _global_adapter


def set_com_adapter(adapter: PPTCOMAdapter) -> None:
    """Replaces COM adapter (useful for mocking in unit tests)."""
    global _global_adapter
    _global_adapter = adapter


# ==============================================================================
# 3. High-level Controller API
# ==============================================================================

def start_presentation() -> tuple[bool, str]:
    """Starts the slide show presentation if a presentation is open."""
    ok, msg = get_com_adapter().start_slideshow()
    if ok:
        return True, "Slide show presentation started."
    return False, f"Could not start presentation: {msg}"


def open_ppt_at_slide(
    file_path: str,
    slide_number: int = 1,
    audit: Audit | None = None,
    allowed_roots: list[Path] | None = None,
) -> tuple[bool, str]:
    """Resolves file_path via file_navigator (restricted to .pptx / .ppt) and opens it at slide_number."""
    p = Path(file_path).resolve()
    target_path: Path | None = None

    if p.is_file() and p.suffix.lower() in PPT_EXTENSIONS:
        if allowed_roots is None:
            allowed_roots = get_allowed_roots()
        allowed_resolved = [r.resolve() for r in allowed_roots if r.exists()]
        if not any(ar == p or ar in p.parents for ar in allowed_resolved):
            raise SecurityBlockError(f"Security block: '{p}' is outside allowed directories.")
        target_path = p
    else:
        matches = find_files(
            query=file_path,
            ext_filter={"powerpoint"},
            audit=audit,
            allowed_roots=allowed_roots,
        )
        if not matches:
            return False, f"I couldn't find any presentation related to {file_path}."

        if len(matches) > 1 and abs(matches[0].score - matches[1].score) < 0.15 and matches[1].score >= 0.6:
            close_matches = [m.filename for m in matches[:3] if abs(m.score - matches[0].score) < 0.15]
            return False, f"I found multiple presentations matching that: {', '.join(close_matches)}. Which one would you like to open?"

        target_path = matches[0].path

    if target_path.suffix.lower() not in PPT_EXTENSIONS:
        return False, f"'{target_path.name}' is not a PowerPoint presentation (.pptx / .ppt)."

    ok, msg = get_com_adapter().open_presentation_at_slide(str(target_path), slide_number)
    if ok:
        return True, f"Opened {target_path.name} at slide {slide_number}."
    return False, f"Could not open {target_path.name}: {msg}"


def goto_slide(slide_number: int) -> tuple[bool, str]:
    """Jumps to slide_number in an active PowerPoint presentation."""
    ok, msg = get_com_adapter().goto_slide(slide_number)
    if ok:
        return True, f"Jumped to slide {slide_number}."
    return False, f"Failed to jump to slide {slide_number}: {msg}"


def next_slide() -> tuple[bool, str]:
    """Advances to next slide in an active PowerPoint presentation."""
    ok, msg = get_com_adapter().next_slide()
    if ok:
        return True, "Advanced to next slide."
    return False, f"Failed to advance slide: {msg}"


def previous_slide() -> tuple[bool, str]:
    """Returns to previous slide in an active PowerPoint presentation."""
    ok, msg = get_com_adapter().previous_slide()
    if ok:
        return True, "Returned to previous slide."
    return False, f"Failed to return to previous slide: {msg}"


def show_slide_about(topic: str, file_path: str | None = None) -> tuple[bool, str]:
    """Finds slide by topic in presentation and jumps to it."""
    if not file_path:
        return False, "No presentation file specified to search for slides."
    target_path = Path(file_path).resolve()
    if not target_path.is_file():
        return False, f"Presentation file not found: {file_path}"

    slide_num = find_slide_by_topic(target_path, topic)
    if slide_num is None:
        return False, f"I couldn't find any slide about {topic}."

    ok, msg = goto_slide(slide_num)
    if ok:
        return True, f"Jumped to slide {slide_num} about {topic}."
    return False, msg
