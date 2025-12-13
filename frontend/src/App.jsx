import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Dashboard from './components/Dashboard';
import Filters from './components/Filters';
import TranscriptList from './components/TranscriptList';
import WordFrequency from './components/WordFrequency';
import WordTrend from './components/WordTrend';
import './App.css';

const API_BASE = 'http://localhost:3000/api';

function App() {
  const [stats, setStats] = useState(null);
  const [filters, setFilters] = useState({
    startDate: '2016-01-01',
    endDate: new Date().toISOString().split('T')[0],
    speechType: 'all',
    search: ''
  });
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_BASE}/stats`);
      setStats(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to load statistics. Make sure the backend server is running.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (newFilters) => {
    setFilters({ ...filters, ...newFilters });
  };

  if (loading && !stats) {
    return (
      <div className="container">
        <div className="loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="container">
          <h1>Mention Market Tool</h1>
          <p>Donald Trump Speech Transcript Analysis</p>
        </div>
      </header>

      <div className="container">
        {error && <div className="error">{error}</div>}

        <Filters
          filters={filters}
          onFilterChange={handleFilterChange}
          stats={stats}
        />

        <div className="tabs">
          <button
            className={activeTab === 'dashboard' ? 'active' : ''}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button
            className={activeTab === 'transcripts' ? 'active' : ''}
            onClick={() => setActiveTab('transcripts')}
          >
            Transcripts
          </button>
          <button
            className={activeTab === 'word-frequency' ? 'active' : ''}
            onClick={() => setActiveTab('word-frequency')}
          >
            Word Frequency
          </button>
          <button
            className={activeTab === 'word-trend' ? 'active' : ''}
            onClick={() => setActiveTab('word-trend')}
          >
            Word Trends
          </button>
        </div>

        <div className="tab-content">
          {activeTab === 'dashboard' && <Dashboard stats={stats} filters={filters} />}
          {activeTab === 'transcripts' && <TranscriptList filters={filters} />}
          {activeTab === 'word-frequency' && <WordFrequency filters={filters} />}
          {activeTab === 'word-trend' && <WordTrend filters={filters} />}
        </div>
      </div>
    </div>
  );
}

export default App;
