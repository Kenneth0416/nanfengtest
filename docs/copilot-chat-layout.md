# Copilot 對話版面規格：參照 ChatGPT

2026-10-11 · 研究 thread 產出，只做研究與規格，不改 PoC 與原型。
實作分工：PoC（`london-office-agent/app.py`）由「閱讀面試測試要求」thread 改；原型（`prototype/index.html`）由「Agent 原型設計」thread 改。

示意圖：[screenshots/copilot-chat-layout.png](screenshots/copilot-chat-layout.png)（桌面整頁、側邊面板、手機三種版面，標出固定與捲動區）。

---

## 1. 一句話結論

ChatGPT 的版面是「**三段式**」：頂欄固定在上、輸入框固定在下、中間只有一條置中、限寬約 768px 的對話欄在捲動。其餘東西（歷史、設定、身份）全收進左側欄或選單，對話欄裡除了訊息本身幾乎沒有任何框線、頭像或大按鈕。PoC 目前最大的差距是：對話欄沒有限寬（寬螢幕一行超過 150 字）、頁首和控制列跟著內容捲走、兩邊都有頭像而且都靠左、Stop 鍵和輸入框分開、每則回答沒有複製／重試／讚踩的操作列。

---

## 2. ChatGPT 版面拆解（桌面，≥ 1024px）

依據標記：**［來源］** 有公開資料可查（見文末）；**［觀察］** 來自產品的公開截圖與日常使用，OpenAI 經常調整，細節以當下產品為準。此 thread 的雲端環境連不上 chatgpt.com（回 403），無法現場量 DOM，所以尺寸取自公開的 class 拆解與 ChatGPT 仿製範例。

