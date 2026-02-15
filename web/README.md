# MentionMarkets Web App

Next.js App Router application for uploading Otter.ai transcripts and searching mentions across political speeches, press conferences, and more.

## Features

- **Otter.ai Parser**: Upload TXT/SRT transcripts with automatic speaker detection and timing
- **Admin Panel**: Protected upload/edit/delete interface for managing transcripts
- **Public Search**: Keyword search across all transcript segments with filters (speaker, theme, date range)
- **Analytics**: Speaker breakdowns, turn counts, speaking time percentages
- **Dark Theme**: Modern UI with Tailwind CSS

## Local Development

### Prerequisites

- Node.js 18+
- PostgreSQL database

### Setup

1. **Install dependencies:**
   ```bash
   cd web
   npm install
   ```

2. **Configure environment variables:**
   
   Copy `.env` and update with your settings:
   ```bash
   # Database
   DATABASE_URL="postgresql://user:password@localhost:5432/mention_markets?schema=public"
   
   # Admin auth (change these!)
   ADMIN_PASSWORD="your-secure-password"
   ADMIN_SESSION_SECRET="random-32-char-secret-key-here"
   ```

3. **Initialize database:**
   ```bash
   npx prisma db push
   # Or for production migrations:
   npx prisma migrate dev
   ```

4. **Run dev server:**
   ```bash
   npm run dev
   ```

5. **Open app:**
   - Homepage: http://localhost:3000
   - Admin login: http://localhost:3000/admin/login
   - Search: http://localhost:3000/search

## Deployment (Render)

### Option 1: Using render.yaml Blueprint (Recommended)

1. **Rename `render-web.yaml` to `render.yaml`** in the repo root
2. **Push to GitHub**
3. **In Render Dashboard:**
   - Go to "Blueprints" → "New Blueprint Instance"
   - Connect your GitHub repo
   - Render will auto-create the Postgres DB + Web Service
4. **Set admin password:**
   - After deployment, go to your web service → Environment
   - Update `ADMIN_PASSWORD` to a secure value
   - Save (triggers redeploy)

### Option 2: Manual Setup

1. **Create PostgreSQL Database:**
   - In Render: New → PostgreSQL
   - Name: `mention-markets-db`
   - Plan: Starter ($7/mo) or Free
   - Copy the "Internal Database URL" after creation

2. **Create Web Service:**
   - In Render: New → Web Service
   - Connect your GitHub repo: `Superdupersupersuper/funnylolhaha`
   - Settings:
     - **Name**: `mention-markets-web`
     - **Root Directory**: `web`
     - **Environment**: `Node`
     - **Region**: `Ohio` (or nearest)
     - **Branch**: `main`
     - **Build Command**: 
       ```
       npm install && npx prisma generate && npm run build
       ```
     - **Start Command**: 
       ```
       npx prisma migrate deploy && npm start
       ```

3. **Environment Variables** (in web service settings):
   - `NODE_ENV` = `production`
   - `DATABASE_URL` = (paste Internal Database URL from step 1)
   - `ADMIN_PASSWORD` = (your secure password)
   - `ADMIN_SESSION_SECRET` = (generate 32+ random chars)

4. **Deploy:**
   - Save settings → Render auto-deploys
   - First deploy takes ~5 minutes
   - Visit your Render URL: `https://mention-markets-web.onrender.com`

## First Use

1. Visit `/admin/login`
2. Enter your `ADMIN_PASSWORD`
3. Go to `/admin/transcripts/new`
4. Upload an Otter.ai transcript (TXT or SRT):
   - Paste text or choose file
   - Click "Parse Transcript"
   - Review parsed segments
   - Fill in metadata (title, date, speaker, themes)
   - Click "Save Transcript"
5. Search at `/search`

## Database Schema

### Transcript
- `id` (uuid)
- `title`, `event_date`, `speech_type`, `primary_speaker`
- `speakers_present` (array), `key_themes` (array)
- `has_q_and_a` (boolean)
- `total_speech_length_seconds` (int, nullable)
- Timestamps: `created_at`, `updated_at`

### SpeakingSegment
- `id` (uuid)
- `transcriptId` (FK → Transcript, cascade delete)
- `speaker`, `start_seconds` (float), `end_seconds` (float, nullable)
- `text` (full segment content)

## Scripts

```bash
npm run dev          # Dev server (localhost:3000)
npm run build        # Production build
npm start            # Production server
npm run lint         # ESLint check
npx prisma studio    # Database GUI
npx prisma db push   # Sync schema (dev)
npx prisma migrate dev  # Create migration (dev)
npx prisma migrate deploy  # Apply migrations (prod)
```

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Database**: Prisma + PostgreSQL
- **Auth**: JWT session cookies (jose)
- **UI**: Tailwind CSS + custom components
- **Parser**: Custom Otter.ai TXT/SRT parser

## Folder Structure

```
web/
├── src/
│   ├── app/                 # Next.js App Router pages
│   │   ├── page.tsx         # Homepage
│   │   ├── search/          # Public search
│   │   ├── admin/           # Admin panel (auth-protected)
│   │   └── api/             # API routes
│   ├── components/
│   │   └── admin/           # Admin UI components
│   ├── lib/
│   │   ├── auth.ts          # JWT session logic
│   │   ├── db.ts            # Prisma client
│   │   └── parsers/
│   │       └── otter.ts     # Otter.ai parser
│   └── middleware.ts        # Route protection
├── prisma/
│   └── schema.prisma        # Database schema
└── package.json
```

## Troubleshooting

**"Database error" in admin:**
- Check `DATABASE_URL` is correct
- Run `npx prisma db push` to sync schema

**"Invalid password" on login:**
- Verify `ADMIN_PASSWORD` env var matches what you're entering

**Parser not detecting speakers:**
- Ensure Otter export includes timestamps
- Check format: `Speaker Name  M:SS  ` (Otter default) or `[MM:SS] Speaker: text`

**Build fails on Render:**
- Check build logs for missing env vars
- Ensure `DATABASE_URL` is set before build (needed for Prisma generate)

