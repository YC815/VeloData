"""
Backward-compatibility shim for wuling_engine.

app.py 仍可 import WulingPredictor / ROUTE_DISTANCE_KM / calc_subx_ftp，
實際邏輯已移至 predictor.py + routes/wuling.json。
"""
from predictor import RoutePredictor, load_route, calc_subx_ftp as _calc_subx_ftp

_WULING = load_route("wuling")

ROUTE_DISTANCE_KM = _WULING["distance_km"]
ROUTE_ELEVATION_M = _WULING["elevation_m"]


class WulingPredictor:
    def __init__(self, ftp, weight_kg, tsb=0):
        self._inner = RoutePredictor(route=_WULING, ftp=ftp, weight_kg=weight_kg, tsb=tsb)

    def simulate(self):
        return self._inner.simulate()


def calc_subx_ftp(target_minutes, weight_kg, tsb=0, bike_weight_kg=8.0):
    return _calc_subx_ftp(route=_WULING, target_minutes=target_minutes, weight_kg=weight_kg, tsb=tsb, bike_weight_kg=bike_weight_kg)
