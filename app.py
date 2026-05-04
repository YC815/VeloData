import os
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, redirect, request, url_for, jsonify
from dotenv import load_dotenv
import requests
import pytz

from db import db, UserProfile, RaceEvent, init_db
from wuling_engine import WulingPredictor, ROUTE_DISTANCE_KM, calc_subx_ftp
from predictor import RoutePredictor, load_route, list_routes, calc_subx_ftp as _route_calc_subx_ftp
from ftp_calibration import estimate_ftp

load_dotenv()
app = Flask(__name__)
init_db(app)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = os.getenv('STRAVA_REDIRECT_URI', 'http://localhost:8000/callback')

BIKE_SPORT_TYPES = {
    'Ride', 'MountainBikeRide', 'GravelRide', 'VirtualRide',
    'EBikeRide', 'Velomobile', 'Handcycle',
}


def get_user_profile():
    profile = UserProfile.query.first()
    if not profile:
        profile = UserProfile()
        db.session.add(profile)
        db.session.commit()
    return profile


def _get_refresh_token() -> str:
    """DB 優先，回退到 env var（首次部署 / 本機開發用）。"""
    profile = get_user_profile()
    if profile.strava_refresh_token:
        return profile.strava_refresh_token
    return os.getenv('STRAVA_REFRESH_TOKEN', '')


def _save_refresh_token(token: str):
    """將 refresh token 存入 DB，不寫 .env 檔（雲端重啟安全）。"""
    profile = get_user_profile()
    profile.strava_refresh_token = token
    db.session.commit()


def _clear_refresh_token():
    """登出 / token 失效時清除。"""
    profile = get_user_profile()
    profile.strava_refresh_token = None
    db.session.commit()


def refresh_strava_token():
    profile = get_user_profile()
    if profile.is_access_token_valid():
        return profile.strava_access_token

    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'refresh_token': _get_refresh_token(),
            'grant_type': 'refresh_token'
        }
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get('refresh_token'):
        profile.strava_refresh_token = data['refresh_token']
    profile.strava_access_token = data['access_token']
    profile.strava_access_token_expires_at = data.get('expires_at')
    db.session.commit()
    return data['access_token']


def get_local_now(tz_str):
    try:
        tz = pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone('Asia/Taipei')
    return datetime.now(tz)


def calc_tss(moving_time_sec, weighted_watts, ftp):
    if not weighted_watts or ftp <= 0:
        return None
    intensity_factor = weighted_watts / ftp
    return round((moving_time_sec * weighted_watts * intensity_factor) / (ftp * 3600) * 100, 1)


def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fetch_activities_90d(header):
    after_ts = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp())
    resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=header,
        params={'per_page': 100, 'after': after_ts}
    )
    if resp.status_code == 401:
        return None
    resp.raise_for_status()
    return resp.json()


def _fetch_activities_cached(header: dict, force: bool = False) -> list | None:
    import json as _json
    profile = get_user_profile()
    if not force and profile.is_activities_cache_valid():
        return _json.loads(profile.activities_cache)
    data = fetch_activities_90d(header)
    if data is not None:
        profile.activities_cache = _json.dumps(data, ensure_ascii=False)
        profile.activities_cache_at = datetime.utcnow()
        db.session.commit()
    return data


def calc_pmc(activities_raw, ftp, tz_str='Asia/Taipei'):
    tss_by_date = {}
    has_suffer_fallback = False

    for act in activities_raw:
        local_dt = datetime.fromisoformat(act.get('start_date_local', '1970-01-01T00:00:00Z').rstrip('Z'))
        act_date = local_dt.date()

        if act.get('device_watts') and act.get('weighted_average_watts'):
            tss = calc_tss(act['moving_time'], act['weighted_average_watts'], ftp)
            if tss:
                tss_by_date[act_date] = tss_by_date.get(act_date, 0.0) + tss
        elif act.get('suffer_score'):
            tss_by_date[act_date] = tss_by_date.get(act_date, 0.0) + act['suffer_score']
            has_suffer_fallback = True

    today = get_local_now(tz_str).date()
    start = today - timedelta(days=89)

    ctl, atl = 0.0, 0.0
    labels, ctl_series, atl_series, tsb_series = [], [], [], []

    current = start
    while current <= today:
        tss_today = tss_by_date.get(current, 0.0)
        ctl = ctl + (tss_today - ctl) / 42
        atl = atl + (tss_today - atl) / 7
        tsb = ctl - atl
        labels.append(current.strftime('%m/%d'))
        ctl_series.append(round(ctl, 1))
        atl_series.append(round(atl, 1))
        tsb_series.append(round(tsb, 1))
        current += timedelta(days=1)

    return {
        'labels': labels,
        'ctl': ctl_series,
        'atl': atl_series,
        'tsb': tsb_series,
        'current_ctl': ctl_series[-1],
        'current_atl': atl_series[-1],
        'current_tsb': tsb_series[-1],
        'has_suffer_fallback': has_suffer_fallback,
    }


