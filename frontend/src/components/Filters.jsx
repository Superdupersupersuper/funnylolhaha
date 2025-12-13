import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './Filters.css';

const API_BASE = 'http://localhost:3000/api';

function Filters({ filters, onFilterChange, stats }) {
  const [speechTypes, setSpeechTypes] = useState([]);

  useEffect(() => {
    fetchSpeechTypes();
  }, []);

  const fetchSpeechTypes = async () => {
    try {
      const response = await axios.get(`${API_BASE}/speech-types`);
      setSpeechTypes(response.data);
    } catch (err) {
      console.error('Failed to fetch speech types:', err);
    }
  };

  const handleChange = (field, value) => {
    onFilterChange({ [field]: value });
  };

  return (
    <div className="filters card">
      <h3>Filters</h3>
      <div className="filter-grid">
        <div className="filter-item">
          <label>Start Date</label>
          <input
            type="date"
            value={filters.startDate}
            onChange={(e) => handleChange('startDate', e.target.value)}
          />
        </div>

        <div className="filter-item">
          <label>End Date</label>
          <input
            type="date"
            value={filters.endDate}
            onChange={(e) => handleChange('endDate', e.target.value)}
          />
        </div>

        <div className="filter-item">
          <label>Speech Type</label>
          <select
            value={filters.speechType}
            onChange={(e) => handleChange('speechType', e.target.value)}
          >
            <option value="all">All Types</option>
            {speechTypes.map((type) => (
              <option key={type.speech_type} value={type.speech_type}>
                {type.speech_type} ({type.count})
              </option>
            ))}
          </select>
        </div>

        <div className="filter-item">
          <label>Search</label>
          <input
            type="text"
            placeholder="Search in titles or content..."
            value={filters.search}
            onChange={(e) => handleChange('search', e.target.value)}
          />
        </div>
      </div>

      {stats && (
        <div className="filter-stats">
          <div className="stat">
            <strong>{stats.totalTranscripts}</strong> Transcripts
          </div>
          <div className="stat">
            <strong>{stats.totalWords?.toLocaleString()}</strong> Total Words
          </div>
          <div className="stat">
            <strong>{stats.dateRange?.minDate}</strong> to <strong>{stats.dateRange?.maxDate}</strong>
          </div>
        </div>
      )}
    </div>
  );
}

export default Filters;
