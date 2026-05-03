import os
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, redirect, request, url_for, jsonify
from dotenv import load_dotenv, set_key, find_dotenv
import requests
import pytz

from db import db, UserProfile, init_db
from wuling_engine import WulingPredictor, ROUTE_DISTANCE_KM

load_dotenv()
app = Flask(__name__)
init_db(app)

DOTENV_PATH = find_dotenv() or os.path.join(os.path.dirname(__file__), '.env')

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = "http://localhost:8000/callback"

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


def refresh_strava_token():
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'refresh_token': os.getenv('STRAVA_REFRESH_TOKEN'),
            'grant_type': 'refresh_token'
        }
    )
    resp.raise_for_status()
    data = resp.json()
    new_refresh = data.get('refresh_token')
    if new_refresh and new_refresh != os.getenv('STRAVA_REFRESH_TOKEN'):
        os.environ['STRAVA_REFRESH_TOKEN'] = new_refresh
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', new_refresh)
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


_activity_cache: list | None = None
_activity_cache_at: datetime | None = None
_ACTIVITY_CACHE_TTL = 300  # 5 分鐘


def _fetch_activities_cached(header: dict) -> list | None:
    global _activity_cache, _activity_cache_at
    now = datetime.now()
    if (
        _activity_cache is not None
        and _activity_cache_at is not None
        and (now - _activity_cache_at).total_seconds() < _ACTIVITY_CACHE_TTL
    ):
        return _activity_cache
    data = fetch_activities_90d(header)
    if data is not None:
        _activity_cache = data
        _activity_cache_at = now
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


def calc_wuling(ftp, weight_kg, tsb):
    if not weight_kg:
        empty = {'time_display': '—', 'speed_kmh': None, 'sub_three': False, 'tsb': None}
        return {'current': empty, 'ideal': empty, 'delta_mins': 0}
    total_mass = weight_kg + 8
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


def calc_ftp_progress(ftp, weight_kg):
    target = 300
    progress_pct = min(round(ftp / target * 100), 100)
    w_per_kg = round(ftp / weight_kg, 2) if weight_kg else None
    return {'current': ftp, 'target': target, 'progress_pct': progress_pct, 'w_per_kg': w_per_kg}


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
    if not os.getenv('STRAVA_REFRESH_TOKEN'):
        return None, None, None, redirect(url_for('auth'))
    try:
        access_token = refresh_strava_token()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            os.environ.pop('STRAVA_REFRESH_TOKEN', None)
            set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
            return None, None, None, redirect(url_for('auth'))
        raise
    header = {'Authorization': f'Bearer {access_token}'}
    athlete_resp = requests.get("https://www.strava.com/api/v3/athlete", headers=header)
    athlete_resp.raise_for_status()
    return header, athlete_resp.json(), get_user_profile(), None


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

    os.environ['STRAVA_REFRESH_TOKEN'] = refresh_token
    set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', refresh_token)

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

    tz_str = data.get('timezone')
    if tz_str is not None:
        try:
            pytz.timezone(tz_str)
            profile.timezone = tz_str
        except pytz.UnknownTimeZoneError:
            return jsonify({'error': f'不支援的時區：{tz_str}'}), 400

    db.session.commit()
    return jsonify(profile.to_dict())


@app.route('/')
def index():
    header, athlete, profile, redir = _require_strava()
    if redir:
        return redir

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    stats = _calc_weekly_stats(acts_raw, ftp, profile)
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'index.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        weekly_tss=stats['weekly_tss'],
        weekly_km=stats['weekly_km'],
        weekly_time=stats['weekly_time'],
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        target_race=None,
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
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    stats = _calc_weekly_stats(acts_raw, ftp, profile)
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'partials/_content_dashboard.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=profile.weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        weekly_tss=stats['weekly_tss'],
        weekly_km=stats['weekly_km'],
        weekly_time=stats['weekly_time'],
        timezone=profile.timezone,
        used_timezones=used_timezones,
        all_timezones=pytz.all_timezones,
        target_race=None,
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
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
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
    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    ftp_progress = calc_ftp_progress(ftp, weight_kg)
    wuling = calc_wuling(ftp, weight_kg, pmc['current_tsb'])
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'partials/_content_racing.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        ftp_progress=ftp_progress,
        wuling=wuling,
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
        timezone=profile.timezone,
        used_timezones=[],
        all_timezones=pytz.all_timezones,
    )


@app.route('/api/export-for-ai')
def api_export_for_ai():
    import json as _json

    if not os.getenv('STRAVA_REFRESH_TOKEN'):
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

    athlete_resp = requests.get("https://www.strava.com/api/v3/athlete", headers=header)
    athlete_resp.raise_for_status()
    athlete = athlete_resp.json()

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        return jsonify({'error': '無法取得活動資料'}), 401

    ftp = profile.ftp_watts
    weight_kg = profile.weight_kg

    bike_acts_raw = [a for a in acts_raw if a.get('sport_type') in BIKE_SPORT_TYPES]
    activities = [enrich_activity(a, ftp) for a in bike_acts_raw]

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    ftp_progress = calc_ftp_progress(ftp, weight_kg)
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
            'w_per_kg': ftp_progress['w_per_kg'],
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
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
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

    acts_raw = _fetch_activities_cached(header)
    if acts_raw is None:
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
        return redirect(url_for('auth'))

    pmc = calc_pmc(acts_raw, ftp, profile.timezone)
    tsb_status = calc_tsb_status(pmc['current_tsb'])
    ftp_progress = calc_ftp_progress(ftp, weight_kg)
    wuling = calc_wuling(ftp, weight_kg, pmc['current_tsb'])
    used_timezones = _extract_used_timezones(acts_raw)

    return render_template(
        'racing.html',
        athlete=athlete,
        ftp=ftp,
        weight_kg=weight_kg,
        pmc=pmc,
        tsb_status=tsb_status,
        ftp_progress=ftp_progress,
        wuling=wuling,
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
        timezone=profile.timezone,
        used_timezones=[],
        all_timezones=pytz.all_timezones,
        active_tab='profile',
    )


if __name__ == '__main__':
    app.run(debug=True, port=8000)
