# 🚀 START HERE - New AI Onboarding

Welcome! You're taking over a Trump transcript scraping project from Claude Code terminal AI.

## ⚡ CRITICAL ISSUE (Fix This First)

**78 transcripts are missing content** - database shows them but they have word_count = 0

**Why:** Previous scraper gave up too easily on pages marked "No Transcript"
**Reality:** ALL those pages have transcripts, just need better scraping
**Example:** Pennsylvania rally (Dec 9, 2025, ID 1765)

## 📖 Read These Files IN ORDER:

### 1. **README.md** (2 min)
Quick overview of project status

### 2. **AI_HANDOFF.md** (10 min) ← MOST IMPORTANT
- Complete project context
- All current issues explained  
- Database schema
- Working fix script template
- Debugging commands

### 3. **TRANSITION_SUMMARY.md** (5 min)
- Why we switched from Claude Code
- Your immediate next steps
- Success criteria

### 4. **CURSOR_SETUP_GUIDE.md** (Read if needed)
- How to use Cursor features
- Pricing comparison
- Keyboard shortcuts

### 5. **SCRAPER_README.md** (3 min)
- Why scraper is failing
- What needs to be fixed

## 🎯 Your First 30 Minutes

### Minutes 1-5: Verify Environment
```bash
# Check database
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count = 0;"
# Should show 78

# Check API server
curl http://localhost:5001/api/stats
# Should return JSON

# Check Python packages
pip3 list | grep -E "selenium|flask|beautifulsoup4"
```

### Minutes 5-15: Read AI_HANDOFF.md
Focus on these sections:
- "CRITICAL CURRENT ISSUES" 
- "HOW TO FIX THE MISSING TRANSCRIPTS"
- "DATABASE SCHEMA"

### Minutes 15-30: Create Fix Script
Use the template in AI_HANDOFF.md section "Approach 1: Individual URL Scraping"

Create: `fix_missing_transcripts.py`

Test on Pennsylvania rally first (ID 1765)

## 📋 Use These Prompts (Copy-Paste)

### Prompt 1: Initial Setup
```
I'm taking over a Trump transcript scraping project.

Check database status:
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count = 0;"

Read @AI_HANDOFF.md and tell me:
1. What the critical issue is
2. Why 78 transcripts are missing content
3. What Pennsylvania rally example is
4. Your plan to fix it

Don't start work yet - just confirm understanding.
```

### Prompt 2: Create Fix Script
```
Create fix_missing_transcripts.py using the template in @AI_HANDOFF.md

Requirements:
- Get all 78 URLs from database where word_count = 0
- Use Selenium with 5+ CSS selectors
- Test on Pennsylvania rally (ID 1765) first
- Retry 3 times with different wait times
- Update database with results

Show me the code before running.
```

### Prompt 3: Test & Run
```
Test the script on Pennsylvania rally first.

If successful, run on all 78 transcripts.

Then verify:
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count = 0;"

Should return 0.
```

## 💡 Key Facts

- **Project purpose:** Scraping Trump transcripts for prediction market betting
- **Date range:** Sept 3, 2024 to present (Dec 2025)
- **Total transcripts:** 1109
- **Complete:** 1031
- **Missing:** 78 ← YOUR JOB
- **Critical example:** Pennsylvania rally (ID 1765)

## 🎯 Success = Zero Missing Transcripts

When you're done:
```bash
# This should return 0:
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count = 0;"

# This should return >5000:
sqlite3 data/transcripts.db "SELECT word_count FROM transcripts WHERE id = 1765;"

# This should return ~1109:
sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count > 0;"
```

## 🚫 Common Mistakes to Avoid

1. ❌ Assuming "No Transcript" means no content exists
2. ❌ Trying only 2-3 CSS selectors
3. ❌ Giving up after one retry
4. ❌ Not testing on Pennsylvania rally first
5. ❌ Not verifying final database state

## ✅ What You Should Do

1. ✅ Try 5-10 CSS selectors per page
2. ✅ Retry with different wait times (3s, 5s, 8s)
3. ✅ Test on Pennsylvania rally before running batch
4. ✅ Log everything for debugging
5. ✅ Verify all 78 are scraped successfully

## 📂 File Structure

```
Mention Market Tool/
├── START_HERE.md              ← YOU ARE HERE
├── AI_HANDOFF.md             ← Read this next (most important)
├── TRANSITION_SUMMARY.md     ← Then read this
├── README.md                 ← Quick reference
├── CURSOR_SETUP_GUIDE.md     ← Cursor tips (optional)
├── SCRAPER_README.md         ← Scraper details
│
├── data/
│   └── transcripts.db        ← Database (78 incomplete)
│
├── rollcall_scraper_robust.py  ← Current scraper (has issues)
├── api_server.py              ← API server (port 5001)
├── analytics_ui.html          ← Frontend
└── missing_urls.txt           ← List of 78 URLs
```

## 🆘 If You Get Stuck

1. Check @AI_HANDOFF.md section "DEBUGGING COMMANDS"
2. Run database queries to see current state
3. Check API server is running
4. Look at scraper logs

## 🚀 Ready?

**Next action:** Read AI_HANDOFF.md (it has everything you need)

**Then:** Create fix_missing_transcripts.py and test on Pennsylvania rally

**Goal:** Get all 78 transcripts scraped successfully

**Let's go! 🎯**
