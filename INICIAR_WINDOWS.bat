@echo off
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
 echo Instale e abra o Docker Desktop antes de continuar.
 pause
 exit /b 1
)
if not exist .env copy .env.example .env >nul
docker compose up -d --build
if errorlevel 1 (
 echo Nao foi possivel iniciar. Confira o Docker Desktop e o README.md.
 pause
 exit /b 1
)
echo Abra http://localhost:8501 e importe a amostra.
start http://localhost:8501
pause
