#!/usr/bin/env python3
"""Create a new private GitHub repository and push this prepared Git history."""
import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='econvaibhav/video-trust-lab', help='owner/name for a new repository')
    parser.add_argument('--execute', action='store_true', help='Create the private remote and push; otherwise show the command')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('Repository must be owner/name')
    command = ['gh', 'repo', 'create', args.repository, '--private', '--source', str(ROOT),
               '--remote', 'origin', '--push', '--description',
               'Human and LLM trust judgments of short videos: surveys, interviews, Whisper/OpenCV analysis, and comparison.']
    if not args.execute:
        print('This will create a NEW PRIVATE repository and push the existing commits:')
        print(subprocess.list2cmdline(command))
        print('Run again with --execute when ready. Existing repositories are never overwritten.')
        return 0
    if not shutil.which('gh'):
        parser.error('Install GitHub CLI from https://cli.github.com and run: gh auth login')
    if not (ROOT / '.git').is_dir():
        parser.error('Restore the Git bundle first; see docs/GITHUB.md')
    def git(*argv):
        return subprocess.check_output(['git', '-C', str(ROOT), *argv], text=True).strip()
    if git('status', '--porcelain'):
        parser.error('Commit or remove local changes before publishing')
    if git('remote'):
        parser.error('A remote already exists. Inspect it and use git push; this helper only creates new repositories.')
    subprocess.run(['gh', 'auth', 'status'], check=True)
    existing = subprocess.run(['gh', 'repo', 'view', args.repository, '--json', 'name'], capture_output=True, text=True)
    if existing.returncode == 0:
        parser.error('The destination repository already exists. Choose a new name; no changes were made.')
    subprocess.run(command, check=True)
    print(f'Published https://github.com/{args.repository}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
