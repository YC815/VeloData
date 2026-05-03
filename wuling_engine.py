from math import ceil

ROUTE_DISTANCE_KM = 52.56   # 地理中心碑→武嶺，8段合計
ROUTE_ELEVATION_M = 2593    # 各段 grade×distance 合計


class WulingPredictor:
    def __init__(self, ftp, weight_kg, tsb=0):
        self.ftp = ftp
        self.weight = weight_kg
        self.tsb = max(-40, min(tsb, 20))

        # 西進武嶺 8 個路段（地理中心碑出發）
        self.segments = [
            {"name": "地理中心碑-人止關", "dist": 16.29, "grade": 0.018, "alt_decay": 1.00},
            {"name": "人止關-霧社",       "dist":  5.67, "grade": 0.064, "alt_decay": 0.98},
            {"name": "霧社-見晴",         "dist":  5.48, "grade": 0.067, "alt_decay": 0.95},
            {"name": "見晴-最高小7",      "dist":  3.10, "grade": 0.101, "alt_decay": 0.92},
            {"name": "最高小7-翠峰",      "dist":  8.42, "grade": 0.036, "alt_decay": 0.88},
            {"name": "翠峰-鳶峰",         "dist":  6.38, "grade": 0.067, "alt_decay": 0.84},
            {"name": "鳶峰-昆陽",         "dist":  5.09, "grade": 0.066, "alt_decay": 0.80},
            {"name": "昆陽-武嶺",         "dist":  2.13, "grade": 0.089, "alt_decay": 0.77},
        ]

    def _effective_ftp(self):
        return self.ftp * (1 + self.tsb * 0.002)

    def _solve_velocity(self, power, grade):
        if power <= 0:
            return 0.0
        g    = 9.81
        Crr  = 0.004
        CdA  = 0.35
        rho  = 1.15
        loss = 0.03
        p_wheel = power * (1 - loss)
        lo, hi = 0.0, 20.0
        for _ in range(40):
            v = (lo + hi) / 2
            p_req = v * (self.weight * g * (grade + Crr)) + 0.5 * rho * CdA * v ** 3
            if p_req < p_wheel:
                lo = v
            else:
                hi = v
        return (lo + hi) / 2

    def simulate(self):
        base = self._effective_ftp()
        total_sec = 0.0
        details = []

        for seg in self.segments:
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
            "details":        details,
        }


def calc_subx_ftp(target_minutes, weight_kg, tsb=0):
    """Binary search：求達到 target_minutes 所需的最低 FTP。"""
    total_mass = weight_kg + 8
    lo, hi = 100.0, 600.0
    for _ in range(40):
        mid = (lo + hi) / 2
        pred = WulingPredictor(ftp=mid, weight_kg=total_mass, tsb=tsb).simulate()
        if pred["total_minutes"] <= target_minutes:
            hi = mid
        else:
            lo = mid
    return ceil(hi)
