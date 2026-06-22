# Claude Code Instructions

## Read this first, every session

Before doing anything, read the full project reference:

```
/Users/nandakumar/Documents/Nanda_Investment/TradeAgent/PROJECT.md
```

It contains everything you need: folder structure, git workflow, app architecture,
data sources, CAN SLIM roadmap, known issues, and next steps.

## The one rule

**All code changes go inside `TradeAgent/`.** This is the only git repo.

```bash
# Every push from here:
cd /Users/nandakumar/Documents/Nanda_Investment/TradeAgent
git add <files>
git commit -m "description"
git push
# → Streamlit Cloud at greencandlecult.streamlit.app redeploys automatically
```

Never edit files in `Archive/` — that folder is stale and ignored.
