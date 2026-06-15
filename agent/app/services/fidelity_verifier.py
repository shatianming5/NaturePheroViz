from pathlib import Path
import base64
import json
import os
import re
import sys
import textwrap
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import requests

TOLERANCE = float(os.getenv('FIDELITY_TOLERANCE', '0.015') or 0.015)


def _nan_result() -> Dict[str, Any]:
    return {'data_fidelity': float('nan'), 'rms_f1': float('nan'), 'rnss': float('nan'), 'pred_table': pd.DataFrame(), 'mismatches': []}


def _to_float(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, bool):
        return float(int(v))
    if not isinstance(v, str):
        return None
    s = v.strip().replace(',', '')
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding='utf-8', errors='ignore')


def _truncate(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    half = limit // 2
    return value[:half] + '\n...\n' + value[-half:]


def _chart_table_client_config() -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    base_url = (
        os.getenv('CHART2TABLE_API_BASE')
        or os.getenv('UNICHART_API_BASE')
        or os.getenv('ONECHART_API_BASE')
        or os.getenv('LLM_API_BASE')
    )
    api_key = (
        os.getenv('CHART2TABLE_API_KEY')
        or os.getenv('UNICHART_API_KEY')
        or os.getenv('ONECHART_API_KEY')
        or os.getenv('VLM_API_KEY')
        or os.getenv('LLM_API_KEY')
    )
    model = (
        os.getenv('CHART2TABLE_MODEL')
        or os.getenv('UNICHART_MODEL')
        or os.getenv('ONECHART_MODEL')
        or os.getenv('VLM_MODEL')
        or os.getenv('LLM_MODEL')
    )
    provider = os.getenv('CHART2TABLE_PROVIDER')
    if not provider:
        if os.getenv('UNICHART_MODEL'):
            provider = 'unichart'
        elif os.getenv('ONECHART_MODEL'):
            provider = 'onechart'
        elif os.getenv('CHART2TABLE_MODEL'):
            provider = 'chart2table'
        else:
            provider = 'vlm'
    return base_url, api_key, model, provider


def _parse_points(d: str) -> List[Tuple[float, float]]:
    nums = [float(v) for v in re.findall(r'[-+]?\d*\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+', d)]
    return list(zip(nums[::2], nums[1::2]))


def _extract_plot_bounds(svg: str) -> Optional[Tuple[float, float, float, float]]:
    best = None
    best_area = -1.0
    for m in re.finditer(r'<rect\b[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*width="([^"]+)"[^>]*height="([^"]+)"', svg):
        try:
            x = float(m.group(1))
            y = float(m.group(2))
            w = float(m.group(3))
            h = float(m.group(4))
        except ValueError:
            continue
        if w <= 40 or h <= 40:
            continue
        area = w * h
        if area > best_area:
            best_area = area
            best = (x, x + w, y, y + h)
    return best


def _extract_ticks(svg: str, bounds: Optional[Tuple[float, float, float, float]]) -> Tuple[List[Tuple[float, str]], List[Tuple[float, float]]]:
    if not bounds:
        return [], []
    x0, x1, y0, y1 = bounds
    out_x_ticks: List[Tuple[float, str]] = []
    out_y_ticks: List[Tuple[float, float]] = []

    for m in re.finditer(r'<g id="text_\d+"[^>]*>(.*?)</g>\s*</g>', svg, flags=re.S):
        block = m.group(1)
        cm = re.search(r'<!--\s*(.*?)\s*-->', block, flags=re.S)
        if not cm:
            continue
        txt = cm.group(1).strip()
        if not txt:
            continue
        tr = re.search(r'transform="([^"]+)"', block)
        if not tr:
            continue
        tr_s = tr.group(1)
        mt = re.search(r'translate\(\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\s*,?\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\)', tr_s)
        if not mt:
            continue
        try:
            tx = float(mt.group(1))
            ty = float(mt.group(2))
        except ValueError:
            continue

        if ty >= y1 - 8 and x0 - 8 <= tx <= x1 + 8:
            out_x_ticks.append((tx, txt))
            continue

        if tx <= x0 + 12 and y0 - 8 <= ty <= y1 + 8:
            value = _to_float(txt)
            if value is None:
                continue
            out_y_ticks.append((ty, value))

    if not out_x_ticks:
        # fallback: nearby bottom-of-axes labels
        for m in re.finditer(r'<g id="text_\d+"[^>]*>(.*?)</g>\s*</g>', svg, flags=re.S):
            block = m.group(1)
            cm = re.search(r'<!--\s*(.*?)\s*-->', block, flags=re.S)
            if not cm:
                continue
            txt = cm.group(1).strip()
            if not txt:
                continue
            tr = re.search(r'transform="([^"]+)"', block)
            if not tr:
                continue
            tr_s = tr.group(1)
            mt = re.search(r'translate\(\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\s*,?\s*([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\)', tr_s)
            if not mt:
                continue
            try:
                tx = float(mt.group(1))
                ty = float(mt.group(2))
            except ValueError:
                continue
            if x0 - 8 <= tx <= x1 + 8 and ty > y1 - 70:
                out_x_ticks.append((tx, txt))

    out_x_ticks = sorted(out_x_ticks, key=lambda t: t[0])
    out_y_ticks = sorted(out_y_ticks, key=lambda t: t[0])
    return out_x_ticks, out_y_ticks


def _fit_linear(xs: Sequence[float], ys: Sequence[float]) -> Optional[Tuple[float, float]]:
    if len(xs) < 2 or len(set(xs)) < 2:
        return None
    # Use first and last pair (enough for axis ticks; robust enough for monotonic axis)
    x1, x2 = xs[0], xs[-1]
    y1, y2 = ys[0], ys[-1]
    if abs(x2 - x1) < 1e-12:
        return None
    a = (y2 - y1) / (x2 - x1)
    b = y1 - a * x1
    return a, b


def _categorical_or_numeric_map(x_ticks: List[Tuple[float, str]]) -> Tuple[bool, Optional[Tuple[float, float]]]:
    vals = [_to_float(v) for _, v in x_ticks]
    pairs = [(px, v) for (px, _), v in zip(x_ticks, vals) if v is not None]
    if len(pairs) >= 2:
        xs = [px for px, _ in pairs]
        ys = [v for _, v in pairs]
        model = _fit_linear(xs, ys)
        if model is not None:
            return True, model
    return False, None


def _to_data_x(px: float, x_ticks: List[Tuple[float, str]]) -> Optional[Any]:
    if not x_ticks:
        return None
    is_num, model = _categorical_or_numeric_map(x_ticks)
    if is_num and model is not None:
        a, b = model
        return a * px + b
    best = x_ticks[0][1]
    best_dist = abs(px - x_ticks[0][0])
    for tx, label in x_ticks:
        d = abs(px - tx)
        if d < best_dist:
            best_dist = d
            best = label
    return best


def _to_data_y(py: float, y_ticks: List[Tuple[float, float]]) -> Optional[float]:
    if len(y_ticks) < 2:
        return None
    xs = [p[0] for p in y_ticks]
    ys = [p[1] for p in y_ticks]
    model = _fit_linear(xs, ys)
    if not model:
        return None
    a, b = model
    return a * py + b


def _extract_bar_rows(svg: str, x_ticks: List[Tuple[float, str]], y_ticks: List[Tuple[float, float]], bounds: Tuple[float, float, float, float]) -> pd.DataFrame:
    x0, x1, y0, y1 = bounds
    rows: List[Dict[str, Any]] = []
    for m in re.finditer(r'<g id="patch_\d+"[^>]*>\s*<path\s+[^>]*?d="([^"]+)"[^>]*style="([^"]+)"[^>]*>', svg):
        d = m.group(1)
        style = re.sub(r'\s+', '', m.group(2).lower())
        if 'fill:none' in style:
            continue
        if 'fill:#fff' in style or 'fill:#ffffff' in style or 'fill:rgb(255,255,255)' in style:
            continue
        pts = _parse_points(d)
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

        x_mid = (min(xs) + max(xs)) / 2
        y_pixel = min(ys)
        x_val = _to_data_x(x_mid, x_ticks)
        y_val = _to_data_y(y_pixel, y_ticks)
        if x_val is None or y_val is None:
            continue
        rows.append({'x': str(x_val), 'value': float(y_val), 'color': style})

    if not rows:
        return pd.DataFrame(columns=['x', 'value'])
    return pd.DataFrame(rows)


def _extract_line_rows(svg: str, x_ticks: List[Tuple[float, str]], y_ticks: List[Tuple[float, float]], bounds: Tuple[float, float, float, float]) -> pd.DataFrame:
    x0, x1, y0, y1 = bounds
    rows: List[Dict[str, Any]] = []
    line_index = 0
    for m in re.finditer(r'<g id="line2d_\d+"[^>]*>\s*<path\s+[^>]*?d="([^"]+)"[^>]*style="([^"]+)"[^>]*>', svg):
        d = m.group(1)
        style = re.sub(r'\s+', '', m.group(2).lower())
        if 'fill:none' not in style:
            # line2d paths in matplotlib include fill:none; skip odd objects if style malformed
            pass

        if 'stroke-width' not in style:
            continue
        pts = _parse_points(d)
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if max(xs) - min(xs) < 3 and max(ys) - min(ys) < 3:
            continue
        if max(xs) < x0 - 2 or min(xs) > x1 + 2 or max(ys) < y0 - 2 or min(ys) > y1 + 2:
            continue
        for px, py in pts:
            if px < x0 - 1 or px > x1 + 1 or py < y0 - 1 or py > y1 + 1:
                continue
            x_val = _to_data_x(px, x_ticks)
            y_val = _to_data_y(py, y_ticks)
            if x_val is None or y_val is None:
                continue
            rows.append({'x': str(x_val), 'value': float(y_val), 'color': style, 'series_order': line_index})
        line_index += 1
    if not rows:
        return pd.DataFrame(columns=['x', 'value'])
    return pd.DataFrame(rows)


def _overlay_series_names(spec: Dict[str, Any], mark_kind: Optional[str] = None) -> List[str]:
    overlays = spec.get('overlays') or []
    names: List[str] = []
    for overlay in overlays:
        if not isinstance(overlay, dict):
            continue
        if mark_kind and overlay.get('mark') != mark_kind:
            continue
        y_name = overlay.get('y')
        if isinstance(y_name, str) and y_name.strip():
            names.append(y_name)
    return names


def _tag_predicted_series(pred: pd.DataFrame, spec: Dict[str, Any]) -> pd.DataFrame:
    if pred.empty or 'series' not in pred.columns:
        return pred

    out = pred.copy()
    missing_series = out['series'].isna() | (out['series'].astype(str).str.strip() == '')
    if not missing_series.any():
        return out

    line_names = _overlay_series_names(spec, 'line')
    if line_names and 'series_order' in out.columns:
        for idx, series_name in enumerate(line_names):
            mask = missing_series & (out['series_order'] == idx)
            out.loc[mask, 'series'] = series_name
        missing_series = out['series'].isna() | (out['series'].astype(str).str.strip() == '')

    if missing_series.any() and 'color' in out.columns:
        unique_series = out.loc[missing_series, 'color'].dropna().astype(str).drop_duplicates().tolist()
        if len(unique_series) > 1:
            overlay_names = _overlay_series_names(spec)
            for idx, color_name in enumerate(unique_series):
                if idx >= len(overlay_names):
                    break
                mask = missing_series & (out['color'].astype(str) == color_name)
                out.loc[mask, 'series'] = overlay_names[idx]

    return out


def _collect_predictions(svg: str, spec: Dict[str, Any]) -> pd.DataFrame:
    bounds = _extract_plot_bounds(svg)
    if not bounds:
        return pd.DataFrame(columns=['x', 'value'])
    x_ticks, y_ticks = _extract_ticks(svg, bounds)
    if not x_ticks and not y_ticks:
        return pd.DataFrame(columns=['x', 'value'])

    bar_rows = _extract_bar_rows(svg, x_ticks, y_ticks, bounds)
    line_rows = _extract_line_rows(svg, x_ticks, y_ticks, bounds)
    dfs = [df for df in [bar_rows, line_rows] if df is not None and not df.empty]
    if not dfs:
        return pd.DataFrame(columns=['x', 'value'])

    pred = pd.concat(dfs, ignore_index=True)
    pred = pred.dropna(subset=['x', 'value'])
    pred = pred.copy()
    if pred.empty:
        return pred
    if 'series' not in pred.columns:
        pred['series'] = None
    pred = _tag_predicted_series(pred, spec)
    pred['x'] = pred['x'].astype(str)
    pred['value'] = pd.to_numeric(pred['value'], errors='coerce')
    pred = pred.dropna(subset=['x', 'value'])
    return pred[['series', 'x', 'value']]


def _infer_columns(gt: pd.DataFrame, spec: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    overlays = spec.get('overlays') or []
    overlay = overlays[0] if overlays and isinstance(overlays[0], dict) else {}

    x_col = overlay.get('x') if isinstance(overlay, dict) else None
    y_col = overlay.get('y') if isinstance(overlay, dict) else None
    g_col = overlay.get('group') or overlay.get('series') if isinstance(overlay, dict) else None

    if not isinstance(x_col, str) or x_col not in gt.columns:
        x_candidates = [c for c in gt.columns if not str(c).startswith('_')]
        x_col = x_candidates[0] if x_candidates else gt.columns[0]
    if not isinstance(y_col, str) or y_col not in gt.columns:
        num_cols = [c for c in gt.columns if pd.api.types.is_numeric_dtype(gt[c])]
        y_col = num_cols[0] if num_cols else gt.columns[-1]
    if not (isinstance(g_col, str) and g_col in gt.columns):
        g_col = None
    return x_col, y_col, g_col


def _normalize_ground_truth(gt: pd.DataFrame, spec: Dict[str, Any]) -> Tuple[pd.DataFrame, str, str, Optional[str]]:
    x_col, y_col, g_col = _infer_columns(gt, spec)
    overlays = [overlay for overlay in (spec.get('overlays') or []) if isinstance(overlay, dict)]
    overlay_y_cols = [str(overlay.get('y')) for overlay in overlays if isinstance(overlay.get('y'), str) and overlay.get('y') in gt.columns]

    if g_col or len(overlay_y_cols) <= 1:
        return gt.copy(), x_col, y_col, g_col

    series_rows: List[pd.DataFrame] = []
    for y_name in overlay_y_cols:
        if x_col not in gt.columns or y_name not in gt.columns:
            continue
        series_rows.append(
            pd.DataFrame(
                {
                    'series': y_name,
                    'x': gt[x_col].astype(str),
                    'value': pd.to_numeric(gt[y_name], errors='coerce'),
                }
            )
        )

    if not series_rows:
        return gt.copy(), x_col, y_col, g_col

    long_gt = pd.concat(series_rows, ignore_index=True).dropna(subset=['x', 'value'])
    return long_gt, 'x', 'value', 'series'


def _assign_series(pred_df: pd.DataFrame, gt_df: pd.DataFrame, x_col: str, g_col: Optional[str]) -> pd.DataFrame:
    if not g_col:
        return pred_df

    pred = pred_df.copy()
    if g_col not in pred.columns:
        pred[g_col] = None
    if g_col not in gt_df.columns:
        pred[g_col] = pred[g_col].fillna('').astype(str)
        return pred
    pred[g_col] = pred[g_col].astype(object)

    gt = gt_df.copy()
    gt[x_col] = gt[x_col].astype(str)
    pred[x_col] = pred[x_col].astype(str)

    missing_mask = pred[g_col].isna() | (pred[g_col].astype(str).str.strip() == '')

    # one-to-one by x
    for x_val, sub in pred[missing_mask].groupby(x_col):
        gt_sub = gt[gt[x_col] == x_val]
        if len(gt_sub) == 1:
            pred.loc[sub.index, g_col] = str(gt_sub.iloc[0][g_col])

    # fallback: if still missing and only one ground-truth group exists overall
    left_mask = pred[g_col].isna() | (pred[g_col].astype(str).str.strip() == '')
    if left_mask.any() and gt[g_col].nunique(dropna=True) == 1:
        only = str(gt[g_col].dropna().iloc[0]) if not gt[g_col].dropna().empty else ''
        pred.loc[left_mask, g_col] = only

    pred[g_col] = pred[g_col].fillna('').astype(str)
    return pred


def _safe_match(pred: pd.DataFrame, gt: pd.DataFrame, x_col: str, y_col: str, g_col: Optional[str]) -> Dict[str, Any]:
    gt_df = gt.copy()
    if gt_df.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    if g_col and g_col not in gt_df.columns:
        g_col = None

    gt_df[x_col] = gt_df[x_col].astype(str)
    gt_df[y_col] = pd.to_numeric(gt_df[y_col], errors='coerce')
    gt_df = gt_df.dropna(subset=[x_col, y_col])
    if gt_df.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    pred_df = pred.copy()
    pred_df[y_col] = pd.to_numeric(pred_df['value'], errors='coerce')
    pred_df[x_col] = pred_df['x'].astype(str)
    if g_col and g_col in pred_df.columns:
        pred_df[g_col] = pred_df[g_col].astype(object)
    pred_df = pred_df.dropna(subset=[x_col, y_col])

    if pred_df.empty:
        mismatches = []
        for _, row in gt_df.iterrows():
            mismatches.append(
                {
                    'type': 'missing_series',
                    'series': str(row[g_col]) if g_col else '',
                    'x': str(row[x_col]),
                    'gt': float(row[y_col]),
                    'pred': None,
                }
            )
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred_df, 'mismatches': mismatches}

    if g_col:
        pred_df = _assign_series(pred_df, gt_df, x_col, g_col)

    gt_candidates: Dict[Tuple[str, str], List[int]] = {}
    for idx, row in gt_df.iterrows():
        s = str(row[g_col]) if g_col else ''
        key = (str(row[x_col]), s)
        gt_candidates.setdefault(key, []).append(idx)

    # matching
    matched_gt = set()
    mismatches: List[Dict[str, Any]] = []
    tp = 0

    for idx, prow in pred_df.iterrows():
        x_val = str(prow[x_col])
        s_val = str(prow[g_col]) if g_col else ''

        exact_key = (x_val, s_val)
        candidates = gt_candidates.get(exact_key, []) if g_col else gt_candidates.get((x_val, ''), [])

        if not candidates and g_col:
            # try same x but wrong series
            for (xk, _), cand_idx in gt_candidates.items():
                if xk == x_val:
                    candidates.extend(cand_idx)

        if not candidates:
            mismatches.append({'type': 'wrong_mapping', 'series': s_val if g_col else '', 'x': x_val, 'gt': None, 'pred': float(prow[y_col])})
            continue

        # choose first unused gt candidate with minimum absolute value diff
        best_idx = None
        best_diff = None
        for ci in candidates:
            if ci in matched_gt:
                continue
            gv = float(gt_df.loc[ci, y_col])
            diff = abs(float(prow[y_col]) - gv)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_idx = ci

        if best_idx is None:
            mismatches.append({'type': 'wrong_mapping', 'series': s_val if g_col else '', 'x': x_val, 'gt': None, 'pred': float(prow[y_col])})
            continue

        gt_val = float(gt_df.loc[best_idx, y_col])
        if abs(float(prow[y_col]) - gt_val) <= max(abs(gt_val) * TOLERANCE, 1.0):
            tp += 1
            matched_gt.add(best_idx)
        else:
            mismatch = {
                'type': 'wrong_value',
                'series': s_val if g_col else '',
                'x': x_val,
                'gt': gt_val,
                'pred': float(prow[y_col]),
            }
            mismatches.append(mismatch)
            matched_gt.add(best_idx)

    for idx, row in gt_df.iterrows():
        matched = False
        for s in mismatches:
            # no-op, only to avoid unused warnings in static analyzers
            pass
        if idx in matched_gt:
            matched = True
            continue
        missing = {
            'type': 'missing_series',
            'series': str(row[g_col]) if g_col else '',
            'x': str(row[x_col]),
            'gt': float(row[y_col]),
            'pred': None,
        }
        mismatches.append(missing)

    fn = len(gt_df) - len(matched_gt)
    fp = len(pred_df) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    pred_out = pred_df[['x', 'y', y_col] if False else [x_col, y_col]].copy() if x_col in pred_df.columns else pred_df.copy()
    if g_col:
        pred_out[g_col] = pred_df[g_col]

    # ensure requested output shape
    if 'series' not in pred_out.columns and g_col:
        pred_out = pred_out.rename(columns={g_col: 'series'})
    if 'series' in pred_out.columns and g_col != 'series' and g_col:
        pred_out = pred_out.rename(columns={g_col: 'series'})
    if x_col != 'x' and x_col in pred_out.columns:
        pred_out = pred_out.rename(columns={x_col: 'x'})
    if y_col != 'value' and y_col in pred_out.columns:
        pred_out = pred_out.rename(columns={y_col: 'value'})
    if 'x' not in pred_out.columns:
        pred_out = pred_out.rename(columns={pred_df.columns[0]: 'x'})
    if 'value' not in pred_out.columns and y_col in pred_out.columns:
        pred_out = pred_out.rename(columns={y_col: 'value'})

    return {
        'data_fidelity': float(f1),
        'rms_f1': float(f1),
        'rnss': float(_rnss(pred_df[y_col].dropna().astype(float).tolist(), gt_df[y_col].dropna().astype(float).tolist())),
        'pred_table': pred_out[['series', 'x', 'value']] if g_col else pred_out[['x', 'value']],
        'mismatches': mismatches,
    }


def _rnss(pred_vals: List[float], gt_vals: List[float], tolerance: float = TOLERANCE) -> float:
    if not pred_vals or not gt_vals:
        return 0.0
    gt_used = [False] * len(gt_vals)
    hits = 0
    for pv in pred_vals:
        best = None
        best_diff = None
        for i, gv in enumerate(gt_vals):
            if gt_used[i]:
                continue
            diff = abs(pv - gv)
            tol = max(abs(gv) * tolerance, 1.0)
            if diff <= tol and (best_diff is None or diff < best_diff):
                best_diff = diff
                best = i
        if best is not None:
            gt_used[best] = True
            hits += 1
    precision = hits / len(pred_vals) if pred_vals else 0.0
    recall = hits / len(gt_vals) if gt_vals else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _extract_response_text(data: Dict[str, Any]) -> str:
    choices = data.get('choices') or []
    if not choices:
        return ''
    message = choices[0].get('message') or {}
    content = message.get('content')
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get('type') == 'text':
                    parts.append(str(part.get('text') or ''))
            else:
                parts.append(str(part))
        content = ''.join(parts)
    if not isinstance(content, str):
        content = str(content or '')
    content = content.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?', '', content, count=1).strip()
        if content.endswith('```'):
            content = content[:-3].strip()
    return content


def _vlm_rows_to_frame(parsed: Dict[str, Any]) -> pd.DataFrame:
    rows = parsed.get('rows') or parsed.get('table') or parsed.get('pred_table') or parsed.get('data')
    if isinstance(rows, dict):
        rows = rows.get('rows') or rows.get('data')
    if not isinstance(rows, list):
        return pd.DataFrame(columns=['series', 'x', 'value'])

    records: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        x_val = row.get('x')
        if x_val is None:
            x_val = row.get('x_category') or row.get('category') or row.get('label')
        y_val = row.get('value')
        if y_val is None:
            y_val = row.get('y') or row.get('amount')
        y_num = _to_float(y_val)
        if x_val is None or y_num is None:
            continue
        records.append({'series': row.get('series') or row.get('group'), 'x': str(x_val), 'value': float(y_num)})

    if not records:
        return pd.DataFrame(columns=['series', 'x', 'value'])
    return pd.DataFrame(records)


def _coerce_pred_table(frame: pd.DataFrame, gt: pd.DataFrame, spec: Dict[str, Any]) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=['series', 'x', 'value'])

    if not gt.empty:
        raw_x_col, raw_y_col, raw_g_col = _infer_columns(gt, spec)
        gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
    else:
        raw_x_col, raw_y_col, raw_g_col = 'x', 'value', None
        gt_norm, x_col, y_col, g_col = frame, 'x', 'value', 'series'

    overlay_y_cols = _overlay_series_names(spec)
    if overlay_y_cols and raw_g_col is None:
        x_candidates = []
        overlays = spec.get('overlays') or []
        for overlay in overlays:
            if isinstance(overlay, dict) and isinstance(overlay.get('x'), str):
                x_candidates.append(overlay.get('x'))
        x_name = next((name for name in x_candidates if isinstance(name, str) and name in frame.columns), None)
        if x_name is not None and all(col in frame.columns for col in overlay_y_cols):
            rows: List[pd.DataFrame] = []
            for y_name in overlay_y_cols:
                rows.append(
                    pd.DataFrame(
                        {
                            'series': y_name,
                            'x': frame[x_name].astype(str),
                            'value': pd.to_numeric(frame[y_name], errors='coerce'),
                        }
                    )
                )
            out = pd.concat(rows, ignore_index=True).dropna(subset=['x', 'value'])
            return out[['series', 'x', 'value']]

    pred = frame.copy()
    x_candidates = [x_col, 'x', 'x_category', 'category', 'label']
    y_candidates = [y_col, 'value', 'y', 'amount']
    g_candidates = [g_col, 'series', 'group'] if g_col else ['series', 'group']

    x_name = next((name for name in x_candidates if isinstance(name, str) and name in pred.columns), None)
    y_name = next((name for name in y_candidates if isinstance(name, str) and name in pred.columns), None)
    g_name = next((name for name in g_candidates if isinstance(name, str) and name in pred.columns), None)

    if x_name is None:
        non_numeric = [col for col in pred.columns if not pd.api.types.is_numeric_dtype(pred[col])]
        x_name = non_numeric[0] if non_numeric else (pred.columns[0] if len(pred.columns) else None)
    if y_name is None:
        numeric = [col for col in pred.columns if pd.api.types.is_numeric_dtype(pred[col])]
        y_name = numeric[0] if numeric else None

    if x_name is None or y_name is None:
        return pd.DataFrame(columns=['series', 'x', 'value'])

    out = pd.DataFrame(
        {
            'x': pred[x_name].astype(str),
            'value': pd.to_numeric(pred[y_name], errors='coerce'),
        }
    )
    if g_name is not None:
        out['series'] = pred[g_name]
    else:
        out['series'] = None
    out = out.dropna(subset=['x', 'value'])
    out = _tag_predicted_series(out[['series', 'x', 'value']], spec)
    return out[['series', 'x', 'value']]