def calc_tsb_status(tsb):
    if tsb > 5:
        return {'color': 'green', 'label': '狀態良好，可高強度', 'tw_class': 'bg-green-500'}
    if tsb > 0:
        return {'color': 'yellow', 'label': '輕微疲勞，建議Z2有氧', 'tw_class': 'bg-yellow-400'}
    if tsb > -10:
        return {'color': 'orange', 'label': '中度疲勞，注意恢復', 'tw_class': 'bg-orange-400'}
    return {'color': 'red', 'label': '過度訓練，強制休息', 'tw_class': 'bg-red-500'}


def calc_wuling(ftp, weight_kg, tsb, bike_weight_kg=8.0):
    if not weight_kg:
        empty = {'time_display': '—', 'speed_kmh': None, 'sub_three': False, 'tsb': None}
        return {'current': empty, 'ideal': empty, 'delta_mins': 0}
    total_mass = weight_kg + bike_weight_kg
    current_pred = WulingPredictor(ftp=ftp, weight_kg=total_mass, tsb=tsb).simulate()
    ideal_pred   = WulingPredictor(ftp=ftp, weight_kg=total_mass, tsb=15).simulate()

    def _pred_dict(pred, tsb_val):
        mins = pred['total_minutes']
        speed = round(ROUTE_DISTANCE_KM / (mins / 60), 1) if mins > 0 else None
        color = 'green' if mins < 180 else ('yellow' if mins < 240 else 'red')
        return {
            'time_display': pred['total_time_str'],
            'speed_kmh':    speed,
            'sub_three':    mins < 180,
            'color':        color,
            'tsb':          tsb_val,
        }

    return {
        'current':    _pred_dict(current_pred, round(tsb, 1)),
        'ideal':      _pred_dict(ideal_pred, 15),
        'delta_mins': round(current_pred['total_minutes'] - ideal_pred['total_minutes']),
    }


def calc_wuling_subx(ftp, weight_kg, tsb, bike_weight_kg=8.0):
    """計算破 3h/3.5h/4h/4.5h 所需 FTP，並回傳與當前 FTP 的落差。"""
    if not weight_kg:
        return []
    targets = [
        {"label": "破 3 小時", "minutes": 180},
        {"label": "破 3.5 小時", "minutes": 210},
        {"label": "破 4 小時", "minutes": 240},
        {"label": "破 4.5 小時", "minutes": 270},
    ]
    results = []
    w_per_kg = round(ftp / weight_kg, 2) if weight_kg else None
    for t in targets:
        req_ftp = calc_subx_ftp(t["minutes"], weight_kg, tsb, bike_weight_kg=bike_weight_kg)
        req_wkg = round(req_ftp / weight_kg, 2) if weight_kg else None
        results.append({
            "label": t["label"],
            "minutes": t["minutes"],
            "req_ftp": req_ftp,
            "req_wkg": req_wkg,
            "gap_ftp": req_ftp - ftp,
            "gap_wkg": round((req_wkg or 0) - (w_per_kg or 0), 2),
            "achievable": ftp >= req_ftp,
        })
    return results


def calc_all_routes_benchmark(ftp, weight_kg, tsb, bike_weight_kg=8.0):
    """對 routes/ 下所有路線做預測，回傳列表供 Benchmark Lab 列表 UI 使用。"""
    if not weight_kg:
        return []
    total_mass = weight_kg + bike_weight_kg
    w_per_kg = round(ftp / weight_kg, 2)
    results = []
    for meta in list_routes():
        route = load_route(meta["id"])
        current = RoutePredictor(route=route, ftp=ftp, weight_kg=total_mass, tsb=tsb).simulate()
        ideal   = RoutePredictor(route=route, ftp=ftp, weight_kg=total_mass, tsb=15).simulate()
        delta   = round(current["total_minutes"] - ideal["total_minutes"])

        subx = []
        for t in sorted(route.get("sub_x_targets", []), key=lambda x: x["minutes"]):
            req_ftp = _route_calc_subx_ftp(
                route=route, target_minutes=t["minutes"],
                weight_kg=weight_kg, tsb=tsb, bike_weight_kg=bike_weight_kg
            )
            req_wkg = round(req_ftp / weight_kg, 2)
            subx.append({
                "label":      t["label"],
                "minutes":    t["minutes"],
                "req_ftp":    req_ftp,
                "req_wkg":    req_wkg,
                "gap_ftp":    req_ftp - ftp,
                "gap_wkg":    round(req_wkg - w_per_kg, 2),
                "achievable": ftp >= req_ftp,
            })

        results.append({
            "id":          route["id"],
            "name":        route["name"],
            "description": route.get("description", ""),
            "distance_km": route["distance_km"],
            "elevation_m": route["elevation_m"],
            "current_time": current["total_time_str"],
            "ideal_time":   ideal["total_time_str"],
            "current_mins": round(current["total_minutes"], 1),
            "ideal_mins":   round(ideal["total_minutes"], 1),
            "delta_mins":   delta,
            "current_speed": round(route["distance_km"] / (current["total_minutes"] / 60), 1)
                             if current["total_minutes"] > 0 else None,
            "current_tsb":  round(tsb, 1),
            "w_per_kg":     w_per_kg,
            "subx":         subx,
        })
    return results


