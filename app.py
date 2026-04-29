import os
from flask import Flask, render_template
from dotenv import load_dotenv
import requests
import time

load_dotenv()
app = Flask(__name__)

# --- Token 管理邏輯 ---


def refresh_strava_token():
    url = "https://www.strava.com/oauth/token"
    payload = {
        'client_id': os.getenv('STRAVA_CLIENT_ID'),
        'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
        'refresh_token': os.getenv('STRAVA_REFRESH_TOKEN'),
        'grant_type': 'refresh_token'
    }
    response = requests.post(url, data=payload).json()
    return response['access_token']

# --- 主頁面路由 ---


@app.route('/')
def index():
    # 1. 取得最新門票
    access_token = refresh_strava_token()

    # 2. 取得運動員資料（頭像、姓名）
    header = {'Authorization': f'Bearer {access_token}'}
    athlete = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers=header
    ).json()

    # 3. 跟 Strava 要最近 5 筆活動
    activities = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers=header,
        params={'per_page': 5}
    ).json()

    return render_template('index.html', activities=activities, athlete=athlete)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