def _fallback_from_vlm(png_path: Optional[str], gt: pd.DataFrame, spec: Dict[str, Any]) -> Dict[str, Any]:
    base_url, api_key, model, provider = _chart_table_client_config()
    if not (base_url and api_key and model and png_path):
        return _nan_result()

    png_file = Path(png_path)
    if not png_file.exists():
        return _nan_result()

    try:
        image_b64 = base64.b64encode(png_file.read_bytes()).decode('ascii')
    except Exception as exc:
        if os.getenv('VLM_DEBUG'):
            print(f'[fidelity_verifier] VLM image read failed: {exc}', file=sys.stderr)
        return _nan_result()

    overlays = spec.get('overlays') or []
    schema_hint = {'required_rows': [{'series': 'string or null', 'x': 'category label', 'value': 'number'}]}
    prompt = textwrap.dedent(
        f'''
        Extract the data table shown in this chart image.
        Return strict JSON only, with this schema:
        {json.dumps(schema_hint, ensure_ascii=False)}

        Rules:
        - Read values from the visual marks, not from the source data.
        - Use the axis/category labels shown in the image.
        - Use null for series when there is only one visible series.
        - Do not include explanations.

        Chart spec context, for column names only:
        {json.dumps({'overlays': overlays}, ensure_ascii=False)}
        '''
    ).strip()
    system_prompt = 'You convert chart images into numeric data tables.'
    if provider in {'unichart', 'onechart', 'chart2table'}:
        system_prompt = f'You are a {provider} chart-to-table extractor. Return numeric rows as strict JSON.'

    payload = {
        'model': model,
        'temperature': 0,
        'messages': [
            {'role': 'system', 'content': [{'type': 'text', 'text': system_prompt}]},
            {'role': 'user', 'content': [{'type': 'text', 'text': prompt}, {'type': 'input_image', 'image_base64': image_b64}]},
        ],
        'response_format': {'type': 'json_object'},
        'max_output_tokens': int(os.getenv('LLM_MAX_TOKENS', '700') or 700),
    }

    try:
        resp = requests.post(
            base_url.rstrip('/') + os.getenv('CHART2TABLE_API_PATH', '/chat/completions'),
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json=payload,
            timeout=(10, float(os.getenv('LLM_TIMEOUT', '180') or 180)),
        )
        resp.raise_for_status()
        content = _extract_response_text(resp.json())
        parsed = json.loads(content)
    except Exception as exc:
        if os.getenv('VLM_DEBUG'):
            print(f'[fidelity_verifier] VLM chart-to-table failed: {exc}', file=sys.stderr)
        return _nan_result()

    pred = _vlm_rows_to_frame(parsed)
    if pred.empty:
        return _nan_result()
    if gt.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
    pred = _tag_predicted_series(pred, spec)
    return _safe_match(pred, gt_norm, x_col, y_col, g_col)


