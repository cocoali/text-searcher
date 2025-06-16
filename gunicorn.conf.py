# Gunicorn設定ファイル
bind = "0.0.0.0:8000"
workers = 4
timeout = 120  # タイムアウトを120秒に設定
worker_class = "sync"
keepalive = 5
max_requests = 1000
max_requests_jitter = 50 