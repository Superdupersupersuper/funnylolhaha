# Complete Cursor Setup Guide

## 📥 Installation (5 minutes)

1. **Download Cursor:**
   - Go to https://cursor.sh
   - Download for Mac
   - Drag to Applications folder
   - Open Cursor

2. **First Launch:**
   - Sign up with email (or GitHub)
   - Skip the tutorial (or do it if you want)

---

## 🔑 Setting Up Claude in Cursor

### Method 1: Using Anthropic API Key (RECOMMENDED for your use case)

1. **Get your Anthropic API key:**
   - Go to https://console.anthropic.com
   - Click "Get API Keys"
   - Create new key
   - Copy it

2. **Add to Cursor:**
   - Open Cursor Settings (Cmd + ,)
   - Go to "Models" tab
   - Under "API Keys" click "Add API Key"
   - Select "Anthropic"
   - Paste your key
   - Choose model: **Claude Sonnet 4** (or Sonnet 3.5)

3. **Set as default:**
   - In chat, click model dropdown
   - Select "Claude Sonnet 4"
   - Check "Set as default"

### Method 2: Using Cursor's Built-in Credits

- Cursor Pro includes 500 fast requests/month with Claude
- Easier but limited
- Good for trying it out first

---

## 🎯 Cursor Plans Comparison

### Your Current Setup (Claude Code)
- **Cost:** Included with Claude Pro ($20/month)
- **Limits:** Based on Claude Pro token limits (~200k tokens per conversation)
- **Interface:** Terminal only
- **File handling:** Limited
- **Long processes:** Often timeout/fail

### Cursor Pro ($20/month)
**What you get:**
- 500 "fast" premium AI requests/month (GPT-4, Claude Sonnet)
- Unlimited "slow" requests
- Unlimited basic completions
- Full VS Code features
- Multi-file editing
- **PLUS your own API keys (unlimited if you bring Anthropic key)**

**Limits:**
- 500 premium requests seems like a lot but burns fast with complex tasks
- Once you hit limit, falls back to slower models
- Can add your own API key for unlimited Claude

### Cursor Business ($40/month)
**Additional features:**
- 1,000 premium requests/month (2x Pro)
- Priority support
- Team features (not relevant for solo)
- Admin controls (not relevant for solo)

### Cursor Enterprise (Custom pricing ~$200+/month)
**For companies:**
- Unlimited everything
- Self-hosted options
- SOC 2 compliance
- Not relevant for your use case

---

## 💡 RECOMMENDATION FOR YOU

**Option A: Cursor Pro + Your Own Anthropic API Key**
- **Cost:** $20/month (Cursor) + ~$20-50/month (Anthropic usage)
- **Total:** ~$40-70/month
- **Why:** Unlimited Claude Sonnet 4, best for your scraping project

**Option B: Cursor Pro Only**
- **Cost:** $20/month
- **Why:** Try it first, see if 500 requests/month is enough
- **Risk:** May run out during heavy scraping sessions

**Option C: Just Use Anthropic API Key (Free Cursor)**
- **Cost:** ~$20-50/month (just API usage)
- **Why:** Free Cursor tier + your API key works fine
- **Limitation:** Some features limited

**MY RECOMMENDATION: Option A**
- You need reliability for your betting business
- Unlimited Claude Sonnet 4 with your API key
- Cursor Pro features help with complex projects

---

## 🎓 Essential Cursor Features to Learn

### 1. **Cmd + K** (Inline Edit)
- Select code → Cmd + K
- Tell AI what to change
- AI edits in place
- **Use for:** Quick fixes, refactoring functions

### 2. **Cmd + L** (Chat)
- Opens AI chat sidebar
- Shows full file context
- **Use for:** Complex questions, debugging

### 3. **Cmd + Shift + L** (Chat with Codebase)
- AI can see ALL your files
- Ask about project structure
- **Use for:** "Where is the scraper?" "How does the API work?"

### 4. **@file mentions**
- In chat: type `@filename`
- AI sees that specific file
- **Example:** "@rollcall_scraper_robust.py why is this skipping transcripts?"

### 5. **Composer (Cmd + I)**
- Multi-file editing
- AI can edit multiple files at once
- **Use for:** Large refactors, adding features across files

### 6. **Auto-complete**
- As you type, AI suggests completions
- Tab to accept
- **Great for:** Writing repetitive code

---

## 🚀 Advanced Features (Learn These After Basics)

