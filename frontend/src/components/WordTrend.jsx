import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './WordTrend.css';

const API_BASE = 'http://localhost:3000/api';

function WordTrend({ filters }) {
  const [word, setWord] = useState('');
  const [searchWord, setSearchWord] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = () => {
    if (word.trim()) {
      setSearchWord(word.trim().toLowerCase());
    }
  };

  useEffect(() => {
    if (searchWord) {
      fetchWordTrend();
    }
  }, [searchWord, filters]);

  const fetchWordTrend = async () => {
    try {
      setLoading(true);
      const params = { ...filters };
      const response = await axios.get(`${API_BASE}/analysis/word-trend/${searchWord}`, { params });
      setData(response.data);
    } catch (err) {
      console.error('Failed to fetch word trend:', err);
    } finally {
      setLoading(false);
    }
  };

  const totalMentions = data?.trends.reduce((sum, item) => sum + item.count, 0) || 0;

  return (
    <div className="word-trend">
      <h2>Word Trend Analysis</h2>

      <div className="card">
        <div className="search-bar">
          <input
            type="text"
            placeholder="Enter a word to track (e.g., 'economy', 'border', 'china')..."
            value={word}
            onChange={(e) => setWord(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          />
          <button onClick={handleSearch} className="search-button">
            Search
          </button>
        </div>

        {searchWord && (
          <div className="search-info">
            Tracking: <strong>"{searchWord}"</strong>
          </div>
        )}
      </div>

      {loading && <div className="loading">Analyzing word trend...</div>}

      {!loading && data && (
        <>
          <div className="card">
            <h3>Summary</h3>
            <div className="trend-summary">
              <div className="summary-stat">
                <div className="summary-label">Total Mentions</div>
                <div className="summary-value">{totalMentions.toLocaleString()}</div>
              </div>
              <div className="summary-stat">
                <div className="summary-label">Speeches Containing Word</div>
                <div className="summary-value">
                  {data.trends.filter(t => t.count > 0).length}
                </div>
              </div>
              <div className="summary-stat">
                <div className="summary-label">Average per Speech</div>
                <div className="summary-value">
                  {data.trends.length > 0
                    ? (totalMentions / data.trends.length).toFixed(1)
                    : '0'}
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Timeline</h3>
            {data.trends.length === 0 ? (
              <p>No mentions found in the selected date range.</p>
            ) : (
              <div className="trend-timeline">
                {data.trends.map((item, index) => (
                  <div key={index} className="trend-item">
                    <div className="trend-date">{item.date}</div>
                    <div className="trend-info">
                      <div className="trend-title">{item.title}</div>
                      <div className="trend-meta">
                        <span className="trend-type">{item.speechType}</span>
                        <span className="trend-count">
                          {item.count} {item.count === 1 ? 'mention' : 'mentions'}
                        </span>
                      </div>
                    </div>
                    <div className="trend-bar-container">
                      <div
                        className="trend-bar"
                        style={{
                          width: `${(item.count / Math.max(...data.trends.map(t => t.count))) * 100}%`
                        }}
                      ></div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {!loading && !data && (
        <div className="card empty-state">
          <p>Enter a word above to see how frequently it appears across different speeches over time.</p>
          <p className="hint">
            Try words like: "economy", "immigration", "jobs", "china", "america", "great"
          </p>
        </div>
      )}
    </div>
  );
}

export default WordTrend;
