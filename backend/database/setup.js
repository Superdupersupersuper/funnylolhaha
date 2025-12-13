require('dotenv').config();
const db = require('./db');

async function setup() {
    try {
        console.log('Setting up database...');
        await db.initialize();
        console.log('Database setup complete!');
        process.exit(0);
    } catch (error) {
        console.error('Error setting up database:', error);
        process.exit(1);
    }
}

setup();
