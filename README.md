# How I could have burned 1200 USD with Openclaw if I haven't stopped and reflected?

One Saturday afternoon I spent about 3 hours playing with OpenClaw, testing ideas and prompts. Out of curiosity I checked the token usage. The cost? $10 — gone. Not catastrophic, but enough to trigger a realization: at that rate, casual experimentation would quietly turn into $300 a month, $1,200+ a year. The lesson hit immediately: when building with AI, the real constraint isn’t intelligence — it’s token economics.

It was almost one month ago when I decided to start out my Openclaw personal experiment. An AI agent that could actually *do* things—not just chat, but manage my calendar, track my principles, summarize my day, and handle the hundred micro-tasks that were eating my attention.

What followed was a crash course in token economics, security paranoia, and the gap between "looks good in the README" and "actually works at 6 AM when you need it."

If you're considering building your own agent system, here's the unpolished truth—including the expensive mistakes I made so you don't have to.


---

## Why Personal AI Agents Matter Now (Not Later)

We're past the "experiment with ChatGPT" phase. Some cool people I know (and follow) are already augmenting themselves—automating research, delegating analysis, building memory systems that persist beyond a single conversation.

But here's the thing: the real competitive advantage isn't using AI. It's *owning* your AI infrastructure.

A personal agent that lives on hardware you control, with memory you curate, integrated into *your* systems (Notion, Gmail, calendar, training logs)—that's not just convenience. It's compound leverage.

The cost of building this? Surprisingly low. The cost of building it *wrong*? I found out the hard way.

---

## The Setup Journey: What Actually Happened

I started on a Raspberry Pi 4. Seemed logical—dedicated hardware, low power, always on. I installed OpenClaw, connected Telegram as my interface, and started building skills.

The first week felt like magic. I had my agent pulling my Garmin data, summarizing my calendar, nudging me on my weekly principles review and help with journaling.

Then week two hit.
On that Saturday, I noticed. 10USD in 3h; or 1200USD a month. 

Understanding how was a must. Saw old session files ballooned to several megabytes. A cronjob I thought I'd deleted was still firing every hour, burning tokens on redundant checks. I'd accidentally committed an API key to a test repo. And then adopted gitleaks so that thankfully anything like that get caught before push. And my "simple" multi-agent architecture had turned into a spaghetti mess where three subagents were knocking heads.

I had built something functional at first. Then it got disfunctional. I hadn't built it *right*.

---

## The Five Expensive Mistakes (And How to Avoid Them)

### 1. Token Burn Ignorance

My first mistake: not monitoring costs per interaction. I was using Claude Opus 4.6 for everything—including tasks that other models could handle. After a careful research, I set out to test Kimi 2.5. I became impressed with the ~90% of Opus performance, at a 1/10th the price.

