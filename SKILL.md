---
name: content-schedule
description: 內容地圖的「上架管理 / 編輯行事曆」——品牌無關。當要決定文章上架時間、把能立即見效的文章往前排、排程上站(CMS future)、重平衡發佈節奏、或與其他上稿來源共用同一張行事曆避免撞期時使用。每完稿一篇就做「重要性檢視→排期」。輸入＝內容地圖 Google Sheet，輸出＝CMS 排程(future)＋回寫地圖狀態。CMS 以 WordPress 為參考實作，可替換。
---

# 內容地圖上架管理（編輯行事曆 / 排程上站）

`content-pipeline` 產出草稿之後的「**排程上站**」決策層。
原則：**每完稿一篇 → 按重要性評分 → 能立即見效的往前排 → 設成 CMS 排程(future) → 回寫內容地圖**。和任何其他上稿來源**共用同一張行事曆**（內容地圖的「排程」欄），絕不雙開清單、不撞期。

## 唯一行事曆 = 內容地圖 Google Sheet
- 由上游 **content-map-builder** 維護的那張表（用 `--sheet-id` 指定，或設 `CONTENT_MAP_SHEET_ID`）。
- 預設欄位對應（見 `scripts/schedule.py` 頂端 `COL`，**要對齊你的表**）：
  A 叢集 / B 關鍵字 / C 角色 / D 狀態 / E 線上連結或 post id / … Q 漏斗階段 / R 轉換目標 / T 曝光(GSC) / U 點擊(GSC) / **W 排程時間** / X 後台編輯連結。
- **「排程」欄＝共用排程槽**：所有上稿來源都先讀它（＋ CMS 既有 future 貼文）看哪些時段被占，再排新的、不重複。

## 何時用
- **完稿一篇就跑一次**（評分＋排期）。
- 想**重平衡**整張行事曆（有更重要的新文要插隊）。
- 例行：把所有「草稿/可發、尚未排程」的列補上上架時間。

## 重要性評分 rubric（0–100，全部從地圖欄位算；可在 `schedule.py` CONFIG 調權重/關鍵字）
| 訊號 | 來源欄 | 加權 |
|---|---|---|
| 角色 | C/A | 核心保衛 +35、藍海卡位 +28、側翼擴張 +22、長尾/supporting +12 |
| 漏斗階段（立即見效） | Q | BOFU/轉換/決策 +25、MOFU/評估/比較 +18、TOFU/認知 +8 |
| 搜尋機會（快贏） | T,U | +min(20, 曝光/80)；曝光≥200 且 CTR<2% 再 +10 |
| 有轉換目標 | R | 非空 +6 |
| 決策意圖關鍵字 | B | 含 vs/比較/費用/挑選/避雷/推薦/compare/best… +10 |
| 時效題 | B | 含 AI/缺工/自動化/AEO/Agent/automation +6 |

→ **P0 ≥70｜P1 55–69｜P2 40–54｜P3 <40**

> 「立即見效」＝離成交近（BOFU/決策比較）、守核心關鍵字、對打競品、補漏斗缺口。藍海卡位重要但搜尋量還小 → 通常 P1（搶先機但不急）。supporting/機器文 → backlog。

## 優先級 → 排期
- **P0**：插到最近的空槽（可排到最前）。**P1**：數天內前段空槽。**P2**：一般節奏排隊。**P3**：backlog。
- 排法：「待排」清單依分數**由高到低**塞進最早的空槽 → 重要的自然往前。

## 上架節奏（cadence）
- 預設 **1 篇/工作天、09:00**（`--per-day 2` → 09:00 & 15:00；`--start` 起排日；`--skip-weekends`）。
- 已占用槽 = 地圖排程欄已填 ＋ CMS 既有 `status=future` → 新排程一律跳過已占用槽。

## 與其他上稿來源協作（共用一張行事曆）
- 約定：其他來源（人工、另一支自動化）**只把狀態推到「可發/審核通過」就停、不直接發布**；本 skill 是**唯一**寫「排程」欄＋設 CMS 排程的一方 → 天生單一行事曆、不撞期。
- 萬一對方真的占了某槽，本 skill 讀「排程」欄與 CMS future 時會視為**已占用、跳過**，仍安全。

## 流程（每篇 / 批次都一樣）
1. **讀地圖** → 算每列重要性分數。
2. `--plan`：列出「待排」（狀態含草稿/可發、且排程欄空）依分數+節奏指派日期，**印出行事曆、不寫**。先看一眼。
3. `--apply`：執行 → 對每篇 `POST /wp/v2/posts/{id} {status:future, date}`；回寫地圖 狀態=已排程、排程欄=時間、編輯連結。
4. 到點 CMS 自動上線；事後用 GSC/GA4 回拉成效（曝光/點擊/轉換），作為下一輪重排依據（見 content-pipeline 的 backfill）。

## 指令
```bash
PY=python3   # 需 google-api-python-client（讀寫 Sheet）
SHEET=<你的內容地圖 sheet id>;  BASE=https://<your-site>/wp-json;  SITE=https://<your-site>

# 看現況＋分數（不動任何東西）
$PY scripts/schedule.py --list --sheet-id "$SHEET"
# 規劃排程（印行事曆、不寫）
$PY scripts/schedule.py --plan --sheet-id "$SHEET" --start 2026-06-13 --per-day 1
# 執行排程（寫 CMS future + 回寫地圖）— 要 CMS 憑證
WP_USER=<帳號> WP_APP_PW='<應用程式密碼>' \
  $PY scripts/schedule.py --apply --sheet-id "$SHEET" --base "$BASE" --site "$SITE" --start 2026-06-13 --per-day 1
# 單篇插隊到指定時間（完稿即排）
WP_USER=<帳號> WP_APP_PW='<密碼>' \
  $PY scripts/schedule.py --post 1234 --date 2026-06-13T09:00:00 --sheet-id "$SHEET" --base "$BASE" --site "$SITE"
```
憑證：Google OAuth token（spreadsheets 範圍，`--token` 或 `GOOGLE_TOKEN`，預設 `~/.config/google/token.json`）；CMS `WP_USER`/`WP_APP_PW` 走環境變數、**不寫檔**。API 帶瀏覽器 UA（避 CDN/WAF 1010）。

## 鐵則
- **單一行事曆**（地圖排程欄）：所有來源共用，不各開清單。
- **不撞槽**：排前先讀已占用（排程欄 ＋ CMS future）。
- **重要的先上**：BOFU/核心防守/競品對打/漏斗缺口優先插隊；藍海次之；supporting/機器文走 backlog。
- **不繞品質閘門**：要排的文必須已過 content-pipeline 的對抗式事實查核（與易讀性）。沒過 → 退回修，不排。
- **回寫即同步**：排完立刻把 狀態/排程欄/編輯連結 寫回地圖，其他來源才看得到最新行事曆。
- 欄位對應（`COL`）與 `--sheet-id` 必須對齊你的內容地圖（建議直接沿用 content-map-builder 模板的欄序）。
