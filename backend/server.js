require('dotenv').config();
const express = require('express');
const cors = require('cors');
const db = require('./database/db');
const {
    analyzeWordFrequency,
    getTopWords,
    analyzeWordTrends,
    compareWordFrequencies,
    extractPhrases
} = require('./utils/textAnalysis');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

db.initialize().catch(console.error);

app.get('/api/transcripts', async (req, res) => {
    try {
        const {
            startDate,
            endDate,
            speechType,
            limit = 100,
            offset = 0,
            search
        } = req.query;

        let query = 'SELECT id, title, date, speech_type, location, url, word_count FROM transcripts WHERE 1=1';
        const params = [];

        if (startDate) {
            query += ' AND date >= ?';
            params.push(startDate);
        }

        if (endDate) {
            query += ' AND date <= ?';
            params.push(endDate);
        }

        if (speechType && speechType !== 'all') {
            query += ' AND speech_type = ?';
            params.push(speechType);
        }

        if (search) {
            query += ' AND (title LIKE ? OR full_text LIKE ?)';
            params.push(`%${search}%`, `%${search}%`);
        }

        query += ' ORDER BY date DESC LIMIT ? OFFSET ?';
        params.push(parseInt(limit), parseInt(offset));

        const transcripts = await db.all(query, params);

        const countQuery = query.split('ORDER BY')[0].replace(
            'SELECT id, title, date, speech_type, location, url, word_count',
            'SELECT COUNT(*) as count'
        ).split('LIMIT')[0];
        const countResult = await db.get(countQuery, params.slice(0, -2));

        res.json({
            transcripts,
            total: countResult.count,
            limit: parseInt(limit),
            offset: parseInt(offset)
        });
    } catch (error) {
        console.error('Error fetching transcripts:', error);
        res.status(500).json({ error: 'Failed to fetch transcripts' });
    }
});

app.get('/api/transcripts/:id', async (req, res) => {
    try {
        const transcript = await db.get(
            'SELECT * FROM transcripts WHERE id = ?',
            [req.params.id]
        );

        if (!transcript) {
            return res.status(404).json({ error: 'Transcript not found' });
        }

        res.json(transcript);
    } catch (error) {
        console.error('Error fetching transcript:', error);
        res.status(500).json({ error: 'Failed to fetch transcript' });
    }
});

app.get('/api/speech-types', async (req, res) => {
    try {
        const types = await db.all(
            'SELECT DISTINCT speech_type, COUNT(*) as count FROM transcripts GROUP BY speech_type ORDER BY count DESC'
        );
        res.json(types);
    } catch (error) {
        console.error('Error fetching speech types:', error);
        res.status(500).json({ error: 'Failed to fetch speech types' });
    }
});

app.get('/api/date-range', async (req, res) => {
    try {
        // Get dates and convert to sortable format
        const allDates = await db.all('SELECT DISTINCT date FROM transcripts ORDER BY date');
        const minDate = allDates[0]?.date || '';
        const maxDate = allDates[allDates.length - 1]?.date || '';

        res.json({ minDate, maxDate });
    } catch (error) {
        console.error('Error fetching date range:', error);
        res.status(500).json({ error: 'Failed to fetch date range' });
    }
});

app.get('/api/analysis/word-frequency', async (req, res) => {
    try {
        const {
            startDate,
            endDate,
            speechType,
            topN = 50,
            excludeCommon = 'true'
        } = req.query;

        let query = 'SELECT full_text FROM transcripts WHERE 1=1';
        const params = [];

        if (startDate) {
            query += ' AND date >= ?';
            params.push(startDate);
        }

        if (endDate) {
            query += ' AND date <= ?';
            params.push(endDate);
        }

        if (speechType && speechType !== 'all') {
            query += ' AND speech_type = ?';
            params.push(speechType);
        }

        const transcripts = await db.all(query, params);

        if (transcripts.length === 0) {
            return res.json({ words: [], totalWords: 0, transcriptCount: 0 });
        }

        const combinedText = transcripts.map(t => t.full_text).join(' ');
        const frequencies = analyzeWordFrequency(combinedText, {
            excludeCommon: excludeCommon === 'true',
            maxWords: parseInt(topN)
        });

        const words = Object.entries(frequencies).map(([word, freq]) => ({
            word,
            frequency: freq
        }));

        res.json({
            words,
            totalWords: combinedText.split(/\s+/).length,
            transcriptCount: transcripts.length
        });
    } catch (error) {
        console.error('Error analyzing word frequency:', error);
        res.status(500).json({ error: 'Failed to analyze word frequency' });
    }
});

