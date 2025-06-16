# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import base64
import os
import json
from datetime import datetime, timedelta
from functools import wraps
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)  # セッション用の秘密鍵

# レート制限の設定
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# ユーザー認証用のデコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ユーザー情報（本番環境ではデータベースを使用することを推奨）
USERS = {
    'admin': 'b65fe679c5abc007b55e3dfd28b782d5b9b2cc75fa739ccda4e751fa35e7a905378e05edf99169596f73864d545fdcf5f638f9d9e847bc8c2e3d6626318d0e31'  # 'password123'のSHA512ハッシュ値
}

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # パスワードのSHA512ハッシュを計算
        password_hash = hashlib.sha512(password.encode()).hexdigest()
        
        if username in USERS and USERS[username] == password_hash:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='ユーザー名またはパスワードが正しくありません。')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=session['user'])

@app.route('/history')
@login_required
def history():
    """検索履歴ページを表示"""
    try:
        with open('search_history.json', 'r', encoding='utf-8') as f:
            history = json.load(f)
    except FileNotFoundError:
        history = []
    
    # 履歴を日時でソート（新しい順）
    history.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
    
    return render_template('history.html', history=history)

class WebTextSearcher:
    def __init__(self):
        self.timeout = 10
        self.visited_urls = set()
        self.max_depth = 3
        self.max_pages = 100
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.history_file = 'search_history.json'
        self.load_history()

    def load_history(self):
        """検索履歴を読み込む"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.search_history = json.load(f)
            except:
                self.search_history = {}
        else:
            self.search_history = {}

    def save_history(self):
        """検索履歴を保存"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(self.search_history, f, ensure_ascii=False, indent=2)

    def _highlight_text(self, text, search_text):
        """検索テキストをハイライト表示"""
        pattern = re.compile(re.escape(search_text), re.IGNORECASE)
        return pattern.sub(lambda m: f'<mark>{m.group()}</mark>', text)

    def _is_same_domain(self, url, base_url):
        """同じドメインかチェック"""
        try:
            return urlparse(url).netloc == urlparse(base_url).netloc
        except:
            return False

    def search(self, url, search_text, auth=None, skip_visited=True):
        """指定されたURLから検索を開始"""
        print(f"検索開始: URL={url}, 検索テキスト={search_text}")
        self.visited_urls = set()
        results = []
        
        # 検索履歴から既に検索済みのURLを取得
        if skip_visited and search_text in self.search_history:
            self.visited_urls.update(self.search_history[search_text]['urls'])
            print(f"既に検索済みのURL数: {len(self.visited_urls)}")
        
        try:
            self._search_page(url, search_text, depth=0, results=results, auth=auth)
            
            # 検索履歴を更新
            if search_text not in self.search_history:
                self.search_history[search_text] = {
                    'urls': [],
                    'results': [],
                    'last_updated': datetime.now().isoformat()
                }
            
            # 新しい結果を追加
            self.search_history[search_text]['urls'].extend(list(self.visited_urls))
            self.search_history[search_text]['results'].extend(results)
            self.search_history[search_text]['last_updated'] = datetime.now().isoformat()
            
            # 重複を除去
            self.search_history[search_text]['urls'] = list(set(self.search_history[search_text]['urls']))
            
            self.save_history()
            
            return {
                'success': True,
                'results': results,
                'total_pages': len(self.visited_urls)
            }
        except Exception as e:
            print(f"検索中にエラー: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _search_page(self, url, search_text, depth=0, results=None, auth=None):
        """ページを検索し、結果を追加"""
        if results is None:
            results = []
            
        if (url in self.visited_urls or 
            depth > self.max_depth or 
            len(self.visited_urls) >= self.max_pages):
            return
            
        self.visited_urls.add(url)
        print(f"ページを検索中: {url} (深さ: {depth})")
        
        try:
            # ページを取得
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            if auth:
                auth_str = f"{auth['username']}:{auth['password']}"
                auth_bytes = auth_str.encode('ascii')
                base64_bytes = base64.b64encode(auth_bytes)
                headers['Authorization'] = f"Basic {base64_bytes.decode('ascii')}"
            
            response = self.session.get(url, timeout=self.timeout, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ページの検索結果を格納
            page_results = {
                'url': url,
                'title': soup.find('title').get_text() if soup.find('title') else url,
                'depth': depth,
                'body_matches': [],
                'head_matches': [],
                'href_matches': []
            }
            
            # 本文の検索
            text = soup.get_text()
            clean_text = ' '.join(text.split())
            if search_text.lower() in clean_text.lower():
                highlighted_text = self._highlight_text(clean_text, search_text)
                page_results['body_matches'] = [highlighted_text]
            
            # headタグ内の検索
            head = soup.find('head')
            if head:
                head_text = head.get_text()
                if search_text.lower() in head_text.lower():
                    highlighted_text = self._highlight_text(head_text, search_text)
                    page_results['head_matches'] = [highlighted_text]
            
            # href属性の検索
            for link in soup.find_all('a', href=True):
                href = link['href']
                link_text = link.get_text().strip()
                
                try:
                    # 相対URLを絶対URLに変換
                    full_url = urljoin(url, href)
                    normalized_url = full_url.rstrip('/')
                    
                    # 検索テキストが数字の場合の特別な処理
                    if search_text.isdigit():
                        if f"/journal/{search_text}" in normalized_url:
                            highlighted_url = self._highlight_text(full_url, search_text)
                            highlighted_text = self._highlight_text(link_text, search_text) if link_text else highlighted_url
                            page_results['href_matches'].append({
                                'text': highlighted_text,
                                'href': highlighted_url,
                                'original_url': full_url,
                                'page_url': url
                            })
                    # 通常のテキスト検索
                    elif search_text.lower() in normalized_url.lower() or search_text.lower() in link_text.lower():
                        highlighted_url = self._highlight_text(full_url, search_text)
                        highlighted_text = self._highlight_text(link_text, search_text) if link_text else highlighted_url
                        page_results['href_matches'].append({
                            'text': highlighted_text,
                            'href': highlighted_url,
                            'original_url': full_url,
                            'page_url': url
                        })
                except Exception as e:
                    print(f"リンクの処理中にエラー: {href} - {str(e)}")
                    continue
            
            # マッチがある場合のみ結果に追加
            if any([page_results['body_matches'], page_results['head_matches'], page_results['href_matches']]):
                # 同じURLの結果が既に存在する場合は、より深い階層の結果を優先
                existing_result = next((r for r in results if r['url'] == url), None)
                if existing_result is None or existing_result['depth'] > depth:
                    if existing_result is not None:
                        results.remove(existing_result)
                    results.append(page_results)
            
            # 次の階層のリンクを取得
            if depth < self.max_depth:
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    try:
                        full_url = urljoin(url, href)
                        if self._is_same_domain(full_url, url) and full_url not in self.visited_urls:
                            self._search_page(full_url, search_text, depth + 1, results, auth)
                    except Exception as e:
                        print(f"リンクの処理中にエラー: {href} - {str(e)}")
                        continue
                        
        except Exception as e:
            print(f"ページの検索中にエラー: {url} - {str(e)}")

@app.route('/search', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def search():
    """検索を実行"""
    url = request.form.get('url')
    search_text = request.form.get('search_text')
    is_research = request.form.get('is_research') == 'true'
    
    if not url or not search_text:
        return jsonify({'error': 'URLと検索テキストを入力してください。'})
    
    try:
        # 検索履歴を読み込む
        try:
            with open('search_history.json', 'r', encoding='utf-8') as f:
                history = json.load(f)
        except FileNotFoundError:
            history = []
        
        # 前回の検索結果を取得
        previous_results = None
        if is_research and history and isinstance(history, list) and len(history) > 0:
            previous_results = history[0]  # 最新の検索結果
        
        # 検索を実行
        searcher = WebTextSearcher()
        results = searcher.search(url, search_text)
        
        if results['success']:
            # 検索結果を整形
            formatted_results = []
            for result in results.get('results', []):
                match_count = 0
                body_matches = result.get('body_matches', [])
                head_matches = result.get('head_matches', [])
                href_matches = result.get('href_matches', [])
                
                if body_matches:
                    match_count += len(body_matches)
                if head_matches:
                    match_count += len(head_matches)
                if href_matches:
                    match_count += len(href_matches)
                
                snippets = []
                if body_matches:
                    snippets.extend(body_matches)
                if head_matches:
                    snippets.extend(head_matches)
                
                # href_matchesの各要素が辞書であることを保証し、リンクテキストとURLをセット
                href_snippets = []
                for h in href_matches:
                    try:
                        if isinstance(h, dict):
                            text = h.get('text', '')
                            url = h.get('original_url', h.get('href', ''))
                            href_snippets.append({'text': text, 'url': url})
                        elif isinstance(h, str):
                            href_snippets.append({'text': h, 'url': h})
                    except Exception as e:
                        print(f"href_matchの処理中にエラー: {str(e)}")
                        continue
                
                formatted_results.append({
                    'url': result.get('url', ''),
                    'title': result.get('title', '') or result.get('url', ''),
                    'depth': result.get('depth', 0),  # 階層情報を追加
                    'matches': match_count,
                    'body_matches': body_matches,
                    'head_matches': head_matches,
                    'href_matches': href_snippets,
                    'snippets': snippets
                })
            
            # 検索履歴に追加
            history_entry = {
                'search_text': search_text,
                'base_url': url,
                'results': formatted_results,
                'total_urls': results.get('total_pages', 0),
                'total_results': len(formatted_results),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_research': is_research
            }
            
            # 前回の検索結果がある場合、未検索のURLを追加
            if is_research and previous_results:
                previous_urls = {result['url'] for result in previous_results['results']}
                new_urls = {result['url'] for result in formatted_results}
                skipped_urls = previous_urls - new_urls
                
                if skipped_urls:
                    history_entry['skipped_urls'] = list(skipped_urls)
                    history_entry['skipped_count'] = len(skipped_urls)
            
            # 履歴を更新
            history.insert(0, history_entry)
            
            # 履歴を保存（最新の10件のみ保持）
            with open('search_history.json', 'w', encoding='utf-8') as f:
                json.dump(history[:10], f, ensure_ascii=False, indent=2)
            
            return jsonify({
                'success': True,
                'results': formatted_results,
                'total_pages': results.get('total_pages', 0),
                'total_results': len(formatted_results),
                'is_research': is_research,
                'skipped_urls': history_entry.get('skipped_urls', []),
                'skipped_count': history_entry.get('skipped_count', 0)
            })
        else:
            return jsonify({'error': results['error']})
    
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/search_history', methods=['GET'])
@login_required
def get_search_history():
    """検索履歴を取得"""
    try:
        if os.path.exists('search_history.json'):
            with open('search_history.json', 'r', encoding='utf-8') as f:
                history = json.load(f)
            return jsonify({
                'success': True,
                'history': history
            })
        return jsonify({
            'success': True,
            'history': []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'success': False,
        'error': 'リクエストが多すぎます。しばらく待ってから再試行してください。'
    }), 429

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
