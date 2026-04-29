# 專案說明：Strava API 自動化整合工具 (Project Introduction)

這份文件旨在為 AI 提供本專案的核心背景、技術規格與操作邏輯，以便於在開發過程中提供精準的協助。

## 1. 專案目標 (Project Objectives)

本專案的主要目標是透過 **Strava API v3** 建立一個自動化流程，用於管理、同步及分析運動員的活動數據。

- **自動化建立活動**：從外部資料源（如手錶數據、手動輸入）自動生成 Strava 活動。
- **數據整合**：確保活動類型、距離、時間等關鍵數據準確對齊 Strava 的標準。

## 2. 技術規格 (Technical Context)

- **API 來源**：[Strava API v3 Documentation](https://developers.strava.com/docs/reference/)
- **認證機制**：OAuth 2.0 (授權範圍需包含 `activity:write` 及 `activity:read_all`)
- **主要交互端點**：
  - `POST /activities`: 用於建立新手動活動。
  - `GET /athlete/activities`: 獲取活動清單進行比對。

## 3. 核心 API 結構參考 (Core Data Structure)

為了讓 AI 能精確生成程式碼，以下是我們最常用的 `Create Activity` 參數規範：

| 參數               | 說明     | 單位 / 格式                                         |
| :----------------- | :------- | :-------------------------------------------------- |
| `name`             | 活動標題 | 字串 (String)                                       |
| `sport_type`       | 運動類型 | 參考官方列舉值 (如 `Run`, `Ride`, `WeightTraining`) |
| `start_date_local` | 開始時間 | ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)                     |
| `elapsed_time`     | 持續時間 | 秒 (Seconds)                                        |
| `distance`         | 距離     | 公尺 (Meters)                                       |

## 4. 給 AI 的開發指令 (Instructions for AI)

當我詢問有關此專案的程式碼生成或除錯時，請遵循以下原則：

1.  **型別檢查**：確保 `elapsed_time` 為整數，`distance` 為浮點數。
2.  **錯誤處理**：優先考慮 Strava API 的 Rate Limiting (流量限制) 以及 401 Unauthorized 處理。
3.  **單位轉換**：如果輸入是公里 (km)，請務必在 API 請求前乘以 1000 轉換為公尺。
4.  **語言慣例**：預設使用專案慣用的語言環境（例如 Python/Node.js）進行示例編寫。

---

_文件更新日期：2026-04-29_
