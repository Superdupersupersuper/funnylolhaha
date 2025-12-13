import React from 'react';
import './Dashboard.css';

function Dashboard({ stats, filters }) {
  if (!stats) {
    return <div className="loading">Loading statistics...</div>;
  }

  return (
    <div className="dashboard">
      <h2>Overview</h2>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">📄</div>
          <div className="stat-value">{stats.totalTranscripts}</div>
          <div className="stat-label">Total Transcripts</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">💬</div>
          <div className="stat-value">{stats.totalWords?.toLocaleString()}</div>
          <div className="stat-label">Total Words</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">📅</div>
          <div className="stat-value">
            {stats.dateRange?.minDate && stats.dateRange?.maxDate
              ? `${new Date(stats.dateRange.minDate).getFullYear()} - ${new Date(stats.dateRange.maxDate).getFullYear()}`
              : 'N/A'}
          </div>
          <div className="stat-label">Date Range</div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">🎤</div>
          <div className="stat-value">{stats.speechTypes?.length || 0}</div>
          <div className="stat-label">Speech Types</div>
        </div>
      </div>

      <div className="card">
        <h3>Speech Types Breakdown</h3>
        <div className="speech-types-list">
          {stats.speechTypes?.map((type) => (
            <div key={type.speech_type} className="speech-type-item">
              <div className="speech-type-name">{type.speech_type}</div>
              <div className="speech-type-bar">
                <div
                  className="speech-type-fill"
                  style={{
                    width: `${(type.count / stats.totalTranscripts) * 100}%`
                  }}
                ></div>
              </div>
              <div className="speech-type-count">{type.count}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Active Filters</h3>
        <div className="active-filters">
          <div><strong>Date Range:</strong> {filters.startDate} to {filters.endDate}</div>
          <div><strong>Speech Type:</strong> {filters.speechType === 'all' ? 'All Types' : filters.speechType}</div>
          {filters.search && <div><strong>Search:</strong> "{filters.search}"</div>}
        </div>
      </div>

      <div className="card info-box">
        <h3>Getting Started</h3>
        <ol>
          <li>Use the filters above to select your date range and speech types</li>
          <li>Navigate to "Word Frequency" to see the most common words used</li>
          <li>Check "Word Trends" to track specific words over time</li>
          <li>Browse "Transcripts" to read individual speeches</li>
        </ol>
        {stats.totalTranscripts === 0 && (
          <div className="warning">
            <strong>No transcripts found!</strong> Run the scraper first: <code>npm run scrape</code>
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
