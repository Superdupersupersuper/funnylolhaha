# Deployment Guide

## Quick Deploy to Render (Recommended)

### Why Render?
- ✅ Free tier available
- ✅ Auto-deploys from GitHub
- ✅ Supports Python Flask natively
- ✅ Includes free PostgreSQL database
- ✅ Free SSL/HTTPS

### Steps:

1. **Push to GitHub** (Already done! ✓)
   Your code is at: https://github.com/Superdupersupersuper/funnylolhaha

2. **Sign up for Render**
   - Go to: https://render.com/
   - Sign up with your GitHub account

3. **Create New Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repo: `Superdupersupersuper/funnylolhaha`
   - Render will auto-detect it's a Python app

4. **Configure the Service**
   - **Name**: `mention-markets-api`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn api_server:app`
   - **Plan**: Free

5. **Add Environment Variables** (Optional)
   ```
   MENTION_MARKETS_DB_PATH=/opt/render/project/src/data/transcripts.db
   ```

6. **Deploy!**
   - Click "Create Web Service"
   - Render will automatically deploy
   - Your API will be live at: `https://mention-markets-api.onrender.com`

### Database Considerations

**Option A: Keep SQLite (Simple)**
- SQLite file is in your repo (52MB)
- Works immediately
- ⚠️ Free tier doesn't persist files between deployments
- Good for: Testing, prototypes

**Option B: Upgrade to PostgreSQL (Production)**
- Render offers free PostgreSQL
- Better for production
- Data persists between deployments
- Requires migration script

---

## Alternative: Deploy to Vercel

Vercel is great for static sites but doesn't support long-running Python processes well. Best used for just the frontend:

1. **Deploy Frontend Only**
   - Connect GitHub repo to Vercel
   - It will deploy `analytics_ui.html`
   - Configure API URL to point to Render backend

2. **Deploy Backend Separately**
   - Use Render/Railway for the API
   - Update `analytics_ui.html` API_BASE to point to your deployed API

---

## Current Vercel Deployment

Your repo already has a Vercel deployment at:
**https://funnylolhaha.vercel.app**

To update it:
1. Vercel auto-deploys from GitHub
2. Just push to main branch (which we just did!)
3. It should rebuild automatically

---

## Local Development

### Start API Server:
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 api_server.py
```

### Start UI Server:
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 -m http.server 8080
```

### Open in browser:
http://localhost:8080/analytics_ui.html

---

## Production URLs (After Deployment)

After deploying to Render:
- **API**: `https://mention-markets-api.onrender.com/api/health`
- **Frontend**: `https://funnylolhaha.vercel.app`

Update `analytics_ui.html` line 1608:
```javascript
const API_BASE = 'https://mention-markets-api.onrender.com';
```

---

## Database Migration to PostgreSQL (Optional)

If you want to use PostgreSQL on Render:

1. **Create PostgreSQL Database** in Render
2. **Install psycopg2** in requirements.txt
3. **Update api_server.py** to use PostgreSQL instead of SQLite
4. **Migrate data** from SQLite to PostgreSQL

I can help with this migration if needed!

---

## Monitoring & Health Checks

Once deployed, monitor your API:
- **Health Check**: `/api/health`
- **Stats**: `/api/stats`
- **Transcripts**: `/api/transcripts`

Render free tier:
- ⚠️ Spins down after 15 min of inactivity
- ⚠️ Cold start takes ~30 seconds
- ✅ Automatically wakes up on request

---

## Next Steps

1. ✅ Code pushed to GitHub
2. ⬜ Sign up for Render
3. ⬜ Connect GitHub repo
4. ⬜ Deploy API
5. ⬜ Update frontend API_BASE URL
6. ⬜ Test production deployment

**Let me know when you're ready to deploy and I'll guide you through it!**

