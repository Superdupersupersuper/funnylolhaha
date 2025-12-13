import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './TranscriptList.css';

const API_BASE = 'http://localhost:3000/api';

function TranscriptList({ filters }) {
  const [transcripts, setTranscripts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedTranscript, setSelectedTranscript] = useState(null);
  const [pagination, setPagination] = useState({
    total: 0,
    limit: 20,
    offset: 0
  });

  useEffect(() => {
    fetchTranscripts();
  }, [filters, pagination.offset]);

  const fetchTranscripts = async () => {
    try {
      setLoading(true);
      const params = {
        ...filters,
        limit: pagination.limit,
        offset: pagination.offset
      };
      const response = await axios.get(`${API_BASE}/transcripts`, { params });
      setTranscripts(response.data.transcripts);
      setPagination(prev => ({ ...prev, total: response.data.total }));
    } catch (err) {
      console.error('Failed to fetch transcripts:', err);
    } finally {
      setLoading(false);
    }
  };

  const viewTranscript = async (id) => {
    try {
      const response = await axios.get(`${API_BASE}/transcripts/${id}`);
      setSelectedTranscript(response.data);
    } catch (err) {
      console.error('Failed to fetch transcript details:', err);
    }
  };

  const nextPage = () => {
    if (pagination.offset + pagination.limit < pagination.total) {
      setPagination(prev => ({ ...prev, offset: prev.offset + prev.limit }));
    }
  };

  const prevPage = () => {
    if (pagination.offset > 0) {
      setPagination(prev => ({ ...prev, offset: Math.max(0, prev.offset - prev.limit) }));
    }
  };

  if (selectedTranscript) {
    return (
      <div className="transcript-detail card">
        <button onClick={() => setSelectedTranscript(null)} className="back-button">
          ← Back to List
        </button>
        <h2>{selectedTranscript.title}</h2>
        <div className="transcript-meta">
          <span>📅 {selectedTranscript.date}</span>
          <span>🎤 {selectedTranscript.speech_type}</span>
          {selectedTranscript.location && <span>📍 {selectedTranscript.location}</span>}
          <span>💬 {selectedTranscript.word_count?.toLocaleString()} words</span>
        </div>
        <div className="transcript-text">
          {selectedTranscript.full_text}
        </div>
        <a href={selectedTranscript.url} target="_blank" rel="noopener noreferrer" className="source-link">
          View Original Source →
        </a>
      </div>
    );
  }

  return (
    <div className="transcript-list">
      <h2>Transcripts</h2>

      {loading ? (
        <div className="loading">Loading transcripts...</div>
      ) : (
        <>
          <div className="transcript-count">
            Showing {pagination.offset + 1}-{Math.min(pagination.offset + pagination.limit, pagination.total)} of {pagination.total} transcripts
          </div>

          <div className="transcripts">
            {transcripts.map((transcript) => (
              <div key={transcript.id} className="transcript-card card">
                <h3>{transcript.title}</h3>
                <div className="transcript-meta">
                  <span>📅 {transcript.date}</span>
                  <span>🎤 {transcript.speech_type}</span>
                  {transcript.location && <span>📍 {transcript.location}</span>}
                  <span>💬 {transcript.word_count?.toLocaleString()} words</span>
                </div>
                <button onClick={() => viewTranscript(transcript.id)} className="view-button">
                  Read Transcript →
                </button>
              </div>
            ))}
          </div>

          <div className="pagination">
            <button onClick={prevPage} disabled={pagination.offset === 0}>
              ← Previous
            </button>
            <span>
              Page {Math.floor(pagination.offset / pagination.limit) + 1} of{' '}
              {Math.ceil(pagination.total / pagination.limit)}
            </span>
            <button
              onClick={nextPage}
              disabled={pagination.offset + pagination.limit >= pagination.total}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default TranscriptList;