| 區域 | 固定／捲動 | 位置 | 怎麼顯示 |
|---|---|---|---|
| 左側欄 | **固定**（整欄高 100vh，內部清單自己捲動） | 左，約 260px | 上段固定：收合鍵、New chat（筆形圖示）、Search chats、Library／GPTs／Projects。中段捲動：對話列表，最近的在最上，滑過某一條才出現「…」（重新命名、分享、封存、刪除）。下段固定：頭像＋名字＋方案。收合後變成約 52px 的圖示列（只剩展開、新對話、搜尋）。［來源：側欄指南、教學］［觀察］ |
| 頂欄 | **固定**（sticky top，高約 52–56px） | 對話區最上方，橫跨整個主區（不是只有 768px） | 左：模型選擇下拉（「ChatGPT 5 ⌄」）。右：**Share**（有訊息才出現）、「…」選單；新對話時右上角出現「Temporary」膠囊。背景與頁面同色、沒有邊線，往下捲後才有一條細陰影。［來源：Temporary chat 說明］［觀察］ |
| 對話欄 | **捲動**（整個主區捲，不是內嵌小框） | 置中，`max-width` 隨視窗：md 768px（max-w-3xl）、lg 640px、xl 768px（48rem），左右留 16–24px | 訊息之間間距約 32px（gap-8）。頂部留白約 64px（pt-16）給頂欄。［來源：社群貼文引述 class、assistant-ui 仿製］ |
| 用戶訊息 | 捲動 | **靠右** | 淺灰圓角泡泡（圓角約 22px，內距 16×10px），最寬 70% 欄寬，**沒有頭像**。滑過才在泡泡下方出現「複製」「編輯」小圖示。［來源：assistant-ui 仿製］［觀察］ |
| 助理訊息 | 捲動 | **靠左，佔滿欄寬** | **沒有泡泡、沒有框、沒有頭像**，就是排版好的文字。16px、行高約 1.6–1.75。Markdown：標題、清單、表格（過寬時表格自己橫向捲）、程式碼區塊（深色或灰底，上方一條語言名＋Copy 的標頭）。網頁搜尋的引用是行內小膠囊（網站名），末尾一顆「Sources」鍵打開右側來源面板。推理模型在答案上方有可展開的一行「Thought for 12s」。［觀察］ |
| 回答操作列 | 捲動（跟著那則回答） | 回答正下方，左對齊、與文字左緣對齊（-8px） | 32px 圖示鍵、無邊框、滑過才有淺灰底：複製、讚、踩、朗讀、分享、重新生成（可換模型）、「…」（另開分支）。**最新一則一直顯示，較舊的滑過才顯示**；生成中隱藏。［來源：assistant-ui 仿製 `hideWhenRunning`］［觀察］ |
| 串流中 | 捲動 | 最新回答位置 | 第一個字出來之前是一個脈動的圓點；字出來後尾端有游標點。工具或搜尋時有一行灰色狀態字（「Searching the web」）。［觀察］ |
| 輸入框 | **固定**（sticky bottom） | 置中，與對話欄**同寬**；距底約 8–16px | 大圓角（約 28px）白底細邊框，內距 8px。左：「＋」（附件與工具選單）。中：多行文字框，1 行起，自動長高到約視窗 1/4 後內部捲動。右：無文字時是麥克風＋語音模式鍵；有文字時變黑色圓形「↑」送出鍵；**生成中同一位置變成黑色方形「停止」**。送出後清空並縮回一行。可把檔案拖進整個視窗。［來源：assistant-ui 仿製、aiuxplayground］ |
| 免責小字 | 固定（跟輸入框一起） | 輸入框正下方、置中 | 約 12px 灰字：「ChatGPT can make mistakes. Check important info.」［來源：assistant-ui 仿製］ |
| 「捲到最新」鍵 | **浮動** | 輸入框正上方約 40px、水平置中 | 白底圓形 ↓ 鍵帶細邊；只在沒貼底時出現。［來源：assistant-ui 仿製 `ThreadScrollToBottom`］ |
| 空白狀態 | 只在新對話 | 垂直置中偏上（pb 16vh） | 一句問候大字（約 24–28px，例如「What can I help with?」或帶名字的問候），**輸入框就放在問候下面、畫面中間**；有些版本下面再一排建議膠囊。送出第一句後輸入框移到底部，問候消失。［來源：assistant-ui 仿製］［觀察］ |
| 捲動行為 | — | — | 送出新問題時，那則問題被捲到靠近頂部，下方留空讓答案往下長；用戶往上捲就不再自動跟。［觀察，社群有相關 bug 回報］ |

### 手機版（< 768px）

| 區域 | 固定／捲動 | 怎麼顯示 |
|---|---|---|
| 頂欄 | 固定 | 左：兩橫線選單鍵（打開側欄抽屜）。中：模型名／對話標題。右：新對話（筆形）圖示。 |
| 側欄 | 抽屜 | 從左滑出蓋住內容，點外面關閉。 |
| 對話欄 | 捲動 | 全寬，左右 16px；用戶泡泡仍靠右、最寬約 85%。 |
| 操作列 | 捲動 | 觸控沒有 hover，最新回答的操作列一直顯示；舊訊息長按出選單。 |
| 輸入框 | 固定 | 貼底，加 `env(safe-area-inset-bottom)`；鍵盤彈出時跟著鍵盤上移。免責小字通常省略或更小。 |

---

## 3. 現況對照與差距

### 3.1 PoC Copilot 整頁（`app.py` `copilot_page` / `copilot_body`，截圖 `docs/screenshots/copilot*.png`）

