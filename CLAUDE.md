# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

VeloData 是一個單車訓練數據監控工具，透過 Strava API v3 拉取活動資料，計算 TSS（Training Stress Score）並顯示在 Flask Web UI 上。

## 開發指令

```bash
# 啟動開發伺服器
source .venv/bin/activate && python app.py

# 安裝依賴
source .venv/bin/activate && pip install -r requirements.txt
```

## 環境設定

複製 `.env.example` 為 `.env`，填入三個必要變數：

```
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REFRESH_TOKEN=
```

Strava OAuth 使用 `refresh_token` grant type，每次請求前都需呼叫 `/oauth/token` 換取短效 `access_token`。

## 架構

- **`app.py`** — Flask 入口，包含 Strava token 刷新邏輯與路由。目前 `/` 路由每次都即時刷新 token 再打 API，適合原型但不適合高頻訪問。
- **`templates/index.html`** — Jinja2 模板，使用 Tailwind CSS CDN。顯示最近 5 筆騎乘的 `average_watts`。
- **`docs/introdoce.md`** — Strava API 核心參數規格（欄位、單位、型別）。
- **`docs/strava_swagger_api.json`** — Strava API v3 完整 OpenAPI 規格。

## Strava API 關鍵規則

- `elapsed_time` 必須為整數（秒）
- `distance` 必須為浮點數（公尺），公里輸入需乘以 1000
- Rate Limiting：需處理 429 狀態碼
- 401 Unauthorized：token 過期，需重新刷新
- 主要端點：`GET /athlete/activities`、`POST /activities`
