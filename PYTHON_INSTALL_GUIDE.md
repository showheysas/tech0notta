# Python環境のセットアップガイド

## 🔍 現在の状況

Pythonがインストールされていないか、パスが通っていない状態です。

---

## 📋 Pythonのインストール確認

### 方法1: 別のPythonコマンドを試す

WindowsではPythonが複数の方法でインストールされている可能性があります。

```powershell
# py コマンドを試す（Windows Python Launcher）
py --version

# python3 を試す
python3 --version

# where コマンドでPythonの場所を探す
where.exe py
where.exe python
where.exe python3
```

---

## 🚀 Pythonがインストールされている場合

### pyコマンドが使える場合

```powershell
# 仮想環境作成
py -m venv venv

# 仮想環境有効化
.\venv\Scripts\Activate.ps1

# 依存パッケージインストール
pip install -r requirements.txt

# サーバー起動
py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📥 Pythonがインストールされていない場合

### オプション1: Microsoft Store からインストール（推奨）

1. **Microsoft Store を開く**
   - Windowsキー → "Microsoft Store" と入力

2. **Python を検索**
   - "Python 3.11" または "Python 3.12" を検索

3. **インストール**
   - 「入手」または「インストール」をクリック

4. **確認**
   ```powershell
   python --version
   # または
   py --version
   ```

### オプション2: 公式サイトからインストール

1. **ダウンロード**
   - https://www.python.org/downloads/
   - "Download Python 3.11.x" をクリック

2. **インストール**
   - ダウンロードしたインストーラーを実行
   - **重要**: "Add Python to PATH" にチェックを入れる
   - "Install Now" をクリック

3. **確認**
   ```powershell
   python --version
   ```

---

## 🔧 既存の仮想環境がある場合

もし既に仮想環境が存在する場合は、以下を試してください：

```powershell
# 仮想環境の確認
dir venv

# 仮想環境が存在する場合、有効化を試す
.\venv\Scripts\Activate.ps1

# PowerShell実行ポリシーエラーが出る場合
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 再度有効化
.\venv\Scripts\Activate.ps1
```

---

## 🐳 代替案: Dockerを使用

Pythonのインストールが難しい場合、Dockerを使用することもできます。

### 前提条件
- Docker Desktop がインストールされていること

### 手順

1. **Dockerfileの確認**
   ```powershell
   dir Dockerfile
   ```

2. **Dockerイメージのビルド**
   ```powershell
   docker build -t meeting-notes-api .
   ```

3. **コンテナの起動**
   ```powershell
   docker run -p 8000:8000 --env-file .env meeting-notes-api
   ```

4. **Swagger UIにアクセス**
   ```
   http://localhost:8000/docs
   ```

---

## 🔍 トラブルシューティング

### ケース1: "py" コマンドは動くが "python" は動かない

```powershell
# すべてのコマンドで "python" の代わりに "py" を使用
py -m venv venv
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload
```

### ケース2: 仮想環境の有効化でエラー

```powershell
# 実行ポリシーを確認
Get-ExecutionPolicy

# RemoteSigned に変更
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 再度有効化
.\venv\Scripts\Activate.ps1
```

### ケース3: 管理者権限が必要

PowerShellを管理者として実行：
1. Windowsキー → "PowerShell" と入力
2. 右クリック → "管理者として実行"
3. 再度コマンドを実行

---

## ✅ 次のステップ

Pythonのインストールが完了したら、以下を実行：

```powershell
# 1. ディレクトリ移動
cd "C:\Users\shohey sasaki\Documents\202510_techSWAT\20260124_tech0notta\backend_clone"

# 2. Pythonバージョン確認
python --version
# または
py --version

# 3. 仮想環境作成
python -m venv venv
# または
py -m venv venv

# 4. 仮想環境有効化
.\venv\Scripts\Activate.ps1

# 5. 依存パッケージインストール
pip install -r requirements.txt

# 6. サーバー起動
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# または
py -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. ブラウザでSwagger UIを開く
# http://localhost:8000/docs
```

---

## 📞 サポート

上記の方法でも解決しない場合は、以下の情報を共有してください：

```powershell
# システム情報
systeminfo | findstr /B /C:"OS Name" /C:"OS Version"

# Pythonの検索
where.exe python
where.exe py
where.exe python3

# 環境変数PATH
$env:PATH
```

---

## 🎯 推奨環境

- **OS**: Windows 10/11
- **Python**: 3.11 以上
- **PowerShell**: 5.1 以上
- **メモリ**: 4GB以上
- **ディスク**: 1GB以上の空き容量

---

以上の手順でPython環境をセットアップできます！
