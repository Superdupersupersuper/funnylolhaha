# Vercel Deployment Instructions - Updated Database

## What Changed
✅ **Database Updated:**
- Separated 519 tweets into `tweets` table
- Standardized speech types to 9 categories
- Added 1,257 new transcripts from RollCall (2024-2025)
- **Total: 2,645 speeches + 519 tweets**

✅ **Backend Fixed:**
- Updated date range query in `backend/server.js`
- Now handles mixed date formats correctly

## Files Ready for Deployment

1. **Database File:**
   - Location: `transcripts.db.zip` (11 MB compressed, 30 MB uncompressed)
   - Contains updated database with all changes

2. **Code Changes:**
   - `backend/server.js` - Fixed date range query
   - All code is in current directory

## Deploy to Vercel (Quick Method)

### Option 1: Using Vercel CLI (Recommended)
```bash
# Install Vercel CLI if you haven't
npm i -g vercel

# From this directory, run:
cd "/Users/alexandermiron/Desktop/Mention Market Tool"
vercel --prod
```

### Option 2: Manual Upload via Vercel Dashboard

1. Go to https://vercel.com/dashboard
2. Find your existing "mention-market" project
3. Click "Settings" → "Environment Variables"
4. Upload the database:
   - Upload `transcripts.db.zip` to a GitHub Release OR
   - Use a cloud storage service (Dropbox, Google Drive) and get a public download link
5. Redeploy the project

## Database Upload Options

### GitHub Release (Recommended)
```bash
# Create a GitHub repo if you haven't
# Then create a release and upload transcripts.db.zip

# The download URL will be:
# https://github.com/YOUR_USERNAME/mention-market/releases/download/v1.0/transcripts.db.zip
```

### Quick Test Locally
```bash
# Backend
cd backend
node server.js

# Frontend (in another terminal)
cd frontend
npm run dev
```

## Current Status
- ✅ Backend server: Working (port 3000)
- ✅ Frontend: Working (port 5175)
- ✅ Database: Updated and ready
- ⏳ Vercel deployment: Needs manual push

## Next Steps
1. Upload `transcripts.db.zip` to GitHub Releases or cloud storage
2. Get the public download URL
3. Update your Vercel deployment to download the database on build
4. Redeploy

Your local version is working perfectly at http://localhost:5175
