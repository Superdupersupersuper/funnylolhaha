#!/bin/bash
# Render startup script - initialize DB schema then start app

echo "🗄️ Initializing database schema..."
npx prisma db push --accept-data-loss --skip-generate

if [ $? -eq 0 ]; then
    echo "✅ Database schema ready"
else
    echo "⚠️ Schema push failed, but continuing anyway..."
fi

echo "🚀 Starting Next.js server..."
npm start