app.get('/api/analysis/word-trend/:word', async (req, res) => {
    try {
        const { word } = req.params;
        const { startDate, endDate, speechType } = req.query;

        let query = 'SELECT id, title, date, speech_type, full_text FROM transcripts WHERE 1=1';
        const params = [];

        if (startDate) {
            query += ' AND date >= ?';
            params.push(startDate);
        }

        if (endDate) {
            query += ' AND date <= ?';
            params.push(endDate);
        }

        if (speechType && speechType !== 'all') {
            query += ' AND speech_type = ?';
            params.push(speechType);
        }

        query += ' ORDER BY date ASC';

        const transcripts = await db.all(query, params);
        const trends = analyzeWordTrends(transcripts, word);

        res.json({ word, trends });
    } catch (error) {
        console.error('Error analyzing word trend:', error);
        res.status(500).json({ error: 'Failed to analyze word trend' });
    }
});

app.post('/api/analysis/compare', async (req, res) => {
    try {
        const { group1, group2 } = req.body;

        const getTranscripts = async (filters) => {
            let query = 'SELECT full_text FROM transcripts WHERE 1=1';
            const params = [];

            if (filters.startDate) {
                query += ' AND date >= ?';
                params.push(filters.startDate);
            }

            if (filters.endDate) {
                query += ' AND date <= ?';
                params.push(filters.endDate);
            }

            if (filters.speechType && filters.speechType !== 'all') {
                query += ' AND speech_type = ?';
                params.push(filters.speechType);
            }

            return await db.all(query, params);
        };

        const transcripts1 = await getTranscripts(group1);
        const transcripts2 = await getTranscripts(group2);

        const comparison = compareWordFrequencies(transcripts1, transcripts2);

        res.json({
            comparison: comparison.slice(0, 100),
            group1Count: transcripts1.length,
            group2Count: transcripts2.length
        });
    } catch (error) {
        console.error('Error comparing word frequencies:', error);
        res.status(500).json({ error: 'Failed to compare word frequencies' });
    }
});

app.get('/api/analysis/phrases', async (req, res) => {
    try {
        const {
            startDate,
            endDate,
            speechType,
            phraseLength = 2,
            minFrequency = 3
        } = req.query;

        let query = 'SELECT full_text FROM transcripts WHERE 1=1';
        const params = [];

        if (startDate) {
            query += ' AND date >= ?';
            params.push(startDate);
        }

        if (endDate) {
            query += ' AND date <= ?';
            params.push(endDate);
        }

        if (speechType && speechType !== 'all') {
            query += ' AND speech_type = ?';
            params.push(speechType);
        }

        const transcripts = await db.all(query, params);

        if (transcripts.length === 0) {
            return res.json({ phrases: [] });
        }

        const combinedText = transcripts.map(t => t.full_text).join(' ');
        const phrases = extractPhrases(
            combinedText,
            parseInt(phraseLength),
            parseInt(minFrequency)
        );

        res.json({ phrases });
    } catch (error) {
        console.error('Error extracting phrases:', error);
        res.status(500).json({ error: 'Failed to extract phrases' });
    }
});

app.get('/api/stats', async (req, res) => {
    try {
        const totalTranscripts = await db.get('SELECT COUNT(*) as count FROM transcripts');
        const totalWords = await db.get('SELECT SUM(word_count) as total FROM transcripts');
        const dateRange = await db.get('SELECT MIN(date) as minDate, MAX(date) as maxDate FROM transcripts');
        const speechTypes = await db.all('SELECT speech_type, COUNT(*) as count FROM transcripts GROUP BY speech_type');

        res.json({
            totalTranscripts: totalTranscripts.count,
            totalWords: totalWords.total || 0,
            dateRange: dateRange,
            speechTypes: speechTypes
        });
    } catch (error) {
        console.error('Error fetching stats:', error);
        res.status(500).json({ error: 'Failed to fetch stats' });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
