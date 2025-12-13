import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './WordFrequency.css';

const API_BASE = 'http://localhost:3000/api';

function WordFrequency({ filters }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [topN, setTopN] = useState(50);
  const [excludeCommon, setExcludeCommon] = useState(true);

  useEffect(() => {
    fetchWordFrequency();
  }, [filters, topN, excludeCommon]);

  const fetchWordFrequency = async () => {
    try {
      setLoading(true);
      const params = {
        ...filters,
        topN,
        excludeCommon: excludeCommon.toString()
      };
      const response = await axios.get(`${API_BASE}/analysis/word-frequency`, { params });
      setData(response.data);
    } catch (err) {
      console.error('Failed to fetch word frequency:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Analyzing word frequency...</div>;
  }

  if (!data || data.words.length === 0) {
    return (
      <div className="card">
        <h2>Word Frequency</h2>
        <p>No data available. Make sure you have transcripts in the selected date range.</p>
      </div>
    );
  }

  const maxFreq = data.words[0]?.frequency || 1;

  return (
    <div className="word-frequency">
      <h2>Word Frequency Analysis</h2>

      <div className="card">
        <div className="controls">
          <div className="control-item">
            <label>Top Words:</label>
            <select value={topN} onChange={(e) => setTopN(parseInt(e.target.value))}>
              <option value="25">Top 25</option>
              <option value="50">Top 50</option>
              <option value="100">Top 100</option>
              <option value="200">Top 200</option>
            </select>
          </div>

          <div className="control-item">
            <label>
              <input
                type="checkbox"
                checked={excludeCommon}
                onChange={(e) => setExcludeCommon(e.target.checked)}
              />
              Exclude common words
            </label>
          </div>
        </div>

        <div className="stats-summary">
          <div>
            <strong>{data.transcriptCount}</strong> transcripts analyzed
          </div>
          <div>
            <strong>{data.totalWords?.toLocaleString()}</strong> total words
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Top {topN} Words</h3>
        <div className="word-list">
          {data.words.map((item, index) => (
            <div key={item.word} className="word-item">
              <div className="word-rank">{index + 1}</div>
              <div className="word-name">{item.word}</div>
              <div className="word-bar-container">
                <div
                  className="word-bar"
                  style={{ width: `${(item.frequency / maxFreq) * 100}%` }}
                ></div>
              </div>
              <div className="word-freq">{item.frequency.toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default WordFrequency;
