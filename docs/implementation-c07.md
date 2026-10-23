# C07：Skeleton Release 發布驗收與維護制度

## 一、版本狀態及本次目標

C07 增加公開 README、唯讀發布檢查器及自動化負面測試。**不修改 v0.1.1 Tag、不重新上傳或覆蓋舊 Release、不宣稱九個真實測試模組已實作。**

截至 2026-10-23：GitHub `xlldll/NetworkLab` 的 `v0.1.1` Release 已存在；包含 ZIP 及 SHA-256；C06 Hotfix 在 `main` 的 GitHub Actions Run `39935946080` 上四個 Job 全部成功（macOS 15、Ubuntu 24.04、Debian 12、Alpine 3.21）。這是當時的狀態快照，請勿把歷史 CI 結果套用到未來新 Commit。

**重大發布缺口**：原 v0.1.1 的 README 為無法使用的重複數字，C07 在 `main` 將其更正。既有 Tag 的歷史檔案不會隨 `main` 改動。因此 v0.1.1 可作為已驗證過的歷史 Skeleton，但要發布包含 C06 Hotfix 及 C07 文檔的新代碼，應使用新的不可變 Tag，例如 `v0.1.2`。

## 二、雙層品質門檻

### Level 1：GitHub CI（必要）

驗證：CLI、嚴格配置與退出碼、B12 安裝器、B13 模擬 Release 更新回滾、報告生成和損壞拒絕、macOS/Ubuntu 原生 Runner，以及 Debian/Alpine 隔離容器。新增 C07 檢查 README 完整、源代碼可用、版本一致、九個模組沒有冒充已實作的情況。

這些測試使用合成數據，**不測跨境 RTT、真實 TCP MTR/iperf3、不測網路高峰期 QoE**。

### Level 2：Field Acceptance（必要，但依功能適用性）

Mac：正式安裝、配置持久化、Bash 3.2、Self-test；Debian/Ubuntu：S 安裝、私有權限與 Server ID；Alpine：BusyBox ash、OpenRC 不被意外修改；發布更新：真實 GitHub Release 檔案、更新與跨版本回滾（隔離安裝環境）。未來真實網路 Worker 上線時，才需要附上真實 TCP Connect/MTR/iperf3 原始輸出與測量環境。

**通過 CI 與通過實機必須分別記錄，不能以彼此代替。**

## 三、C07 離線檢查

```sh
sh tests/test-c07-all.sh
python3 -B scripts/release_audit.py
```

預設只讀取 Git Checkout，不連線、不修改真實 HOME、不建立 Git Tag 或 Release。會檢查 README 的重要警告、兩端 CLI 版本、發行版檔案清單與九個 Skeleton Worker 狀態。

準備新版本的**本地 Release 資產**後可額外校驗：

```sh
python3 -B scripts/release_audit.py \
  --tag v0.1.2 \
  --asset networklab-v0.1.2.zip \
  --checksum networklab-v0.1.2.zip.sha256
```

驗證包括：資產命名、SHA-256、ZIP 版本、缺失的核心檔案、路徑穿越、符號連結、重複／大小寫碰撞名稱、私有檔案滲入。若 ZIP 中的 `NETLAB_VERSION` 與 Tag 不一致，應拒絕發布。

明確請求時才查詢**官方 GitHub Release**（需網路）：

```sh
python3 -B scripts/release_audit.py --online --tag v0.1.2
```

線上模式會使用 B13 已有的 GitHub 安全下載實作，核對 Release 的 ZIP 與 `.sha256`，不執行安裝、不連 VPS。

**注意**：此檢查器對新版要求 README 正確披露 Skeleton 限制；因此用來重新審查舊 `v0.1.1` 時，可能拒絕它當年的壞 README。這代表文件品質不合格，不代表舊 Tag 應被重寫。

## 四、下一個版本的發布步驟（例如 v0.1.2）

1. 在 `main` 完成 C07 程式及文件合併，驗證全部 CI 成功；Mac／VPS 上完成適用的 Level 2 驗收。
2. 將 `lib/common.sh` 的 `NETLAB_VERSION` 改成 `0.1.2`；同步 README、版本說明中的範例。再提交並讓新 Commit CI 綠燈。
3. 選定通過上述雙層驗收的 Commit，建立**新** Tag `v0.1.2`。不重用／移動 `v0.1.1`。
4. 從 Tag 建立 ZIP 與 SHA-256：

```sh
git archive --format=zip --output=networklab-v0.1.2.zip v0.1.2
shasum -a 256 networklab-v0.1.2.zip > networklab-v0.1.2.zip.sha256
shasum -a 256 -c networklab-v0.1.2.zip.sha256
python3 -B scripts/release_audit.py --tag v0.1.2 \
  --asset networklab-v0.1.2.zip --checksum networklab-v0.1.2.zip.sha256
```

5. 建立非 Draft、非 Pre-release 的 GitHub Release，附上兩份驗證通過的資產；發布後用 `--online --tag v0.1.2` 讀取官方資產再校驗一次。
6. 在**隔離的** `NETLAB_HOME` 先驗證 `v0.1.1 -> v0.1.2` 真實更新、設定／Server ID／結果保留與失敗回滾；不要在執行中的測量工作上測試升級。
7. 整理 CI Run URL、兩層驗收證據、限制清單及變更紀錄，才將新版本標為可發布。

GitHub Release 的 SHA-256 檢查只能檢測資產一致性，**並不提供獨立於 GitHub 的來源認證或簽章**。保護 Tag、簽章與更完整的版本回滾屬後續版本工程。

## 五、發佈風險與未完成工作

- 九個正式測量／服務模組仍返回 `NOT_IMPLEMENTED (8)`，不產生真實網路結果。
- 自動恢復 Manifest 發布前殘留的孤兒檔案尚未實作；只保證不將未索引結果冒充可信報告。
- B13 更新是受控兩次 rename，不是單次原子交換；成功後舊版本不長期保留，不支持任意手動降級。
- 以 GitHub CI 全綠不能替代現實網路品質測量；新的實測 Worker 應在未來 Phase D 分別經 CI 與 Field Acceptance。
- Release 資產必須配套固定版本，若只 Push 新 Commit、不建立 Tag/Release，更新器不會把 main 當成可升級版本。

## 六、C07 驗收回報模板

每次發布需分別填寫：

- 版本／Tag、固定 Commit SHA：
- CI Run URL：四個 Job 各自結論：
- Release ZIP／SHA-256：本地及官方檢查結果：
- Mac、Debian／Ubuntu、Alpine 的必要 Field Acceptance：
- 跨版本更新／回滾（使用的兩個版本，是否保留配置與報告）：
- 明確尚未實作的功能及被批准的限制：

**判定規則：** 所有該次變更所需的 Level 1／Level 2 及 Release 安全門檻完成後，才標記 Release Accepted；其餘標記 Pending，不能以過去版本的實測證據宣稱新版本全通過。
