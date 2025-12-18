# Deployment Guide - Mention Market Tool

## ✅ Website is Live Locally!

Your website is currently running at:
- **Frontend**: http://localhost:5174
- **Backend API**: http://localhost:3000

**Current Data**: 1,907 transcripts with 1.9 million words!

## How to Deploy to a Real Website

You have several options for deploying your mention markets tool to the internet:

---

## Option 1: Vercel + Railway (Recommended - FREE)

This is the easiest and fastest option with free tiers.

### Step 1: Deploy Backend to Railway

Railway hosts your Node.js backend and SQLite database.

1. **Sign up** at https://railway.app (free tier: $5/month credit)

2. **Create new project** and select "Deploy from GitHub repo"

3. **Prepare your code**:
   ```bash
   cd "/Users/alexandermiron/Desktop/Mention Market Tool"

   # Create .gitignore if needed
   echo "node_modules/" >> .gitignore
   echo ".env" >> .gitignore

   # Initialize git (if not already)
   git init
   git add .
   git commit -m "Initial commit"
   ```

4. **Push to GitHub**:
   - Create a new repository on GitHub
   - Follow GitHub's instructions to push your code

5. **Deploy on Railway**:
   - Select your GitHub repo
   - Railway will auto-detect Node.js
   - Add environment variables:
     - `PORT=3000`
     - `DATABASE_PATH=./data/transcripts.db`
   - Deploy!

6. **Note your backend URL** (e.g., `https://your-app.railway.app`)

### Step 2: Deploy Frontend to Vercel

Vercel hosts your React frontend (FREE tier).

1. **Sign up** at https://vercel.com (free for personal projects)

2. **Update frontend to use Railway backend**:
   ```bash
   # Edit frontend/src/App.jsx and all component files
   # Change API_BASE from 'http://localhost:3000/api' to:
   # const API_BASE = 'https://your-app.railway.app/api'
   ```

3. **Deploy**:
   - Click "Import Project" on Vercel
   - Select your GitHub repo
   - Set root directory to `frontend`
   - Deploy!

4. **Your site will be live** at `https://your-app.vercel.app`

**Total Cost**: FREE (within limits)

---

## Option 2: Render (All-in-One - FREE)

Render can host both frontend and backend.

1. **Sign up** at https://render.com (free tier available)

2. **Deploy Backend**:
   - Create "New Web Service"
   - Connect GitHub repo
   - Build command: `npm install`
   - Start command: `node backend/server.js`
   - Add environment variables
   - Free tier available!

3. **Deploy Frontend**:
   - Create "New Static Site"
   - Root directory: `frontend`
   - Build command: `npm run build`
   - Publish directory: `dist`

**Total Cost**: FREE (with some limitations)

---

## Option 3: Netlify + Heroku

1. **Backend on Heroku**: https://heroku.com
   - Free tier available (with limits)
   - Supports Node.js + SQLite

2. **Frontend on Netlify**: https://netlify.com
   - Generous free tier
   - Easy continuous deployment

---

## Option 4: VPS (Most Control - $5-10/month)

For complete control, use a VPS provider:

### Recommended VPS Providers:
- **DigitalOcean** ($6/month): https://digitalocean.com
- **Linode** ($5/month): https://linode.com
- **Vultr** ($5/month): https://vultr.com

### Setup on VPS:

1. **Create Ubuntu server**

2. **SSH into server**:
   ```bash
   ssh root@your-server-ip
   ```

3. **Install Node.js**:
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt-get install -y nodejs
   ```

4. **Transfer your code**:
   ```bash
   # On your local machine:
   cd "/Users/alexandermiron/Desktop/Mention Market Tool"
   scp -r . root@your-server-ip:/var/www/mention-market
   ```

5. **Install dependencies on server**:
   ```bash
   cd /var/www/mention-market
   npm install
   cd frontend && npm install && npm run build
   ```

6. **Install nginx**:
   ```bash
   sudo apt install nginx
   ```

7. **Configure nginx** (`/etc/nginx/sites-available/mention-market`):
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       # Serve frontend
       location / {
           root /var/www/mention-market/frontend/dist;
           try_files $uri $uri/ /index.html;
       }

       # Proxy API to backend
       location /api {
           proxy_pass http://localhost:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }
   }
   ```

8. **Enable site**:
   ```bash
   sudo ln -s /etc/nginx/sites-available/mention-market /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

9. **Run backend with PM2**:
   ```bash
   sudo npm install -g pm2
   cd /var/www/mention-market
   pm2 start backend/server.js --name mention-market
   pm2 startup
   pm2 save
   ```

10. **Get free SSL** (HTTPS):
    ```bash
    sudo apt install certbot python3-certbot-nginx
    sudo certbot --nginx -d your-domain.com
    ```

**Total Cost**: $5-10/month

---

## Quick Deploy with Vercel + Railway (Step-by-Step)

This is the fastest option. Let me create scripts to help:

### 1. Prepare Backend for Railway

Create `backend/package.json`:
```json
{
  "name": "mention-market-backend",
  "version": "1.0.0",
  "main": "server.js",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "cors": "^2.8.5",
    "sqlite3": "^5.1.6"
  }
}
```

### 2. Update Frontend API URL

You'll need to update the API URL in these files:
- `frontend/src/App.jsx`
- `frontend/src/components/Filters.jsx`
- `frontend/src/components/TranscriptList.jsx`
- `frontend/src/components/WordFrequency.jsx`
- `frontend/src/components/WordTrend.jsx`

Change `http://localhost:3000/api` to your Railway URL.

### 3. Deploy!

1. Push to GitHub
2. Connect Railway to GitHub → Deploy backend
3. Connect Vercel to GitHub → Deploy frontend

**Done!** Your site will be live in minutes.

---

## Domain Setup

Once deployed, you can add a custom domain:

1. **Buy a domain** (GoDaddy, Namecheap, Google Domains, etc.)
   - Example: `mentionmarket.com` (~$10-15/year)

2. **Configure DNS**:
   - Point to Vercel/Netlify (for frontend)
   - They'll provide DNS instructions

3. **SSL is automatic** on Vercel/Netlify/Railway

---

## Cost Comparison

| Option | Monthly Cost | Pros | Cons |
|--------|-------------|------|------|
| Vercel + Railway | FREE-$5 | Easiest, auto-scaling | Free tier limits |
| Render | FREE-$7 | All-in-one | Free tier has spin-down |
| Netlify + Heroku | FREE-$7 | Popular, reliable | Heroku removed free tier |
| VPS | $5-10 | Full control | Requires setup |

---

## Recommended: Start Free, Scale Later

1. **Start with Railway + Vercel** (FREE)
2. **If you hit limits**, upgrade to paid tiers ($5-7/month)
3. **If you need more control**, move to VPS ($10/month)

---

## Next Steps

1. ✅ Website is running locally
2. Choose a deployment option above
3. Push code to GitHub
4. Deploy backend and frontend
5. Optional: Buy a custom domain

Need help with deployment? Let me know which option you'd like and I can guide you through it!