**The fix:**
- Run `/usage` regularly. Know your burn rate.
- Use cost-benefit model tiers: Sonnet 4.6 for complex reasoning, Kimi 2.5 for structured tasks, GPT-4 as fallback. And use Opus 4.6 for very advanced tasks. [More details in this github repo](https://github.com/lauroBRCWB/openclaw-tweaks/tree/main/openclaw.json):
  - [Enable different models (OpenAI, Anthropic, Kimi)](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/models.json).
  - [Configure default and fallback models](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/agents.defaults.model.json)
  - [Create aliases to reference other models in other parts of config file](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/agents.defaults.models.json)
- Audit skill descriptions—they inject into every interaction. Bloated descriptions = wasted tokens on every call. Run below command, you'll understand how many tokens each file is consuming.
  `/context detail` on your channel (i.e. Telegram)
- Delete session files >1MB. Old sessions accumulate fast.

`find . -size +1M -name "*.jsonl" -and \( -path '*sessions*' \) -exec trash {} \;`
- Set thinking to "minimal" for subagents. They don't need to reason aloud for routine tasks [See how here](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/agents.defaults.thinkingDefault.json)
 
**My rule now:** 100k tokens (instead of default 200k) is typically enough. If a task needs more, I'm probably doing it wrong.
[How to set context to 100k](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/agents.defaults.context.json)

### 2. Security Theater vs. Security Reality

I thought "I'll just be careful" was a security strategy. It wasn't.

**What I implemented after the near-miss:**
- Moved *everything* to environment variables. No hardcoded secrets, ever. But, then you build another nightmare: how do I secure I will have always the right .env map organized for when I need to reset .env?
  - I built something. A script that always copy the contents of .env to .env.example, wipes all the secrets, and run organizer so that your file looks amazing. [Check more here](https://github.com/lauroBRCWB/openclaw-tweaks/tree/main/env_file)
- Blocked Openclaw social media sites and Clawhub (you only want you messing with skills) via `/etc/hosts` and iptables (distraction + attack surface). [Firewall here!](https://github.com/lauroBRCWB/openclaw-tweaks/tree/main/firewall)
- Use Claude Opus 4.6 for any sensitive operations—it's slower but more reliable on security-critical tasks.
- Before installing skills, always download, scrutinize yourself and then you install it manually by copying the skill folder to skills under openclaw (or any agent workspace).
- Exec approvals enabled—human-in-the-loop for any command that could break things. [Configure this here](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/openclaw.json/agents.defaults.elevatedDefault)
- Principle of least privilege on all tools and skills. Secure tools have only access to what they need.
- Regular security audits using automated scans. Add the command below to your weekly cron job: `openclaw security audit --deep`

**The rule:** If it's inconvenient, it's probably secure. If it's convenient, assume it's broken.

### 3. Architecture Confusion: Cron vs. Heartbeat

I spent long time wrestling with cronjobs that wouldn't die. Some tasks need scheduled execution (daily backups, weekly research). Others need event-driven triggers (new email, calendar change). I kept mixing the two.

**What works:**
- Cronjobs for backoffice tasks: daily summaries, package updates, file cleanup, AI news digests.
- Heartbeats for state checks: memory review, trainer checkpoint, networking reminders.
- Heartbeat interval: max every 2 hours, configured to only reach out when there's actually something to say.

**The lesson:** Multi-agent setups sound elegant, but skills are often simpler and more maintainable. Start with skills. Graduate to subagents only when you need true parallel execution or specialized reasoning domains.
Read more: [Guide to choose between cronjob and heartbeat](https://docs.openclaw.ai/automation/cron-vs-heartbeat)

### 4. Skill Bloat

I built 20+ skills before I really understood the system. Pollen forecasts, Notion database handlers, recipe suggestions, book note capture—each one injected into context on every relevant call. The descriptions alone were eating tokens.

**Better approach:**
- Start with 3-5 core skills that solve real daily problems.
- For consistency and failproof, make skills modular—one skill per database, not one skill per use case. But know: this will eat more tokens (but just a bit: everything that is between the first two lines in the file. See below).
```
---
name: Skill name
description: The longer the description, the more tokens
---
No words from here will get directed. Only if the usage is required.
```
- Document dependencies clearly. A skill that calls another skill that calls an API is a failure chain waiting to happen.

### 5. Ignoring Remote Recovery

My box stopped responded in the end of week 2. I had backups, but no automated recovery process. 
I spent a full day reconstructing the environment.

**What I built after:**
- Telegram command that forces a git pull and restarts services.
- Deployment scripts stored in version control.
- Service files for systemd that auto-restart on failure.
- Regular `git status` checks that alert on uncommitted changes.
Get here for free :) just following instructions from [README.md](https://github.com/lauroBRCWB/openclaw-tweaks/tree/main/restauration-bot-service)

### 6. File system manipulation
If you go to it's file system, you'll be surprised how chaotic it will look like. I am much more organized than it is. Hence, I decided to spend some tokens every call to organize the mess. This is what I proposed, and it's working.

[Check how I did it here.](https://github.com/lauroBRCWB/openclaw-tweaks/blob/main/AGENTS.md)

### 7. Multi agent setup vs single agent
I initially designed the system with three specialized agents—**Main**, **Cmd Executor**, and **Researcher**—to enforce a strict separation of responsibilities and reduce the risk of prompt-level manipulation. The idea was to keep the orchestrator constrained while delegating sensitive capabilities to purpose-built agents.

* **Main** handled orchestration and most interactions, but had no permission to write files or execute commands.
* **Cmd Executor** was responsible for filesystem changes and Linux commands, with safeguards against unsafe operations.
* **Researcher** used stronger models for complex reasoning, debugging, and web retrieval.

The reasoning was straightforward: if the orchestrator could not modify its own environment, prompt injections would face an additional barrier. Execution and research would remain isolated, each with a narrower mandate.

In practice, however, the design produced unintended friction. When **Main** spawned **Cmd Executor**, the executor often lacked the broader context needed to recover from failures. The result was a ping-pong loop:

* Cmd Executor fails → returns control to Main
* Main reassesses → sends a revised instruction
* Context erodes across iterations → token consumption increases

Attempts to introduce additional specialized agents (for example, a book-writing agent) made coordination even more brittle. Whenever workflows required multiple hops through Main, the system tended to stall and gradually lose the original objective.

To address this, I shifted to a **skill-based architecture with only two agents**:

* **Main** – multi-purpose, running cheaper models and handling most tasks with full operational capability.
* **Researcher** – reserved for deeper reasoning, complex research, and heavier cognitive workloads.

This simplification significantly improved flow and reduced token waste. The trade-off, however, is architectural: the original **segregation of duties** is now weaker. While the system is more practical and efficient, achieving both strong isolation and smooth agent collaboration remains an open design challenge I am still investigating.

---

## The Practical Starter Checklist

If you're starting today, here's the order I'd recommend:

**Week 1: Foundation**
- [ ] Install on dedicated hardware (VM, cloud instance, Raspberry Pi, Mac Mini—*not* your daily driver)
- [ ] Set up Telegram as your interface
- [ ] Configure one model (start with Kimi 2.5—cheap, capable)
- [ ] Enable exec approvals (don't skip this / it messes up with the full thing if you disable)
- [ ] Set up basic security: env vars, blocked sites, gitleaks scanning (command below)
```
brew install gitleaks
cd $OPENCLAW_HOME
gitleaks dir .
```
- [ ] Run a test on your prompts: [https://compliance.earlycore.dev/](https://compliance.earlycore.dev/)

**Week 2: First Skills**
- [ ] Build ONE skill that solves a real daily problem (calendar check, todo sync, weather)
- [ ] Implement token monitoring (`/usage` becomes your new best friend)
- [ ] Set up daily session cleanup
- [ ] Create your first cronjob for something simple (daily summary) / remember: [Guide to choose between cronjob and heartbeat](https://docs.openclaw.ai/automation/cron-vs-heartbeat)
- [ ] Remember to review its header; the more words there, the more tokens consumed every single call to completion apis.

**Week 3: Memory & Integration**
- [ ] Connect one external system you actually use (Notion, Gmail, etc.)
- [ ] Set up persistent memory (SQLite sync from Notion works well) and configure it to use vectorization
- [ ] Configure heartbeat for one state check (principles review, training log, etc.)

**Week 4: Hardening**
- [ ] Security audit—scan for secrets, review tool permissions
- [ ] Set up remote recovery (git-based deployment)
- [ ] Document your architecture (future you will thank present you)

**Month 2+: Expansion**
- [ ] Add subagents only when skills can't handle the complexity
- [ ] Build cost-conscious model routing (cheap → expensive, not the other way)
- [ ] Create domain-specific agents: Researcher, News, Health/Fitness, Executive Assistant

---

## What's Next?

My current setup handles daily summaries, principles management, training coordination, recipe suggestions, and AI news monitoring. But there's more to build. Each new capability builds on what came before.

---

## The Real Lesson

Building a personal AI agent isn't about having the perfect setup on day one. It's about building a system that gets *better* as you use it—more secure, more efficient, more aligned with how you actually work.

The mistakes I made weren't were tuition. The $10 in API calls taught me token economics. The halted system taught me infrastructure as code. The runaway cronjobs taught me that simple beats elegant.

If you're on the fence about building your own system, my advice is: start. Start small, start cheap, start with one skill that actually matters to your daily life.

But start with your eyes open. The tools are powerful. That power cuts both ways.

---

## You are still curious what are my usecase? I asked Nex to reply to you. Here's what he says:

My OpenClaw Use Cases — Article Summary

🎯 Life Architecture

- Principles management (life + work operating system)
- Weekly life reviews across 5 vectors
- Life inventory nudges (keep everything documented)
- Memory check-ins (surface one insight from the past)

📅 Daily Orchestration

- Morning briefing: yesterday's lessons, today's principle, tasks, calendar (personal + work free/busy), weather, pollen, newsletters, unread mail actions
- Journaling coach with Garmin data cross-reference
- Recipe memory + suggestions when I'm out of ideas

🏃 Training & Health

- Trainer checkpoint — adherence tracking, workout adjustments, accountability

💼 Career & Networking

- AI news digest (OpenAI, Anthropic RSS)
- Weekly research (AI evolution, Nordic ecosystem)
- Networking reminders (who to contact, what topic, weekly outreach prompt)
- Media clipping (what's being said about me online)

✍️ Content Creation

- Article/post ghostwriter
- Children's book writing → image generation → audiobook recording pipeline

🛠️ Coaches On-Demand

- Principles coach (stress-test decisions against values)
- Leadership coach (team dynamics, psychological safety)

🔧 System Maintenance (Backoffice)

- Automated OpenClaw backups with secrets scanning
- Model validation (ensure configs don't drift)
- Notion ↔ SQLite sync (principles, journal for better memory retrieval)
- File/folder cleanup (I stay more organized than the agent)
- Cronjob cleanup (buggy — they don't always disappear)
- Media file cleanup (inbound/outbound folders grow forever)
- Outdated package detection (brew, npm, pip)

## My skills? Here they are:
### Skills only used by main

	./workspace/skills 
	├── gmail-attachments # download gmail attachments
	├── gog # interact with calendar, gmail, etc
	├── mcporter # multi purpose
	├── notion # notion interaction
	
	# Notion skills specialized in the databases I have
	├── notion-db1-filler # A powerfull list of things I have seen and liked
	├── notion-book-notes # Notes of books
	├── notion-daily-planner # Task list
	├── notion-db2 # Help me manage my network
	├── notion-recipes # Remind me of recipes I know, and suggest dishes when I'm out of ideas
	
	├── pollen-forecast # Fetch polen forecast in Sweden
	├── garmer # fetch data from my garmin
	├── journal-coach # helps me write my journal entries
	├── principles-coach # Help me write better principles
	├── principles-tracker # Help me keep track of my life and work principles
	├── leadership-coach # Coach me for leadership questions
	
	└── children-book-creator # create books

### Skills shared with all subagents
	./skills
	├── Weather # weather forecast
	├── agent-browser # powerfull cli browser interaction
	├── caldav-calendar # interaction with calendar from WEBDAV
	├── cronjob-maintainer # helps me manage my cronjobs
	├── elevenlabs-stt # speech to text
	├── self-improving-agent # skill installed to self-improve
	├── copywriter # helpe me write
	└── trainer-coach # follow my training 

## [Prompt library]([link](https://github.com/lauroBRCWB/openclaw-tweaks/tree/main/prompts))

## Building something similar? 
**Hit me up.** I'm always interested in comparing notes on architecture, security patterns, and the weird edge cases that only show up at 2 AM when your agent decides to summarize your entire email history because of a regex typo.

The future is agentic. Let's build it carefully.

#AI #OpenClaw #PersonalAI #Automation #AgentInfrastructure #LLMOps

## Sources
- https://docs.google.com/document/u/0/d/1ffmZEfT7aenfAz2lkjyHsQIlYRWFpGcM/mobilebasic
- https://www.getopenclaw.ai/help/token-usage-cost-managementhttps://www.getopenclaw.ai/help/token-usage-cost-management
- https://www.notion.so/lifeaser/mattganzak-guide-on-token-optimization-31d68ef01cc38092b6f2db242945e513?source=copy_link
- [@mattganzak guide on token optimization](https://www.notion.so/mattganzak-guide-on-token-optimization-31d68ef01cc38092b6f2db242945e513?pvs=21)   
- https://earlycore.dev/collection/openclaw-security-hardening-80-percent-attacks-succeeded
- My experimentation and a lot more reading
