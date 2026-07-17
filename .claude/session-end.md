# Shabbos Situation Monitor — Session End Checklist

Perform these steps in order. Skip any that don't apply.

**`/session-end` itself is the authorization** — do NOT pause for commit / push / rebuild confirmation. The user invoking the command IS the green light. Only stop for destructive operations (force-push, branch delete, dropping data).

## 1. Uncommitted changes

Run `git status --short` in the main repo and any active worktrees. If uncommitted changes exist:
- Stage + commit straight through. Follow project commit conventions (descriptive message, Co-Authored-By trailer, name files explicitly — never `git add -A`).
- After committing: `git push origin <current-branch>`. Don't ask. If push fails, surface the failure and stop.

## 2. Open PRs

Run `gh pr list`. If any open PRs from this session, surface them in the final summary. No action required unless explicitly asked.

## 3. Worktrees

Run `git worktree list` from the main repo. If there are worktrees from completed work, mention them in the summary so the user can clean up next session. Don't auto-remove — worktree cleanup can lose in-progress work.

## 4. Reconcile TODO list

Check for a TODO file at `docs/plans/TODO.md`, `tasks/todo.md`, or `TODO.md`. If one exists:

- Cross-reference every open item against `git log` since session start — sibling fixes often ride along with the headline work.
- **Verify each candidate tick by grep/read before marking it done** — items can stay open after silently shipping in earlier sessions; flag those rather than re-implementing.
- Match the file's existing convention (`- [x]`, `✅`, `~~strikethrough~~`, move-to-Shipped-section). Do NOT introduce a new one.
- Record today's date + commit hash (`git log -1 --format=%h`) on each newly-ticked item.
- Add any new TODOs discovered this session (bugs, deferred work, follow-ups) with enough context for a cold pickup.

If no TODO file exists, offer to create one at `docs/plans/TODO.md` seeded from conversation + auto-memory backlog.

## 5. Update auto-memory

Read `/Users/Yitzi/.claude/projects/-Users-Yitzi-code-shabbos-situation-monitor/memory/MEMORY.md` and update:
- Add new TODO items discovered this session
- Update PR history with any new PRs created/merged
- Add any new patterns or lessons learned
- Remove items that are no longer relevant

## 6. Update CLAUDE.md

If any known issues were fixed or new lessons were learned:
- Strike through fixed issues with `~~text~~`
- Add new lessons to "Lessons & Best Practices"
- Update architecture notes if the system changed

## 7. Verify production server is running

```bash
curl -s http://localhost:8080/health
```

Should return 200. If not running, **remind the user to start it from Terminal with `./start.sh`** — NEVER start it via the Bash tool (the process dies when Claude Code exits).

## 8. Summary

Brief summary of what was accomplished this session and any remaining TODO items.
