@echo off
chcp 65001 >nul
title BAMC 热带气旋 · 多模式自动更新
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [错误] 没有找到 Python。请安装 Python 3.10 或以上版本。
  echo.
  pause
  exit /b 1
)

echo.
echo  正在启动热带气旋自动更新器……
echo  每 10 分钟检查 AIFS / GEFS 官方源；IFS 需要 pybufrkit。
echo  关闭此窗口即停止自动更新。
echo.

python tc_auto_update.py
pause
