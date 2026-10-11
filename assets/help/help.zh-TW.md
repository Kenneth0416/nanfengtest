# 使用說明

London Office Market Agent 是全組共用的一個工具，做三件事：**Monitor** 盯住市場，**Ask Copilot** 幫你做判斷，**Team brief** 把一週整理成一份董事會和投委會共用的 brief，可下載成研究報告或簡報。**Sources** 是這三者背後的資料庫。應用裡每個數字都連到它的出處。

## 開始使用

1. 打開應用。第一次會請你選自己的名字（或自己輸入）；有其他人用同一個瀏覽器時，按 **Change** 換人。不需要登入：瀏覽器會記住你，你的焦點、警示和對話都存在你的名字下。
2. 用左邊的選單切換 **Monitor**、**Ask Copilot**、**Team brief** 和 **Sources**。名字旁的數字表示有東西在等你，例如 *Team brief · 2* 或 *Sources · 4 to check*。
3. 右下角的圓形按鈕可在任何頁面打開 Copilot。**Ctrl+K** 效果相同，**/** 會把游標放進 Copilot 的輸入框。

![選單、你的名字和 Copilot 按鈕](screenshots/01-overview-navigation.png)

## Monitor

Monitor 是第一頁，顯示本週倫敦寫字樓市場有什麼變化，全組都看得到。

### 看本週動態

1. 頂部的**更新狀態列**顯示公開資料上次何時進來、市場數據涵蓋哪一季、有多少數字待核對，以及有哪些預期中的報告還沒人上傳（按 **Upload it** 直接過去上傳）。
2. **團隊摘要**用兩句話講完本週。下面的小標籤是它的出處。
3. **Whole team** 顯示當天給全組的精選。設定好焦點後，**For you** 顯示你自己的版本。
4. **Set up my focus** 用一句描述你工作的話，幫你建立這個個人視圖。

![Monitor：更新狀態列、摘要和兩個視圖](screenshots/02-monitor-overview.png)

### 使用訊號卡

每張卡是一件有變動的事。

1. 標題和數字列：變動前 → 變動後、變幅，以及一兩年前同一季的數值。
2. 出處標籤會打開數字來源的報告。
3. **Ask Copilot** 打開已經對準這個訊號的 Copilot。
4. **Add to brief** 把訊號放進 Team brief。按鈕會變成 **In team brief**，任何人都可以再按一下把它拿走。
5. **Hide for me** 只在你的視圖中隱藏，其他同事仍然看得到。
6. **Looks wrong** 向全組標記這個數字有問題。寫下哪裡不對，再按 **Flag for the team**。在有人到 Sources 處理之前，這個數字仍可使用，但會帶警示。

精選只顯示幾張卡，其餘的按類別收在最後一張卡下面。

![一張訊號卡和它的按鈕](screenshots/03-monitor-signal-card.png)

### 分享消息、設定警示、看團隊動態

1. **Share a link or tip**：貼上連結，或寫下你聽到的消息（例如「經紀說 Triton Square 又有一層在洽談中」），再按 **Share with the team**。代理會閱讀內容，檢查團隊是否已有這則消息，再合併或新增，記上你的名字並評估熱度。沒有公開出處的消息會顯示為 *Unverified tip*，直到有連結或第二個來源為止。
2. **Alerts**：用英文寫一條規則，例如「Alert me when City Core vacancy goes above 7%」。應用會在你輸入時即時解讀（指標、子市場、條件），並告訴你以今天的數據會不會觸發。按 **Save** 儲存。警示屬於你，會在你的 *For you* 視圖觸發；按 **Share with team** 可分享給全組。
3. **Team activity** 列出同事新增、標記、上傳或選擇分享的內容，最新的在最上面。

![分享消息、警示和團隊動態](screenshots/04-monitor-share-alerts-activity.png)

### 設定你自己的視圖

1. 按 **Set up my focus**，用一句話描述你的工作，例如「I manage our West End buildings and report to the board」。
2. Copilot 會建議子市場、指標、顯示多少個訊號、「為何重要」用誰的口吻，以及略高於今天數值的警示。這時還沒有儲存任何東西。
3. 按 **Apply**（或 **Discard**）。**Clear my focus** 會回到團隊視圖。

![設定你的焦點](screenshots/05-monitor-set-up-focus.png)

之後 Monitor 會以 **For you** 打開。你的焦點顯示在卡片上方；按 **Change with Copilot**，或直接跟 Copilot 說一句修改，例如「more Fitzrovia, less macro」。它設定的警示放在 **Alerts** 下。

![For you 視圖，含你的焦點和警示](screenshots/06-monitor-for-you.png)

## Ask Copilot

Copilot 根據團隊的資料庫回答倫敦寫字樓市場的問題，可用英文或中文提問。每個數字都來自帶出處的工具。

### 開始對話

1. 選一個示例問題，或按 **Set up my focus**。
2. **History** 列出你已存的對話。
3. **New chat** 開一個全新的對話。
4. 在底部的輸入框打字，按 Enter 送出。

![新對話](screenshots/07-copilot-new-chat.png)

### 看它工作

1. 狀態列寫出 Copilot 正在用的工具（「pulling the trend」、「comparing submarkets」）。
2. 答案邊寫邊出現。
3. 寫的時候，送出按鈕變成 **Stop**。按 Stop 會保留已寫的內容。

![答案寫到一半，帶 Stop 按鈕](screenshots/08-copilot-streaming-stop.png)

### 看答案

1. 你的問題在右邊。
2. **Worked through N steps** 收起了它用過的工具，展開就能看到。
3. 答案中每個數字都寫明季度，一看就知道有多新。

![完成的答案](screenshots/09-copilot-answer.png)

答案下方：

1. 用同一份數據畫的圖表。
2. **Sources**：每個標籤打開數字來源的報告。
3. 操作列：複製、有用／沒用、重新回答、分享給團隊。
4. Copilot 建議的追問，按一下就會發問。

![圖表、出處、操作和追問](screenshots/10-copilot-sources-actions.png)

### 停止與重新回答

1. 被停止的答案會保留已寫內容，並標示 *Stopped*。
2. **Ask again** 把同一個問題再問一次。

![已停止的答案和 Ask again](screenshots/11-copilot-stopped-ask-again.png)

### 找回以前的對話

按 **History**。你的對話按時間排列，最新的在最上面，並顯示時間和訊息數。這些對話只有你看得到。按一下就能從上次停下的地方繼續。

![History](screenshots/12-copilot-history.png)

### 把答案分享給團隊

答案在你分享前都是私人的。

1. 按答案操作列中的分享按鈕。
2. 可以加一句原因（例如「Useful for Thursday's IC」），再按 **Share**。

問題、答案、圖表和出處會以你的名字出現在 Monitor 的 **Team activity**。同事可以按 **Continue in my Copilot** 在自己的對話中接著問。你答案下方會顯示 *Shared to team · Undo*，按 Undo 可撤回。

![分享答案](screenshots/13-copilot-share-to-team.png)

### 在任何頁面提問

1. 訊號卡上的 **Ask Copilot** 會以側邊面板打開 Copilot。
2. 面板知道你指的是哪個訊號（「About: Bloomsbury prime rent up +6.1%」）。
3. 輸入自己的問題，或選一個建議。頁面仍在面板旁邊；按 X 關閉。

![Copilot 側邊面板](screenshots/14-copilot-side-panel.png)

### 離開後它仍繼續工作

你不用等答案寫完。關掉面板、打開別的頁面或重新整理都可以：Copilot 會在背景繼續寫，你回來時完成的答案就在那裡。如果你回來時它還在寫，會從頭接上文字。只有 **Stop** 會結束一次執行。Team brief 和正在製作的簡報也一樣。

![在背景完成的答案](screenshots/15-copilot-background.png)

## Team brief

Team brief 根據同事在 Monitor 加入的訊號撰寫，每個數字都有註腳。

### 閱讀和下載 brief

1. brief 中的訊號，以及各自由誰加入。按 x 移除一個；**Add more from Monitor** 帶你回去挑選更多。
2. 一份 brief 同時給董事會和投委會：倫敦的關鍵數字、團隊子市場的證據表，以及支持與風險兩邊的訊號。只列出標為可引用的成交。
3. **Word** 和 **PDF** 把 brief 下載成帶品牌的研究報告。檔案製作期間兩個按鈕會變灰等待。
4. **Build slides** 打開簡報編輯器（已有簡報時按鈕會顯示 **Slides**）。
5. brief 本身。每個 [n] 指向文末的 Sources 列表。數據不變時 brief 只寫一次；**Write again** 會用同一份數據重新寫過。

![Team brief](screenshots/16-team-brief.png)

### 製作簡報

按 **Build slides**，簡報編輯器會蓋在頁面上打開。你可以在右欄看 Copilot 規劃故事線，同時每張投影片排好後就出現在縮圖中。**Stop** 會保留已做好的部分。製作期間可以關掉編輯器；brief 上的按鈕會顯示 *Slides · working…*，直到簡報完成。

![製作中的簡報](screenshots/17-slides-building.png)

### 在簡報編輯器中工作

1. 縮圖和頁碼，按一下打開那一頁。
2. 選中的投影片，放大顯示。
3. 下方工具列：上一張、下一張、上移或下移，或刪除。封面和出處頁固定在最前和最後。
4. Copilot：用英文或中文說出你想怎樣改簡報。
5. **Theme**：五套內部主題。換主題會用新主題重建同樣的投影片。
6. **Download .pptx**（可編輯的 PowerPoint）或 **PDF**。兩者都會跟著每次修改更新。

![簡報編輯器](screenshots/18-slides-editor.png)

### 用對話修改簡報

在編輯器的對話框輸入你想要的修改，例如：

- 「Swap slides 2 and 3」、「Remove slide 3」、「Add a slide on investment」
- 「Make slide 2's title shorter」、「Shorten to 4 slides」
- 「Only show the last four quarters of vacancy」、「as a line chart」
- 「Theme forest」、「for a client update」
- 「需要多兩頁」、「刪第3頁，然後換森林主題」

「這一頁」指目前選中的投影片。Copilot 只用數據中已有的數字，其他數字會被拒絕，並附上目前的數值。

1. 你的要求。
2. 回覆會說明簡報實際改了甚麼。
3. **Undo** 回到上一步；版本按鈕（v1、v2…）列出所有可回到的版本。

![用對話修改簡報](screenshots/19-slides-edit-by-chat.png)

## Sources

Sources 是團隊共用的資料庫。來源有三種，各有一個顏色圓點和標籤：代理自動收集的**公開資料**、同事上傳的**報告**，以及公司自己的**內部資料**。

### 瀏覽資料庫

1. 每種來源的數量。
2. **Updates** 每天在伺服器上執行；**Update now** 立即執行一次。
3. **Add a source for the team**：貼上連結或寫出來源名稱（見下文）。
4. **Needs a person**：有人標記的數字，以及互相矛盾的來源。全組任何人都可以處理，處理人會顯示在團隊動態中。

下面的分頁按類型列出資料庫：**Collected automatically**、**Uploaded reports**、**Internal data** 和 **News and tips**。

![Sources](screenshots/20-sources-overview.png)

### 處理被標記的數字

1. 打開待核對的數字組。每個數字都顯示數值、季度和被標記的原因。
2. 對照報告核對，然後按 **Right** 保留，或按 **Wrong** 為所有人移除。
3. 兩個來源對同一個數字說法不同時，核對後按 **Mark checked**，或按 **Ask Copilot** 問它。

![Needs a person](screenshots/21-sources-needs-a-person.png)

### 為團隊新增來源

1. 貼上連結，或寫出你想追蹤的來源（「Follow Savills Market Watch」），按 **Check source**。也可以直接跟 Copilot 說「follow …」。
2. 代理會先讀網站的 robots.txt 和使用條款。允許的話，來源會自動收集；如果條款限制自動收集或 AI 使用，就改為只接受上傳，並在新一期到期時由 Monitor 提醒團隊。建議中會寫明原因，並引用條款中所依據的那一句。
3. 按 **Add for the team** 開始追蹤，或按 **Cancel**。

![新增來源](screenshots/22-sources-add-a-source.png)

### 上傳報告

條款禁止自動收集或 AI 使用的報告（Knight Frank、Savills、BNP Paribas 等），由有權限的同事上傳 PDF。

1. 打開 **Uploaded reports**，把 PDF 拖進去（或按 **Try the sample**）。
2. 代理會閱讀每個數據頁，並顯示用了哪些技能。
3. 每個數字都會列出頁碼和三項檢查：是否在頁面文字中、是否在合理範圍、是否與資料庫已有數據一致。通過的數字原樣分享。你親眼核對過的，勾 **I checked it**；不要的，取消勾選 **keep**。有數字待核對的頁面會顯示在表格下方。
4. 按 **Publish to the team**。如果已有人上傳過同一份報告，應用會說明是誰、何時上傳，並且不會重複加入。

![上傳報告](screenshots/23-sources-upload-report.png)

## 小提示

- **語言**：可用英文或中文問 Copilot，它會用你提問的語言回答。
- **鍵盤**：Ctrl+K 打開 Copilot；/ 把游標放進輸入框；Esc 關閉面板或簡報編輯器。
- **私隱**：你的對話、焦點和警示只屬於你。只有你分享、標記、上傳或加入 brief 的內容，團隊才看得到。
- **數據說明**：此評估版本中的市場數字取自公開的 Knight Frank 報告並經重述，只供評估使用；英倫銀行利率和新聞為即時收集；內部交易和同事名字為示範資料。
