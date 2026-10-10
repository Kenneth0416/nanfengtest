# 後端架構（2026-10-10，只保留 Pi）

```
                ┌──────────────────────────────────────────────┐
  使用者  ───▶  │ ① 介面  app.py (Streamlit) · main.py (CLI/排程) │
                └───────────────┬──────────────────────────────┘
                                │ app.call(tool) / engine.ask()
                ┌───────────────▼──────────────────────────────┐
                │ ② Agent 引擎：只有 Pi Durable  core/engine.py │
                │     pi_engine/*.ts                            │
                │     Copilot agent · 信息處理 agent            │
                │     ⇅ HTTP bridge (core/bridge.py)            │
                └───────────────┬──────────────────────────────┘
                                │ 44 個工具
                ┌───────────────▼──────────────────────────────┐
                │ ③ Skills  skills/<name>/SKILL.md + tools.py   │
                │ ④ 參考 skills  info_skills/<name>/SKILL.md    │
                └───────┬───────────────────────┬──────────────┘
                        │                       │
     ┌──────────────────▼───────┐   ┌───────────▼──────────────┐
     │ ⑤ Core 服務 (core/*.py)  │   │ ⑥ LLM 提供者 core/llm.py │
     │ 抓取解析 · 分析 · 信號   │   │ MiMo / Anthropic / 離線  │
     └──────────┬───────────────┘   └──────────────────────────┘
                │
     ┌──────────▼───────────────┐   ┌──────────────────────────┐
     │ ⑦ 數據源 connectors/*.py │──▶│ ⑧ 存儲 SQLite (WAL)       │
     └──────────────────────────┘   │ core/store.py · 17 張表   │
                                    └──────────────────────────┘
        全部由 config.yaml 組裝（core/registry.py 讀取）
```

## 八類組件和數量

| # | 類別 | 數量 | 內容 |
|---|---|---|---|
| ① | 介面 / 入口 | 2 | `app.py`（網頁：Monitor、Ask Copilot、Team brief 含 Slides 面板（Build slides → Download .pptx）、Sources 含 🔵 Internal data 分頁）；`main.py`（9 個命令：refresh、gather、process、chat、ask、brief [--pptx --theme]、signals、ingest、classify，供 cron 排程用） |
| ② | Agent 引擎 | 1 套、2 個 agent | **Pi Durable**：`agent.ts`（Copilot）和 `info_agent.ts`（綜合信息處理），共用 `common.ts`。沒有後備引擎：Pi 未就緒時（缺 Node、套件或 key），Copilot、上傳和抓取會說明缺什麼；儀表板、信號、brief 和來源頁照常可用 |
| ③ | Skills（可調用工具） | 12 個 skill、52 個工具 | market_metrics 2、submarket_compare 2、supply_and_deals 2、macro_watch 1、news_monitor 2、watchlist_alerts 6、market_brief 1、brief_deck 3（brief 轉 PPT，故事線由數據決定而非固定模板：`brief_deck_data` 讀數據並回傳依本週變化排序的故事候選（越線的警示、最大變動、與長期平均的差距、新成交）、Copilot 從中挑 1–4 頁、每頁寫 why 進講稿；無模型時以 planner 規則挑選並在 UI 標示 fallback；`brief_deck_guide` 讀故事線／版式／風格說明與範例 spec、`build_brief_pptx` 用 python-pptx 把 spec 填進 5 套主題模板（13 個具名版式）出 3–6 頁；Copilot 寫主題、版式、標題、so-what 與講稿，數字不在數據中即拒絕，建檔後 check_deck 回報 problems 供其修正；設計包依 Grok Build 模板特點分析自家重寫，未複製任何模板，見 docs/brief-deck.md）、report_ingest 1、market_gather 12、info_processing 16（含 🔵 內部數據入口 `read_photo`、`save_internal_deal`、`deals_from_table`）、internal_data 4（🔵 `record_deal` 一句話成一筆、`list_our_deals`、`confirm_deal`、`set_deal_confidentiality`；見 docs/internal-data.md） |
| ④ | 參考 skills（給信息 agent 的操作手冊） | 9 | check-terms、fetch-source、dedupe、read-pdf、read-photo（🔵 照片、截圖、租約 PDF）、read-table、read-article、map-submarkets、check-figures。agent 用 `load_skill` 按需讀取 |
| ⑤ | Core 服務模組 | 21 | 見下表 |
| ⑥ | 模型調用（工具內） | 4 | Anthropic、OpenAI 兼容、Vision（MiMo-V2.6-Flash 讀 PDF 頁面）、無 key 時的規則版本。只供工具內的短調用（brief headline、分類、讀 PDF）；agent 循環在 Pi |
| ⑦ | 數據源 connectors | 4 | `seed_csv`（PoC 種子數據）、`boe_rates`（英倫銀行利率）、`news_rss`（新聞 RSS）、`followed`（同事新增並自動抓取的來源）。上傳報告則走 ③ 的工具 |
| ⑧ | 存儲 | 1 個庫、16 張表 | 數據：sources、observations、deals、pipeline、macro、news。團隊：watch_rules、feedback、user_focus、brief_items、team_log、checked。抓取流程：inbox、followed、staged、connector_status |