def _get_upcoming_events():
    """取得未來 90 天內的 A/B 級賽事，用於 Upcoming Events 卡片。"""
    from datetime import date as _date
    today = _date.today()
    cutoff = today + timedelta(days=90)
    rows = (RaceEvent.query
            .filter(RaceEvent.event_date >= today)
            .filter(RaceEvent.event_date <= cutoff)
            .filter(RaceEvent.priority.in_(['A', 'B']))
            .order_by(RaceEvent.event_date)
            .all())
    return [r.to_dict() for r in rows]


def _get_next_race():
    """取得最近一筆未來賽事（不限等級），用於儀表板倒數卡片。"""
    from datetime import date as _date
    today = _date.today()
    row = (RaceEvent.query
           .filter(RaceEvent.event_date >= today)
           .order_by(RaceEvent.event_date)
           .first())
    return row.to_dict() if row else None


def enrich_activity(act, ftp):
    local_dt = datetime.fromisoformat(act.get('start_date_local', '1970-01-01T00:00:00Z').rstrip('Z'))
    utc_dt = datetime.fromisoformat(act.get('start_date', '1970-01-01T00:00:00Z').rstrip('Z'))

    tss = None
    if act.get('device_watts') and act.get('weighted_average_watts'):
        tss = calc_tss(act['moving_time'], act['weighted_average_watts'], ftp)

    if_value = None
    interpretation = None
    if act.get('device_watts') and act.get('weighted_average_watts'):
        if_value = round(act['weighted_average_watts'] / ftp, 2)
        if if_value < 0.75:
            interpretation = '恢復騎，隔天可繼續練'
        elif if_value < 0.85:
            interpretation = '有氧耐力訓練'
        elif if_value < 0.95:
            interpretation = '甜區/閾值訓練'
        elif if_value < 1.05:
            interpretation = 'VO2max 強度'
        else:
            interpretation = '全力噴發，建議休息24h'

    recovery_note = None
    if tss is not None:
        if tss < 50:
            recovery_note = '低負荷，恢復迅速'
        elif tss < 100:
            recovery_note = '中等強度，建議休息12-16h'
        elif tss < 150:
            recovery_note = '高負荷，建議休息24h'
        else:
            recovery_note = '極高負荷，建議休息48h'

    return {
        'name': act.get('name', '未命名'),
        'local_dt': local_dt,
        'utc_dt': utc_dt,
        'date_display': local_dt.strftime('%m/%d'),
        'time_display': local_dt.strftime('%H:%M'),
        'sport_type': act.get('sport_type', 'Ride'),
        'distance_km': round(act.get('distance', 0) / 1000, 1),
        'moving_time_sec': act.get('moving_time', 0),
        'duration': format_duration(act.get('moving_time', 0)),
        'elevation_m': round(act.get('total_elevation_gain', 0)),
        'has_power': bool(act.get('device_watts')),
        'avg_watts': round(act['average_watts']) if act.get('device_watts') and act.get('average_watts') else None,
        'weighted_watts': round(act['weighted_average_watts']) if act.get('device_watts') and act.get('weighted_average_watts') else None,
        'vi': round(act['weighted_average_watts'] / act['average_watts'], 2) if act.get('device_watts') and act.get('average_watts') and act.get('weighted_average_watts') and act['average_watts'] > 0 else None,
        'has_hr': bool(act.get('has_heartrate')),
        'avg_hr': round(act['average_heartrate']) if act.get('has_heartrate') and act.get('average_heartrate') else None,
        'avg_speed_kmh': round(act['average_speed'] * 3.6, 1) if act.get('average_speed') else None,
        'avg_cadence': round(act['average_cadence']) if act.get('average_cadence') else None,
        'suffer_score': act.get('suffer_score'),
        'tss': tss,
        'if_value': if_value,
        'interpretation': interpretation,
        'recovery_note': recovery_note,
    }


def _require_strava():
    """Returns (header, athlete, profile, redirect_response). redirect_response is non-None on auth failure."""
    import json as _json
    if not _get_refresh_token():
        return None, None, None, redirect(url_for('auth'))
    try:
        access_token = refresh_strava_token()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            _clear_refresh_token()
            return None, None, None, redirect(url_for('auth'))
        raise
    header = {'Authorization': f'Bearer {access_token}'}
    profile = get_user_profile()
    if profile.is_athlete_cache_valid():
        athlete = _json.loads(profile.athlete_cache)
    else:
        athlete_resp = requests.get("https://www.strava.com/api/v3/athlete", headers=header)
        athlete_resp.raise_for_status()
        athlete = athlete_resp.json()
        profile.athlete_cache = _json.dumps(athlete, ensure_ascii=False)
        profile.athlete_cache_at = datetime.utcnow()
        db.session.commit()
    return header, athlete, profile, None