| 項目 | PoC 現況 | ChatGPT | 差距與優先度 |
|---|---|---|---|
| 對話欄寬度 | `layout="wide"`，訊息與輸入框撐滿主區（1400px 視窗約 940px，1920px 約 1500px） | 置中 768px | **P0**：長文難讀，是最明顯的差距 |
| 頁首 | 大標「Ask Copilot」＋副標＋「Set up my focus」，再一列「Looking at / 名字 / History / New chat」四個大按鈕，**全部跟著捲走** | 52px 固定頂欄，只放少量圖示鍵 | **P0**：捲下去就找不到 New chat、History |
| Streamlit 工具列 | 右上「Deploy」「⋮」和跑步小人 | 無 | P1：與產品無關的東西 |
| 用戶訊息 | `st.chat_message("user")` 紅色頭像、靠左、灰底整列 | 靠右泡泡、無頭像 | **P0** |
| 助理訊息 | 橘色機器人頭像、靠左 | 無頭像、無框 | **P0** |
| 回答操作 | 只有每則都常駐的「Share to team」popover；沒有複製、重試、讚踩 | 一列小圖示，最新常駐、舊的 hover | **P1** |
| 工作過程 | `st.status`「How I worked this out」框在答案**上方**，另有「Tools used:」灰字在最下 | 一行可展開的「Thought for…」 | P1：合併成一行，Tools used 收進去 |
| 停止鍵 | 狀態框下方獨立一顆 tertiary「Stop」 | 輸入框送出鍵原位變停止 | **P1** |
| 輸入框 | Streamlit 預設固定在底（好），但 placeholder 塞了「Enter sends, Shift+Enter…」 | 短 placeholder；提示放下方小字 | P1 |
| 免責小字 | 無 | 有 | P1：我們的版本可寫「每個數字都附來源；⚠️ 標記的要再核對」 |
| 空白狀態 | 一段左對齊說明＋四顆全寬灰框按鈕；頁首和控制列照樣佔位 | 置中問候＋輸入框在中間＋建議膠囊 | **P1** |
| 追問建議 | 「FOLLOW UP」標題＋等寬三欄全寬按鈕 | 左對齊膠囊（如有） | P2 |
| 捲到最新 | 已有跟隨捲動＋「↓ Latest」膠囊（好） | 圓形 ↓、在輸入框正上方置中 | P2：只調位置與樣式 |
| 身份 | 頁內「Kenneth ⌄」popover，與側欄的「Your name」重複 | 身份在側欄底部 | P2：拿掉頁內那顆 |

### 3.2 PoC 側邊面板（`st.dialog` position=right，CSS 註解寫 752px）

| 項目 | 現況 | 建議 |
|---|---|---|
| 寬度 | `width="medium"`（約 750px），蓋住大半頁 | 改 `width="small"`（約 500px）；`.st-key-fab_close` 的 `right` 隨之改為 520px。原型定 420px，Streamlit 最接近的是 small |
| 頂部 | 對話框標題「💬 Copilot」大字＋×，下一列四顆大按鈕 | 一列 48px：左「Copilot」16px 粗體＋名字小灰字；右三顆 32px 圖示鍵（History 時鐘、New chat 加號、×）。下一行是「Looking at: Monitor」情境膠囊（可 × 掉） |
| 訊息 | 同整頁，有頭像 | 同整頁規格；面板內字級 14–15px，用戶泡泡最寬 85% |
| 輸入框 | 已 sticky 在面板底（好） | 加送出↔停止同位、下方一行提示小字 |

### 3.3 原型（`prototype/index.html` 的 `.cp` 面板）

原型已經做對的：用戶訊息靠右深色泡泡、助理無頭像、輸入框固定在面板底並自動長高（最高 160px）、生成中「Ask」變「Stop」、游標閃爍、「Jump to latest」、預設問題只在新對話出現、標頭有 History／New chat 圖示鍵。

差距：

| 項目 | 現況 | 建議 |
|---|---|---|
| 助理訊息 | 白底卡片＋邊框（`.msg-a`） | 去掉卡片和邊框，直接排文字；來源行保留上方細線 |
| 操作列 | 只有「Was this useful? 👍👎」放在來源行裡，沒有複製、重試 | 改成第 4 節的操作列 |
| 送出鍵 | 文字鍵「Ask」，`--r` 6px 方角輸入框 | 32px 圓形「↑」圖示鍵，停止時同位方形；輸入框圓角 12px（設計 token 唯一例外，見 4.1） |
| 空白狀態 | 一張「Hi Kenneth…」卡片當第一則回答 | 改為面板中間的問候文字＋建議膠囊，不是一則訊息 |
| 「Jump to latest」 | 有文字的膠囊 | 圓形 ↓（可保留 tooltip 文字） |

