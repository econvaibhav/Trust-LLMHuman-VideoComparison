# GitHub setup

The package includes a complete repository on `main` with 28 commits between October 2024 and April 2025. Both author and committer timestamps are set. The history contains code, interface, tests, diagram and README changes.

## Publish the repository

Install [GitHub CLI](https://cli.github.com), then sign in:

```bash
gh auth login
```

From the `video-trust-lab` directory:

```bash
python scripts/publish_github.py --execute
```

This creates the private repository `econvaibhav/video-trust-lab` and pushes its existing commits. To choose a different destination:

```bash
python scripts/publish_github.py --repository econvaibhav/video-trust-study --execute
```

The helper refuses an existing destination, existing remote or uncommitted working changes. It never force-pushes. You can change repository visibility through GitHub settings after reviewing it.

## Restore from the portable bundle

If your unzip tool dropped the `.git` directory, clone the sibling bundle into a new directory:

```bash
git clone video-trust-lab.bundle video-trust-lab-restored
cd video-trust-lab-restored
git remote remove origin
python scripts/publish_github.py --execute
```

The removed `origin` points to the local bundle. The publishing command creates the GitHub remote.

## Inspect the commits

```bash
git log --reverse --format='%h %aI %cI %s'
git status --short
```

The commits use the GitHub noreply address associated with `econvaibhav`. Contribution display is controlled by GitHub account, repository, branch and privacy settings.

## Generate a separate local copy

```bash
python scripts/create_git_history.py --output ../video-trust-lab-copy \
  --name 'Vaibhav Agarwal' \
  --email '126394404+econvaibhav@users.noreply.github.com'
```

The script requires a new destination, writes real nonempty commits, verifies the final files and does not push. `--dry-run` prints the planned dates and file groups; `--seed` changes the timestamp distribution.
