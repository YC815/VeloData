"""
FTP 多維度估算引擎。

提供兩個子模型：
1. MMP 近似模型：從 Strava summary 欄位（weighted_average_watts + moving_time）
   找出近期最佳 15-40 分鐘騎乘，套用時長換算係數推算 FTP。
2. 物理逆推模型：由使用者手動指定活動 + 路段，透過 /api/ftp-physics 端點
   單筆查詢後逆推 FTP，結果以 ftp_physics 參數傳入 estimate_ftp()。

兩模型加權（有物理逆推：MMP 60% + Physics 40%；無：100% MMP）。
"""
from __future__ import annotations

from typing import Any

from predictor import load_route, list_routes

# MMP 時長換算係數（依文獻：20 min × 0.95、30 min × 0.97）
def _mmp_coeff(moving_time_sec: float) -> float:
    if moving_time_sec <= 1350:   # ≤ 22.5 min → 視為 20min 測驗
        return 0.95
    return 0.97                   # 22.5–40 min → 視為 30min 測驗


def _candidate_activities(acts_raw: list[dict]) -> list[dict]:
    """篩出可用於 MMP 估算的活動：有功率計 + 15–40 min。"""
    result = []
    for act in acts_raw:
        if not (act.get('device_watts') and act.get('weighted_average_watts')):
            continue
        t = act.get('moving_time', 0)
        if 900 <= t <= 2400:
            result.append(act)
    return result


# ── MMP 近似模型 ────────────────────────────────────────────────────────────

def calc_ftp_mmp(acts_raw: list[dict]) -> dict[str, Any] | None:
    """
    掃描 summary 欄位，找出最高 NP 的 15-40 min 活動，推算 FTP。

    Returns:
        dict 含 ftp_mmp, basis_activity, basis_np, basis_duration_sec, coeff
        或 None（資料不足）
    """
    candidates = _candidate_activities(acts_raw)
    if not candidates:
        return None

    best = max(candidates, key=lambda a: a['weighted_average_watts'])
    np_w = best['weighted_average_watts']
    t = best['moving_time']
    coeff = _mmp_coeff(t)
    ftp = round(np_w * coeff)

    return {
        'ftp_mmp': ftp,
        'basis_activity_name': best.get('name', '未命名'),
        'basis_activity_id': best.get('id'),
        'basis_np': round(np_w),
        'basis_duration_sec': t,
        'basis_date': best.get('start_date_local', '')[:10],
        'coeff': coeff,
    }


# ── 物理逆推輔助函式（供 app.py /api/ftp-physics 使用）────────────────────

def _build_segment_route_map() -> dict[int, dict]:
    """回傳 {strava_segment_id: route_dict}，只含有設定 strava_segment_id 的路線。"""
    mapping = {}
    for meta in list_routes():
        route = load_route(meta['id'])
        sid = route.get('strava_segment_id')
        if sid:
            mapping[int(sid)] = route
    return mapping

_SEGMENT_ROUTE_MAP: dict[int, dict] = _build_segment_route_map()


def _find_segment_effort(detailed_act: dict) -> tuple[dict, dict] | None:
    """
    從 DetailedActivity 的 segment_efforts 找到已知指標路段。

    Returns:
        (segment_effort_dict, route_dict) 或 None
    """
    for effort in detailed_act.get('segment_efforts', []):
        sid = effort.get('segment', {}).get('id')
        if sid and sid in _SEGMENT_ROUTE_MAP:
            return effort, _SEGMENT_ROUTE_MAP[sid]
    return None


# ── 加權合成 ────────────────────────────────────────────────────────────────

def estimate_ftp(
    acts_raw: list[dict],
    current_ftp: int,
    weight_kg: float,
    tsb: float,
    bike_weight_kg: float = 8.0,
    ftp_physics: int | None = None,
    physics_detail: dict | None = None,
) -> dict[str, Any]:
    """
    主入口：執行 MMP 模型並與可選的物理逆推結果加權合成。

    Args:
        acts_raw:      90 天 Strava 活動列表（已快取）
        current_ftp:   使用者目前設定的 FTP
        weight_kg:     騎手體重（kg）
        tsb:           當前 TSB
        bike_weight_kg: 車重（kg）
        ftp_physics:   物理逆推結果（由 /api/ftp-physics 端點計算後傳入），無則為 None
        physics_detail: 物理逆推的詳細資訊 dict，無則為 None

    Returns:
        dict 含所有估算數值與說明，供 API 直接序列化為 JSON。
    """
    mmp_result = calc_ftp_mmp(acts_raw)

    if mmp_result and ftp_physics:
        w_mmp, w_phys = 0.60, 0.40
        ftp_final = round(mmp_result['ftp_mmp'] * w_mmp + ftp_physics * w_phys)
    elif mmp_result:
        w_mmp, w_phys = 1.0, 0.0
        ftp_final = mmp_result['ftp_mmp']
    elif ftp_physics:
        w_mmp, w_phys = 0.0, 1.0
        ftp_final = ftp_physics
    else:
        return {
            'ok': False,
            'error': '90 天內無足夠功率資料可估算 FTP',
        }

    return {
        'ok': True,
        'ftp_final': ftp_final,
        'ftp_current': current_ftp,
        'delta': ftp_final - current_ftp,
        'ftp_mmp': mmp_result['ftp_mmp'] if mmp_result else None,
        'ftp_physics': ftp_physics,
        'weights': {'mmp': w_mmp, 'physics': w_phys},
        'mmp_detail': mmp_result,
        'physics_detail': physics_detail,
        'weight_kg': weight_kg,
        'bike_weight_kg': bike_weight_kg,
        'tsb': tsb,
    }
