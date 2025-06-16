timeout = 300  # タイムアウトを300秒に延長
workers = 2  # ワーカー数を2に制限
worker_class = 'sync'
keepalive = 5
max_requests = 100
max_requests_jitter = 10 