def _extract_used_timezones(acts_raw):
    used_tz_raw = [act.get('timezone', '') for act in acts_raw if act.get('timezone')]
    return list(dict.fromkeys(
        m.group(1) for raw in used_tz_raw
        if (m := re.search(r'\)\s*(.+)$', raw))
    ))


def _calc_weekly_stats(acts_raw, ftp, profile):
    tz = pytz.timezone(profile.timezone)
    now_local = datetime.now(tz)
    week_start_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start_utc = week_start_local.astimezone(timezone.utc).replace(tzinfo=None)

    weekly_tss = 0.0
    weekly_km = 0.0
    weekly_time_sec = 0

    for act in acts_raw:
        if act.get('sport_type') not in BIKE_SPORT_TYPES:
            continue
        utc_dt = datetime.fromisoformat(act.get('start_date', '1970-01-01T00:00:00Z').rstrip('Z'))
        if utc_dt < week_start_utc:
            continue
        if act.get('device_watts') and act.get('weighted_average_watts'):
            tss = calc_tss(act['moving_time'], act['weighted_average_watts'], ftp)
            if tss:
                weekly_tss += tss
        weekly_km += act.get('distance', 0) / 1000
        weekly_time_sec += act.get('moving_time', 0)

    return {
        'weekly_tss': round(weekly_tss, 1),
        'weekly_km': round(weekly_km, 1),
        'weekly_time': format_duration(weekly_time_sec),
    }


@app.route('/auth')
def auth():
    client_id = os.getenv('STRAVA_CLIENT_ID', '')
    url = (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&approval_prompt=force"
        f"&scope=read,activity:read_all"
    )
    return redirect(url)


@app.route('/callback')
def callback():
    if request.args.get('error'):
        return render_template('login.html', error='授權被取消。')

    code = request.args.get('code')
    if not code:
        return render_template('login.html', error='未收到授權碼。')

    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code'
        }
    )
    if not resp.ok:
        return render_template('login.html', error=f'Strava 回傳錯誤：{resp.status_code}')

    data = resp.json()
    refresh_token = data.get('refresh_token')
    if not refresh_token:
        return render_template('login.html', error='授權成功但未取得 refresh token。')

    _save_refresh_token(refresh_token)
    return redirect(url_for('index'))


@app.route('/api/profile', methods=['GET'])
def api_profile_get():
    profile = get_user_profile()
    return jsonify(profile.to_dict())


@app.route('/api/profile', methods=['PUT'])
def api_profile_put():
    data = request.get_json(force=True)
    profile = get_user_profile()

    ftp = data.get('ftp_watts')
    weight = data.get('weight_kg')

    if ftp is not None:
        try:
            ftp_int = int(ftp)
            if ftp_int <= 0:
                return jsonify({'error': 'FTP 必須大於 0'}), 400
            profile.ftp_watts = ftp_int
        except (ValueError, TypeError):
            return jsonify({'error': 'FTP 格式錯誤'}), 400

    if weight is not None:
        try:
            weight_float = float(weight)
            if weight_float <= 0:
                return jsonify({'error': '體重必須大於 0'}), 400
            profile.weight_kg = weight_float
        except (ValueError, TypeError):
            return jsonify({'error': '體重格式錯誤'}), 400

    bike_weight = data.get('bike_weight_kg')
    if bike_weight is not None:
        try:
            bike_weight_float = float(bike_weight)
            if bike_weight_float <= 0:
                return jsonify({'error': '車重必須大於 0'}), 400
            profile.bike_weight_kg = bike_weight_float
        except (ValueError, TypeError):
            return jsonify({'error': '車重格式錯誤'}), 400

    tz_str = data.get('timezone')
    if tz_str is not None:
        try:
            pytz.timezone(tz_str)
            profile.timezone = tz_str
        except pytz.UnknownTimeZoneError:
            return jsonify({'error': f'不支援的時區：{tz_str}'}), 400

    # FTP 有變動時，同步更新 ftp_suggest_cache 裡的 ftp_current / delta
    if ftp is not None and profile.ftp_suggest_cache:
        import json as _json
        try:
            cached = _json.loads(profile.ftp_suggest_cache)
            new_ftp = profile.ftp_watts
            cached['ftp_current'] = new_ftp
            cached['delta'] = cached.get('ftp_final', new_ftp) - new_ftp
            profile.ftp_suggest_cache = _json.dumps(cached, ensure_ascii=False)
        except Exception:
            pass

    db.session.commit()
    return jsonify(profile.to_dict())


