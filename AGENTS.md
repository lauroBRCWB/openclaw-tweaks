# AGENTS.md

Append to agents.md

# Files system interactions

When interacting, it might be relevant to send previous research output already conducted. Save files strictly as below.

- `SOUL.md`, `USER.md`, `IDENTITY.md` — core identity files (stay in root)
- `$OPENCLAW_HOME/workspace/data/` a.k.a. [DATA_FOLDER] — for raw artifacts and exports. Accepts only text related files (i.e. txt, md, pdf, docx, etc), images, voice, but NO scripts (py, sh etc). 
- `[DATA_FOLDER]/plans/` — structured plans and strategic drafts like content calendars, posting schedules, plans for book/project execution, life plan documents
- `[DATA_FOLDER]/frameworks` - Frameworks, strategy for executing stuff
- `[DATA_FOLDER]/garmin/` — data extracted from garmin plans
- `[DATA_FOLDER]/researches/` — analytical outputs, researches
- `[DATA_FOLDER]/routines/` — Outputs of daily, weekly, monthly or other routines established
- `[DATA_FOLDER]/templates/` — Templates for email, messages, calendar invites and other interactions. This is NOT a template for commands. For that, store inside the skills or scripts folder
- `$OPENCLAW_HOME/workspace/scripts/` — Python, bash, or other scripts

**Always use this path pattern:**
```
[DATA_FOLDER]/folder-name/{descriptive-name}-{optional-date}.md
```

**Example workflow:**
```
# During execution
read (or write) $OPENCLAW_HOME/workspace/working-file.md
# ... do work ...
# After completion
mv workspace/working-file.md [DATA_FOLDER]/appropriate-folder/
# Update references in memory/ or other docs
```

**Agent-Specific Notes**

-> Agent 2 (if you have any)
  - Saves outputs to `[DATA_FOLDER]/`