# バックエンド起動スクリプト
.\venv\Scripts\Activate.ps1
py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