def _fallback_from_csv(svg_path: str, png_path: Optional[str], gt: pd.DataFrame, spec: Dict[str, Any]) -> Dict[str, Any]:
    overlays = spec.get('overlays') or []
    csv_candidates: List[Path] = []
    if png_path:
        csv_candidates.append(Path(png_path).with_suffix('.csv'))
    if svg_path:
        csv_candidates.append(Path(svg_path).with_suffix('.csv'))

    csv_path = next((p for p in csv_candidates if p and p.exists()), None)
    if not csv_path:
        return _nan_result()

    try:
        pred_df = pd.read_csv(csv_path)
    except Exception:
        return _nan_result()

    pred = _coerce_pred_table(pred_df, gt, spec)
    if pred.empty:
        return _nan_result()
    if gt.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
    return _safe_match(pred, gt_norm, x_col, y_col, g_col)


def _fallback_after_svg_failure(svg_path: str, png_path: Optional[str], gt: pd.DataFrame, spec: Dict[str, Any]) -> Dict[str, Any]:
    vlm_result = _fallback_from_vlm(png_path, gt, spec)
    if pd.notna(vlm_result.get('data_fidelity')):
        return vlm_result
    return _fallback_from_csv(svg_path, png_path, gt, spec)


def _pick_better_result(primary: Dict[str, Any], alternate: Dict[str, Any]) -> Dict[str, Any]:
    primary_score = primary.get('data_fidelity')
    alternate_score = alternate.get('data_fidelity')
    primary_ok = pd.notna(primary_score)
    alternate_ok = pd.notna(alternate_score)
    if alternate_ok and (not primary_ok or float(alternate_score) > float(primary_score)):
        return alternate
    return primary


