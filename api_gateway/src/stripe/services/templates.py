from pathlib import Path
from typing import Optional, Dict

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

class TemplateNotFound(Exception):
    pass


def _load(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def render_templates(event_name: str, vars: Dict[str, object]) -> Dict[str, Optional[str]]:
    """
    Load and render `{event_name}.txt` (required) and `{event_name}.html` (optional)
    from the stripe templates directory. Returns a dict with keys `text` and `html`.
    Uses Python str.format for placeholder substitution.
    """
    txt_path = TEMPLATES_DIR / f"{event_name}.txt"
    html_path = TEMPLATES_DIR / f"{event_name}.html"

    if not txt_path.exists():
        raise TemplateNotFound(f"Missing required text template: {txt_path}")

    text_raw = _load(txt_path)
    try:
        text = text_raw.format(**vars)
    except KeyError as e:
        missing = e.args[0]
        raise KeyError(f"Missing template variable '{missing}' for {txt_path}")

    html: Optional[str] = None
    if html_path.exists():
        html_raw = _load(html_path)
        try:
            html = html_raw.format(**vars)
        except KeyError as e:
            missing = e.args[0]
            raise KeyError(f"Missing template variable '{missing}' for {html_path}")

    return {"text": text, "html": html}