---

## 4. 目標規格（PoC 與原型共用）

### 4.1 版面骨架

```
┌ 側欄 236px（已存在，固定）┬──────────── 主區 ────────────────────────────┐
│ Logo / 名字 / 導航        │ 頂欄 56px  sticky top:0  z 20                 │
│                           │  左 Copilot · [Looking at: Monitor ×]         │
│                           │  右 [🕘 History] [＋ New chat]                 │
│                           ├───────────────────────────────────────────────┤
│                           │   對話欄  max-width 760px  置中  捲動         │
│                           │     （用戶泡泡靠右 / 助理全寬無框）           │
│                           │                     ( ↓ ) 浮動，置中          │
│                           ├───────────────────────────────────────────────┤
│                           │ 輸入框 max-width 760px  sticky bottom  z 20   │
│                           │ 提示小字 12px 置中                            │
└───────────────────────────┴───────────────────────────────────────────────┘
```

| 名稱 | 值 | 備註 |
|---|---|---|
| `--chat-w` | 760px | 對話欄與輸入框同寬；1024px 以下改 100% 減左右 16px |
| 頂欄高 | 56px | 背景 `--bg`，往下捲後加 `box-shadow:0 1px 0 var(--line)` |
| 訊息間距 | 28px（同一輪問答之間 12px） | |
| 用戶泡泡 | 背景 `--sunk`，字色 `--ink`，圓角 18px，內距 10px 16px，最寬 75%（面板 85%） | 原型現用 `--ink` 深色泡泡，二選一；建議改淺色 `--sunk`，讓答案才是視覺重心，跟 ChatGPT 一致 |
| 助理文字 | 16px／行高 1.65（面板 15px），段落上限 70ch | 無框、無頭像 |
| 輸入框 | 白底，1px `--line`，圓角 **12px**，內距 8px，陰影 `0 2px 12px rgba(15,26,42,.06)`；聚焦時邊框 `--accent` | 圓角是 design-tokens 的 `--r:6px` 之外唯一例外，寫進 design-tokens.md |
| 送出鍵 | 32px 圓形，`--accent` 底白色「↑」；無文字時 `--sunk` 底灰色、disabled | 生成中同位換成 32px 圓形 `--ink` 底白色「■」 |
| 文字框 | 1 行起，最高 200px（面板 160px），超過內部捲動；Enter 送出、Shift+Enter 換行；送出後清空縮回 | |
| 提示小字 | 12px `--ink3` 置中，在輸入框下 6px | 文字：「Copilot can be wrong. Every number links to its source; check the ones marked ⚠.」右側可附快捷鍵「/ to focus · Ctrl+K」 |
| 捲到最新 | 32px 白底圓形 ↓，1px `--line`，陰影，輸入框上緣上方 12px、水平置中 | 貼底（距底 < 48px）時隱藏 |

### 4.2 一則回答的結構（由上而下）

1. **工作過程一行**（可展開）：生成中「Working: reading this week's signals…」配轉圈；完成後收成「Worked through 3 steps ›」灰字，展開看工具清單（原來的「Tools used」併入這裡）。
2. **答案文字**：Markdown；表格過寬時表格本身橫向捲；`[1]` 這類腳註保留。
3. **圖表／下載鍵**：照現在的順序。
4. **來源列**：上方 1px 細線，「Sources」小字＋來源膠囊（綠點自動、橘點上傳、藍點內部，沿用現有 chip）。這是我們比 ChatGPT 多的部分，保留。
5. **操作列**：32px 無框圖示鍵，間距 2px，與文字左緣對齊：
   - 複製（copy）· 讚（thumbs-up）· 踩（thumbs-down）· 重新回答（refresh-cw）· 分享給團隊（share-2，打開原本的 Share to team 小框；已分享則顯示「Shared · 撤回」小字）。
   - 最新一則常駐；較舊的滑過整則訊息才顯示；觸控裝置（`@media (hover:none)`）全部常駐。
   - 生成中整列隱藏。
