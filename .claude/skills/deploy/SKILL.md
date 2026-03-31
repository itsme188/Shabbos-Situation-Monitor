---
name: deploy
description: Use after merging a PR on GitHub, when the user says "deploy", "update the server", "pull and restart", or when you just merged/approved a PR and need to get the changes running on the production server. Also use when the user reports the server is running old code.
---

# Deploy Shabbos Monitor

You are deploying the latest code to the production Shabbos Monitor server running on this Mac.

## Steps

### 1. Pull latest code
Run in the **main repo** (NOT a worktree):
```
cd "/Users/Yitzi/code/shabbos-situation-monitor" && git pull origin main
```
Show the user what changed (new commits pulled).

### 2. Kill ALL existing processes
**CRITICAL**: You must kill BOTH start.sh AND server.py. Killing only the port holder leaves zombie start.sh processes that crash-loop.
```
pkill -f 'start.sh' ; pkill -f 'server.py'
```
Wait 2 seconds, then verify nothing is left:
```
lsof -i :8080 | head -5
```
If anything is still on port 8080, show the user and ask them to handle it.

### 3. Instruct the user to restart
**You cannot start the server yourself** — a server launched via Claude Code's Bash tool will die when the session exits.

Tell the user:
> Server processes killed and code updated. To restart, do ONE of these:
> - **Double-click** `launcher.applescript` on the Desktop
> - **Open Terminal** and run: `cd "/Users/Yitzi/code/shabbos-situation-monitor" && ./start.sh`
>
> The server will be available at http://localhost:8080 once it starts (takes ~10 seconds for initial feed fetch).

### Error handling
- If `git pull` has merge conflicts, show them and ask the user how to resolve
- If processes won't die after pkill, suggest `kill -9 $(lsof -i :8080 -t)` as last resort
- If port 8080 is held by something other than server.py/start.sh, warn the user
