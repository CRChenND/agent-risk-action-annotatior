from __future__ import annotations
import json, re, ast
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------- IO ----------
def read_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    path = Path(path)
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except Exception as e:
                raise ValueError(f"[JSONL Error] line {i}: {e}\n{ s[:200] }")
    return rows

def save_json(path: str | Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- thoughts parsing ----------
_THOUGHT_KV_RE = re.compile(
    r"""
    (?P<key>thinking|evaluation_previous_goal|memory|next_goal)
    \s*=\s*
    (?:
        (?P<q>['"])(?P<valq>.*?)(?P=q)   # quoted
        |
        (?P<valbare>[^'"\s][^ ]*)        # bare (e.g., None)
    )
    """,
    re.VERBOSE,
)

def parse_thoughts(last_thought: Optional[str]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {
        "thinking": None,
        "memory": None,
        "next_goal": None,
        "evaluation_previous_goal": None,
    }
    if not isinstance(last_thought, str) or not last_thought:
        return out
    for m in _THOUGHT_KV_RE.finditer(last_thought):
        key = m.group("key")
        val = m.group("valq") if m.group("valq") is not None else m.group("valbare")
        if isinstance(val, str) and val.strip().lower() == "none":
            val = None
        out[key] = val
    # fallback: try to infer next_goal from narrative
    if not out.get("next_goal"):
        m = re.search(r'next step is to\s+(?P<q>["\'])(.+?)(?P=q)', last_thought, flags=re.IGNORECASE)
        if m:
            out["next_goal"] = m.group(2)
    return out

# ---------- interacted_element parsing (multi-round) ----------
# Example repr:
# DOMInteractedElement(node_id=76, backend_node_id=129, ..., node_name='BUTTON',
#   attributes={'type': 'submit', 'class': 'find-btn', 'disabled': ''},
#   bounds=DOMRect(x=312.5, y=514.5, ...),
#   x_path='html/body/...', element_hash=...)
_DOMIE_RE = re.compile(r"DOMInteractedElement\((.*)\)$", re.DOTALL)
_DOMRECT_RE = re.compile(r"DOMRect\((.*?)\)")

def _safe_literal_eval(s: str) -> Any:
    try:
        return ast.literal_eval(s)
    except Exception:
        return s

def _kvlist_to_dict(arg_str: str) -> Dict[str, Any]:
    """
    Turn "a=1, b='x', attributes={...}, bounds=DOMRect(...)" into dict safely.
    Strategy:
      1) Replace DOMRect(...) -> dict
      2) Wrap to a dict literal: '{a:..., b:...}' -> "{'a':..., 'b':...}" if needed
      3) Try literal_eval
    """
    s = arg_str.strip()
    # Expand DOMRect(...) into dict string
    def _rect_to_dict(m: re.Match) -> str:
        inner = m.group(1)
        # inner like "x=312.5, y=514.5, width=160.0, height=42.5"
        parts = {}
        for kv in re.split(r",\s*", inner):
            if not kv:
                continue
            k, _, v = kv.partition("=")
            k = k.strip()
            v = v.strip()
            parts[k] = _safe_literal_eval(v)
        return repr(parts)

    s = _DOMRECT_RE.sub(_rect_to_dict, s)
    # Convert k=v pairs into a Python dict literal string
    # We will quote bare keys; values may be Python literals already.
    items = []
    depth = 0
    buff = ""
    # split on commas at depth 0 to get k=v chunks
    for ch in s:
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(buff.strip())
            buff = ""
        else:
            buff += ch
    if buff.strip():
        items.append(buff.strip())

    out: Dict[str, Any] = {}
    for kv in items:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        k = k.strip().strip("'\"")
        v = v.strip()
        out[k] = _safe_literal_eval(v)
    return out

def parse_interacted_element(raw: Any) -> Any:
    """
    Try hard to convert DOMInteractedElement(...) into a dict with keys like:
      node_id, backend_node_id, node_name, attributes (dict), bounds (dict), x_path, element_hash, ...
    If it's already json-serializable, return as-is. Otherwise, return str(raw).
    """
    # If already json-serializable, keep
    try:
        json.dumps(raw)
        return raw
    except Exception:
        pass

    if isinstance(raw, str):
        s = raw.strip()
    else:
        s = str(raw)

    m = _DOMIE_RE.search(s)
    if not m:
        # maybe action string entire; try to find DOMInteractedElement(...) substring
        m2 = _DOMIE_RE.search(s)
        if not m2:
            return s  # fallback
        inner = m2.group(1)
    else:
        inner = m.group(1)

    try:
        info = _kvlist_to_dict(inner)
        # Ensure attributes/bounds are JSON-serializable; they should be after literal_eval/_rect_to_dict
        return info
    except Exception:
        return s

# ---------- action parsing (multi-round, with repeated passes) ----------
def _strip_nonserializables_once(s: str) -> str:
    # Replace DOMInteractedElement(...) / DOMRect(...) with placeholders to let literal_eval succeed.
    s2 = re.sub(r"DOMInteractedElement\([^)]*\)", "'__DOMInteractedElement__'", s, flags=re.DOTALL)
    s2 = re.sub(r"DOMRect\([^)]*\)", "'__DOMRect__'", s2)
    s2 = re.sub(r"<NodeType\.[^>]+>", "'NodeType'", s2)
    return s2

def parse_action_obj(raw: Any) -> Dict[str, Any]:
    """
    Returns:
    {
      "name": str | None,
      "args": dict | None,
      "interacted_element": Any | None,   # parsed dict if possible
      "type": "click"|"input_text"|"navigate"|"select"|"other"|None,
      "raw_type": "dict"|"str"|"unknown"
    }
    Repeatedly tries to convert str repr -> dict, then extract interacted_element deeply.
    """
    out = {
        "name": None,
        "args": None,
        "interacted_element": None,
        "type": None,
        "raw_type": "unknown",
    }

    def _infer_type(name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        n = name.lower()
        if n in {"click_element_by_index", "click", "press_key", "press_enter"}:
            return "click"
        if n in {"type_text", "input_text", "fill_field", "set_text"}:
            return "input_text"
        if n in {"go_to_url", "navigate", "open_new_tab"}:
            return "navigate"
        if n in {"select_option", "select_dropdown", "select"}:
            return "select"
        return "other"

    def _extract_from_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        # separate interacted_element, and pick first non-interacted key as action
        iel = d.get("interacted_element")
        parsed_ie = parse_interacted_element(iel) if iel is not None else None
        name, args = None, None
        for k, v in d.items():
            if k == "interacted_element":
                continue
            name = k
            args = v if isinstance(v, dict) else {"value": v}
            break
        return {
            "name": name,
            "args": args,
            "interacted_element": parsed_ie,
            "type": _infer_type(name),
            "raw_type": "dict"
        }

    # Case 1: already dict
    if isinstance(raw, dict):
        return _extract_from_dict(raw)

    # Case 2: string repr — attempt several passes
    if isinstance(raw, str):
        s = raw.strip()
        # Pass A: try JSON
        try:
            dj = json.loads(s)
            got = _extract_from_dict(dj if isinstance(dj, dict) else {"value": dj})
            got["raw_type"] = "str"
            return got
        except Exception:
            pass

        # Pass B: literal_eval directly
        try:
            d1 = ast.literal_eval(s)
            if isinstance(d1, dict):
                got = _extract_from_dict(d1)
                got["raw_type"] = "str"
                return got
        except Exception:
            pass

        # Pass C: strip non-serializables then literal_eval
        s2 = s
        for _ in range(3):  # multi-round stripping to be safe
            s2_new = _strip_nonserializables_once(s2)
            if s2_new == s2:
                break
            s2 = s2_new
        try:
            d2 = ast.literal_eval(s2)
            if isinstance(d2, dict):
                # if interacted_element was replaced by placeholder, try to parse from original string
                ie = d2.get("interacted_element")
                if ie == "__DOMInteractedElement__":
                    parsed_ie = parse_interacted_element(s)
                    d2["interacted_element"] = parsed_ie
                got = _extract_from_dict(d2)
                got["raw_type"] = "str"
                return got
        except Exception:
            pass

        # Pass D: regex extract inner {...} for first key as action, plus original DOMInteractedElement
        m = re.search(r"\{\s*(['\"]?)([A-Za-z0-9_]+)\1\s*:\s*(\{.*\})\s*,\s*['\"]?interacted_element['\"]?\s*:\s*(DOMInteractedElement\(.*\))\s*\}$",
                      s, flags=re.DOTALL)
        if m:
            name = m.group(2)
            arg_str = m.group(3)
            domie = m.group(4)
            args = _safe_literal_eval(arg_str)
            parsed_ie = parse_interacted_element(domie)
            return {
                "name": name,
                "args": args if isinstance(args, dict) else {"value": args},
                "interacted_element": parsed_ie,
                "type": _infer_type(name),
                "raw_type": "str"
            }

        # Last resort: stuff everything into interacted_element for visibility
        return {
            "name": None,
            "args": None,
            "interacted_element": parse_interacted_element(s),
            "type": None,
            "raw_type": "str"
        }

    # Unknown type
    return out

# ---------- main transform ----------
def to_combined(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined: List[Dict[str, Any]] = []
    for ev in events:
        phase = ev.get("phase")
        if phase not in ("on_step_start", "on_step_end"):
            continue
        kind = "planned" if phase == "on_step_start" else "executed"

        # thoughts -> three explicit fields (no last_thought)
        thoughts = parse_thoughts(ev.get("last_thought"))

        # parse action from the right source
        if kind == "planned":
            action_parsed = parse_action_obj(ev.get("planned_action"))
        else:
            action_parsed = parse_action_obj(ev.get("action"))

        rec: Dict[str, Any] = {
            "kind": kind,
            "ts": ev.get("ts"),
            "url": ev.get("url"),
            # replace last_thought with parsed fields:
            "thinking": thoughts.get("thinking"),
            "memory": thoughts.get("memory"),
            "next_goal": thoughts.get("next_goal"),
            "evaluation_previous_goal": thoughts.get("evaluation_previous_goal"),
            # replace planned_action/action with parsed action:
            "action": action_parsed,
        }

        # keep other useful fields verbatim if present
        if kind == "planned":
            rec["planned_target"] = ev.get("planned_target")
        else:
            rec["target"] = ev.get("target")
            rec["extracted"] = ev.get("extracted")
            rec["result"] = ev.get("result")

        combined.append(rec)

    combined.sort(key=lambda r: (r.get("ts") or 0))
    return combined

def parse_jsonl_to_combined(jsonl_path: str | Path, out_path: Optional[str | Path] = None) -> Path:
    jsonl_path = Path(jsonl_path)
    events = read_jsonl(jsonl_path)
    combined = to_combined(events)
    if out_path is None:
        out_path = jsonl_path.with_suffix(".combined.parsed.json")
    out_path = Path(out_path)
    save_json(out_path, combined)
    return out_path

# ---------- CLI ----------
if __name__ == "__main__":
    in_path = Path("logs/agent_run_1758664479.jsonl")
    out_path = parse_jsonl_to_combined(in_path)