6. **追問膠囊**：只在**最新一則**下方，左對齊，圓角 999px，1px `--line`，13.5px；不要等寬三欄、不要「FOLLOW UP」大寫標題（可留 12px 灰字「Follow up」）。

用戶訊息：泡泡靠右；滑過時泡泡下方右側出現「複製」一顆（編輯重送列為 P2）。

### 4.3 空白狀態（新對話、尚無訊息）

- 對話欄內垂直置中：一行 24px 問候「Hi Kenneth. What do you want to know about London offices?」，下一行 15px `--ink2` 說明「I can see what's on your screen, and every number comes with its source.」
- 下方 2×2 建議膠囊（依頁面情境，沿用 `PAGE_SUGGESTIONS`）。
- PoC 的輸入框是 Streamlit 固定在底的 `st.chat_input`，無法像 ChatGPT 移到中間；保留在底部即可，問候與膠囊放在上方空間置中。原型可以做到「輸入框在中間、送出後移到底」，但不是必要。
- 頂欄照常顯示；「Set up my focus」從頁首移到建議膠囊的第一顆（「Set up my focus」帶 sparkles 圖示）。

### 4.4 頂欄內容

| 位置 | 整頁 | 側邊面板 |
|---|---|---|
| 左 | 「Copilot」16px 粗體 ＋ 情境膠囊「Looking at: Copilot / About: 某信號 ×」 | 「Copilot」＋名字 12px 灰字；情境膠囊在第二行 |
| 右 | History（clock 圖示＋字，點開下拉清單）、New chat（plus 圖示＋字）、對話中再加 Share to team（分享整段，P2） | 三顆 32px 圖示鍵：History、New chat、× |

身份：整頁不再放名字 popover，側欄已有「Your name」；面板保留小字名字＋「change」連結。

### 4.5 捲動

- 送出新問題：貼底並開始跟隨（現有 FOLLOW_CORE 行為），不改成 ChatGPT「問題頂到上方」那種，因為現有的跟隨已經運作且有截圖驗證。
- 用戶往上捲 > 48px：停止跟隨，顯示 ↓ 鍵；按下或再送出問題恢復跟隨（現有邏輯保留，只改按鈕位置與樣式）。

### 4.6 手機（< 760px）

- 整頁：Streamlit 側欄自動收合；頂欄左「Copilot」，右只留 History 與 New chat 兩顆圖示鍵（不帶字）；情境膠囊移到頂欄下方一行，可捲走。
- 對話欄左右 16px；用戶泡泡最寬 85%；操作列常駐。
- 輸入框貼底，`padding-bottom: env(safe-area-inset-bottom)`；提示小字只留第一句。
- 側邊面板在手機為全螢幕（現有行為），浮動 × 隱藏（現有行為）。

---

## 5. 實作提示

### 5.1 PoC（Streamlit，給「閱讀面試測試要求」thread）

以下 selector 以專案目前使用的 Streamlit 版本為準，改前先在瀏覽器確認 `data-testid`。

- **只對 Copilot 頁生效**：在 `copilot_page()` 開頭 `st.html('<span class="loa-cp-page"></span>')`，CSS 一律用 `body:has(.loa-cp-page)` 開頭，不影響 Monitor 等頁面。
- **限寬**：`body:has(.loa-cp-page) [data-testid="stMainBlockContainer"], body:has(.loa-cp-page) [data-testid="stBottomBlockContainer"] { max-width: 808px; margin: 0 auto; }`（760 ＋左右 24px）。
- **工具列**：`.streamlit/config.toml` 加 `[client] toolbarMode = "viewer"`（去掉 Deploy），或 CSS 隱藏 `[data-testid="stToolbar"]`；部署到 VPS 時本來也該關。
- **固定頂欄**：用 `st.container(key="cp_top")` 包「Copilot＋情境膠囊＋History＋New chat」，CSS `.st-key-cp_top { position: sticky; top: 0; z-index: 20; background: var(--bg); }`；頁首大標與副標刪掉（側欄導航已說明是哪一頁）。若 Streamlit 頂部 `header[data-testid="stHeader"]` 擋住，給它 `background: transparent; height: 0` 或把 `top` 設成它的高度。
- **拿掉頭像、用戶靠右**：
  `[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] { display: none; }`
  `[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: none; justify-content: flex-end; }`
  其內 `[data-testid="stChatMessageContent"]` 給泡泡樣式並 `flex: 0 1 auto; max-width: 75%`。面板用 `div[data-testid="stDialog"]` 前綴同樣處理。
