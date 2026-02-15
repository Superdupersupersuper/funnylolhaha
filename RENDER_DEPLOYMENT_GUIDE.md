# 🚀 Render Deployment Guide - MentionMarkets Web App

This guide will walk you through deploying the new Next.js app to Render alongside your existing Flask app.

## Current Setup

- **Existing Service**: `funnylolhaha.onrender.com` (Flask/SQLite app)
- **New Service**: Next.js app in `/web` folder (requires Postgres)

## 🎯 Quick Deploy (Recommended)

### Step 1: In Render Dashboard

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
   - **Name**: `mention-markets-db`
   - **Database**: `mention_markets`
   - **User**: `mention_markets_user`
   - **Region**: Ohio (or closest to you)
   - **Plan**: **Starter ($7/mo)** *(Free tier has limitations)*
   - Click **"Create Database"**
   - ⏱️ Wait ~2 minutes for provisioning
   - **Copy the "Internal Database URL"** (looks like `postgresql://mention_markets_user:...@...render.com/mention_markets`)

### Step 2: Create Web Service

1. Click **"New +"** → **"Web Service"**
2. **Connect Repository**:
   - Select your GitHub repo: `Superdupersupersuper/funnylolhaha`
   - Click **"Connect"**

3. **Configure Service**:
   - **Name**: `mention-markets-web` (or anything you like)
   - **Root Directory**: `web`
   - **Environment**: `Node`
   - **Region**: `Ohio` (same as DB)
   - **Branch**: `main`
   - **Build Command**:
     ```bash
     npm install && npx prisma generate && npm run build
     ```
   - **Start Command**:
     ```bash
     npx prisma migrate deploy && npm start
     ```
   - **Plan**: Free or Starter

4. **Environment Variables** (click "Add Environment Variable"):
   
   | Key | Value |
   |-----|-------|
   | `NODE_ENV` | `production` |
   | `DATABASE_URL` | *(paste Internal Database URL from Step 1)* |
   | `ADMIN_PASSWORD` | `YourSecurePassword123!` *(change this!)* |
   | `ADMIN_SESSION_SECRET` | *(generate random 32+ chars)* |

   **To generate session secret**, run in your terminal:
   ```bash
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   ```

5. Click **"Create Web Service"**

### Step 3: Wait for Deployment

- First build takes ~5 minutes
- Watch the logs in Render dashboard
- Look for: ✅ `Build successful` → ✅ `Deploy live`
- Your app will be at: `https://mention-markets-web.onrender.com` (or your chosen name)

### Step 4: Initialize & Test

1. Visit `https://your-service.onrender.com/admin/login`
2. Enter your `ADMIN_PASSWORD`
3. Upload a transcript:
   - Go to `/admin/transcripts/new`
   - Upload the Mamdani transcript from `transcripts/mamdani/`
   - Parse → Preview → Save
4. Test search: `/search`

## ✅ Success Checklist

- [ ] Postgres DB created & running
- [ ] Web service deployed successfully
- [ ] Can access admin login page
- [ ] Admin password works
- [ ] Can upload & parse Otter transcript
- [ ] Transcript appears in list
- [ ] Search finds mentions

## 🔧 Troubleshooting

### Build Fails: "Cannot find module '@prisma/client'"

**Cause**: Prisma client not generated before build.

**Fix**: Ensure build command includes `npx prisma generate`:
```bash
npm install && npx prisma generate && npm run build
```

### Runtime Error: "PrismaClientInitializationError"

**Cause**: `DATABASE_URL` not set or incorrect.

**Fix**:
1. Go to your web service → Environment
2. Verify `DATABASE_URL` is set
3. Make sure it's the **Internal Database URL** (starts with `postgresql://`)
4. Re-deploy

### "Invalid admin password"

**Cause**: `ADMIN_PASSWORD` env var doesn't match what you're entering.

**Fix**:
1. Check Environment tab in Render
2. Update `ADMIN_PASSWORD` to a known value
3. Save (triggers redeploy)

### Database Connection Timeout

**Cause**: Web service & DB in different regions, or DB not ready.

**Fix**:
1. Ensure DB status is "Available" (green)
2. Both services should be in same region (Ohio recommended)
3. Use **Internal Database URL**, not External

### Migrations Won't Apply

**Cause**: First-time deployment or schema changes.

**Fix**:
1. In Render dashboard, open web service **Shell**
2. Run manually:
   ```bash
   cd web
   npx prisma migrate deploy
   ```

### "504 Gateway Timeout" on First Request

**Cause**: Render free tier spins down after inactivity (cold start).

**Fix**: Normal behavior. Refresh after 30 seconds. Upgrade to Starter plan to prevent spin-down.

## 💡 Production Tips

### 1. Upgrade Database Plan
Free Postgres has limits (90-day expiration, less storage). For production:
- Upgrade to **Starter ($7/mo)**: Persistent, 1GB RAM
- Or **Standard ($20/mo)**: 4GB RAM, daily backups

### 2. Custom Domain
1. In web service settings → **"Custom Domains"**
2. Add your domain (e.g. `mentionmarkets.com`)
3. Update DNS:
   - **CNAME** record: `www` → `mention-markets-web.onrender.com`
   - **A** record: `@` → Render's IP (shown in dashboard)

### 3. Auto-Deploy on Push
Already configured! Every push to `main` triggers a new deploy.

### 4. Monitoring
- Render Dashboard shows:
  - Deployment logs
  - Runtime logs
  - Metrics (CPU, memory)
  - Events
- Set up alerts for deployment failures

### 5. Backups
Enable **Postgres backups** (Starter plan+):
- Dashboard → Your DB → Settings → Backups
- Daily automatic backups
- Point-in-time recovery

## 📊 What About the Old Flask App?

Your existing `funnylolhaha.onrender.com` Flask app will **keep running** unchanged. You now have two separate services:

1. **Flask app** (existing): `funnylolhaha.onrender.com` — transcript scraper/API
2. **Next.js app** (new): `mention-markets-web.onrender.com` — admin UI + search

They are independent. If you want to retire the Flask app later, you can delete that service from Render.

## 🆘 Need Help?

Common issues:
- **DB connection**: Ensure `DATABASE_URL` uses **Internal Database URL**
- **Build fails**: Check Node version (Render uses Node 20 by default)
- **Slow cold starts**: Upgrade from Free plan
- **Auth not working**: Verify `ADMIN_SESSION_SECRET` is 32+ chars

Check Render logs:
```
Dashboard → Your Service → Logs (tab)
```

## 🎉 You're Live!

Once deployed, share your new search interface:
- **Public search**: `https://your-service.onrender.com/search`
- **Admin panel**: `https://your-service.onrender.com/admin/login`

Keep your admin password safe and start uploading transcripts! 🚀

