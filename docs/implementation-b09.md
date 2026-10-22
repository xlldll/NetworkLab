# NetworkLab B09：Report Writer v0.1.0

**範圍：** A07 JSON Schema 1.0 的正式保存與完整性驗證，接入 B05 Runner。**不包含**真實測速、結果匯入、排程、可供使用者查詢的 results CLI；後者留待後續階段。

## 交付與增量更新

- `lib/report.py`：新增，Python 3 標準函式庫實作。負責 handoff 解析、檔案驗證、原生資料無損複製、Report Summary、Manifest 和 SHA-256 校驗。
- `lib/runner_host.py`：更新。工作程序結束後呼叫 Report Writer；worker exit=8、管理命令或沒有 handoff 時**不**製造正式測試報告；發布失敗回報 `REPORT_ERROR (5)`，保留私有工作目錄。
- `schemas/manifest.schema.json`、`schemas/summary.schema.json`：沿用已定稿的 A07 Draft 2020-12 Schema，**不是另起一套格式**。
- `tests/test-b09.py`：19 組獨立離線測試，包含真正執行模擬 Worker 和 Schema 驗證（需另有 `jsonschema` 才執行標準驗證；不影響正式執行時的標準函式庫要求）。
- `tests/test-b09-all.sh`：B01–B09 回歸測試。

## Worker → Runner 的 handoff 格式

新模組應在由 Runner 創建的 `NETLAB_WORK_DIR` 中，準備：

```text
run-<run_id>/
├── context.json             # Runner 生成；模組不可擅自改寫
├── raw/
│   └── probe.json           # 模組原生檔案，可為 JSON/TXT/CSV/NDJSON 等
└── worker-report.json       # 模組寫入的原子完成／checkpoint 記錄
```

`worker-report.json` 格式（以下所有資料均是 **synthetic**）：

```json
{
  "contract_version": 1,
  "synthetic": true,
  "requested_tests": ["probe"],
  "tests": [{
    "test_id": "probe",
    "attempt": 1,
    "status": "completed",
    "evidence_scope": "local",
    "data_provenance": "observed",
    "tool": {"name": "synthetic-fixture", "version": "1.0"},
    "network": {"ip_family": null, "transport": null, "direction": "LOCAL", "proxy_mode": null},
    "parameters": {},
    "metrics": {"fixture_value": 42},
    "raw_files": ["probe.json"],
    "errors": [],
    "warnings": []
  }],
  "raw_files": [{"path": "probe.json", "format": "json", "test_id": "probe"}],
  "errors": [],
  "warnings": []
}
```

重要：`raw_files[].path` 只允許 `raw/` 目錄內安全的 basename；`tests[].raw_files` 填原本的 basename，正式發布後 Writer 會替換成扁平結果目錄中的固定檔名。所有已請求的測試須有對應 `tests[]` 記錄，否則成功的 worker 會降級成 `partial (7)`。任務記錄應由模組先寫臨時檔，完成並 fsync 後原子改名為 `worker-report.json`，避免中斷時產生半份 JSON。

模組不可自行產生正式 `manifest` / `summary`，亦不可將模擬資料標示 `synthetic: false`。未完成的九個佔位模組繼續返回 8，**不建立**正式報告。

## 結果位置

- C inventory／standalone → `~/.networklab/results/c/local/`
- C proxy → `~/.networklab/results/c/proxy/`
- C paired → `~/.networklab/results/c/<target_id>/`
- S inventory／toolbox → `~/.networklab/results/s/<server_id>/`
- C collect → 將來進行真實匯入；B09 可以保存 worker 的交付資料，但沒有實作遠端收集。
- S service／schedule → 管理操作，B09 不發布測量報告。

檔名按 A07：`c-manifest-local-YYYY-MM-DD-HH-mm-ss[-NN].json`、`c-summary-...`、`c-probe-local-...json`，其中 `[-NN]` 同一 Run 一致。

儲存過程：生成 Run／Context → 子程序生成檔案和 handoff → Publisher 驗證 → 原生檔案以原始位元組複製 → 可選對 stdout/stderr 做遮蔽後保存 → Summary → SHA-256 索引 → **最後發布 Manifest**。

使用排他工作目錄和排他檔案發布（硬連結 no-clobber），重複檔名不會被默默覆蓋；如果在最後 Manifest 前崩潰，可能留下尚未完整封存的檔案，但它們不應被視為完整報告。此次尚未實作孤兒檔案掃描和恢復命令。

## 安全與資料完整性

- 私有 Context／工作區沿用 B06 權限驗證；不允許 raw 或結果目錄的符號連結。拒絕原始檔硬連結、路徑穿越、重複 ID、無效 JSON／NDJSON、NaN／Infinity。
- `manifest.files[]` 記錄各個檔案的 SHA-256 和長度，並與 Summary 身分欄位交叉驗證。Manifest 不含自己的 SHA-256。
- `effective_parameters` 僅記錄必要且已遮蔽的參數，不能當成完全的系統配置備份。
- `stdout/stderr` 是處理過的操作日誌，與保留原位元組的第三方原生報告不同。**正規表示式遮蔽不保證排除所有機密**，尤其任意格式、雜湊憑證、Base64、帶密碼網址等。模組在產生 raw 前須確保敏感資料已移除；發布、上傳前需人工審閱。
- 原始工作區仍可能保存未遮蔽的 stdout／stderr；僅同一作業系統帳號可存取，待未來資料清理機制處理。
- JSON Schema 在測試環境以 `jsonschema` 驗證；正式 Report Writer 無第三方 Python 依賴，內建相應結構與語義檢查。`synthetic` 僅標記來源不是實測，無法防止惡意 Worker 虛報。

## 安裝及驗收

將增量 ZIP 依相對路徑合併至現有 Repository，無需更動 `~/.networklab/config`。

```bash
bash tests/test-b09-all.sh
bash netlab-c.sh inventory --non-interactive
echo $?
```

第二項在 v0.1.0 應仍返回 `8`，而且不產生正式測量報告。

如需驗證真正的寫入流程，請執行 `python3 -B tests/test-b09.py`。測試只使用隔離暫存目錄、假的 C/S 裝置和 `synthetic: true` 數據，不需要連線 VPS，也不產生真實測速流量。

## 尚未完成與下一步

B09 **已實作並驗證 Report Writer**，但尚未開發實際採集模組、正式結果列表、B10 日誌瀏覽、B11 自檢命令、B12 安裝器及跨平台真機驗收。部分異常退出在沒有有效 handoff 時，只會保存私有工作目錄而不產生正式報告；後續模組需在每個已完成子測試後安全更新 checkpoint。
