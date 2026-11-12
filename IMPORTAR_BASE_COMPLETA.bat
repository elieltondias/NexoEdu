@echo off
cd /d "%~dp0"
echo Iniciando importacao completa. Isto pode demorar bastante e consumir muita memoria.
docker compose exec app python -m src.cli ingest --path lpg --scope completa --graph ensino_2024_completo
if errorlevel 1 (
 echo A importacao falhou. Envie uma foto desta janela para verificar o erro.
 pause
 exit /b 1
)
echo Importacao concluida. Para visualizar, configure GRAPH_NAME=ensino_2024_completo no arquivo .env e execute INICIAR_WINDOWS novamente.
pause
