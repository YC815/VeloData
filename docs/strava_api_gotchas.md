# Strava API 踩坑紀錄

串接過程中遇到的「文件沒寫清楚但真的很重要」知識點。適合在寫新功能前、或出現奇怪 bug 時閱讀。

---

## 1. `average_watts` 不見了？因為沒有功率計

**症狀**：UI 的瓦數欄位空白。

**原因**：`average_watts` 和 `weighted_average_watts` 只在 `device_watts: true` 時才出現在 API 回應裡。`device_watts: true` 代表活動來自**實體功率計**（如 Garmin Vector、Favero Assioma）。虛擬訓練台（Wahoo、Tacx）有時也會帶這個值，但需確認。

如果運動員用的是沒有功率計的一般碼錶，這兩個欄位**完全不存在**於 JSON 中，不是 null 而是根本沒有這個 key。

**正確做法**：
```python
if act.get('device_watts') and act.get('average_watts'):
    watts = act['average_watts']
```

---

## 2. `start_date_local` 後面的 `Z` 是謊言

**症狀**：時間顯示正確但時區計算錯了 8 小時（或其他偏移量）。

**原因**：Strava 回傳的 `start_date_local` 格式長這樣：
```
"2024-01-15T08:30:00Z"
```

這個 `Z` 正常代表 UTC，**但這裡的 `start_date_local` 其實是運動員的本地時間**，`Z` 只是格式佔位符，沒有時區語意。

**兩個欄位對照**：

| 欄位 | 說明 |
|------|------|
| `start_date` | 真正的 UTC 時間，用於跨時區比較、週期計算 |
| `start_date_local` | 運動員本地時間，用於顯示給使用者看 |

**正確做法**：
```python
# 顯示用：strip Z，當作 naive datetime
local_dt = datetime.fromisoformat(act['start_date_local'].rstrip('Z'))

# 時間邊界比較（如本週）：用 start_date
utc_dt = datetime.fromisoformat(act['start_date'].rstrip('Z'))
```

---

## 3. TSS 計算要用 NP，不是 avg watts

**TSS 公式**：
```
TSS = (duration_sec × NP × IF) / (FTP × 3600) × 100
其中 IF = NP / FTP
    NP = Normalized Power = weighted_average_watts
```

**為什麼不用 `average_watts`**：平均功率包含零值（滑行、停紅燈），會低估訓練強度。NP 透過演算法去掉這些影響，更能代表生理負荷。

---

## 4. OAuth Scope 不足 — `GET /athlete/activities` 回 401

**症狀**：`/athlete` 正常，但 `/athlete/activities` 回 `401 Unauthorized`。

**原因**：這兩個端點需要不同 scope：

| 端點 | 需要的 scope |
|------|------------|
| `GET /athlete` | `read`（預設，不需特別設定）|
| `GET /athlete/activities` | `activity:read` 或 `activity:read_all` |

refresh token 是在授權時綁死 scope 的。如果當初授權沒帶 `activity:read`，之後刷出來的 access token 也永遠沒有這個權限。

**修復流程**（只需做一次）：

1. 用這個 URL 重新授權（注意 `scope=read,activity:read_all`）：
   ```
   https://www.strava.com/oauth/authorize
     ?client_id=YOUR_CLIENT_ID
     &redirect_uri=http://localhost/exchange_token
     &response_type=code
     &approval_prompt=force
     &scope=read,activity:read_all
   ```

2. 授權後跳轉到 localhost（會 404，正常），複製網址列的 `code=` 值。

3. 用 code 換 token：
   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=YOUR_CLIENT_ID \
     -d client_secret=YOUR_CLIENT_SECRET \
     -d code=PASTE_CODE_HERE \
     -d grant_type=authorization_code
   ```

4. 把回應中的 `refresh_token` 更新到 `.env`。

**重要**：`approval_prompt=force` 強制重新顯示授權畫面，否則 Strava 可能跳過並回傳舊的 refresh token（scope 不會更新）。

---

## 5. `SummaryActivity` vs `DetailedActivity` — 欄位不一樣

`GET /athlete/activities`（列表）回傳的是 **SummaryActivity**，缺少：
- `segment_efforts`（路段成績）
- `laps`（分圈）
- `splits_metric`（公里配速分析）
- `best_efforts`（最佳成績）

要拿完整資料需呼叫 `GET /activities/{id}`（回傳 DetailedActivity），但這會多用一個 API 請求。

**Rate Limit**：100 requests/15min，1000 requests/day。列表頁盡量用 `per_page=30` 減少分頁請求次數。

---

## 6. `suffer_score` 是 Strava 的替代壓力指標

當沒有功率計但有心率帶，可用 `suffer_score` 作為訓練壓力的替代顯示。這是 Strava 內部演算法，不等同於 TSS，但數值意義相近（高 = 壓力大）。

---

## 7. macOS + Flask port 5000 = 403（AirPlay 衝突）

**症狀**：Strava OAuth callback 跳回 `localhost:5000` 後顯示 HTTP 403，瀏覽器說「存取遭到拒絕」。

**原因**：macOS Monterey（12.0）之後，AirPlay Receiver 預設佔用 port 5000。Strava callback 打到的是 AirPlay service 而不是 Flask，AirPlay 回 403。

**解法**：Flask 改用其他 port（如 8000），`REDIRECT_URI` 跟著改。Strava 的 "Authorization Callback Domain" 只填 `localhost`（不含 port），不需要更新。

---

_文件更新日期：2026-04-29_