- **操作列**：`share_controls()` 改為 `action_row(turn, latest)`，一列 `st.columns` 放 tertiary 圖示鍵（key 前綴 `act_`）；CSS 舊訊息 `opacity: 0`，`[data-testid="stChatMessage"]:hover` 時 `opacity: 1`，最新一則加 class 常駐。
  - **複製**：`st.button` 無法寫剪貼簿；用 `st.html` 放一顆 `<button class="loa-copy" data-copy="1">`，在已經注入父頁的 `FOLLOW_CORE` 腳本裡加一個委派 click 監聽，複製 `closest('[data-testid="stChatMessage"]')` 內答案區的 `innerText`。
  - **重新回答**：重用現有「Ask again」邏輯（取前一則用戶問題重問）。
  - **讚／踩**：寫一筆 `team_log`（或新表）即可，前端按下後顯示 pressed 狀態。
- **停止鍵併入輸入框**：保留現有 `stop` 按鈕邏輯，只改位置：`.st-key-stop_… { position: fixed; z-index: 30; }` 對齊 `[data-testid="stChatInputSubmitButton"]` 的位置，並 `body:has([class*="st-key-stop_"]) [data-testid="stChatInputSubmitButton"] { visibility: hidden; }`。位置用 `stBottomBlockContainer` 的寬度計算，或改用小段 JS 在 FOLLOW_CORE 裡把 stop 按鈕搬進輸入框容器。
- **提示小字**：`[data-testid="stBottomBlockContainer"]::after { content: "Copilot can be wrong. …"; display: block; text-align: center; font-size: 12px; color: var(--ink3); padding-top: 6px; }`；placeholder 改成「Ask about any London submarket」。
- **工作過程**：`st.status` 預設收合並移除答案底部的「Tools used」caption（併入 status 內）。
- **追問膠囊**：`st.columns(len(follow_ups))` 改成 `st.pills`（若版本支援，`selection_mode="single"`）或一列 `width="content"` 的 secondary 按鈕，左對齊。
- **空白狀態**：`st.container(key="cp_empty")` + CSS `min-height: calc(100vh - 260px); display: flex; flex-direction: column; justify-content: center;`。
- **側邊面板**：`@st.dialog(..., width="small")`；面板內頂部改成第 4.4 節的單列圖示鍵；對話框原生標題可用 CSS 隱藏，改用自己的頂欄。

### 5.2 原型（給「Agent 原型設計」thread）

- `.msg-a`：去掉 `background`、`border`、`padding`；`.cites` 保留上邊線。
- `.msg-q`：改 `background: var(--sunk); color: var(--ink); border-radius: 18px;`（若決定保留深色泡泡也可，但兩邊要一致）。
- `.composer`：`border-radius: 12px`；送出鍵改 32px 圓形圖示鍵（arrow-up），`cpstop` 同位方形。
- 新增 `.acts` 操作列（copy、thumbs-up、thumbs-down、refresh-cw、share-2），取代 `.cites` 內的「Was this useful?」。
- 空白狀態從 `.msg-a` 卡片改為 `.cp-empty` 置中問候＋`.sugg` 膠囊。
- `.jump`：改 32px 圓形 ↓。
- `design-tokens.md` 增補：`--chat-w: 760px`、輸入框圓角 12px、泡泡圓角 18px、操作列 32px 圖示鍵。

