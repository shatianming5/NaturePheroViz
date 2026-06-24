from __future__ import annotations

import base64
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests

from PIL import Image

from . import fidelity_verifier as fv
from .fidelity_verifier import verify_fidelity

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parse_rules(text: str) -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Dict[str, Any]] = {}
    current: Dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        if not line.startswith('  '):
            key = line.rstrip(':')
            data[key] = {}
            current = data[key]
        elif current is not None:
            sub_key, _, raw_value = line.strip().partition(':')
            value_str = raw_value.strip()
            if value_str.lower() in {'true', 'false'}:
                value = value_str.lower() == 'true'
            else:
                try:
                    value = float(value_str)
                except ValueError:
                    value = value_str
            current[sub_key] = value
    return data


def _parse_diagnostics(text: str) -> Dict[str, Dict[str, Any]]:
    data: Dict[str, Dict[str, Any]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, _, payload = line.partition(':')
        key = key.strip()
        body = payload.strip().strip('{}')
        entry: Dict[str, Any] = {}
        for part in body.split(','):
            sub_key, _, value = part.partition(':')
            entry[sub_key.strip()] = value.strip().strip("'\"")
        data[key] = entry
    return data


MAP = _parse_diagnostics((PROJECT_ROOT / 'configs' / 'diagnostics_map.yml').read_text(encoding='utf-8'))
RULES = _parse_rules((PROJECT_ROOT / 'configs' / 'judge_rules.yml').read_text(encoding='utf-8'))


def _truncate(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return value[:half] + '\n...\n' + value[-half:]


def _weighted_score(scores: Dict[str, float]) -> float:
    weights = (RULES.get('weights') or {})
    weighted = 0.0
    total = 0.0
    for key, value in scores.items():
        weight = weights.get(key)
        if weight is None:
            continue
        try:
            w = float(weight)
            v = float(value)
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue
        weighted += w * max(0.0, min(1.0, v))
        total += w
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, weighted / total))


