# HTMX 導入後的已知問題與待修項目

本文件記錄 HTMX 局部換頁機制導入後，觀察到的技術問題與建議修法。
實作完成日期：2026-05-03

---

## 問題一：Chart.js 在 HTMX swap 後無法重新渲染

### 現象
`/partials/analysis` 被 HTMX swap 進 `#content` 後，`pmc_chart.js` 執行 `new Chart(ctx, ...)` 成功建立圖表。
但若使用者切到其他分頁再切回來，HTMX 會再次 swap，產生新的 `<canvas id="pmcChart">`，
此時 `pmc_chart.js` 再次執行，會在舊的 canvas（已不在 DOM 中）或新的 canvas 上重複建立 instance，
可能報錯：`Canvas is already in use. Chart with ID "0" must be destroyed before the canvas with ID "" can be reused.`

### 根本原因
`pmc_chart.js` 目前用模組頂層的 `new Chart(ctx, ...)` 直接初始化，沒有先 `destroy()` 舊的 instance。

### 建議修法
在 `pmc_chart.js` 改為：

```js
const existingChart = Chart.getChart('pmcChart');
if (existingChart) existingChart.destroy();

const ctx = document.getElementById('pmcChart').getContext('2d');
new Chart(ctx, { ... });
```

或監聽 HTMX 事件統一處理：

```js
document.body.addEventListener('htmx:afterSwap', (e) => {
  if (document.getElementById('pmcChart')) {
    initPmcChart(); // 抽成獨立函式
  }
});
```

---

## 問題二：每次切分頁仍重新呼叫 Strava API

### 現象
HTMX 只解決了「渲染」層的問題。每次點擊分頁按鈕，Flask 路由仍然會：
1. `refresh_strava_token()` — 打一次 OAuth token 刷新
2. `fetch_activities_90d()` — 抓 90 天 200+ 筆活動
3. 重算 PMC / TSS / Wuling

切換速度取決於 Strava API 回應時間（通常 500ms–2s），體感並非即時。

### 建議修法
在 Flask 加入 in-memory 快取（可用 `cachetools` 或簡易 dict），
將 `fetch_activities_90d()` 的結果快取 5 分鐘：

```python
from cachetools import TTLCache
_activity_cache = TTLCache(maxsize=10, ttl=300)

def fetch_activities_90d_cached(header, cache_key):
    if cache_key in _activity_cache:
        return _activity_cache[cache_key]
    data = fetch_activities_90d(header)
    _activity_cache[cache_key] = data
    return data
```

參考：`/api/export-for-ai` 已有 `export_cache` + `export_cache_at` 的快取邏輯，
可以用相同模式統一處理活動資料快取。

---

## 問題三：`settings.js` 在每個 partial 重複載入

### 現象
`_content_dashboard.html`、`_content_analysis.html` 等每個 partial 末尾都有：

```html
<script src="/static/js/settings.js"></script>
```

每次 HTMX swap 都會重新載入並執行這支 JS，`openSettings`、`closeSettings`、`saveSettings` 函式會被重複定義（覆蓋），理論上不會出錯，但是冗餘的網路請求與重複執行。

### 建議修法
將 `settings.js` 移到 `base.html` 的 `<head>` 或 `</body>` 前統一載入一次，從所有 partial 移除這行。

---

## 問題四：`copy_for_ai.js` 只在 dashboard partial 載入

### 現象
`copyForAI()` 函式由 `_header.html` 的按鈕呼叫，但函式定義在 `_content_dashboard.html` 尾端的 `copy_for_ai.js`。
當使用者切到其他分頁後，`#content` 被換掉，`copy_for_ai.js` 的 function scope 消失，
header 的「複製訓練摘要」按鈕會報 `ReferenceError: copyForAI is not defined`。

### 建議修法
將 `copy_for_ai.js` 與 `settings.js` 一起移到 `base.html` 統一載入。

---

## 問題五：`hx-push-url` 與直接輸入 URL 的初始分頁狀態不一致

### 現象
點擊分頁 → HTMX 換內容 → URL 更新為 `/analysis`（正確）。
但若使用者直接貼上 `/analysis` 重新整理，Flask 會走完整頁路由，渲染 `analysis.html extends base.html`，
nav 的 `active_tab` 會正確高亮（因為 Python 傳了 `active_tab='analysis'`）。
目前兩條路徑都能正確顯示，無功能性錯誤，只是維護兩套邏輯（full-page 路由 + partial 路由）。

### 現狀評估
目前為可接受狀態，不需立即修正。
長期可考慮合併邏輯：full-page 路由偵測 `HX-Request` header，有則只回 partial、無則回完整頁面：

```python
from flask import request as flask_request

@app.route('/analysis')
def analysis():
    # ... 計算邏輯 ...
    if flask_request.headers.get('HX-Request'):
        return render_template('partials/_content_analysis.html', ...)
    return render_template('analysis.html', ...)
```

這樣可以把 partial 路由與 full-page 路由合一，減少一半路由數量。
