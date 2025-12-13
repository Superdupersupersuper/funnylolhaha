require('dotenv').config();
const axios = require('axios');
const cheerio = require('cheerio');
const db = require('../database/db');
const { analyzeWordFrequency } = require('../utils/textAnalysis');

const BASE_URL = 'https://rollcall.com/factbase/trump/search/';
const DELAY_MS = parseInt(process.env.SCRAPE_DELAY_MS) || 2000;

class TranscriptScraper {
    constructor() {
        this.axios = axios.create({
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        });
    }

    async delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async saveTranscript(transcriptData) {
        try {
            const existing = await db.get(
                'SELECT id FROM transcripts WHERE url = ?',
                [transcriptData.url]
            );

            if (existing) {
                console.log(`Transcript already exists: ${transcriptData.title}`);
                return existing.id;
            }

            const wordCount = transcriptData.fullText.split(/\s+/).length;

            const result = await db.run(
                `INSERT INTO transcripts (title, date, speech_type, location, url, full_text, word_count)
                 VALUES (?, ?, ?, ?, ?, ?, ?)`,
                [
                    transcriptData.title,
                    transcriptData.date,
                    transcriptData.speechType,
                    transcriptData.location,
                    transcriptData.url,
                    transcriptData.fullText,
                    wordCount
                ]
            );

            console.log(`Saved transcript: ${transcriptData.title}`);

            const wordFreqs = analyzeWordFrequency(transcriptData.fullText);
            await this.saveWordFrequencies(result.lastID, wordFreqs);

            return result.lastID;
        } catch (error) {
            console.error('Error saving transcript:', error);
            throw error;
        }
    }

    async saveWordFrequencies(transcriptId, wordFrequencies) {
        const entries = Object.entries(wordFrequencies).slice(0, 500);

        for (const [word, frequency] of entries) {
            await db.run(
                'INSERT INTO word_frequencies (transcript_id, word, frequency) VALUES (?, ?, ?)',
                [transcriptId, word, frequency]
            );
        }
    }

    async run() {
        try {
            await db.initialize();

            console.log('NOTE: To properly scrape data, you need to manually inspect the website');
            console.log('and update the scraper with the correct selectors.');
            console.log('For now, adding sample data for testing...');

            // Sample data for testing
            const sampleTranscripts = [
                {
                    title: "Sample Rally Speech - Make America Great Again",
                    date: "2016-06-15",
                    speechType: "Rally",
                    location: "New York, NY",
                    url: "https://example.com/sample1",
                    fullText: "Thank you very much. It's great to be here. We are going to make America great again. We're going to bring back our jobs. We're going to bring back our borders. We're going to make our country safe again. And we're going to make America wealthy again. The American dream is dead, but we're going to make it bigger and better and stronger than ever before. We love our country and we're going to take care of our military. We're going to take care of our veterans. We're going to rebuild our infrastructure. Our roads, our bridges, our tunnels, our airports. We're going to make them the best in the world again. Thank you very much!"
                },
                {
                    title: "Press Conference on Economy",
                    date: "2016-08-20",
                    speechType: "Press Conference",
                    location: "Washington, DC",
                    url: "https://example.com/sample2",
                    fullText: "Thank you for being here. Today I want to talk about the economy. Our economy is in terrible shape. We have the worst recovery since the Great Depression. We need to cut taxes massively for the middle class. We need to reduce regulations that are killing our businesses. We need to renegotiate our terrible trade deals. China is taking advantage of us. Mexico is taking advantage of us. We're going to change that. We're going to bring businesses back to America. We're going to create millions of new jobs. High-paying jobs. Good jobs. American jobs. That's what we're going to do."
                },
                {
                    title: "Immigration Policy Speech",
                    date: "2016-09-01",
                    speechType: "Policy Speech",
                    location: "Phoenix, AZ",
                    url: "https://example.com/sample3",
                    fullText: "We will build a great wall along the southern border. And Mexico will pay for the wall. They don't know it yet, but they're going to pay for the wall. We need strong borders. We need law and order. We're going to end illegal immigration. We're going to protect American workers. We're going to put America first. Immigration is important, but it has to be legal immigration. We're a nation of laws. We're going to enforce our laws. We're going to take care of our citizens first. Americans first."
                }
            ];

            for (const transcript of sampleTranscripts) {
                await this.saveTranscript(transcript);
                await this.delay(100);
            }

            await db.run(
                `INSERT INTO scrape_metadata (last_scrape_date, total_transcripts_scraped, status, notes)
                 VALUES (datetime('now'), ?, 'completed', 'Sample data for testing')`,
                [sampleTranscripts.length]
            );

            console.log('Sample data loaded successfully!');
            console.log('To scrape real data, visit the website and update the scraper with correct CSS selectors.');
        } catch (error) {
            console.error('Error:', error);
            throw error;
        } finally {
            await db.close();
        }
    }
}

if (require.main === module) {
    const scraper = new TranscriptScraper();
    scraper.run().catch(console.error);
}

module.exports = TranscriptScraper;
