@echo off
echo ========================================
echo TalentFlowAI Startup Script
echo ========================================

echo [1/4] Installing Python dependencies...
D:\home\Python312\python.exe -m pip install --upgrade pip
D:\home\Python312\python.exe -m pip install -r requirements.txt

echo [2/4] Running Django migrations...
D:\home\Python312\python.exe manage.py migrate_schemas --noinput

echo [3/4] Collecting static files...
D:\home\Python312\python.exe manage.py collectstatic --noinput

echo [4/4] Starting Gunicorn...
D:\home\Python312\python.exe -m gunicorn config.wsgi:application --bind 0.0.0.0:%HTTP_PLATFORM_PORT% --workers 2 --timeout 120

echo ========================================
echo Startup complete
echo ========================================
