# D03：Mac C Standalone TCP Connect（實機增量）

## 邊界

- 基準：`manual/d02-c-inventory` commit `f11fedff83d49e8c391855c89f4baaacf6c30148`。增量仍屬開發樹；不是 `v0.1.1` 正式 Release。
- 僅 macOS C 端。使用 Python `socket` 提供的**系統 TCP API**，非自行撰寫 TCP 協定；不對目的端發送 HTTP/TLS／其他應用層請求。
- **使用者必須明確指定 IP、TCP Port**，沒有預設遠端服務，亦不查詢 DNS：`bash netlab-c.sh standalone --tcp-ip 1.1.1.1 --tcp-port 443 --profile quick --non-interactive`。
- D03 Standalone 僅允許全球可路由的 IPv4/IPv6 地址；`127.0.0.1`、`::1` 可用於本機驗收。LAN、CGNAT、link-local、網域名稱不在本階段 Standalone 範圍；未來 C Paired 另支援本地/專用網路。
- Profile `quick=12`、`standard=30`、`deep=100`。每次建連 1.0 秒 timeout，成功與失敗都保存，間隔 0.05 秒；Runner 150 秒 watchdog。深度測試目標不可達時可能接近 105 秒。
- **不證實直連**：原生 Socket 沒有使用 HTTP/SOCKS 代理協定，但 macOS Network Extension、TUN、透明攔截、策略路由仍可能改變實際路徑。`proxy_mode=unknown`；`route -n get IP` 是預期路由提示，不是流量實證。
- `scutil --proxy` 只擷取布林值，不保留 PAC URL/Proxy Host/Token。raw 報告含所測 IP/Port、各次延遲/失敗、系統路由介面與代理開關，分享前需審核。

## 數據與報告

- 每次原始證據：`tcp-connect-attempts.json`，逐筆 `index`、`success`、`elapsed_ms`、`error_code`。不因失敗刪除樣本；沒有成功樣本，P50/P95/P99 為 `null`。
- `success_pct` 分母是全部連線數；延遲分位數只取 **成功連線**。P95/P99 採線性內插分位數，並保留 `successful_samples`。成功樣本少於 100 時標示 `SPARSE_TAIL` 警告。
- 標準化數據：P50/P95/P99、P95−P50、最小/最大值、母體標準差、成功率、樣本量。
- 全成功 = `completed`/0；部分失敗 = `partial`/7；全失敗 = `failed`/5。即使失敗，Worker 先提供可驗證 handoff，以便 Report Writer 保存證據。
- `B09` 原生檔案 SHA-256、Manifest、Summary、有效參數契約沿用現有程式。未改 D01/D02 Worker。

## 驗收

Mac 一條命令：`sh tests/test-d03.sh`。

離線樣本測試數字 IP/Port 防護、分位數、失敗歸類、IPv6、Context 防護、原生檔寫入；唯一真實網路測試為 **Mac 本機 127.0.0.1 臨時 TCP listener**，不會訪問外部站點。

**真實跨境測量尚未驗收**：在使用者主動指定自己有權測量的服務與 Port 後，應核對原始連線次數、P50/P95、成功率，明確區分直連／透明代理的證據不足問題。

### 例子（需明確授權並自行選擇測量對象）

```sh
bash netlab-c.sh standalone --tcp-ip 1.1.1.1 --tcp-port 443 --profile quick --non-interactive
```

`1.1.1.1:443` 是公共 TCP 服務測量例子，**不是你的 Mac↔VPS 專用測試，也不能用它的品質代表 VPS**。D04 C Paired 才會用 C Targets 配置選擇 VPS。
