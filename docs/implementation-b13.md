# NetworkLab B13：版本更新與回滾（v0.1.0 骨架）

## 交付內容

- `lib/updater.py`：GitHub Release/Tag 檢查、Release ZIP 與 `.sha256` 雙檔下載、核對摘要、ZIP 安全解壓、安裝前後驗證、替換及失敗回滾。
- `lib/runner.sh`：把 A03 的 `update check`、`update apply --version VERSION` 導向 updater，不啟動測試 Runner。
- `lib/installer.py`：把 updater 納入安裝來源的完整性預檢；B12 安裝器仍不覆蓋既有 app。
- `lib/menu.sh`：更新確認時顯示正確說明（不再顯示尚未實作）。
- `tests/test-b13.py`、`tests/test-b13-all.sh`：本地模擬 Release、真正切換、失敗注入與回滾測試。

## 先決條件

先合併 B13 增量到目前 Git Repository。B12 的 `sh install.sh` 不會覆蓋已安裝 `~/.networklab/app/`。因此在舊版 B12 安裝上，**先從更新後的 Git Checkout 執行 `./netlab-c.sh update ...`**，它會更新安裝副本。更新完成才使用 `~/.local/bin/netlab-c`。

如果此前沒有安裝過，先執行 `sh install.sh`，再建立更新來源配置。

## 配置可信 GitHub Repository

建立 `~/.networklab/config/update-source.json`（新的**可選**配置，不取代 A05 三份核心配置）：

```json
{"github_repo":"OWNER/REPOSITORY"}
```

請改成你自己公開且可信的 GitHub Repository。`update check` 未配置來源時返回退出碼 3；不會自行猜測或從網路隨機選擇來源。

macOS 使用者可以自行執行：

```bash
nano ~/.networklab/config/update-source.json
chmod 600 ~/.networklab/config/update-source.json
```

## 發布 Release 的檔案契約

需要建立 GitHub 的**已發布、非 Draft、非 Pre-release** Release，Tag 例如 `v0.1.1`，並上傳同一版本的兩個資產：

```text
networklab-v0.1.1.zip
networklab-v0.1.1.zip.sha256
```

`.sha256` 格式：

```text
<64 位十六進位 SHA-256>  networklab-v0.1.1.zip
```

ZIP 為 NetworkLab 專案完整原始碼，允許根目錄直接包含 `lib/` 等，也允許單一包裝目錄 `NetworkLab/`。其 `lib/common.sh` 內 `NETLAB_VERSION` 必須與 Tag 一致，並含 `lib/updater.py`。禁止符號連結、`../` 路徑、大小寫碰撞的重複路徑與特殊檔案。

同一 GitHub Release 中的 SHA-256 側錄檔能檢測下載損壞或資產不一致，**不能獨立抵抗 GitHub 帳號或 Release 被同時竄改的情況**。如需更高強度的來源真實性保障，後續版本應加入獨立金鑰簽章驗證、受保護的 Tag 和發布工作流程。本版沒有宣稱達到獨立的密碼學簽章驗證。

## 公開 CLI

```bash
# 查詢可信 Repository 最新已發布 Release（需連網）
./netlab-c.sh update check
./netlab-s.sh update check

# 預覽（無下載、不改檔案）
./netlab-c.sh update apply --version v0.1.1 --dry-run

# 將已安裝 app/ 更新到指定 Tag（需連網）
./netlab-c.sh update apply --version v0.1.1

# 在 VPS 上相同命令
./netlab-s.sh update apply --version v0.1.1
```

CLI 使用現有 A03 契約，沒有新增公開旗標。更新操作只改變 `~/.networklab/app`，不修改 `config`、`results`、`logs`，不安裝任何系統套件，也不執行 `sudo`。

## 安全與失敗回滾

1. 使用已配置的 GitHub Repository 透過 HTTPS 取得指定 Release 的 Metadata，並核對 Tag。
2. 嚴格校驗兩份官方資產的下載 URL、壓縮包大小與 SHA-256。
3. 先在 `~/.networklab` 的私有暫存資料夾解壓與驗證新版本，並執行 C／S `config validate` 和 `self-test`。
4. 取得與 B12 安裝器共用的 `.install.lock` 排他鎖，讓同時間不會有兩次安裝／升級。
5. 將舊 `app/` 暫存為備份，切換到新 `app/`，再跑一次驗證；失敗自動還原舊版。
6. 驗證成功後刪除臨時備份。`config/`、`results/`、`logs/` 保持不動。

**限制**：`app/` 目錄採取兩次 rename 切換，不是真正單一原子操作；切換期間會有很短的路徑空窗，且 B13 不會主動停止已在執行的測試工作。請在沒有其他 NetworkLab 工作時更新。舊版備份僅用於更新失敗時的自動回滾，成功後不提供永久手動降級功能。

## 測試

```bash
# 完整回歸測試（純離線，可能耗時）
bash tests/test-b13-all.sh

# B13 單獨專項測試（純離線）
python3 -B tests/test-b13.py
```

專項測試使用模擬 GitHub Metadata、模擬 ZIP、SHA-256、故障注入，不訪問 GitHub。實際遠端 GitHub API、macOS 與 Alpine 上的發布與切換仍需另行驗收。

## 退出碼

- 0：檢查／更新成功，或版本已安裝。
- 2：公開命令參數錯誤。
- 3：未配置更新來源、不支援降級、未安裝 app。
- 5：下載錯誤、發布內容或更新後驗證失敗（若已切換則回滾）。
- 9：校驗失敗、不可信的 ZIP、路徑或下載來源。
- 10：與另一個安裝或更新操作衝突。
