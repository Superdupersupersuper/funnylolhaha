# 🔄 Agent Handoff - Render Deployment Issue

## 📋 Quick Context

Built a new Next.js app (`web/` folder) for MentionMarkets with:
- ✅ Otter.ai transcript parser
- ✅ Admin UI for upload/edit
- ✅ Public search
- ✅ Prisma schema (Transcript + SpeakingSegment)

## 🎯 Current Issue

**Render deployment partially working but database not initialized**

### What's Working:
- ✅ Service deployed: `mention-markets-web` (srv-d694bsjuibrs739aiib0)
- ✅ Database created: `mention-markets-db` (dpg-d693piogjchc73dflltg-a)
- ✅ App homepage loads: https://mention-markets-web.onrender.com
- ✅ Admin pages load: https://mention-markets-web.onrender.com/admin/login

### What's NOT Working:
- ❌ Database schema not initialized (Prisma tables don't exist)
- ❌ API endpoints return 500 error: `/api/search/filters`, `/api/admin/transcripts`
- ❌ Can't upload transcripts yet

## 🔧 What Needs to Happen

**Initialize the Postgres database schema** so API endpoints work.

### Option A: Update Start Command (Automatic)
Update the Render service start command to:
```bash
npx prisma db push --accept-data-loss --skip-generate && npm start
```

This runs on every startup and creates the schema if missing.

### Option B: Run Migrations via Render Shell (Manual but guaranteed)
1. Go to: https://dashboard.render.com/web/srv-d694bsjuibrs739aiib0
2. Click "Shell" tab
3. Run:
   ```bash
   npx prisma db push --accept-data-loss
   ```
4. Restart the service

## 🔑 Critical Info

**Render API Key**: `rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy`

**Service IDs:**
- Web service: `srv-d694bsjuibrs739aiib0`
- Database: `dpg-d693piogjchc73dflltg-a`

**Testing Commands:**
```bash
# Check deploy status
python3 render_cli.py status

# Test if API works (should return JSON, not error)
curl https://mention-markets-web.onrender.com/api/search/filters

# Update service via API
python3 -c "
import requests, json
response = requests.patch(
    'https://api.render.com/v1/services/srv-d694bsjuibrs739aiib0',
    headers={'Authorization': 'Bearer rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy', 'Content-Type': 'application/json'},
    data=json.dumps({
        'serviceDetails': {
            'envSpecificDetails': {
                'startCommand': 'npx prisma db push --accept-data-loss --skip-generate && npm start'
            }
        }
    })
)
print(response.ok)
"

# Trigger redeploy
python3 -c "
import requests, json
requests.post(
    'https://api.render.com/v1/services/srv-d694bsjuibrs739aiib0/deploys',
    headers={'Authorization': 'Bearer rnd_XToSneCSEQP0QdaeAYQTtlZWCNzy', 'Content-Type': 'application/json'},
    data=json.dumps({'clearCache': 'clear'})
)
"
```

## ✅ Success Criteria

When working, this should return JSON (not error):
```bash
curl https://mention-markets-web.onrender.com/api/search/filters
# Expected: {"speakers":[],"themes":[],"speechTypes":[]}
```

Then user can:
1. Login at `/admin/login` (password: `changeme-admin-2024`)
2. Upload `transcripts/mamdani/Mayor Mamdani Holds Press Conference to Make an Announcement_otter_ai.txt`
3. Search should work

## 📂 Key Files

- `web/prisma/schema.prisma` - Database schema
- `web/src/lib/parsers/otter.ts` - Transcript parser (tested, works)
- `web/src/app/admin/transcripts/new/page.tsx` - Upload UI
- `web/package.json` - Start command configured with DB init

## 🎯 Your Task

Fix the database initialization so the API endpoints work, then confirm user can upload the Mamdani transcript successfully.