@app.route('/api/events', methods=['GET'])
def api_events_get():
    from datetime import date as _date
    cutoff = _date.today()
    events = (RaceEvent.query
              .filter(RaceEvent.event_date >= cutoff)
              .order_by(RaceEvent.event_date)
              .all())
    return jsonify([e.to_dict() for e in events])


@app.route('/api/events', methods=['POST'])
def api_events_post():
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    date_str = data.get('date') or ''
    priority = data.get('priority') or 'C'

    if not name:
        return jsonify({'error': '賽事名稱不得為空'}), 400
    if priority not in ('A', 'B', 'C'):
        return jsonify({'error': '優先級必須為 A、B 或 C'}), 400
    try:
        from datetime import date as _date
        event_date = _date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式錯誤，請用 YYYY-MM-DD'}), 400

    distance = data.get('distance_km')
    elevation = data.get('elevation_m')
    try:
        distance = float(distance) if distance not in (None, '') else None
        elevation = int(elevation) if elevation not in (None, '') else None
    except (ValueError, TypeError):
        return jsonify({'error': '距離或爬升格式錯誤'}), 400

    ev = RaceEvent(
        name=name,
        event_date=event_date,
        priority=priority,
        distance_km=distance,
        elevation_m=elevation,
    )
    db.session.add(ev)
    db.session.commit()
    return jsonify(ev.to_dict()), 201


@app.route('/api/events/<int:event_id>', methods=['PUT'])
def api_events_put(event_id):
    ev = RaceEvent.query.get(event_id)
    if not ev:
        return jsonify({'error': '找不到此賽事'}), 404
    data = request.get_json(force=True)
    name = (data.get('name') or '').strip()
    date_str = data.get('date') or ''
    priority = data.get('priority') or 'C'

    if not name:
        return jsonify({'error': '賽事名稱不得為空'}), 400
    if priority not in ('A', 'B', 'C'):
        return jsonify({'error': '優先級必須為 A、B 或 C'}), 400
    try:
        from datetime import date as _date
        event_date = _date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': '日期格式錯誤，請用 YYYY-MM-DD'}), 400

    distance = data.get('distance_km')
    elevation = data.get('elevation_m')
    try:
        distance = float(distance) if distance not in (None, '') else None
        elevation = int(elevation) if elevation not in (None, '') else None
    except (ValueError, TypeError):
        return jsonify({'error': '距離或爬升格式錯誤'}), 400

    ev.name = name
    ev.event_date = event_date
    ev.priority = priority
    ev.distance_km = distance
    ev.elevation_m = elevation
    db.session.commit()
    return jsonify(ev.to_dict())


@app.route('/api/events/<int:event_id>', methods=['DELETE'])
def api_events_delete(event_id):
    ev = RaceEvent.query.get(event_id)
    if not ev:
        return jsonify({'error': '找不到此賽事'}), 404
    db.session.delete(ev)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/ftp-suggest', methods=['GET'])
def api_ftp_suggest_get():
    """回傳 DB 中的快取估算結果，無快取時回傳 null。"""
    import json as _json
    profile = get_user_profile()
    if not profile.ftp_suggest_cache or not profile.ftp_suggest_at:
        return jsonify(None)
    data = _json.loads(profile.ftp_suggest_cache)
    data['generated_at'] = profile.ftp_suggest_at.strftime('%Y/%m/%d %H:%M')
    return jsonify(data)


@app.route('/api/ftp-suggest', methods=['POST'])
def api_ftp_suggest_post():
    """重新估算 MMP FTP，結果寫入 DB，回傳新結果。物理逆推由 /api/ftp-physics 單獨處理。"""
    import json as _json

    if not _get_refresh_token():
        return jsonify({'error': '未授權'}), 401

    try:
        access_token = refresh_strava_token()
    except requests.HTTPError:
        return jsonify({'error': 'Token 刷新失敗'}), 401

    header = {'Authorization': f'Bearer {access_token}'}
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        return jsonify({'error': '無法取得活動資料'}), 401

    profile = get_user_profile()
    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg or 70.0
    bike_weight_kg = profile.bike_weight_kg or 8.0

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb = pmc['current_tsb']

    # 嘗試沿用已有的物理逆推快取結果
    ftp_physics = None
    if profile.ftp_suggest_cache:
        try:
            cached = _json.loads(profile.ftp_suggest_cache)
            ftp_physics = cached.get('ftp_physics')
        except Exception:
            pass

    result = estimate_ftp(
        acts_raw=acts_raw,
        current_ftp=ftp,
        weight_kg=weight_kg,
        tsb=tsb,
        bike_weight_kg=bike_weight_kg,
        ftp_physics=ftp_physics,
    )

    if not result.get('ok'):
        return jsonify({'error': result.get('error', '估算失敗')}), 422

    now = datetime.utcnow()
    cache_str = _json.dumps(result, ensure_ascii=False)
    profile.ftp_suggest_cache = cache_str
    profile.ftp_suggest_at = now
    db.session.commit()

    result['generated_at'] = now.strftime('%Y/%m/%d %H:%M')
    return jsonify(result)


