#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# アプリケーションのルートディレクトリをPythonパスに追加
sys.path.insert(0, os.path.dirname(__file__))

from app import app

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
