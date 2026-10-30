# Publish and update Supreme Deity Bot

This folder must be the repository root. Install Git for Windows first.

## First publication

Create an empty GitHub repository (do not add a README, license or .gitignore
on GitHub). Choose public or private as appropriate. In PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Bot\SDB'
git init -b main
git add .
git status --short
# Review the staged files before committing; logs, .venv and local display settings are ignored.
git commit -m "Initial Supreme Deity Bot release"
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the URL with the repository you created. Complete GitHub authentication
when Git asks. GitHub Desktop is an alternative for publishing this local folder.

## Publish later changes

```powershell
git add .
git status --short
git commit -m "Describe the change"
git push
```

## Other users: first installation

```powershell
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
```

Open the cloned folder, run Setup.cmd, and use Start Supreme Deity.vbs. A ZIP
download does not contain Git history and cannot use the Update button.
Private repositories require GitHub access and configured Git authentication.

## Update button

Stop the bot, restore any temporary display settings, then click Update from
GitHub. Git must be installed and this branch must track its remote branch.
The updater fetches, refuses divergent commits or existing conflicts, saves
local tracked/untracked changes in a named stash, runs git pull --ff-only and
reapplies the saved changes. It retains the stash as a backup. It never forces
updates, resets files, deletes local edits or pushes to GitHub.

If reapplying edits conflicts, resolve those conflicts before starting the bot;
Git keeps the backup in git stash list. Backups are not removed automatically.
Restart the launcher after a successful update. Run Setup.cmd if requirements
changed. Do not edit files or run a second updater while an update is running.

Recorded offline tests that refer to scripts/logs require their original run
captures; runtime logs are deliberately not published.