@app.route('/api/ftp-physics', methods=['POST'])
def api_ftp_physics_post():
    """
    對指定活動 + 路段做物理逆推，回傳逆推 FTP。
    Request JSON: {activity_id: int, route_id: str}
    """
    import json as _json
    from ftp_calibration import _find_segment_effort, _SEGMENT_ROUTE_MAP

    if not _get_refresh_token():
        return jsonify({'error': '未授權'}), 401

    data = request.get_json(force=True)
    activity_id = data.get('activity_id')
    route_id = data.get('route_id')

    if not activity_id or not route_id:
        return jsonify({'error': '缺少 activity_id 或 route_id'}), 400

    route = load_route(route_id)

    try:
        access_token = refresh_strava_token()
    except requests.HTTPError:
        return jsonify({'error': 'Token 刷新失敗'}), 401

    header = {'Authorization': f'Bearer {access_token}'}
    resp = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=header,
        timeout=15,
    )
    if not resp.ok:
        return jsonify({'error': f'無法取得活動資料（{resp.status_code}）'}), 502

    detailed = resp.json()

    # 若路線有 strava_segment_id，從 segment_efforts 找精確路段時間
    elapsed_sec = None
    sid = route.get('strava_segment_id')
    if sid:
        effort, _ = _find_segment_effort(detailed) or (None, None)
        if effort:
            elapsed_sec = effort.get('elapsed_time')

    # 無路段時間則退而用整趟 moving_time
    if not elapsed_sec:
        elapsed_sec = detailed.get('moving_time')

    if not elapsed_sec:
        return jsonify({'error': '無法取得活動時間'}), 422

    profile = get_user_profile()
    weight_kg = profile.weight_kg or 70.0
    bike_weight_kg = profile.bike_weight_kg or 8.0

    acts_raw = _fetch_activities_cached(header)
    pmc = calc_pmc(acts_raw or [], profile.ftp_watts, profile.timezone)
    tsb = pmc['current_tsb']

    req_ftp = _route_calc_subx_ftp(
        route=route,
        target_minutes=elapsed_sec / 60,
        weight_kg=weight_kg,
        tsb=tsb,
        bike_weight_kg=bike_weight_kg,
    )

    # 更新快取中的物理逆推結果
    physics_detail = {
        'ftp_physics': req_ftp,
        'matched_route_name': route['name'],
        'basis_activities': [{
            'activity_name': detailed.get('name', '未命名'),
            'activity_id': activity_id,
            'activity_date': detailed.get('start_date_local', '')[:10],
            'duration_sec': elapsed_sec,
            'route_name': route['name'],
            'route_id': route_id,
            'req_ftp': req_ftp,
        }],
    }

    if profile.ftp_suggest_cache:
        try:
            cached = _json.loads(profile.ftp_suggest_cache)
            cached['ftp_physics'] = req_ftp
            cached['physics_detail'] = physics_detail
            # 重算加權 FTP
            ftp_mmp = cached.get('ftp_mmp')
            if ftp_mmp:
                cached['ftp_final'] = round(ftp_mmp * 0.60 + req_ftp * 0.40)
                cached['delta'] = cached['ftp_final'] - cached['ftp_current']
                cached['weights'] = {'mmp': 0.60, 'physics': 0.40}
            profile.ftp_suggest_cache = _json.dumps(cached, ensure_ascii=False)
            db.session.commit()
        except Exception:
            pass

    return jsonify({
        'ftp_physics': req_ftp,
        'elapsed_sec': elapsed_sec,
        'route_name': route['name'],
        'activity_name': detailed.get('name', '未命名'),
        'physics_detail': physics_detail,
    })


@app.route('/api/activities-with-power', methods=['GET'])
def api_activities_with_power():
    """回傳近 90 天有功率計的活動精簡列表，供物理逆推選單使用。"""
    if not _get_refresh_token():
        return jsonify({'error': '未授權'}), 401

    try:
        access_token = refresh_strava_token()
    except requests.HTTPError:
        return jsonify({'error': 'Token 刷新失敗'}), 401

    header = {'Authorization': f'Bearer {access_token}'}
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        return jsonify([])

    result = []
    for act in sorted(acts_raw, key=lambda a: a.get('start_date', ''), reverse=True):
        if not act.get('device_watts'):
            continue
        local_dt = act.get('start_date_local', '')[:10]
        result.append({
            'id': act['id'],
            'name': act.get('name', '未命名'),
            'date': local_dt,
            'moving_time': act.get('moving_time', 0),
            'distance_km': round(act.get('distance', 0) / 1000, 1),
            'elevation_m': round(act.get('total_elevation_gain', 0)),
        })
    return jsonify(result)