def _from_trace(png_path: Optional[str], svg_path: str, gt: pd.DataFrame, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Primary path: read the execution trace (<name>.trace.csv) dumped by
    plot_trace during the subprocess render. This is the EXACT post-transform/
    pre-render data the plotting code passed to matplotlib — no reverse
    engineering from pixels/SVG. Columns: series,x,value[,axis].
    Returns _nan_result() if no usable trace is present (caller falls back to SVG).
    """
    trace_candidates: List[Path] = []
    if png_path:
        trace_candidates.append(Path(png_path).with_suffix('.trace.csv'))
    if svg_path:
        trace_candidates.append(Path(svg_path).with_suffix('.trace.csv'))
    trace_path = next((p for p in trace_candidates if p and p.exists()), None)
    if not trace_path:
        return _nan_result()
    try:
        tdf = pd.read_csv(trace_path)
    except Exception:
        return _nan_result()
    if tdf.empty or not {'series', 'x', 'value'}.issubset(tdf.columns):
        return _nan_result()

    # Route through the same coercion the CSV fallback uses, so the series/x/value
    # columns get normalized consistently with _safe_match's expectations
    # (avoids g_col/series column-name mismatches).
    pred = _coerce_pred_table(tdf[['series', 'x', 'value']], gt, spec)
    if pred.empty:
        return _nan_result()
    if gt.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
    # _safe_match keys pred by g_col; _coerce_pred_table emits a 'series' column,
    # so alias it to g_col when the ground truth groups by a differently-named col.
    if g_col and g_col != 'series' and 'series' in pred.columns and g_col not in pred.columns:
        pred = pred.rename(columns={'series': g_col})
    return _safe_match(pred, gt_norm, x_col, y_col, g_col)


def verify_fidelity(svg_path: str, ground_truth_table: Any, spec: Dict[str, Any], png_path: Optional[str] = None) -> Dict[str, Any]:
    gt = ground_truth_table if isinstance(ground_truth_table, pd.DataFrame) else pd.DataFrame(ground_truth_table or [])
    if gt is None:
        gt = pd.DataFrame()

    # JUDGE_MODE lets ablation experiments force a single judge path:
    #   "trace" = execution trace only (ours), "svg" = SVG deconstruction only,
    #   "auto"/unset = trace-first with SVG/VLM/CSV fallback (production default).
    judge_mode = (os.getenv('JUDGE_MODE') or 'auto').strip().lower()

    if judge_mode == 'svg':
        svg_file = Path(svg_path) if svg_path else None
        if not svg_file or not svg_file.exists():
            return _nan_result()
        try:
            svg = _read_text(str(svg_file))
            pred = _collect_predictions(svg, spec)
        except Exception:
            return _nan_result()
        if pred.empty or gt.empty:
            return _nan_result() if pred.empty else {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}
        gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
        pred = _tag_predicted_series(pred, spec)
        return _safe_match(pred, gt_norm, x_col, y_col, g_col)

    # PRIMARY: execution trace (exact). If a usable .trace.csv exists and yields
    # a non-NaN fidelity, it wins — SVG deconstruction is now the fallback.
    trace_result = _from_trace(png_path, svg_path or '', gt, spec)
    trace_ok = pd.notna(trace_result.get('data_fidelity'))

    if judge_mode == 'trace':
        return trace_result if trace_ok else _nan_result()

    if not svg_path:
        if trace_ok:
            return trace_result
        return _fallback_after_svg_failure('', png_path, gt, spec)

    svg_file = Path(svg_path)
    if not svg_file.exists():
        if trace_ok:
            return trace_result
        return _fallback_after_svg_failure('', png_path, gt, spec)

    # If the trace gave a confident result, use it directly (exact > estimated).
    if trace_ok:
        return trace_result

    try:
        svg = _read_text(str(svg_file))
        pred = _collect_predictions(svg, spec)
    except Exception:
        return _fallback_after_svg_failure(str(svg_file), png_path, gt, spec)

    if pred.empty:
        return _fallback_after_svg_failure(str(svg_file), png_path, gt, spec)

    if gt.empty:
        return {'data_fidelity': 0.0, 'rms_f1': 0.0, 'rnss': 0.0, 'pred_table': pred, 'mismatches': []}

    gt_norm, x_col, y_col, g_col = _normalize_ground_truth(gt, spec)
    pred = _tag_predicted_series(pred, spec)
    result = _safe_match(pred, gt_norm, x_col, y_col, g_col)
    if float(result.get('data_fidelity', 0.0) or 0.0) < 0.75:
        csv_result = _fallback_from_csv(str(svg_file), png_path, gt, spec)
        result = _pick_better_result(result, csv_result)
    return result