---

## 6. 刻意不照抄的地方

| ChatGPT 有 | 我們不做 | 原因 |
|---|---|---|
| 模型選擇下拉 | 不做 | 只有一個 Pi Copilot，選模型對業務用戶沒有意義 |
| 左側欄是對話歷史 | 不做 | 左側欄是產品導航（Monitor／Copilot／Team brief／Sources）；歷史放頂欄 History 下拉 |
| 輸入框「＋」附件 | P2，先不做 | 上傳報告走 Sources 的流程（要比對、確認、去重）；日後可在「＋」裡放「上傳報告」直接跳到 Sources 上傳 |
| 語音輸入、朗讀 | 不做 | 與面試範圍無關 |
| 問題頂到畫面上方的捲動 | 不做 | 現有「跟隨輸出＋↓」已驗證可用 |

我們比 ChatGPT 多、要保留的：情境膠囊（Looking at／About 某信號）、每則回答的來源列與三色來源點、Share to team（團隊共享答案）、⚠ 需核對的數字標記。

---

## 7. 驗收清單

- [ ] 1920px 視窗：對話欄與輸入框同寬 760px、置中，一行約 90–100 字元。
- [ ] 捲到很長的對話中段，頂欄（New chat、History）仍在畫面上方，輸入框仍在下方。
- [ ] 用戶訊息靠右淺灰泡泡、無頭像；助理訊息無頭像、無框。
- [ ] 最新回答下方常駐操作列；舊回答滑過才出現；手機全部常駐；生成中隱藏。
- [ ] 複製鍵實際寫入剪貼簿（貼到別處可見）。
- [ ] 生成中送出鍵位置變成停止鍵，按下保留已寫內容並標 Stopped。
- [ ] 輸入框下方有一行免責小字；placeholder 不再有快捷鍵說明。
- [ ] 新對話：置中問候＋建議膠囊；送出第一句後消失。
- [ ] 往上捲出現圓形 ↓，在輸入框正上方置中；按下回到底部並恢復跟隨。
- [ ] 側邊面板寬約 500px，頂部一列圖示鍵，Monitor 仍有一半以上可見。
- [ ] 390px 寬手機：無橫向捲動，輸入框不被 Home bar 擋住。
- [ ] 更新 `docs/screenshots/copilot*.png`。

---

## 8. 來源

- assistant-ui「ChatGPT Clone」範例與原始碼（max-w-3xl、sticky footer、28px 圓角輸入框、用戶泡泡 70% 靠右、操作列 hideWhenRunning、ScrollToBottom 位置、免責小字）：https://www.assistant-ui.com/examples/chatgpt.md ，https://github.com/assistant-ui/assistant-ui/blob/main/apps/docs/components/pages/examples/chatgpt.tsx
- OpenAI 社群：對話欄 48rem 上限與 `md:max-w-3xl lg:max-w-[40rem] xl:max-w-[48rem]`：https://community.openai.com/t/ability-to-increase-max-width-property-of-chat-output/766195 ，https://community.openai.com/t/wider-conversation-view-adapting-to-main-windows-width/484180
- OpenAI 說明中心 Temporary Chat（右上角 Temporary 膠囊）：https://help.openai.com/en/articles/8914046-temporary-chat-faq
- ChatGPT 側欄改版說明（對話列表、設定在底部）：https://www.ai-toolbox.co/chatgpt-management-and-productivity/chatgpt-sidebar-redesign-guide
- 輸入框設計分析（安靜的預設輸入框、附件靠近送出、工具收進選單）：https://aiuxplayground.com/guides/how-to-design-ai-chat-composer
- 捲動相關社群回報：https://community.openai.com/t/auto-scrolling-error-consistently-impedes-straightforward-usage/1229852
- 介面教學（側欄依時間分組、模型選擇在頂部）：https://freeacademy.ai/lessons/chatgpt-interface