@app.route('/api/routes', methods=['GET'])
def api_routes():
    """回傳系統已知路線列表，供物理逆推路段選單使用。"""
    result = []
    for meta in list_routes():
        route = load_route(meta['id'])
        result.append({
            'id': route['id'],
            'name': route['name'],
            'distance_km': route['distance_km'],
            'elevation_m': route['elevation_m'],
        })
    return jsonify(result)


@app.route('/api/activities/cache-info', methods=['GET'])
def api_activities_cache_info():
    profile = get_user_profile()
    cached_at = profile.activities_cache_at
    return jsonify({
        'cached_at': cached_at.strftime('%Y/%m/%d %H:%M') if cached_at else None,
        'valid': profile.is_activities_cache_valid(),
    })


@app.route('/api/activities/refresh', methods=['POST'])
def api_activities_refresh():
    if not _get_refresh_token():
        return jsonify({'error': '未授權'}), 401
    try:
        access_token = refresh_strava_token()
    except requests.HTTPError:
        return jsonify({'error': 'Token 刷新失敗'}), 401

    header = {'Authorization': f'Bearer {access_token}'}
    data = _fetch_activities_cached(header, force=True)
    if data is None:
        return jsonify({'error': '無法取得活動資料'}), 401

    profile = get_user_profile()
    cached_at = profile.activities_cache_at
    return jsonify({
        'ok': True,
        'count': len(data),
        'cached_at': cached_at.strftime('%Y/%m/%d %H:%M') if cached_at else None,
    })


@app.route('/')
def index():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    chart_data = {
        'labels': pmc['labels'][-42:],
        'ctl': pmc['ctl'][-42:],
        'atl': pmc['atl'][-42:],
        'tsb': pmc['tsb'][-42:],
    }
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    stats = _calc_weekly_stats(acts_raw, ftp, profile)
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'index.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        chart_data=chart_data,
        tsb_status=tsb_status,
        weekly_tss=stats['weekly_tss'],
        weekly_km=stats['weekly_km'],
        weekly_time=stats['weekly_time'],
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        target_race=_get_next_race(),
        active_tab='dashboard',
    )


@app.route('/partials/dashboard')
def partial_dashboard():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    chart_data = {
        'labels': pmc['labels'][-42:],
        'ctl': pmc['ctl'][-42:],
        'atl': pmc['atl'][-42:],
        'tsb': pmc['tsb'][-42:],
    }
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    stats = _calc_weekly_stats(acts_raw, ftp, profile)
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'partials/_content_dashboard.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=profile.weight_kg,
        pmc=pmc,
        chart_data=chart_data,
        tsb_status=tsb_status,
        weekly_tss=stats['weekly_tss'],
        weekly_km=stats['weekly_km'],
        weekly_time=stats['weekly_time'],
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        target_race=_get_next_race(),
    )
@app.route('/partials/analysis')
def partial_analysis():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    bike_acts_raw = [a for a in acts_raw if a.get('sport_type') in BIKE_SPORT_TYPES]
    activities = [enrich_activity(a, ftp) for a in bike_acts_raw]

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    chart_data = {
        'labels': pmc['labels'][-42:],
        'ctl': pmc['ctl'][-42:],
        'atl': pmc['atl'][-42:],
        'tsb': pmc['tsb'][-42:],
    }
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'partials/_content_analysis.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        activities=activities,
        pmc=pmc,
        chart_data=chart_data,
        tsb_status=tsb_status,
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
    )


