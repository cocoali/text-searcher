import os

# 環境変数からポート番号を取得
port = os.environ.get('PORT', '8000')
bind = f"0.0.0.0:{port}"

# ワーカー設定
workers = int(os.environ.get('WEB_CONCURRENCY', 2))  # ワーカー数を減らす
timeout = int(os.environ.get('TIMEOUT', 120))
worker_class = "sync"
keepalive = 5
max_requests = 1000
max_requests_jitter = 50

# ログ設定
loglevel = "debug"
accesslog = "-"
errorlog = "-"
capture_output = True
enable_stdio_inheritance = True

# デバッグ設定
reload = False
preload_app = False 