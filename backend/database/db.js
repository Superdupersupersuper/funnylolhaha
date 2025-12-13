const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const DB_PATH = process.env.DATABASE_PATH || './data/transcripts.db';

// Ensure data directory exists
const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
}

class DatabaseWrapper {
    constructor() {
        this.db = null;
    }

    async connect() {
        this.db = new Database(DB_PATH);
        console.log('Connected to SQLite database');
    }

    async initialize() {
        if (!this.db) await this.connect();

        const schema = fs.readFileSync(
            path.join(__dirname, 'schema.sql'),
            'utf8'
        );

        this.db.exec(schema);
        console.log('Database schema initialized');
    }

    async run(sql, params = []) {
        if (!this.db) await this.connect();
        const info = this.db.prepare(sql).run(params);
        return { lastID: info.lastInsertRowid, changes: info.changes };
    }

    async get(sql, params = []) {
        if (!this.db) await this.connect();
        return this.db.prepare(sql).get(params);
    }

    async all(sql, params = []) {
        if (!this.db) await this.connect();
        return this.db.prepare(sql).all(params);
    }

    async close() {
        if (this.db) {
            this.db.close();
            console.log('Database connection closed');
        }
    }
}

module.exports = new DatabaseWrapper();