def _call_vlm_judge(spec: Dict[str, Any], df_cols: List[str], png_path: str, exec_log: str) -> Dict[str, Any] | None:
    base_url = os.getenv('LLM_API_BASE')
    api_key = os.getenv('VLM_API_KEY') or os.getenv('LLM_API_KEY')
    model = os.getenv('VLM_MODEL') or os.getenv('LLM_MODEL')
    if not (base_url and api_key and model):
        return None
    png_file = Path(png_path)
    if not png_file.exists():
        return None
    try:
        image_b64 = base64.b64encode(png_file.read_bytes()).decode('ascii')
    except Exception as exc:
        debug = os.getenv('VLM_DEBUG')
        if debug:
            print(f'[judge] VLM call failed: {exc}', file=sys.stderr)
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                try:
                    print(f'[judge] status={exc.response.status_code} body={_truncate(exc.response.text, 1200)}', file=sys.stderr)
                except Exception:
                    pass
        return None

    spec_json = json.dumps(spec, ensure_ascii=False)
    data_columns = ', '.join(df_cols) if df_cols else 'n/a'
    exec_excerpt = _truncate(exec_log or '', 600)

    user_prompt = textwrap.dedent(
        f'''
        请作为数据可视化审阅者，评估附图的质量。
        需要给出 JSON 格式结果，包含：
        - scores.visual_form (0-1 浮点数)
        - scores.data_fidelity (0-1 浮点数)
        - diagnostics (列表，每项含 slot、key、hint、sev)
        - 可选 notes （文字说明）

        图表规格（截断）：
        { _truncate(spec_json, 3000) }

        数据列：{data_columns}
        执行日志片段：
        {exec_excerpt}
        '''
    ).strip()

    payload = {
        'model': model,
        'temperature': 0,
        'messages': [
            {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': 'You review charts and must respond with strict JSON.'
                    }
                ]
            },
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': user_prompt},
                    {'type': 'input_image', 'image_base64': image_b64}
                ]
            }
        ],
        'response_format': {'type': 'json_object'},
        'max_output_tokens': int(os.getenv('LLM_MAX_TOKENS', '700') or 700)
    }

    url = base_url.rstrip('/') + '/chat/completions'
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    timeout = float(os.getenv('LLM_TIMEOUT', '180') or 180)

    debug_enabled = bool(os.getenv('VLM_DEBUG'))

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=(10, timeout))
        resp.raise_for_status()
    except Exception as exc:
        if debug_enabled:
            print(f'[judge] VLM call failed: {exc}', file=sys.stderr)
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                try:
                    print(f'[judge] status={exc.response.status_code} body={_truncate(exc.response.text, 1200)}', file=sys.stderr)
                except Exception:
                    pass
        return None

    try:
        data = resp.json()
    except Exception as exc:
        if debug_enabled:
            print(f'[judge] VLM response JSON parse error: {exc}', file=sys.stderr)
            try:
                print(f'[judge] raw body={_truncate(resp.text, 1200)}', file=sys.stderr)
            except Exception:
                pass
        return None

    choices = data.get('choices') or []
    if not choices:
        if debug_enabled:
            try:
                preview = json.dumps(data, ensure_ascii=False)
            except Exception:
                preview = str(data)
            print(f'[judge] VLM response missing choices: {_truncate(preview, 800)}', file=sys.stderr)
        return None

    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get('type') == 'text':
                    parts.append(str(part.get('text') or ''))
            else:
                parts.append(str(part))
        content = ''.join(parts)
    if not isinstance(content, str):
        content = str(content or '')
    content_str = content.strip()
    if not content_str:
        if debug_enabled:
            try:
                message_preview = json.dumps(message, ensure_ascii=False)
            except Exception:
                message_preview = str(message)
            print('[judge] VLM content empty', file=sys.stderr)
            print(f'[judge] raw message={_truncate(message_preview, 800)}', file=sys.stderr)
        return None
    if content_str.startswith('```'):
        content_str = re.sub(r'^```(?:json)?', '', content_str, count=1).strip()
        if content_str.endswith('```'):
            content_str = content_str[:-3].strip()
    try:
        parsed = json.loads(content_str)
    except Exception as exc:
        if debug_enabled:
            print(f'[judge] VLM content parse error: {exc}', file=sys.stderr)
            print(f'[judge] content={_truncate(content_str, 1200)}', file=sys.stderr)
        return None

    scores = parsed.get('scores') or {}
    diagnostics_raw = parsed.get('diagnostics') or []
    vf = float(scores.get('visual_form', 0.0))
    df_score = float(scores.get('data_fidelity', 0.0))

    diagnostics: List[Dict[str, Any]] = []
    for item in diagnostics_raw:
        if not isinstance(item, dict):
            continue
        diagnostics.append(
            {
                'slot': str(item.get('slot') or ''),
                'key': str(item.get('key') or item.get('issue') or ''),
                'hint': str(item.get('hint') or item.get('issue') or ''),
                'sev': int(item.get('sev', 1))
            }
        )

    return {
        'visual_form': max(0.0, min(1.0, vf)),
        'data_fidelity': max(0.0, min(1.0, df_score)),
        'diagnostics': diagnostics,
        'notes': parsed.get('notes', '')
    }


