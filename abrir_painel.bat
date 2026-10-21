@echo off
rem Roda o processar.py desta pasta (gera os resultados e os Excel do dia).
cd /d "%~dp0"
streamlit run app_turma_hud.py
if errorlevel 1 (
    echo.
    echo [ERRO] O processar.py terminou com erro. Veja a mensagem acima.
)
echo.
pause
