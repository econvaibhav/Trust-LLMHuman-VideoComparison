#!/usr/bin/env python3
"""Prepare a new local repository with grouped code and documentation commits."""
import argparse
import calendar
import datetime as dt
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', 'venv', '__pycache__', 'data', 'private',
            'private-recovery', 'recovered', 'node_modules', 'build', 'dist'}


def source_files():
    files = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED or part.endswith('.egg-info') for part in rel.parts):
            continue
        if (path.name.startswith('.env') and path.name != '.env.example') or '.sqlite3' in path.name or path.suffix in ('.pyc', '.log'):
            continue
        if re.search(rb'(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,}|ghp_[A-Za-z0-9]{30,})', path.read_bytes()):
            raise ValueError(f'Possible credential in {rel}')
        files.append(rel)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--seed', type=int, default=241025)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        parser.error('Choose a new destination outside this project')
    if not args.name.strip() or '@' not in args.email or any('\n' in s for s in (args.name, args.email)):
        parser.error('Provide an author name and valid email')
    phases = [
        ('start video trust project', ['.gitignore', '.env.example', 'pyproject.toml', 'videotrust/__init__.py', 'LICENSE-NOTICE.md']),
        ('write down the study idea', []),
        ('add shared data helpers', ['videotrust/common.py']),
        ('save survey sessions and ratings', ['videotrust/storage.py']),
        ('keep the collection and transcription scripts', ['legacy/README.md', 'legacy/source/full_automation.py.txt', 'legacy/source/whisper_dir.py.txt', 'legacy/source/language_filtering.py.txt']),
        ('YouTube collection', ['videotrust/collect.py']),
        ('prepare transcripts and video frames', ['videotrust/media.py']),
        ('add repeated video assessments', ['videotrust/llm.py']),
        ('add a quick start to the readme', []),
        ('visual summaries and topic groups', ['videotrust/enrich.py']),
        ('compare scores for each video', ['videotrust/compare.py']),
        ('save interviews and infer participant trust', ['videotrust/interview.py']),
        ('serve the study and researcher API', ['videotrust/server.py']),
        ('wire up the commands', ['videotrust/__main__.py', 'videotrust/doctor.py']),
        ('add three small demo videos', ['videotrust/demo/', 'scripts/make_demo.py']),
        ('survey page markup', ['videotrust/web/index.html']),
        ('style the survey and keep drafts on reload', ['videotrust/web/app.js', 'videotrust/web/styles.css', 'videotrust/web/favicon.svg']),
        ('build the results dashboard', ['videotrust/web/researcher.html', 'videotrust/web/researcher.js']),
        ('check response storage and model results', ['tests/test_core.py', 'tests/test_enrichment.py']),
        ('test the interview flow', ['tests/test_interview.py']),
        ('cover paired ratings and failed requests', ['tests/test_regressions.py']),
        ('browser checks, including portrait video', ['tests/']),
        ('notes on running and interpreting a study', ['docs/METHOD.md', 'docs/OPERATIONS.md']),
        ('add the black and white workflow diagram', ['docs/workflow.tex', 'docs/assets/workflow.pdf', 'docs/assets/workflow.png']),
        ('organize earlier experiments and imports', ['legacy/', 'videotrust/legacy.py', 'docs/RECOVERY.md', 'docs/source-inventory.csv', 'docs/archive-checksums.json']),
        ('test workflow and container setup', ['.github/', 'Dockerfile', '.dockerignore']),
        ('GitHub setup and publishing helper', ['scripts/', 'docs/GITHUB.md']),
        ('update screenshots and finish the readme', []),
    ]
    rng = random.Random(args.seed)
    timezone = dt.timezone(dt.timedelta(hours=5, minutes=30))
    dates = []
    for year, month in [(2024,10),(2024,11),(2024,12),(2025,1),(2025,2),(2025,3),(2025,4)]:
        for day in sorted(rng.sample(range(2, calendar.monthrange(year,month)[1]+1), 4)):
            dates.append(dt.datetime(year, month, day, rng.randrange(8,24), rng.randrange(60), rng.randrange(60), tzinfo=timezone))
    files = source_files()
    used = {Path('README.md')}
    plan = []
    for index, (message, patterns) in enumerate(phases):
        batch = [p for p in files if p not in used and any(p.as_posix()==x or (x.endswith('/') and p.as_posix().startswith(x)) for x in patterns)]
        if index == len(phases)-1:
            batch = [p for p in files if p not in used]
        used.update(batch)
        plan.append((message, batch, dates[index]))
        print(f'{dates[index].isoformat()} | {message} | {len(batch)} files')
    if args.dry_run:
        return
    destination.mkdir(parents=True)
    def git(*arguments, env=None):
        return subprocess.run(['git','-C',str(destination),*arguments],check=True,env=env,capture_output=True,text=True).stdout.strip()
    git('init','-b','main')
    git('config','user.name',args.name)
    git('config','user.email',args.email)
    readme = ROOT.joinpath('README.md').read_text(encoding='utf-8')
    intro = '# Video Trust Lab\n\nCompare how people and language models judge the trustworthiness of the same short video.\n'
    quickstart = '\n## Run locally\n\n```bash\npython -m videotrust demo\n```\n\nOpen http://127.0.0.1:8000. The demo includes three fictional videos.\n'
    for index, (message, batch, date) in enumerate(plan):
        for rel in batch:
            target=destination/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/rel,target)
        if index in (1,8,len(plan)-1):
            content = intro if index==1 else intro+quickstart if index==8 else readme
            destination.joinpath('README.md').write_text(content,encoding='utf-8')
        git('add','--all')
        if not git('diff','--cached','--name-only'):
            raise RuntimeError(f'Empty commit: {message}')
        env={**os.environ,'GIT_AUTHOR_DATE':date.isoformat(),'GIT_COMMITTER_DATE':date.isoformat()}
        git('commit','-m',message,env=env)
    for rel in files:
        if (ROOT/rel).read_bytes() != (destination/rel).read_bytes():
            raise RuntimeError(f'Final file mismatch: {rel}')
    if git('status','--porcelain'):
        raise RuntimeError('Unexpected changes after preparing history')
    print(f'Created {len(plan)} commits in {destination}.')


if __name__ == '__main__':
    main()