def _image_nonempty_score(png_path: str) -> float:
    try:
        im = Image.open(png_path).convert('RGB')
        pixels = list(im.getdata())
        step = max(1, len(pixels) // 5000)
        score = 0
        for idx in range(0, len(pixels) - 100, step):
            r1, g1, b1 = pixels[idx]
            r2, g2, b2 = pixels[idx + min(50, len(pixels) - idx - 1)]
            score += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
        if score > 50000:
            return 1.0
        if score > 10000:
            return 0.4
        return 0.1
    except Exception:
        return 0.0


def _is_ratio_like(name: Any) -> bool:
    if not isinstance(name, str):
        return False
    lower = name.lower()
    tokens = ('rate', 'ratio', 'share', 'percent', 'pct', '%')
    return any(token in lower for token in tokens)


def _series_style_signature(overlay: Dict[str, Any]) -> str:
    style = overlay.get('style') or {}
    color = style.get('color')
    linestyle = style.get('linestyle') or style.get('line_style')
    alpha = style.get('alpha')
    width = style.get('width')
    marker = style.get('marker')
    return '|'.join(str(v) for v in (color, linestyle, alpha, width, marker))


def _extract_svg_text_blocks(svg: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for m in re.finditer(r'<g id="text_\d+"[^>]*>(.*?)</g>\s*</g>', svg, flags=re.S):
        block = m.group(1)
        cm = re.search(r'<!--\s*(.*?)\s*-->', block, flags=re.S)
        tr = re.search(r'transform="([^"]+)"', block)
        if not cm or not tr:
            continue
        text = cm.group(1).strip()
        tr_s = tr.group(1)
        mt = re.search(r'translate\(\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\s*,?\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\)', tr_s)
        if not mt:
            continue
        try:
            tx = float(mt.group(1))
            ty = float(mt.group(2))
        except ValueError:
            continue
        items.append({'text': text, 'x': tx, 'y': ty})
    return items


def _extract_rendered_line_styles(svg: str, bounds: tuple[float, float, float, float]) -> List[str]:
    x0, x1, y0, y1 = bounds
    styles: List[str] = []
    for m in re.finditer(r'<g id="line2d_\d+"[^>]*>\s*<path\s+[^>]*?d="([^"]+)"[^>]*style="([^"]+)"[^>]*>', svg):
        d = m.group(1)
        style = re.sub(r'\s+', '', m.group(2).lower())
        pts = fv._parse_points(d)
        if len(pts) < 2:
            continue
        if 'clip-path=' not in m.group(0):
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if max(xs) < x0 - 2 or min(xs) > x1 + 2 or max(ys) < y0 - 2 or min(ys) > y1 + 2:
            continue
        if 'stroke:' not in style:
            continue
        # Exclude grid and guide lines; keep sloped or curved data marks only.
        if len(set(round(x, 3) for x in xs)) <= 1 or len(set(round(y, 3) for y in ys)) <= 1:
            continue
        styles.append(style)
    return styles


def _extract_rendered_bar_styles(svg: str, bounds: tuple[float, float, float, float]) -> List[str]:
    x0, x1, y0, y1 = bounds
    styles: List[str] = []
    for m in re.finditer(r'<g id="patch_\d+"[^>]*>\s*<path\s+[^>]*?d="([^"]+)"[^>]*style="([^"]+)"[^>]*>', svg):
        d = m.group(1)
        style = re.sub(r'\s+', '', m.group(2).lower())
        if 'fill:none' in style:
            continue
        if 'fill:#fff' in style or 'fill:#ffffff' in style or 'fill:rgb(255,255,255)' in style:
            continue
        pts = fv._parse_points(d)
        if len(pts) < 4:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if min(xs) < x0 - 2 or max(xs) > x1 + 2 or min(ys) < y0 - 2 or max(ys) > y1 + 2:
            continue
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if width <= 0 or height <= 0 or width * height < 8:
            continue
        styles.append(style)
    return styles


def _has_rendered_legend(svg: str) -> bool:
    return bool(re.search(r'<g id="legend_\d+"', svg))


def _is_percent_text(text: str) -> bool:
    lower = text.lower()
    if '%' in lower or 'percent' in lower or 'pct' in lower:
        return True
    value = fv._to_float(text)
    return value is not None and 0.0 <= value <= 1.0 and any(ch.isdigit() for ch in text)


def _axis_unit_modes(svg: str, bounds: tuple[float, float, float, float]) -> tuple[bool, bool]:
    x0, x1, y0, y1 = bounds
    texts = _extract_svg_text_blocks(svg)
    left_texts = [item['text'] for item in texts if item['x'] <= x0 + 14 and y0 - 8 <= item['y'] <= y1 + 8]
    right_texts = [item['text'] for item in texts if item['x'] >= x1 - 4 and y0 - 8 <= item['y'] <= y1 + 8]
    left_percent = any(_is_percent_text(text) for text in left_texts)
    right_percent = any(_is_percent_text(text) for text in right_texts)
    return left_percent, right_percent


def _rendered_x_order_mismatch(svg: str, spec: Dict[str, Any], df) -> bool:
    bounds = fv._extract_plot_bounds(svg)
    if not bounds:
        return False
    x_ticks, _ = fv._extract_ticks(svg, bounds)
    rendered = [str(label) for _, label in x_ticks]
    if len(rendered) < 2:
        return False
    overlays = [ov for ov in (spec.get('overlays') or []) if isinstance(ov, dict)]
    x_names = [ov.get('x') for ov in overlays if isinstance(ov.get('x'), str)]
    if not x_names or len(set(x_names)) != 1:
        return False
    x_name = x_names[0]
    if df is None or x_name not in getattr(df, 'columns', []):
        return False
    expected = [str(v) for v in pd.Index(df[x_name]).dropna().astype(str).drop_duplicates().tolist()]
    if len(expected) < 2:
        return False
    rendered_filtered = [v for v in rendered if v in expected]
    expected_filtered = [v for v in expected if v in rendered]
    return bool(rendered_filtered and expected_filtered and rendered_filtered != expected_filtered)


def _expected_distinct_series_count(spec: Dict[str, Any], df) -> int:
    overlays = [ov for ov in (spec.get('overlays') or []) if isinstance(ov, dict)]
    groups = [ov.get('group') for ov in overlays if isinstance(ov.get('group'), str)]
    if df is not None:
        for group in groups:
            if group in getattr(df, 'columns', []):
                try:
                    return max(1, int(pd.Series(df[group]).dropna().astype(str).nunique()))
                except Exception:
                    pass
    return max(1, len({str(ov.get('y') or ov.get('id') or '') for ov in overlays}))


def _series_cohesion(spec: Dict[str, Any], df_cols: List[str], png_path: str, df=None) -> tuple[float, List[Dict[str, Any]]]:
    overlays = [ov for ov in (spec.get('overlays') or []) if isinstance(ov, dict)]
    distinct_series_count = _expected_distinct_series_count(spec, df)
    if len(overlays) <= 1 and distinct_series_count <= 1:
        return 1.0, []

    checks = RULES.get('cohesion_checks', {}) or {}
    diagnostics: List[Dict[str, Any]] = []
    penalties = 0.0
    svg = ''
    bounds = None
    svg_path = str(Path(png_path).with_suffix('.svg')) if png_path else ''
    if svg_path and Path(svg_path).exists():
        try:
            svg = fv._read_text(svg_path)
            bounds = fv._extract_plot_bounds(svg)
        except Exception:
            svg = ''
            bounds = None

    x_names = [ov.get('x') for ov in overlays if isinstance(ov.get('x'), str)]
    if checks.get('consistent_x_across_overlays', True) and x_names and len(set(x_names)) > 1:
        item = MAP['x.inconsistent'].copy()
        item.update({'key': 'x.inconsistent', 'sev': 2})
        diagnostics.append(item)
        penalties += 0.35

    if checks.get('require_legend_if_multi_series', True):
        distinct_series = {str(ov.get('y') or ov.get('id') or '') for ov in overlays}
        has_legend = _has_rendered_legend(svg) if svg else False
        if len(distinct_series) > 1 and not has_legend:
            item = MAP['legend.missing.multi'].copy()
            item.update({'key': 'legend.missing.multi', 'sev': 2})
            diagnostics.append(item)
            penalties += 0.2

    if checks.get('distinct_series_styles', True):
        if svg and bounds:
            line_signatures = _extract_rendered_line_styles(svg, bounds)
            bar_signatures = _extract_rendered_bar_styles(svg, bounds)
            signatures = line_signatures or bar_signatures
        else:
            signatures = [_series_style_signature(ov) for ov in overlays]
        expected_series = distinct_series_count
        if signatures and len(set(signatures)) < min(len(signatures), expected_series) and len(signatures) >= 2:
            item = MAP['series.style.conflict'].copy()
            item.update({'key': 'series.style.conflict', 'sev': 1})
            diagnostics.append(item)
            penalties += 0.25

    if checks.get('separate_ratio_axes', True):
        rendered_mismatch = False
        ratio_like_present = any(_is_ratio_like(ov.get('y')) for ov in overlays)
        if svg and bounds:
            left_percent, right_percent = _axis_unit_modes(svg, bounds)
            right_axis_present = any(str(ov.get('yaxis') or 'left') == 'right' for ov in overlays)
            rendered_mismatch = ratio_like_present and right_axis_present and left_percent == right_percent
        ratio_axes = {str((ov.get('yaxis') or 'left')) for ov in overlays if _is_ratio_like(ov.get('y'))}
        absolute_axes = {str((ov.get('yaxis') or 'left')) for ov in overlays if not _is_ratio_like(ov.get('y'))}
        if rendered_mismatch or (ratio_axes and absolute_axes and ratio_axes & absolute_axes):
            item = MAP['ratio.axis.mismatch'].copy()
            item.update({'key': 'ratio.axis.mismatch', 'sev': 2})
            diagnostics.append(item)
            penalties += 0.35

    if svg and checks.get('consistent_x_across_overlays', True) and _rendered_x_order_mismatch(svg, spec, df):
        item = MAP['x.inconsistent'].copy()
        item.update({'key': 'x.inconsistent', 'sev': 2})
        if not any(diag.get('key') == 'x.inconsistent' for diag in diagnostics):
            diagnostics.append(item)
            penalties += 0.2

    missing_cols = 0
    for ov in overlays:
        x_name = ov.get('x')
        y_name = ov.get('y')
        if isinstance(x_name, str) and x_name not in df_cols:
            missing_cols += 1
        if isinstance(y_name, str) and y_name not in df_cols:
            missing_cols += 1
    if missing_cols:
        penalties += min(0.2, 0.05 * missing_cols)

    return max(0.0, min(1.0, 1.0 - penalties)), diagnostics


def _diagnose(spec: Dict[str, Any], df_cols: List[str], overlays_n: int, png_path: str) -> List[Dict[str, Any]]:
    diagnostics: List[Dict[str, Any]] = []
    layout = (spec.get('layout') or {})
    titles = (layout.get('titles') or {})
    if RULES.get('visual_checks', {}).get('need_title') and not any(titles.values()):
        item = MAP['title.missing'].copy()
        item.update({'key': 'title.missing', 'sev': 2})
        diagnostics.append(item)

    if RULES.get('visual_checks', {}).get('need_legend_if_multi') and overlays_n > 1:
        if (layout.get('legend') or {}).get('loc', 'best') == 'none':
            item = MAP['legend.overlap'].copy()
            item.update({'key': 'legend.overlap', 'sev': 1})
            diagnostics.append(item)

    if RULES.get('visual_checks', {}).get('broken_axis_mark'):
        breaks = ((spec.get('scales') or {}).get('y_left') or {}).get('breaks')
        if breaks and not isinstance(breaks, list):
            item = MAP['broken.axis.symbol.missing'].copy()
            item.update({'key': 'broken.axis.symbol.missing', 'sev': 1})
            diagnostics.append(item)

    if ((spec.get('scales') or {}).get('y_right') or {}).get('kind') == 'log':
        item = MAP['bad.scale.y_right.log'].copy()
        item.update({'key': 'bad.scale.y_right.log', 'sev': 1})
        diagnostics.append(item)

    if overlays_n >= 2:
        item = MAP['low.contrast.series.2'].copy()
        item.update({'key': 'low.contrast.series.2', 'sev': 1})
        diagnostics.append(item)

    if _image_nonempty_score(png_path) < 0.2:
        item = MAP['empty.plot'].copy()
        item.update({'key': 'empty.plot', 'sev': 2})
        diagnostics.append(item)

    return diagnostics


def judge(png_path: str, exec_log: str, df, spec: Dict[str, Any]) -> Dict[str, Any]:
    overlays = spec.get('overlays') or []
    overlays_n = len(overlays)
    df_cols = list(getattr(df, 'columns', []))
    svg_path = str(Path(png_path).with_suffix('.svg')) if png_path else ''
    fidelity = verify_fidelity(
        svg_path=svg_path,
        ground_truth_table=df if df is not None else None,
        spec=spec or {},
        png_path=png_path,
    )
    cohesion_score, cohesion_diagnostics = _series_cohesion(spec or {}, df_cols, png_path, df)

    vlm_result = _call_vlm_judge(spec, df_cols, png_path, exec_log)
    if vlm_result:
        diagnostics = vlm_result.get('diagnostics') or []
        if not diagnostics:
            vlm_result['diagnostics'] = _diagnose(spec, df_cols, overlays_n, png_path)
        else:
            vlm_result['diagnostics'] = diagnostics
        vlm_result['diagnostics'].extend(cohesion_diagnostics)
        vlm_result['data_fidelity'] = fidelity.get('data_fidelity', vlm_result.get('data_fidelity', 0.0))
        vlm_result['series_cohesion'] = cohesion_score
        vlm_result['overall_score'] = _weighted_score(
            {
                'visual_form': vlm_result.get('visual_form', 0.0),
                'data_fidelity': vlm_result.get('data_fidelity', 0.0),
                'series_cohesion': vlm_result.get('series_cohesion', 0.0),
            }
        )
        vlm_result['fidelity_detail'] = {
            'rms_f1': fidelity.get('rms_f1', 0.0),
            'rnss': fidelity.get('rnss', 0.0),
            'mismatches': fidelity.get('mismatches', []),
        }
        vlm_result['pred_table'] = fidelity.get('pred_table')
        return vlm_result

    vf = _image_nonempty_score(png_path)
    layout = spec.get('layout') or {}
    grid_cfg = layout.get('grid') or {}
    if grid_cfg.get('y'):
        vf += 0.05
    if (layout.get('legend') or {}).get('loc', 'best') != 'none' and overlays_n > 1:
        vf += 0.05
    vf = max(0.0, min(1.0, vf))

    good_cols = 0
    for overlay in overlays:
        if overlay.get('x') in df_cols and overlay.get('y') in df_cols:
            good_cols += 1
    fid = 0.5 + 0.25 * (good_cols / max(1, overlays_n))
    if pd.notna(fidelity.get('data_fidelity')):
        fid = fidelity.get('data_fidelity')
    else:
        fid = max(0.0, min(1.0, fid))

    diagnostics = _diagnose(spec, df_cols, overlays_n, png_path)
    diagnostics.extend(cohesion_diagnostics)
    result = {
        'visual_form': vf,
        'data_fidelity': fid,
        'series_cohesion': cohesion_score,
        'diagnostics': diagnostics,
        'fidelity_detail': {
            'rms_f1': fidelity.get('rms_f1', 0.0),
            'rnss': fidelity.get('rnss', 0.0),
            'mismatches': fidelity.get('mismatches', []),
        },
        'pred_table': fidelity.get('pred_table'),
    }
    result['overall_score'] = _weighted_score(
        {
            'visual_form': result.get('visual_form', 0.0),
            'data_fidelity': result.get('data_fidelity', 0.0),
            'series_cohesion': result.get('series_cohesion', 0.0),
        }
    )
    return result
