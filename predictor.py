"""
通用路段預測引擎。

路線定義從 routes/*.json 讀入，支援任意路線擴充。
新增路線只需在 routes/ 目錄放一份符合 schema 的 JSON 即可。
"""
from __future__ import annotations

import json
import os
from math import ceil
from typing import Any

_ROUTES_DIR = os.path.join(os.path.dirname(__file__), "routes")


def load_route(route_id: str) -> dict[str, Any]:
    """從 routes/<route_id>.json 載入路線定義。"""
    path = os.path.join(_ROUTES_DIR, f"{route_id}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_routes() -> list[dict[str, str]]:
    """列出所有可用路線的 id 與 name。"""
    result = []
    for fname in sorted(os.listdir(_ROUTES_DIR)):
        if fname.endswith(".json"):
            data = load_route(fname[:-5])
            result.append({"id": data["id"], "name": data["name"]})
    return result


class RoutePredictor:
    """
    給定路線 JSON、FTP、體重、TSB，進行正向速度模擬。

    Args:
        route:     load_route() 回傳的路線 dict
        ftp:       功能性閾值功率（W）
        weight_kg: 系統總重（騎手 + 車重），單位 kg
        tsb:       訓練壓力平衡值，預設 0
    """

    def __init__(self, route: dict, ftp: float, weight_kg: float, tsb: float = 0):
        self.route = route
        self.ftp = ftp
        self.weight = weight_kg
        self.tsb = max(-40.0, min(float(tsb), 20.0))

        p = route["physics"]
        self.Crr  = p["Crr"]
        self.CdA  = p["CdA"]
        self.rho  = p["rho"]
        self.loss = p["loss"]

    def _effective_ftp(self) -> float:
        # Solo 獨推模型；TSB 係數 0.001（疲勞對個人爬坡影響小於集團）
        return self.ftp * (1 + self.tsb * 0.001)

    @staticmethod
    def _intensity_factor(estimated_mins: float) -> float:
        """
        動態強度係數（IF）：依預估完賽時間對應功率持續時間曲線。
        < 30 min  → VO2max 區間（可輸出 FTP × 1.10）
        30–60 min → 門檻區間（FTP × 1.00）
        1–3 hr    → 甜區/節奏（FTP × 0.88）
        > 3 hr    → 有氧耐力（FTP × 0.82）
        """
        if estimated_mins <= 30:
            return 1.10
        elif estimated_mins <= 60:
            return 1.00
        elif estimated_mins <= 180:
            return 0.88
        else:
            return 0.82

    def _solve_velocity(self, power: float, grade: float) -> float:
        if power <= 0:
            return 0.0
        g = 9.81
        p_wheel = power * (1 - self.loss)
        lo, hi = 0.0, 20.0
        for _ in range(40):
            v = (lo + hi) / 2
            p_req = v * (self.weight * g * (grade + self.Crr)) + 0.5 * self.rho * self.CdA * v ** 3
            if p_req < p_wheel:
                lo = v
            else:
                hi = v
        return (lo + hi) / 2

    def simulate(self) -> dict[str, Any]:
        base = self._effective_ftp()

        # 兩輪收斂：先以 IF=1.10 粗估（偏樂觀），取得合理時間後再查正確 IF
        pre_sec = sum(
            (seg["dist"] * 1000) / max(self._solve_velocity(base * 1.10 * seg["alt_decay"], seg["grade"]), 1e-6)
            for seg in self.route["segments"]
        )
        if_factor = self._intensity_factor(pre_sec / 60)
        base = base * if_factor

        total_sec = 0.0
        details = []

        for seg in self.route["segments"]:
            seg_power = base * seg["alt_decay"]
            v_ms = self._solve_velocity(seg_power, seg["grade"])
            seg_sec = (seg["dist"] * 1000) / v_ms if v_ms > 0 else float("inf")
            total_sec += seg_sec
            details.append({
                "name":      seg["name"],
                "power":     round(seg_power, 1),
                "speed_kmh": round(v_ms * 3.6, 1),
                "time_mins": round(seg_sec / 60, 1),
            })

        h = int(total_sec // 3600)
        m = int((total_sec % 3600) // 60)
        return {
            "total_time_str": f"{h} 小時 {m:02d} 分鐘",
            "total_minutes":  total_sec / 60,
            "if_factor":      if_factor,
            "details":        details,
        }


def calc_subx_ftp(
    route: dict,
    target_minutes: float,
    weight_kg: float,
    tsb: float = 0,
    bike_weight_kg: float = 8.0,
) -> int:
    """
    Binary search：求達到 target_minutes 完賽所需的最低 FTP。

    Args:
        route:          load_route() 回傳的路線 dict
        target_minutes: 目標完賽時間（分鐘）
        weight_kg:      騎手體重（kg）
        tsb:            訓練壓力平衡值
        bike_weight_kg: 車重（kg），由呼叫端傳入，預設 8.0
    """
    total_mass = weight_kg + bike_weight_kg
    lo, hi = 100.0, 600.0
    for _ in range(40):
        mid = (lo + hi) / 2
        pred = RoutePredictor(route=route, ftp=mid, weight_kg=total_mass, tsb=tsb).simulate()
        if pred["total_minutes"] <= target_minutes:
            hi = mid
        else:
            lo = mid
    return ceil(hi)
