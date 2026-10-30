@echo off
chcp 65001 >nul
title BAMC 自动更新 · 图片 + 台风
cd /d "%~dp0"

echo 正在启动两个独立更新器：
echo   1) 预报图片（每 30 分钟）
echo   2) 台风 AIFS / GEFS 数据（每 10 分钟）
echo.

start "BAMC 图片自动更新" "%~dp0start_auto_update.bat"
start "BAMC 台风自动更新" "%~dp0start_tc_auto_update.bat"

exit /b 0
