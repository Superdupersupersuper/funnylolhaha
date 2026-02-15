# 🔧 Manual Fix Required - Render Dashboard

The automated deployment hit API limitations. Here's how to fix it manually (5 minutes):

## ✅ Good News
- Web service created: `mention-markets-web`
- Database created: `mention-markets-db`
- Both are running, just not connected properly

## 🔧 Fix Steps

### 1. Get Database Connection String (2 min)

1. Go to: https://dashboard.render.com/d/dpg-d693piogjchc73dflltg-a
2. Scroll to **"Connections"** section
3. Copy the **"Internal Database URL"**
   - Looks like: `postgresql://mention_markets_user:LONG_PASSWORD@dpg-xxx.oregon-postgres.render.com/mention_markets`
   - ⚠️ Use **Internal**, not External

### 2. Add to Web Service (2 min)

1. Go to: https://dashboard.render.com/web/srv-d693pammcj7s738j4bng
2. Click **"Environment"** tab (left sidebar)
3. Add/Update these variables:

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | *(paste Internal Database URL from step 1)* |
   | `NODE_ENV` | `production` |
   | `ADMIN_PASSWORD` | `changeme-admin-2024` *(change this!)* |
   | `ADMIN_SESSION_SECRET` | *(generate: run in terminal)* `node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"` |

4. Click **"Save Changes"** (triggers auto-redeploy)

### 3. Verify Build Settings (1 min)

While in the dashboard, click **"Settings"** tab and verify:

- **Root Directory**: `web`
- **Build Command**: `npm install && npx prisma generate && npm run build`
- **Start Command**: `npm start`

If any are wrong, fix them and click **"Save Changes"**

### 4. Wait for Deploy (3 min)

1. Go to **"Events"** tab
2. Watch the deploy progress
3. Once it shows **"Deploy live"**, continue to step 5

### 5. Initialize Database (1 min)

1. Go to **"Shell"** tab in the web service dashboard
2. Run this command:
   ```bash
   npx prisma db push --accept-data-loss
   ```
3. You should see: `✔ Generated Prisma Client`

### 6. Test It! 🎉

1. Visit: https://mention-markets-web.onrender.com/admin/login
2. Login with password: `changeme-admin-2024`
3. Upload the Mamdani transcript from `transcripts/mamdani/`
4. Test search at: `/search`

---

## 🆘 If Still Failing

**Check Logs:**
1. Dashboard → **"Logs"** tab
2. Look for errors like:
   - `DATABASE_URL` not set
   - Port binding errors
   - Prisma connection errors

**Common Issues:**
- **Wrong DATABASE_URL**: Make sure you used **Internal**, not External
- **Health check timeout**: In Settings, set Health Check Path to empty or `/`
- **Start command wrong**: Should just be `npm start`, nothing else

---

## 📊 Quick Status Check

Run this in your terminal anytime:
```bash
cd /Users/alexandermiron/Downloads/mention-markets
python3 render_cli.py status
```

Look for: `🟢 live` = Success!

---

This manual approach bypasses the API limitations and should work immediately. Let me know once you've completed steps 1-2 and I'll monitor the deployment!

