"""Git updates preserve local work and never reset, clean, force or push."""
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime,timezone

class UpdateError(OSError):pass

def update_repository(folder,notify=lambda _:None):
    root=Path(folder).resolve()
    if not shutil.which('git'):raise UpdateError('Install Git for Windows before using Update.')
    def git(*args,check=True):
        try:
            result=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True,
                encoding='utf-8',errors='replace',timeout=120,
                env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except subprocess.TimeoutExpired as exc:raise UpdateError('Git timed out. Check your connection and Git authentication.') from exc
        if check and result.returncode:
            raise UpdateError(result.stderr.strip() or result.stdout.strip() or 'Git operation failed.')
        return result
    top=git('rev-parse','--show-toplevel',check=False)
    if top.returncode:raise UpdateError('This folder is not a Git clone yet. See GITHUB SETUP.md.')
    if Path(top.stdout.strip()).resolve()!=root:raise UpdateError('Update requires this bot folder to be the repository root.')
    branch=git('symbolic-ref','--quiet','--short','HEAD',check=False)
    if branch.returncode:raise UpdateError('Detached Git checkout. Switch to your update branch first.')
    for name in ('MERGE_HEAD','CHERRY_PICK_HEAD','REVERT_HEAD','rebase-merge','rebase-apply'):
        path=Path(git('rev-parse','--git-path',name).stdout.strip())
        if not path.is_absolute():path=root/path
        if path.exists():raise UpdateError('Finish the existing Git merge/rebase before updating.')
    if git('ls-files','-u').stdout.strip():raise UpdateError('Resolve existing Git conflicts before updating.')
    upstream=git('rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}',check=False)
    if upstream.returncode:raise UpdateError('No upstream branch configured. Clone from GitHub or set the branch upstream first.')
    notify('[Launcher] Checking for updates…\n')
    git('fetch','--prune')
    if git('merge-base','--is-ancestor','HEAD','@{upstream}',check=False).returncode:
        raise UpdateError('Local commits diverge from GitHub. Update stopped; no files changed.')
    before=git('rev-parse','HEAD').stdout.strip()
    remote=git('rev-parse','@{upstream}').stdout.strip()
    if before==remote:return 'Already up to date.'
    stash=None
    if git('status','--porcelain','--untracked-files=normal').stdout.strip():
        label='SupremeDeity update backup '+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        git('stash','push','--include-untracked','--message',label)
        stash=git('rev-parse','refs/stash').stdout.strip()
        notify(f'[Launcher] Local edits saved in Git stash {stash[:12]}. Backup will be retained.\n')
    pull_error=None
    try:
        git('pull','--ff-only')
    except UpdateError as exc:
        pull_error=exc
    if stash:
        reapplied=git('stash','apply','--index',stash,check=False)
        if reapplied.returncode:
            raise UpdateError(f'Local edits could not be reapplied cleanly. Backup {stash} remains in git stash. Resolve conflicts before running the bot.')
    if pull_error:raise UpdateError(f'Update failed: {pull_error} Local edits were restored; the stash backup was retained.' if stash else str(pull_error))
    after=git('rev-parse','HEAD').stdout.strip()
    return f'Updated {before[:8]} → {after[:8]}. Restart the launcher. Run Setup.cmd if dependencies changed.'
