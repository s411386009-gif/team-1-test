# 修正版驗收與兩台電腦操作

這份套件修正未知 type 延後拒收、非空 FILE_END 被接受，以及量測輸出管線阻塞和接收端 wall_ms 錯誤。不要把本機測試當成跨電腦驗收。

## 建置

Windows 請使用 MSYS2 UCRT64 的 GCC/mingw32-make 與 Python 3.9+。在 PowerShell：

```powershell
$env:Path = 'C:\msys64\ucrt64\bin;' + $env:Path
gcc --version
python --version
mingw32-make
mingw32-make test
```

若 Python 不在 PATH，可指定 `mingw32-make test PYTHON=C:/完整路徑/python.exe`。macOS/Linux 使用 `make`、`make test PYTHON=python3`。測試只用 Python 標準函式庫，會開啟本機 loopback TCP，不需連外。防火牆需允許測試程式本機連線。

`make test` 同時執行 C 單元測試與 tests/acceptance.py 整合測試。整合測試建立暫存檔，驗證 SHA、STATS、結束碼、聊天傳檔、RAW/HUFF 半包黏包、非法 UTF-8、錯誤碼表和斷線。結果寫 results/acceptance.json。這些測試會在錯誤時回傳非零碼。

## 兩台電腦最低驗收

兩端使用同一版 source 重新 build。A、B 連同一網路；記下 IP、指定 port、GCC 版本、Git 完整 SHA（若使用 ZIP，記下 ZIP SHA256）。A 用自己的實際 IPv4；B 用 A 的 IPv4。以下示例 port 6123，可替換。

先雙向 RAW、HUFF 聊天，各傳 `Hello é Ω 中文 😀 𠮷 👨‍👩‍👧`，拍兩端 IP/port、發送和接收內容：

```powershell
# A
.\textlink.exe chat server 6123 --raw
# B
.\textlink.exe chat client <A-IP> 6123 --raw
# 重跑時兩端改 --huff
```

V 在 B 執行 `python tests/chunk_send.py <A-IP> 6123`，A 先重開 RAW chat server；確認 5 則黏包＋1 則半包，保留兩端記錄。

### 文字、WAV 四種傳法

准备 `big.txt`（BOM/CRLF/1–4 bytes 混合，>1 MB）及可播放的 16-bit PCM `speech.wav`。檔案在 B。對每個檔案照以下 4 格操作，共 8 次；每次先做 SHA 比對，再進行下一次。不要讓後一輪覆蓋前一輪證據。

|格|A 操作|B 操作|
|---|---|---|
|CLI RAW|`.\textlink.exe recv 6123 out-cli-raw`|`.\textlink.exe send <A-IP> 6123 big.txt --raw`|
|CLI HUFF|`.\textlink.exe recv 6123 out-cli-huff`|`.\textlink.exe send <A-IP> 6123 big.txt --huff`|
|聊天 RAW|啟動 chat server，收到檔後查 hash|啟動 chat client，輸入 `/raw`、`/send big.txt`|
|聊天 HUFF|保持 chat server，收到檔後查 hash|輸入 `/huff`、`/send big.txt`|

WAV 重複上述 4 格，檔名換成 speech.wav。每次收到後播放，保留成功播放證據。SHA 指令：

```powershell
# B 原檔（每格都保留）
Get-FileHash .\big.txt -Algorithm SHA256
# A 接收檔：依本格目錄替換
Get-FileHash .\out-cli-raw\big.txt -Algorithm SHA256
# 聊天接收檔在 received；HUFF 開始前先存 RAW 的 hash
Get-FileHash .\received\big.txt -Algorithm SHA256
```

本機整合測試已驗證這 8 格的程式行為；此表的跨機器欄位還需隊友實跑，不會自動勾過。

## 正式量測（至少 80 次）

選四個 >=1MB、<=20MB 的檔案：中文、英文、真實語音與真實音樂（16-bit PCM WAV）。保留來源、授權、檔案大小與 SHA。合成 tone 只能當開發測試，不能代替真實語音／音樂。

把同一份檔案列表與順序傳給 A/B，檔名不可重複。A 不需持有來源檔，只需列表。兩端 `--env` 必須一致，`--results` 要使用全新的資料夾。

```powershell
# 本機：四檔 × RAW/HUFF × 五次 = 40 次、80 列
python tests/matrix.py local zh.txt en.txt speech.wav music.wav --results results/formal-local --env local

# A 先監聽：會按固定順序連續接收 40 次
python tests/matrix.py recv zh.txt en.txt speech.wav music.wav --port 6123 --results results/formal-A --env wifi

# B 接著送出（與 A 相同列表順序）
python tests/matrix.py send zh.txt en.txt speech.wav music.wav --ip <A-IP> --port 6123 --results results/formal-B --env wifi

# 合併 A/B CSV 後驗證；把路徑替換成真的位置
$csv = Get-ChildItem results/formal-A,results/formal-B -Filter *.csv | ForEach-Object FullName
python tests/matrix.py verify @csv
```

驗證器檢查每次 send/recv 配對、SHA 相同、exit=0、wire_bytes 一致、ratio 四位小數，再列各角色 total_ms 中位數。接收端 wall_ms 包含等待連線，不適合當傳輸時間比較；用 STATS total_ms。兩端計時起點不同，圖表要固定同一角色，不能把送／收兩端時間相加。

每份 CSV 旁的 *_logs 目錄保存原始輸出。重新量測使用新目錄，避免把不同版本或環境混成同一组。把 results 的原始數據、測試 JSON 和報告圖表加入 Git；.gitignore 已允許 results 下的 CSV/log。

## 尚需人員完成

- 兩台電腦按上述 8 格驗證及正式 40 次跨機器量測。
- 真實語音/音樂的選材、實際播放與來源記載。
- 報告圖表與熵/平均碼長/codebook 分析必須使用最終正式資料。
- 每位同學自己實際完成、理解並 commit C 程式貢獻；本套件不代替或偽造個人 commit。
- 更新 TEAM_LOG、CONTRIBUTIONS、AI_USAGE 的真實內容，提交後記錄最終完整 SHA。

