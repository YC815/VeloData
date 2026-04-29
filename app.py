import os
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, redirect, request, url_for
from dotenv import load_dotenv, set_key, find_dotenv
import requests

load_dotenv()
app = Flask(__name__)

FTP = int(os.getenv('FTP_WATTS', 250))
DOTENV_PATH = find_dotenv() or os.path.join(os.path.dirname(__file__), '.env')

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
REDIRECT_URI = "http://localhost:8000/callback"


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
    # Strava may rotate the refresh token; keep .env in sync
    new_refresh = data.get('refresh_token')
    if new_refresh and new_refresh != os.getenv('STRAVA_REFRESH_TOKEN'):
        os.environ['STRAVA_REFRESH_TOKEN'] = new_refresh
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', new_refresh)
    return data['access_token']


def calc_tss(moving_time_sec, weighted_watts, ftp):
    if not weighted_watts or ftp <= 0:
        return None
    intensity_factor = weighted_watts / ftp
    return round((moving_time_sec * weighted_watts * intensity_factor) / (ftp * 3600) * 100, 1)


def format_duration(seconds):
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def enrich_activity(act):
    local_dt = datetime.fromisoformat(act.get('start_date_local', '1970-01-01T00:00:00Z').rstrip('Z'))
    utc_dt = datetime.fromisoformat(act.get('start_date', '1970-01-01T00:00:00Z').rstrip('Z'))

    tss = None
    if act.get('device_watts') and act.get('weighted_average_watts'):
        tss = calc_tss(act['moving_time'], act['weighted_average_watts'], FTP)

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
        'has_hr': bool(act.get('has_heartrate')),
        'avg_hr': round(act['average_heartrate']) if act.get('has_heartrate') and act.get('average_heartrate') else None,
        'suffer_score': act.get('suffer_score'),
        'tss': tss,
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


@app.route('/')
def index():
    if not os.getenv('STRAVA_REFRESH_TOKEN'):
        return redirect(url_for('auth'))

    try:
        access_token = refresh_strava_token()
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            # Refresh token revoked or scope changed — re-auth
            os.environ.pop('STRAVA_REFRESH_TOKEN', None)
            set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
            return redirect(url_for('auth'))
        raise

    header = {'Authorization': f'Bearer {access_token}'}

    athlete_resp = requests.get("https://www.strava.com/api/v3/athlete", headers=header)
    athlete_resp.raise_for_status()
    athlete = athlete_resp.json()

    acts_resp = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=header,
        params={'per_page': 30}
    )
    if acts_resp.status_code == 401:
        os.environ.pop('STRAVA_REFRESH_TOKEN', None)
        set_key(DOTENV_PATH, 'STRAVA_REFRESH_TOKEN', '')
        return redirect(url_for('auth'))
    acts_resp.raise_for_status()

    activities = [enrich_activity(a) for a in acts_resp.json()]

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    week_start = (now_utc - timedelta(days=now_utc.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    this_week = [a for a in activities if a['utc_dt'] >= week_start]

    weekly_tss = round(sum(a['tss'] for a in this_week if a['tss'] is not None), 1)
    weekly_km = round(sum(a['distance_km'] for a in this_week), 1)
    weekly_time = format_duration(sum(a['moving_time_sec'] for a in this_week))

    return render_template(
        'index.html',
        activities=activities[:5],
        athlete=athlete,
        ftp=FTP,
        weekly_tss=weekly_tss,
        weekly_km=weekly_km,
        weekly_time=weekly_time,
    )


if __name__ == '__main__':
    app.run(debug=True, port=8000)
