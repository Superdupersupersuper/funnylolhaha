const https = require('https');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const DB_URL = 'https://github.com/Superdupersupersuper/funnylolhaha/releases/download/v2.0/transcripts.db.zip';
const DB_PATH = '/tmp/transcripts.db';

async function downloadDatabase() {
  return new Promise((resolve, reject) => {
    if (fs.existsSync(DB_PATH)) {
      resolve();
      return;
    }

    console.log('Downloading database...');
    const file = fs.createWriteStream('/tmp/transcripts.db.zip');

    https.get(DB_URL, (response) => {
      response.pipe(file);
      file.on('finish', () => {
        file.close();
        // Unzip
        exec('cd /tmp && unzip -o transcripts.db.zip && mv data/transcripts.db transcripts.db', (err) => {
          if (err) {
            console.error('Unzip error:', err);
            reject(err);
          } else {
            console.log('Database ready');
            resolve();
          }
        });
      });
    }).on('error', (err) => {
      fs.unlink('/tmp/transcripts.db.zip', () => {});
      reject(err);
    });
  });
}

exports.handler = async function(event, context) {
  // Enable CORS
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    await downloadDatabase();

    // Use better-sqlite3 which works on Netlify
    const Database = require('better-sqlite3');
    const db = new Database(DB_PATH, { readonly: true });

    const total = db.prepare('SELECT COUNT(*) as count FROM transcripts').get();
    const dates = db.prepare("SELECT MIN(date) as min, MAX(date) as max FROM transcripts WHERE date LIKE '____-__-__'").get();
    const types = db.prepare('SELECT DISTINCT speech_type FROM transcripts ORDER BY speech_type').all();

    db.close();

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        totalTranscripts: total.count,
        dateRange: { min: dates.min, max: dates.max },
        speechTypes: types.map(t => t.speech_type)
      })
    };
  } catch (error) {
    console.error('Error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: error.message })
    };
  }
};
