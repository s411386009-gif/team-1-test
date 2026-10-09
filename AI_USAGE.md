# AI 使用紀錄

2026-10-09：使用 Codex 協助比對課程規格、檢視 GitHub/Slack 測試證據，並在原始版本 1f0b0600dc557b43d3beecad705b45289f235d82 上準備修正版。

AI 修改：src/frame.c 的合法 type 檢查；src/transfer.c 與 src/chat.c 的非空 FILE_END 拒收；tests/test_codec.c 回歸案例；tests/acceptance.py 整合測試；tests/measure.py 的輸出管線、計時、失敗處理與原始 log；tests/matrix.py 五次量測/CSV 驗證；Makefile、README、docs/acceptance.md 與 .gitignore。

驗證由 AI 在 Windows MSYS2 UCRT64 GCC 16.2 環境實際執行。自動測試與量測為本機 loopback；跨兩台電腦的新版本驗收尚待組員執行。合成樣本數據不冒充真實語音/音樂正式量測。

組員仍需審閱、理解與確認所有改動，補真實的個人 C 程式貢獻、跨機器結果與最終 Git SHA。此紀錄不代表組員已完成審閱，也不替任何人建立或冒署 commit。
