from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import unquote, urlsplit

import requests
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, ValidationError


ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _safe_slug(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:180] if len(value) > 180 else value


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _guess_mime(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suf == ".png":
        return "image/png"
    if suf == ".webp":
        return "image/webp"
    if suf in {".tif", ".tiff"}:
        return "image/tiff"
    return "application/octet-stream"


def _extract_figure_index_from_filename(name: str) -> Optional[int]:
    # Common Nature image filenames contain patterns like `_Fig1_HTML.jpg`.
    m = re.search(r"[_-]Fig(?:ure)?(\d+)", name, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\bfig(?:ure)?\s*(\d+)\b", name, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def _basename_from_url(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        name = Path(unquote(urlsplit(value).path)).name
    except Exception:
        return None
    return name or None


def _figure_id_from_pair(pair: dict[str, Any], fallback: str) -> str:
    kind = pair.get("figureKind")
    number = pair.get("figureNumber") or pair.get("figureIndex")
    if kind == "extended" and isinstance(number, int):
        return f"ExtendedDataFig{number}"
    if isinstance(number, int):
        return f"Fig{number}"
    key = pair.get("figureKey")
    if isinstance(key, str) and key:
        return _safe_slug(key)
    return fallback


@dataclass(frozen=True)
class FigureContext:
    article_dir: Path
    article_key: str
    image_path: Path
    figure_index: Optional[int]
    figure_id: str
    figure_kind: Optional[str]
    figure_key: Optional[str]
    caption: Optional[str]
    figure_page_url: Optional[str]
    source_anchor_ids: list[str]
    matching_data_files: list[str]


class PanelBox(BaseModel):
    panel_id: str = Field(..., description="Panel label such as A/B/C or 1/2/3.")
    bbox: list[int] = Field(..., min_length=4, max_length=4, description="[x0,y0,x1,y1] in pixels.")
    is_data_viz: bool = Field(..., description="True if this panel is a data visualization (chart/plot/heatmap/table).")
    viz_type: str = Field(
        ...,
        description="One of: line/bar/scatter/heatmap/box/violin/table/network/map/flow/other.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: Optional[str] = None


class PanelDetection(BaseModel):
    image_width: int
    image_height: int
    panels: list[PanelBox]


def _find_article_dirs(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Input path not found: {root}")
    return sorted([p for p in root.iterdir() if p.is_dir()])


def _iter_figure_images(article_dir: Path) -> list[Path]:
    img_dir = article_dir / "images"
    if not img_dir.is_dir():
        return []
    images: list[Path] = []
    for p in img_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            images.append(p)
    return sorted(images)


def _iter_data_files(article_dir: Path) -> list[Path]:
    data_dir = article_dir / "data"
    if not data_dir.is_dir():
        return []
    files: list[Path] = []
    for p in data_dir.rglob("*"):
        if p.is_file():
            files.append(p)
    return sorted(files)


def _load_figure_metadata(article_json: Optional[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    if not article_json:
        return {}
    figures = article_json.get("figures")
    if not isinstance(figures, list):
        return {}
    mapping: dict[int, dict[str, Any]] = {}
    for f in figures:
        if not isinstance(f, dict):
            continue
        idx = f.get("figureIndex")
        if isinstance(idx, int):
            existing = mapping.get(idx)
            if not isinstance(existing, dict):
                mapping[idx] = f
                continue

            merged = dict(existing)

            def _prefer_longer_text(key: str) -> None:
                a = merged.get(key) or ""
                b = f.get(key) or ""
                if isinstance(a, str) and isinstance(b, str) and len(b) > len(a):
                    merged[key] = b

            for k in ("caption", "figurePageCaption"):
                _prefer_longer_text(k)

            for k in ("imgUrl", "figurePageUrl"):
                if not merged.get(k) and f.get(k):
                    merged[k] = f.get(k)

            a_ids = merged.get("sourceAnchorIds") or []
            b_ids = f.get("sourceAnchorIds") or []
            if isinstance(a_ids, list) and isinstance(b_ids, list):
                merged["sourceAnchorIds"] = sorted({str(x) for x in a_ids + b_ids if x})

            mapping[idx] = merged
    return mapping


def _match_data_files(anchor_ids: list[str], data_files: list[Path]) -> list[str]:
    if not anchor_ids or not data_files:
        return []
    matches: list[str] = []
    for anchor in anchor_ids:
        for f in data_files:
            if anchor in f.name:
                matches.append(str(f))
    return sorted(set(matches))


def _load_pair_metadata(article_json: Optional[dict[str, Any]], data_files: list[Path]) -> dict[str, dict[str, Any]]:
    if not article_json:
        return {}
    pairs = article_json.get("pairs")
    if not isinstance(pairs, list):
        return {}

    data_by_name = {p.name: p for p in data_files}
    mapping: dict[str, dict[str, Any]] = {}

    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        image_name = _basename_from_url(pair.get("imageUrl"))
        if not image_name:
            continue

        item = mapping.setdefault(
            image_name,
            {
                "matching_data_files": [],
                "data_labels": [],
            },
        )

        caption = pair.get("figurePageCaption") or pair.get("figureCaption")
        if isinstance(caption, str) and caption:
            current = item.get("caption") or ""
            if not isinstance(current, str) or len(caption) > len(current):
                item["caption"] = caption

        for src_key, dst_key in (
            ("figurePageUrl", "figurePageUrl"),
            ("figureKind", "figureKind"),
            ("figureKey", "figureKey"),
            ("figureNumber", "figureNumber"),
            ("figureIndex", "figureIndex"),
        ):
            if pair.get(src_key) is not None and item.get(dst_key) is None:
                item[dst_key] = pair.get(src_key)

        data_name = _basename_from_url(pair.get("dataUrl"))
        if data_name and data_name in data_by_name:
            item["matching_data_files"].append(str(data_by_name[data_name]))

        data_label = pair.get("dataLabel")
        if isinstance(data_label, str) and data_label:
            item["data_labels"].append(data_label)

    for item in mapping.values():
        item["matching_data_files"] = sorted(set(item.get("matching_data_files") or []))
        item["data_labels"] = sorted(set(item.get("data_labels") or []))

    return mapping


def _build_figure_contexts(
    root: Path,
    *,
    probe_image_size: bool = True,
    max_figures: Optional[int] = None,
    progress: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[FigureContext]]:
    article_rows: list[dict[str, Any]] = []
    figure_rows: list[dict[str, Any]] = []
    figure_contexts: list[FigureContext] = []

    article_dirs = _find_article_dirs(root)

    tqdm_mod = None
    if progress:
        try:
            import tqdm as tqdm_mod  # type: ignore
        except Exception:
            tqdm_mod = None

    bar = None
    if tqdm_mod is not None:
        bar = tqdm_mod.tqdm(article_dirs, total=len(article_dirs), desc="scan", unit="article")
        iterator = bar
    else:
        iterator = article_dirs

    try:
        for article_dir in iterator:
            article_key = article_dir.name
            article_json_path = article_dir / "article.json"
            article_json = _load_json(article_json_path)
            figure_meta = _load_figure_metadata(article_json)

            data_files = _iter_data_files(article_dir)
            pair_meta = _load_pair_metadata(article_json, data_files)
            images = _iter_figure_images(article_dir)

            article_rows.append(
                {
                    "article_key": article_key,
                    "article_dir": str(article_dir),
                    "article_json": str(article_json_path) if article_json_path.exists() else None,
                    "articleId": (article_json or {}).get("articleId"),
                    "doi": (article_json or {}).get("doi"),
                    "title": (article_json or {}).get("title"),
                    "articleUrl": (article_json or {}).get("articleUrl"),
                    "n_images": len(images),
                    "n_data_files": len(data_files),
                    "created_at": _now_iso(),
                }
            )

            for image_path in images:
                file_figure_index = _extract_figure_index_from_filename(image_path.name)
                figure_index = file_figure_index
                figure_id = f"Fig{figure_index}" if figure_index else _safe_slug(image_path.stem)

                fm = figure_meta.get(figure_index) if figure_index else None
                caption = None
                figure_page_url = None
                source_anchor_ids: list[str] = []
                figure_kind = None
                figure_key = None
                if isinstance(fm, dict):
                    caption = fm.get("figurePageCaption") or fm.get("caption")
                    figure_page_url = fm.get("figurePageUrl")
                    source_anchor_ids = list(fm.get("sourceAnchorIds") or [])

                matching_data_files = _match_data_files(source_anchor_ids, data_files)
                data_labels: list[str] = []

                pm = pair_meta.get(image_path.name)
                if isinstance(pm, dict):
                    caption = pm.get("caption") or caption
                    figure_page_url = pm.get("figurePageUrl") or figure_page_url
                    figure_kind = pm.get("figureKind")
                    figure_key = pm.get("figureKey")
                    if isinstance(pm.get("figureIndex"), int):
                        figure_index = pm.get("figureIndex")
                    figure_id = _figure_id_from_pair(pm, figure_id)
                    matching_data_files = list(pm.get("matching_data_files") or matching_data_files)
                    data_labels = list(pm.get("data_labels") or [])

                width = height = None
                if probe_image_size:
                    try:
                        with Image.open(image_path) as im:
                            width, height = im.size
                    except Exception:
                        pass

                figure_rows.append(
                    {
                        "article_key": article_key,
                        "article_dir": str(article_dir),
                        "figure_index": figure_index,
                        "image_file_index": file_figure_index,
                        "figure_id": figure_id,
                        "figure_kind": figure_kind,
                        "figure_key": figure_key,
                        "image_path": str(image_path),
                        "image_filename": image_path.name,
                        "image_width": width,
                        "image_height": height,
                        "image_bytes": image_path.stat().st_size,
                        "caption": caption,
                        "figure_page_url": figure_page_url,
                        "source_anchor_ids": source_anchor_ids,
                        "data_labels": data_labels,
                        "matching_data_files": matching_data_files,
                        "created_at": _now_iso(),
                    }
                )

                figure_contexts.append(
                    FigureContext(
                        article_dir=article_dir,
                        article_key=article_key,
                        image_path=image_path,
                        figure_index=figure_index,
                        figure_id=figure_id,
                        figure_kind=figure_kind,
                        figure_key=figure_key,
                        caption=caption,
                        figure_page_url=figure_page_url,
                        source_anchor_ids=source_anchor_ids,
                        matching_data_files=matching_data_files,
                    )
                )
                if max_figures is not None and len(figure_contexts) >= max_figures:
                    break

            if bar is not None:
                bar.set_postfix(figures=len(figure_contexts))

            if max_figures is not None and len(figure_contexts) >= max_figures:
                break
    finally:
        if bar is not None:
            bar.close()

    return article_rows, figure_rows, figure_contexts


def cmd_preflight(args: argparse.Namespace) -> int:
    root = Path(args.input).expanduser()
    output = Path(args.output).expanduser()
    output.mkdir(parents=True, exist_ok=True)

    article_rows, figure_rows, _ = _build_figure_contexts(root, probe_image_size=True, progress=bool(args.progress))
    _write_jsonl(output / "articles_manifest.jsonl", article_rows)
    _write_jsonl(output / "figures_manifest.jsonl", figure_rows)

    n_articles = len(article_rows)
    n_figures = len(figure_rows)
    n_caption_missing = sum(1 for r in figure_rows if not r.get("caption"))
    n_source_missing = sum(1 for r in figure_rows if not r.get("matching_data_files"))

    report = [
        "# Preflight report",
        "",
        f"- generated_at: `{_now_iso()}`",
        f"- input: `{root}`",
        f"- output: `{output}`",
        f"- articles: `{n_articles}`",
        f"- figures: `{n_figures}`",
        f"- caption_missing: `{n_caption_missing}`",
        f"- source_data_missing: `{n_source_missing}`",
        "",
        "## Outputs",
        "",
        f"- `{(output / 'articles_manifest.jsonl')}`",
        f"- `{(output / 'figures_manifest.jsonl')}`",
    ]
    (output / "preflight_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"[preflight] articles={n_articles} figures={n_figures} output={output}")
    return 0


def _load_env_if_present(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(env_path)


def _get_gemini_api_key() -> Optional[str]:
    for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLEAI_API_KEY", "GOOGLE_GENAI_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v
    return None


def _resolve_cli_proxy_config_path(repo_root: Path, override: Optional[str]) -> Optional[Path]:
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        return p if p.exists() else None

    env_path = os.environ.get("CLIPROXY_CONFIG") or os.environ.get("CLIPROXY_CONFIG_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        if p.exists():
            return p

    candidates = [
        repo_root / "CLIProxyAPI" / "config.yaml",
        repo_root / "CLIProxyAPI" / "config.wsl.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_cli_proxy_config(repo_root: Path, override: Optional[str]) -> Optional[dict[str, Any]]:
    config_path = _resolve_cli_proxy_config_path(repo_root, override)
    if not config_path:
        return None
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(config_path.read_text(encoding="utf-8", errors="replace"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _get_clip_proxy_api_key(repo_root: Path, config_override: Optional[str]) -> Optional[str]:
    v = os.environ.get("CLIPROXY_API_KEY")
    if v:
        return v
    cfg = _load_cli_proxy_config(repo_root, config_override)
    if not cfg:
        return None
    keys = cfg.get("api-keys") or cfg.get("api_keys")
    if isinstance(keys, list) and keys:
        first = keys[0]
        return first if isinstance(first, str) and first else None
    return None


def _get_clip_proxy_base_url(repo_root: Path, override: Optional[str], config_override: Optional[str]) -> str:
    if override:
        return override.rstrip("/")
    env_url = os.environ.get("CLIPROXY_BASE_URL")
    if env_url:
        return env_url.rstrip("/")
    cfg = _load_cli_proxy_config(repo_root, config_override) or {}
    port = cfg.get("port")
    if isinstance(port, int):
        return f"http://localhost:{port}"
    return "http://localhost:8317"


def _normalize_gemini_model_id(model_id: str) -> str:
    model_id = model_id.strip()
    if model_id.startswith("models/"):
        return model_id[len("models/") :]
    if model_id.startswith("/models/"):
        return model_id[len("/models/") :]
    return model_id


def _require_langchain() -> tuple[Any, Any]:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependencies. Install with: pip install -r requirements-llm.txt"
        ) from e
    return ChatGoogleGenerativeAI, HumanMessage


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model output does not contain a JSON object.")
    return json.loads(text[start : end + 1])


def _build_panel_detection_prompt(*, w: int, h: int, caption: Optional[str], prompt_version: str) -> str:
    return f"""You are an expert at splitting multi-panel scientific figures into sub-figures (panels).\n\nTask:\n- Given the input image, return a JSON object with detected panels and classifications.\n- A panel is a distinct sub-figure region (e.g. labeled a/b/c; or visually separated by whitespace).\n\nOutput JSON schema (STRICT, no markdown):\n{{\n  \"image_width\": {w},\n  \"image_height\": {h},\n  \"panels\": [\n    {{\n      \"panel_id\": \"A\",\n      \"bbox\": [x0, y0, x1, y1],\n      \"is_data_viz\": true,\n      \"viz_type\": \"line|bar|scatter|heatmap|box|violin|table|network|map|flow|other\",\n      \"confidence\": 0.0\n    }}\n  ]\n}}\n\nRules:\n- bbox must be in pixel coordinates within the image bounds (0<=x0<x1<=image_width, 0<=y0<y1<=image_height).\n- Panels should be non-overlapping (minor overlap is ok), and sorted in reading order.\n- If the figure is single-panel, return one panel covering the whole image.\n- \"is_data_viz\" should be true for charts/plots/heatmaps/tables; false for microscopy/photos/pure diagrams.\n\nContext:\n- prompt_version: {prompt_version}\n- caption (may be empty): {caption or ''}\n"""


def _detect_panels_with_gemini(
    *,
    model_id: str,
    image_path: Path,
    caption: Optional[str],
    prompt_version: str,
) -> PanelDetection:
    ChatGoogleGenerativeAI, HumanMessage = _require_langchain()

    api_key = _get_gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "Missing Gemini API key. Set GOOGLE_API_KEY (recommended) or GEMINI_API_KEY, "
            "or create a .env file in repo root with that key."
        )

    mime = _guess_mime(image_path)
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    with Image.open(image_path) as im:
        w, h = im.size

    prompt = _build_panel_detection_prompt(w=w, h=h, caption=caption, prompt_version=prompt_version)

    llm = ChatGoogleGenerativeAI(
        model=model_id,
        temperature=0,
        google_api_key=api_key,
    )

    message = HumanMessage(content=[{"type": "text", "text": prompt}, {"type": "image_url", "image_url": data_url}])
    resp = llm.invoke([message])
    raw_text = resp.content if isinstance(resp.content, str) else str(resp.content)

    payload = _extract_json_object(raw_text)
    try:
        parsed = PanelDetection.model_validate(payload)
    except ValidationError as e:
        raise RuntimeError(f"Invalid model JSON: {e}") from e

    return parsed


def _extract_text_from_gemini_generate_content(resp_json: dict[str, Any]) -> str:
    candidates = resp_json.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("No candidates in generateContent response.")
    content = candidates[0].get("content")
    if not isinstance(content, dict):
        raise ValueError("Missing content in generateContent response.")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("Missing parts in generateContent response.")
    out: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            out.append(part["text"])
    text = "".join(out).strip()
    if not text:
        raise ValueError("Empty text in generateContent response.")
    return text


def _detect_panels_with_clip_proxy(
    *,
    repo_root: Path,
    base_url: str,
    bearer_key: str,
    model_id: str,
    image_path: Path,
    caption: Optional[str],
    prompt_version: str,
    timeout_s: float,
) -> PanelDetection:
    with Image.open(image_path) as im:
        w, h = im.size

    prompt = _build_panel_detection_prompt(w=w, h=h, caption=caption, prompt_version=prompt_version)

    mime = _guess_mime(image_path)
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    normalized_model = _normalize_gemini_model_id(model_id)
    url = f"{base_url}/v1beta/models/{normalized_model}:generateContent"
    headers = {"Authorization": f"Bearer {bearer_key}"}
    payload = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": b64}}]}],
        "generationConfig": {"temperature": 0},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"CLIProxyAPI error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    raw_text = _extract_text_from_gemini_generate_content(data)
    parsed_json = _extract_json_object(raw_text)
    try:
        return PanelDetection.model_validate(parsed_json)
    except ValidationError as e:
        raise RuntimeError(f"Invalid model JSON: {e}") from e


def _clip_bbox(bbox: list[int], *, width: int, height: int) -> list[int]:
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(int(x0), width - 1))
    y0 = max(0, min(int(y0), height - 1))
    x1 = max(1, min(int(x1), width))
    y1 = max(1, min(int(y1), height))
    if x1 <= x0:
        x1 = min(width, x0 + 1)
    if y1 <= y0:
        y1 = min(height, y0 + 1)
    return [x0, y0, x1, y1]


def _pad_bbox(
    bbox: list[int],
    *,
    width: int,
    height: int,
    pad_px: int,
    pad_frac: float,
    max_pad_frac: float = 0.25,
) -> list[int]:
    x0, y0, x1, y1 = bbox
    box_w = max(1, int(x1) - int(x0))
    box_h = max(1, int(y1) - int(y0))

    pad_x = max(int(pad_px), int(round(box_w * float(pad_frac))))
    pad_y = max(int(pad_px), int(round(box_h * float(pad_frac))))

    pad_x = min(pad_x, int(round(box_w * float(max_pad_frac))))
    pad_y = min(pad_y, int(round(box_h * float(max_pad_frac))))

    return _clip_bbox([x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y], width=width, height=height)


def _save_overlay(image_path: Path, panels: list[PanelBox], out_path: Path) -> None:
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        draw = ImageDraw.Draw(im)
        for p in panels:
            x0, y0, x1, y1 = p.bbox
            color = (220, 20, 60) if p.is_data_viz else (70, 130, 180)
            draw.rectangle([x0, y0, x1, y1], outline=color, width=4)
            draw.text((x0 + 4, y0 + 4), str(p.panel_id), fill=color)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path)


def cmd_segment(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _load_env_if_present(repo_root)

    backend = args.backend
    if backend == "auto":
        backend = "google" if _get_gemini_api_key() else "cliproxy"

    if backend == "google" and not _get_gemini_api_key():
        print("Missing Gemini API key. Set GOOGLE_API_KEY (see .env.example).", file=sys.stderr)
        return 1

    cliproxy_key = None
    cliproxy_url = None
    if backend == "cliproxy":
        cliproxy_key = _get_clip_proxy_api_key(repo_root, args.cliproxy_config)
        cliproxy_url = _get_clip_proxy_base_url(repo_root, args.cliproxy_url, args.cliproxy_config)
        if not cliproxy_key:
            print(
                "Missing CLIProxyAPI key. Set CLIPROXY_API_KEY (see .env.example) "
                "or configure api-keys in CLIProxyAPI/config.yaml (or set CLIPROXY_CONFIG).",
                file=sys.stderr,
            )
            return 1

    input_root = Path(args.input).expanduser()
    output_root = Path(args.output).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    limit = int(args.limit) if args.limit is not None else None
    if limit is not None and limit <= 0:
        limit = None

    _, _, contexts = _build_figure_contexts(
        input_root,
        probe_image_size=False,
        max_figures=limit,
        progress=args.progress,
    )

    model_id = args.model
    prompt_version = args.prompt_version
    timeout_s = float(args.timeout_s)
    pad_px = int(args.pad_px)
    pad_frac = float(args.pad_frac)
    if pad_px < 0 or pad_frac < 0:
        print("--pad-px and --pad-frac must be non-negative.", file=sys.stderr)
        return 1

    errors_path = output_root / "errors.jsonl"
    processed = 0
    skipped = 0
    failed = 0

    tqdm_mod = None
    if args.progress:
        try:
            import tqdm as tqdm_mod  # type: ignore
        except Exception:
            tqdm_mod = None

    bar = None
    if tqdm_mod is not None:
        bar = tqdm_mod.tqdm(contexts, total=len(contexts), desc="segment", unit="figure")
        iterator = bar
    else:
        iterator = contexts

    def _log(msg: str, *, err: bool = False) -> None:
        if tqdm_mod is not None:
            tqdm_mod.tqdm.write(msg, file=sys.stderr if err else sys.stdout)
        else:
            print(msg, file=sys.stderr if err else sys.stdout)

    for ctx in iterator:
        out_dir = output_root / "subfigures" / _safe_slug(ctx.article_key) / _safe_slug(ctx.figure_id)
        panels_path = out_dir / "panels.json"
        if args.resume and panels_path.exists():
            skipped += 1
            if bar is not None:
                bar.set_postfix(processed=processed, skipped=skipped, failed=failed)
            continue

        try:
            with Image.open(ctx.image_path) as im:
                width, height = im.size
        except Exception as e:
            failed += 1
            _append_jsonl(
                errors_path,
                {
                    "created_at": _now_iso(),
                    "stage": "open_image",
                    "article_key": ctx.article_key,
                    "figure_id": ctx.figure_id,
                    "image_path": str(ctx.image_path),
                    "error": str(e),
                },
            )
            if bar is not None:
                bar.set_postfix(processed=processed, skipped=skipped, failed=failed)
            continue

        try:
            figure_hash = _sha256_file(ctx.image_path)
            if backend == "google":
                detection = _detect_panels_with_gemini(
                    model_id=model_id,
                    image_path=ctx.image_path,
                    caption=ctx.caption,
                    prompt_version=prompt_version,
                )
            else:
                detection = _detect_panels_with_clip_proxy(
                    repo_root=repo_root,
                    base_url=str(cliproxy_url),
                    bearer_key=str(cliproxy_key),
                    model_id=model_id,
                    image_path=ctx.image_path,
                    caption=ctx.caption,
                    prompt_version=prompt_version,
                    timeout_s=timeout_s,
                )
        except Exception as e:
            failed += 1
            errors_path.parent.mkdir(parents=True, exist_ok=True)
            with errors_path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(
                    json.dumps(
                        {
                            "created_at": _now_iso(),
                            "stage": "llm_detect_panels",
                            "article_key": ctx.article_key,
                            "figure_id": ctx.figure_id,
                            "image_path": str(ctx.image_path),
                            "error": str(e),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            _log(f"[segment] FAIL {ctx.article_key}/{ctx.figure_id}: {e}", err=True)
            if bar is not None:
                bar.set_postfix(processed=processed, skipped=skipped, failed=failed)
            continue

        panels: list[PanelBox] = []
        panel_records: list[dict[str, Any]] = []
        for p in detection.panels:
            bbox_model = list(p.bbox)
            bbox_clipped = _clip_bbox(bbox_model, width=width, height=height)
            bbox_padded = _pad_bbox(bbox_clipped, width=width, height=height, pad_px=pad_px, pad_frac=pad_frac)

            panel_obj = p.model_copy(update={"bbox": bbox_padded})
            panels.append(panel_obj)
            rec = panel_obj.model_dump()
            rec["bbox_model"] = bbox_model
            rec["bbox_clipped"] = bbox_clipped
            panel_records.append(rec)

        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": _now_iso(),
            "model_id": model_id,
            "prompt_version": prompt_version,
            "crop_pad_px": pad_px,
            "crop_pad_frac": pad_frac,
            "article_key": ctx.article_key,
            "figure_id": ctx.figure_id,
            "figure_index": ctx.figure_index,
            "figure_kind": ctx.figure_kind,
            "figure_key": ctx.figure_key,
            "image_path": str(ctx.image_path),
            "image_sha256": figure_hash,
            "image_width": width,
            "image_height": height,
            "caption": ctx.caption,
            "figure_page_url": ctx.figure_page_url,
            "source_anchor_ids": ctx.source_anchor_ids,
            "matching_data_files": ctx.matching_data_files,
            "panels": panel_records,
        }
        panels_path.write_text(_json_dumps(payload), encoding="utf-8")

        # Crop and keep only data-viz panels.
        with Image.open(ctx.image_path) as im:
            im = im.convert("RGB")
            for p in panels:
                if not p.is_data_viz:
                    continue
                x0, y0, x1, y1 = p.bbox
                crop = im.crop((x0, y0, x1, y1))
                out_img = out_dir / f"panel_{_safe_slug(p.panel_id)}.png"
                crop.save(out_img)

        if args.save_overlay:
            _save_overlay(ctx.image_path, panels, out_dir / "overlay.png")

        processed += 1
        _log(f"[segment] OK {ctx.article_key}/{ctx.figure_id} panels={len(panels)} out={out_dir}")
        if bar is not None:
            bar.set_postfix(processed=processed, skipped=skipped, failed=failed)

    print(f"[segment] done processed={processed} skipped={skipped} failed={failed} output={output_root}")
    return 0 if failed == 0 else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="process_articles", description="Preflight + subfigure segmentation for downloads/articles")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_pre = sub.add_parser("preflight", help="Scan downloads/articles and write manifests")
    p_pre.add_argument("--input", default="data/downloads/articles", help="Input root (default: data/downloads/articles)")
    p_pre.add_argument("--output", default="data/downloads/derived", help="Output root (default: data/downloads/derived)")
    p_pre.add_argument("--progress", action="store_true", help="Show a tqdm progress bar while scanning")
    p_pre.set_defaults(func=cmd_preflight)

    p_seg = sub.add_parser("segment", help="Run Gemini panel detection and crop data-viz panels")
    p_seg.add_argument("--input", default="data/downloads/articles", help="Input root (default: data/downloads/articles)")
    p_seg.add_argument("--output", default="data/downloads/derived", help="Output root (default: data/downloads/derived)")
    p_seg.add_argument(
        "--backend",
        choices=("auto", "google", "cliproxy"),
        default="auto",
        help="LLM backend: auto|google (direct Gemini API key)|cliproxy (CLIProxyAPI /v1beta)",
    )
    p_seg.add_argument(
        "--cliproxy-url",
        default=None,
        help="Override CLIProxyAPI base URL (default: env CLIPROXY_BASE_URL or localhost:<port from CLIProxyAPI/config.yaml>)",
    )
    p_seg.add_argument(
        "--cliproxy-config",
        default=None,
        help="Path to CLIProxyAPI config yaml (default: env CLIPROXY_CONFIG or CLIProxyAPI/config.yaml)",
    )
    p_seg.add_argument(
        "--model",
        default="models/gemini-3-flash-preview",
        help="Gemini model id (default: models/gemini-3-flash-preview)",
    )
    p_seg.add_argument("--prompt-version", default="v1", help="Prompt version tag stored in outputs (default: v1)")
    p_seg.add_argument("--limit", type=int, default=10, help="Limit number of figures to process (0 = no limit, default: 10)")
    p_seg.add_argument("--resume", action="store_true", help="Skip figures with existing panels.json")
    p_seg.add_argument("--save-overlay", action="store_true", help="Save overlay.png with panel boxes")
    p_seg.add_argument(
        "--pad-px",
        type=int,
        default=20,
        help="Expand each detected bbox by at least this many pixels before cropping (default: 20)",
    )
    p_seg.add_argument(
        "--pad-frac",
        type=float,
        default=0.02,
        help="Expand each detected bbox by this fraction of its size before cropping (default: 0.02)",
    )
    p_seg.add_argument("--progress", action="store_true", help="Show a tqdm progress bar")
    p_seg.add_argument("--timeout-s", type=float, default=120.0, help="HTTP timeout seconds for LLM calls (default: 120)")
    p_seg.set_defaults(func=cmd_segment)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
