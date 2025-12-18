#!/usr/bin/env python3
"""
Simple Flask app for Replit deployment
All-in-one file for easy hosting
"""
from flask import Flask, render_template_string, jsonify, request
from flask_cors import CORS
import sqlite3
import threading
import os
from full_scraper import FullScraper
from text_analysis import analyze_word_frequency, count_words

app = Flask(__name__)
CORS(app)

DB_PATH = './data/transcripts.db'
scraper_status = {'running': False, 'progress': 'Ready', 'last_run': None}

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mention Market Tool - Trump Transcripts</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { color: white; text-align: center; margin-bottom: 30px; }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .card {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-value { font-size: 2.5rem; font-weight: bold; }
        .stat-label { font-size: 1rem; opacity: 0.9; margin-top: 5px; }
        .refresh-btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 18px 40px;
            font-size: 1.2rem;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
        }
        .refresh-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
        .refresh-btn:disabled { background: #ccc; cursor: not-allowed; transform: none; }
        .status { margin-top: 20px; padding: 15px; border-radius: 8px; font-weight: 500; }
        .status-running { background: #fff3cd; color: #856404; }
        .status-success { background: #d4edda; color: #155724; }
        .year-bar { display: flex; align-items: center; margin-bottom: 10px; }
        .year-label { width: 80px; font-weight: 600; }
        .year-progress {
            flex: 1;
            height: 30px;
            background: #f0f0f0;
            border-radius: 15px;
            overflow: hidden;
            margin: 0 15px;
        }
        .year-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.5s ease;
        }
        .year-count { font-weight: 600; color: #667eea; min-width: 60px; text-align: right; }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s linear infinite;
            margin-left: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .progress-text { text-align: center; margin-top: 10px; color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Mention Market Tool</h1>
            <p>Trump Transcript Database - Live Updates</p>
        </div>

        <div class="card">
            <h2 style="margin-bottom: 20px;">Database Statistics</h2>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-value" id="totalTranscripts">---</div>
                    <div class="stat-label">Total Transcripts</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="totalWords">---</div>
                    <div class="stat-label">Total Words</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="dateRange">---</div>
                    <div class="stat-label">Date Range</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value" id="currentYear">---</div>
                    <div class="stat-label">Latest Year</div>
                </div>
            </div>
            <div id="yearChart"></div>
            <div class="progress-text" id="progressText">Scraper is running in background...</div>
        </div>

        <div class="card" style="text-align: center;">
            <h2 style="margin-bottom: 20px;">Scraper Control</h2>
            <p style="margin-bottom: 20px; color: #666;">
                Click to refresh and download the latest transcripts
            </p>
            <button class="refresh-btn" id="refreshBtn" onclick="triggerRefresh()">
                🔄 Refresh Transcripts
            </button>
            <div id="statusMessage"></div>
        </div>
    </div>

    <script>
        let autoRefresh = true;

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();

                document.getElementById('totalTranscripts').textContent = data.totalTranscripts.toLocaleString();
                document.getElementById('totalWords').textContent = data.totalWords.toLocaleString();

                if (data.dateRange.minDate && data.dateRange.maxDate) {
                    const minYear = data.dateRange.minDate.split('-')[0];
                    const maxYear = data.dateRange.maxDate.split('-')[0];
                    document.getElementById('dateRange').textContent = `${minYear} - ${maxYear}`;
                    document.getElementById('currentYear').textContent = maxYear;
                } else {
                    document.getElementById('dateRange').textContent = 'N/A';
                }

                // Year chart
                if (data.yearDistribution && data.yearDistribution.length > 0) {
                    const maxCount = Math.max(...data.yearDistribution.map(y => y.count));
                    const chartHTML = '<h3 style="margin: 20px 0 15px 0;">By Year</h3>' +
                        data.yearDistribution.map(year => `
                            <div class="year-bar">
                                <div class="year-label">${year.year}</div>
                                <div class="year-progress">
                                    <div class="year-fill" style="width: ${(year.count / maxCount) * 100}%"></div>
                                </div>
                                <div class="year-count">${year.count.toLocaleString()}</div>
                            </div>
                        `).join('');
                    document.getElementById('yearChart').innerHTML = chartHTML;
                }

                // Update progress text
                const latestYear = data.yearDistribution[data.yearDistribution.length - 1]?.year;
                if (latestYear && latestYear < '2024') {
                    document.getElementById('progressText').textContent =
                        `Currently collecting year ${latestYear} - More transcripts being added automatically...`;
                } else {
                    document.getElementById('progressText').textContent =
                        'Database is up to date! Click refresh to check for new transcripts.';
                }
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        async function triggerRefresh() {
            const btn = document.getElementById('refreshBtn');
            btn.disabled = true;
            btn.innerHTML = '🔄 Starting Scraper<span class="loading"></span>';

            try {
                const response = await fetch('/api/scraper/refresh', { method: 'POST' });
                const data = await response.json();

                if (data.status === 'started' || data.status === 'already_running') {
                    showStatus('Scraper is running! New transcripts will be added shortly...', 'running');
                    monitorScraper();
                } else {
                    showStatus('Error: ' + data.message, 'success');
                    btn.disabled = false;
                    btn.innerHTML = '🔄 Refresh Transcripts';
                }
            } catch (error) {
                showStatus('Error: ' + error.message, 'success');
                btn.disabled = false;
                btn.innerHTML = '🔄 Refresh Transcripts';
            }
        }

        function monitorScraper() {
            const interval = setInterval(async () => {
                try {
                    const response = await fetch('/api/scraper/status');
                    const data = await response.json();

                    if (!data.running) {
                        clearInterval(interval);
                        const btn = document.getElementById('refreshBtn');
                        btn.disabled = false;
                        btn.innerHTML = '🔄 Refresh Transcripts';

                        if (data.last_run) {
                            showStatus(`✅ Complete! Added ${data.last_run.success} new transcripts. Total: ${data.last_run.total}`, 'success');
                            loadStats();
                        }
                    } else {
                        showStatus('Scraper running: ' + data.progress, 'running');
                    }
                } catch (error) {
                    clearInterval(interval);
                }
            }, 3000);
        }

        function showStatus(message, type) {
            const statusDiv = document.getElementById('statusMessage');
            statusDiv.textContent = message;
            statusDiv.className = 'status status-' + type;
        }

        // Load stats on page load and every 10 seconds
        loadStats();
        setInterval(loadStats, 10000);
    </script>
</body>
</html>
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def run_scraper_async():
    global scraper_status
    scraper_status['running'] = True
    scraper_status['progress'] = 'Starting...'

    try:
        scraper = FullScraper()
        result = scraper.run(skip_existing=True)
        scraper_status['progress'] = f"Complete! Added {result['success']} transcripts"
        scraper_status['last_run'] = result
    except Exception as e:
        scraper_status['progress'] = f'Error: {str(e)}'
    finally:
        scraper_status['running'] = False

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stats')
def get_stats():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM transcripts")
    total = cursor.fetchone()['count']

    cursor.execute("SELECT SUM(word_count) as total FROM transcripts")
    total_words = cursor.fetchone()['total'] or 0

    cursor.execute("""
        SELECT
            MIN(CASE WHEN date LIKE '____-__-__' THEN date END) as min_date,
            MAX(CASE WHEN date LIKE '____-__-__' THEN date END) as max_date
        FROM transcripts
    """)
    date_range = cursor.fetchone()

    cursor.execute("""
        SELECT
            SUBSTR(date, 1, 4) as year,
            COUNT(*) as count
        FROM transcripts
        WHERE date LIKE '____-__-__'
        GROUP BY SUBSTR(date, 1, 4)
        ORDER BY year
    """)
    years = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'totalTranscripts': total,
        'totalWords': total_words,
        'dateRange': {
            'minDate': date_range['min_date'],
            'maxDate': date_range['max_date']
        },
        'yearDistribution': years
    })

@app.route('/api/scraper/refresh', methods=['POST'])
def refresh_scraper():
    global scraper_status

    if scraper_status['running']:
        return jsonify({
            'status': 'already_running',
            'message': 'Scraper is already running',
            'progress': scraper_status['progress']
        })

    thread = threading.Thread(target=run_scraper_async)
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'started', 'message': 'Scraper started'})

@app.route('/api/scraper/status')
def scraper_status_endpoint():
    return jsonify(scraper_status)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