## Core 服務模組（21 個）

| 分組 | 模組 |
|---|---|
| 組裝和運行（4） | `app.py` 組裝、`registry.py` 按 config 載入、`skill.py` 工具定義、`bridge.py` Pi↔Python 橋 |
| Agent 和模型（3） | `engine.py`、`pi_engine.py`（啟動 Pi、系統提示）、`llm.py` ；Copilot 回答以串流呈現：agent.ts 用 pi-durable 的 watchEvents 把 text_delta 與工具啟動事件逐行輸出，pi_engine.py 以 Popen 逐行讀取，頁面用 st.write_stream 逐字顯示，並注入少量 JS 做「跟隨輸出、上捲即停、回底再跟」的捲動。身份不需登入：首次開啟的「Who's asking?」卡片選名字，瀏覽器以 cookie 記住（`st.context.cookies`），對話存在 SQLite 的 `chats`／`chat_messages`（依名字、含工具 trace，重新整理即恢復最近對話；History 續聊、New chat 另開），每個 chat 以自己的 id 作為 Pi 對話的 key（`PI_CONVERSATION_KEY`），新對話上下文乾淨；系統提示要求以提問語言作答（預設英文、中文問中文答）並以 `Follow up: a | b | c` 結尾，頁面把這一行轉成追問按鈕，預設建議問題只在空白新對話出現|
| 數據進入（6） | `ingest.py` 入庫、`classifier.py` 分類、`documents.py` PDF 解析與三項核對、`gather.py` 連結和 tip、`follow.py` 條款檢查和新增來源、`library.py` 更新時間和提醒 |
| 分析（6） | `analytics.py` 序列和出處、`signals.py` 信號排序、`summary.py` 三句市場總結、`coverage.py` 覆蓋缺口、`focus.py` 個人視圖、`taxonomy.py` 市場和指標詞表 |
| 模型和存儲（2） | `models.py` 數據類、`store.py` SQLite |

## 怎樣插拔

- **新增能力**：在 `skills/` 新增資料夾（SKILL.md + tools.py），再在 `config.yaml` 的 `skills:` 列出。core 不用改。
- **新增數據源**：在 `connectors/` 新增模組，再在 `connectors:` 列出；或由同事在介面「Follow a new source」新增，不用寫代碼。
- **換模型**：修改 `llm.provider` 和 `vision`。
- **Pi 負責思考，Python 負責工具**：Pi 透過 bridge 的 manifest 取得 44 個工具和 8 套參考 skills，工具在 Python 執行，數字一律來自數據庫。
- **部署**：在 VPS 上運行 Streamlit 加 cron 執行 `main.py refresh / gather`。SQLite 使用 WAL，網頁和排程可以同時讀寫。