### 1. **Rules for AI (@.cursorrules)**
Create `.cursorrules` file in your project:
```
# Project Rules
- This is a Trump transcript scraper for betting markets
- Data accuracy is CRITICAL - 100% complete transcripts required
- User is direct - no excuses, just solutions
- When scraping fails, try multiple CSS selectors
- Never skip transcripts marked "No Transcript" - they have content
```

### 2. **Context Management**
- Cursor is smart about which files to include
- But you can force with `@folder` or `@file`
- **Tip:** Keep conversations focused on one problem

### 3. **Terminal Integration**
- Built-in terminal (Cmd + `)
- Run scraper and see output
- Better than Claude Code's terminal

### 4. **Git Integration**
- See changes inline
- Commit from UI
- Review AI changes before committing

### 5. **Debugging**
- Set breakpoints
- Step through scraper code
- See variable values
- **Huge for:** Understanding why scraper fails

---

## 🎯 Cursor Keyboard Shortcuts (Essential)

| Shortcut | Action |
|----------|--------|
| `Cmd + K` | Inline AI edit |
| `Cmd + L` | Open AI chat |
| `Cmd + Shift + L` | Chat with codebase |
| `Cmd + I` | Composer (multi-file edit) |
| `Cmd + P` | Quick file open |
| `Cmd + Shift + P` | Command palette |
| `Cmd + B` | Toggle sidebar |
| `Cmd + `` | Toggle terminal |
| `Cmd + /` | Toggle comment |
| `Cmd + F` | Find in file |
| `Cmd + Shift + F` | Find in all files |

---

## 📚 What to Learn Before Using Cursor

### Beginner Level (Start Here)
1. **Basic VS Code navigation**
   - How to open files
   - How to use split view
   - How to use terminal

2. **How to ask AI good questions**
   - Be specific: "Fix the scraper to try 5 different CSS selectors"
   - Not vague: "Make it work better"

3. **How to review AI changes**
   - Don't blindly accept
   - Understand what changed
   - Test changes

### Intermediate (Learn Week 2)
1. **Multi-file patterns**
   - How your project files relate
   - When to use @mentions
   - How to structure conversations

2. **Debugging basics**
   - Set breakpoints
   - Inspect variables
   - Step through code

3. **Git basics in Cursor**
   - Stage changes
   - Commit
   - View diffs

### Advanced (Learn Month 2)
1. **Custom rules and context**
   - Writing good .cursorrules
   - Project-specific AI behavior

2. **Cursor API integration**
   - Using multiple models
   - Cost optimization

3. **Extension ecosystem**
   - SQLite viewers
   - Python debuggers
   - API testing tools

---

## 🎬 Getting Started: Your First 30 Minutes

### Minute 0-5: Install & Setup
1. Download Cursor
2. Add Anthropic API key
3. Open your project folder

### Minute 5-15: Explore Interface
1. Open file tree (left sidebar)
2. Open `AI_HANDOFF.md`
3. Try Cmd + L (chat)
4. Ask: "Read AI_HANDOFF.md and summarize the main issues"

### Minute 15-25: First Task
1. Select code in `rollcall_scraper_robust.py`
2. Press Cmd + K
3. Say: "Add retry logic with 5 different CSS selectors"
4. Review changes
5. Accept if good

### Minute 25-30: Test Changes
1. Open terminal (Cmd + `)
2. Run: `python3 rollcall_scraper_robust.py`
3. Watch for errors
4. Ask AI to fix if needed

---

## 🆚 Cursor vs Claude Code: Side-by-Side

| Feature | Claude Code (Terminal) | Cursor |
|---------|----------------------|--------|
| **File Navigation** | Type paths manually | Visual tree, Cmd+P |
| **Multi-file Edit** | One at a time | Edit 10+ files at once |
| **Long Processes** | Timeout/hang | Run in terminal, monitor |
| **Debugging** | Print statements only | Full debugger |
| **Code Review** | Scroll through chat | See diffs inline |
| **Search** | grep commands | Fuzzy search, regex |
| **Git** | Command line | Visual UI + CLI |
| **Extensions** | None | Thousands available |
| **Cost** | $20/month | $20-70/month |

---

## 🎯 Perfect Setup for Your Project

### 1. **Plan: Cursor Pro + Anthropic API**
- **Cost:** ~$60/month total
- **Why:** Unlimited Claude, all features

### 2. **Install These Extensions:**
```
1. SQLite Viewer - View your database
2. Python - Better Python support
3. Error Lens - See errors inline
4. GitLens - Better git integration
```

### 3. **Create .cursorrules file:**
```bash
cd ~/Desktop/Mention\ Market\ Tool
cat > .cursorrules << 'RULES'
# Mention Market Tool - AI Rules

## Project Context
- Trump transcript scraper for prediction market betting
- User needs 100% accurate, complete data (zero tolerance for missing transcripts)
- Database has 78 missing transcripts that need scraping
- Pennsylvania rally (Dec 9, 2025) is priority example

## Communication Style
- User is direct and results-focused
- No excuses or assumptions
- If user shows screenshot, they are correct
- "100% complete" means literally 100%, not 99.9%

## Technical Requirements
- When scraping fails, try multiple CSS selectors (5+ attempts)
- Never skip transcripts marked "No Transcript" - they have actual content
- Add extensive logging to all scraper operations
- Verify data completeness after every operation

## Code Style
- Simple solutions over complex ones
- Extensive error handling
- Retry logic on all network operations
- Log everything for debugging
RULES
```

### 4. **Open Project in Cursor:**
```bash
cursor ~/Desktop/Mention\ Market\ Tool
```

### 5. **First Command to AI:**
```
Read AI_HANDOFF.md completely. 

We have 78 transcripts with missing content (word_count = 0) that are marked "No Transcript" but actually have full transcripts on RollCall.

Create fix_missing_transcripts.py that:
1. Gets all 78 URLs from database
2. Scrapes each with Selenium
3. Tries 5 different CSS selectors per URL
4. Retries 3 times on failure
5. Logs all attempts
6. Updates database with content

Pennsylvania rally (ID 1765) is the test case - verify that one first.
```

---

## 💰 Cost Comparison: Claude Code vs Cursor

### Current (Claude Code):
- **Cost:** $20/month (Claude Pro)
- **Token limit:** ~200k per conversation
- **Issues:** Terminal limits, timeouts, hard to debug

### Recommended (Cursor Pro + API):
- **Cursor Pro:** $20/month
- **Anthropic API:** ~$20-50/month (pay per use)
- **Total:** $40-70/month
- **Benefits:**
  - Unlimited Claude Sonnet 4
  - Full IDE features
  - Better debugging
  - Multi-file editing
  - No timeouts

### Budget Option (Cursor Pro Only):
- **Cost:** $20/month (same as Claude Code!)
- **Includes:** 500 premium requests
- **Try first:** See if it's enough
- **Can add API key later if needed**

---

## 🎓 Resources to Learn More

### Official Docs:
- https://docs.cursor.com - Official documentation
- https://cursor.sh/features - Feature list

### YouTube Tutorials:
- "Cursor AI Tutorial" by Fireship (10 min intro)
- "Cursor vs GitHub Copilot" comparisons
- "Advanced Cursor Features" deep dives

### Communities:
- Cursor Discord (active community)
- r/cursor on Reddit
- Twitter #CursorAI hashtag

---

## ✅ Quick Setup Checklist

- [ ] Download Cursor from cursor.sh
- [ ] Sign up / log in
- [ ] Add Anthropic API key (Settings → Models → API Keys)
- [ ] Select Claude Sonnet 4 as default model
- [ ] Open your project: `cursor ~/Desktop/Mention\ Market\ Tool`
- [ ] Create .cursorrules file (see above)
- [ ] Install extensions: SQLite Viewer, Python, Error Lens
- [ ] Read AI_HANDOFF.md in Cursor
- [ ] Start first task: Fix 78 missing transcripts

---

## 🚀 Day 1 Goals

1. ✅ Get comfortable with Cmd+K and Cmd+L
2. ✅ Have AI read AI_HANDOFF.md
3. ✅ Create fix_missing_transcripts.py
4. ✅ Test on Pennsylvania rally
5. ✅ Run full scrape of 78 missing transcripts
6. ✅ Verify: `sqlite3 data/transcripts.db "SELECT COUNT(*) FROM transcripts WHERE word_count = 0;"`
   - Should return 0

---

## 🎯 Final Recommendation

**Get Cursor Pro ($20/month) + Add your Anthropic API key**

**Why:**
1. Same price as Claude Code initially
2. Massive improvement in workflow
3. Can add unlimited Claude later via API key
4. Better for your scraping project
5. Pays for itself if it saves you 1 hour of debugging

**Start with:** Cursor Pro trial (14 days free)
**Then add:** Anthropic API key if you need unlimited
**Total:** $20-60/month depending on usage

**For betting business:** Worth every penny for reliable, complete data

---

**Ready? Download Cursor and open AI_HANDOFF.md! 🚀**