@app.route('/partials/racing')
def partial_racing():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg
    bike_weight_kg = profile.bike_weight_kg
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    wuling = calc_wuling(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    wuling_subx = calc_wuling_subx(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    all_benchmarks = calc_all_routes_benchmark(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    used_timezones = _extract_used_timezones(acts_raw)
    upcoming_events = _get_upcoming_events()

    return render_template(
        'partials/_content_racing.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        wuling=wuling,
        wuling_subx=wuling_subx,
        all_benchmarks=all_benchmarks,
        upcoming_events=upcoming_events,
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
    )


@app.route('/partials/profile')
def partial_profile():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    return render_template(
        'partials/_content_profile.html',
        athlete=athlete,
        ftp=profile.ftp_watts,
        weight_kg=profile.weight_kg,
        bike_weight_kg=profile.bike_weight_kg,
        timezone=profile.timezone,
        used_timezones=[],
        all_timezones=pytz.all_timezones,
    )


@app.route('/api/export-for-ai')
def api_export_for_ai():
    import json as _json

    if not _get_refresh_token():
        return jsonify({'error': '未授權'}), 401

    profile = get_user_profile()

    if profile.is_export_cache_valid():
        resp = app.response_class(
            response=profile.export_cache,
            mimetype='application/json'
        )
        resp.headers['X-Cache'] = 'HIT'
        return resp

    try:
        access_token = refresh_strava_token()
    except requests.HTTPError:
        return jsonify({'error': 'Token 刷新失敗'}), 401

    header = {'Authorization': f'Bearer {access_token}'}

    import json as _json_inner
    if profile.is_athlete_cache_valid():
        athlete = _json_inner.loads(profile.athlete_cache)
    else:
        athlete_resp = requests.get("https://www.strava.com/api/v3/athlete", headers=header)
        athlete_resp.raise_for_status()
        athlete = athlete_resp.json()
        profile.athlete_cache = _json_inner.dumps(athlete, ensure_ascii=False)
        profile.athlete_cache_at = datetime.utcnow()
        db.session.commit()

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        return jsonify({'error': '無法取得活動資料'}), 401

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg

    bike_acts_raw = [a for a in acts_raw if a.get('sport_type') in BIKE_SPORT_TYPES]
    activities = [enrich_activity(a, ftp) for a in bike_acts_raw]

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    wuling = calc_wuling(ftp, weight_kg, pmc['current_tsb'])

    tz = pytz.timezone(profile.timezone)
    now_local = datetime.now(tz)
    week_start_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_start_utc = week_start_local.astimezone(timezone.utc).replace(tzinfo=None)
    this_week = [a for a in activities if a['utc_dt'] >= week_start_utc]

    weekly_tss = round(sum(a['tss'] for a in this_week if a['tss'] is not None), 1)
    weekly_km = round(sum(a['distance_km'] for a in this_week), 1)
    weekly_time = format_duration(sum(a['moving_time_sec'] for a in this_week))

    recent_activities = []
    for act in activities[:10]:
        recent_activities.append({
            'name': act['name'],
            'date': act['date_display'],
            'sport_type': act['sport_type'],
            'distance_km': act['distance_km'],
            'duration': act['duration'],
            'elevation_m': act['elevation_m'],
            'avg_speed_kmh': act['avg_speed_kmh'],
            'avg_watts': act['avg_watts'],
            'weighted_watts': act['weighted_watts'],
            'avg_hr': act['avg_hr'],
            'avg_cadence': act['avg_cadence'],
            'tss': act['tss'],
            'if_value': act['if_value'],
            'interpretation': act['interpretation'],
            'recovery_note': act['recovery_note'],
        })

    payload = {
        'athlete': {
            'name': f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip(),
            'ftp_watts': ftp,
            'weight_kg': weight_kg,
            'w_per_kg': round(ftp / weight_kg, 2) if weight_kg else None,
        },
        'current_fitness': {
            'ctl': pmc['current_ctl'],
            'atl': pmc['current_atl'],
            'tsb': pmc['current_tsb'],
            'status': tsb_status['label'],
        },
        'this_week': {
            'tss': weekly_tss,
            'distance_km': weekly_km,
            'time': weekly_time,
        },
        'wuling_prediction': {
            'current_time': wuling['current']['time_display'],
            'ideal_time': wuling['ideal']['time_display'],
            'delta_mins': wuling['delta_mins'],
        },
        'recent_activities': recent_activities,
        'generated_at': now_local.strftime('%Y-%m-%d %H:%M'),
    }

    cache_str = _json.dumps(payload, ensure_ascii=False)
    profile.export_cache = cache_str
    profile.export_cache_at = datetime.utcnow()
    db.session.commit()

    resp = app.response_class(response=cache_str, mimetype='application/json')
    resp.headers['X-Cache'] = 'MISS'
    return resp


@app.route('/analysis')
def analysis():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    bike_acts_raw = [a for a in acts_raw if a.get('sport_type') in BIKE_SPORT_TYPES]
    activities = [enrich_activity(a, ftp) for a in bike_acts_raw]

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    chart_data = {
        'labels': pmc['labels'][-42:],
        'ctl': pmc['ctl'][-42:],
        'atl': pmc['atl'][-42:],
        'tsb': pmc['tsb'][-42:],
    }
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'analysis.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        activities=activities,
        pmc=pmc,
        chart_data=chart_data,
        tsb_status=tsb_status,
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        active_tab='analysis',
    )


@app.route('/racing')
def racing():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg
    bike_weight_kg = profile.bike_weight_kg

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        _clear_refresh_token()
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    wuling = calc_wuling(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    wuling_subx = calc_wuling_subx(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    all_benchmarks = calc_all_routes_benchmark(ftp, weight_kg, pmc['current_tsb'], bike_weight_kg)
    used_timezones = _extract_used_timezones(acts_raw)
    upcoming_events = _get_upcoming_events()

    return render_template(
        'racing.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        wuling=wuling,
        wuling_subx=wuling_subx,
        all_benchmarks=all_benchmarks,
        upcoming_events=upcoming_events,
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        active_tab='racing',
    )


@app.route('/profile')
def profile_page():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    return render_template(
        'profile.html',
        athlete=athlete,
        ftp=profile.ftp_watts,
        weight_kg=profile.weight_kg,
        bike_weight_kg=profile.bike_weight_kg,
        timezone=profile.timezone,
        used_timezones=[],
        all_timezones=pytz.all_timezones,
        active_tab='profile',
    )


if __name__ == '__main__':
    app.run(debug=True, port=8000)
