# DVC cheat sheet (every command used in the workshop)

Mental model: **git** tracks code + small pointer files; **DVC** tracks the big
files those pointers refer to, in `.dvc/cache` locally and on a **remote**.

## Set up

| Command | What it does |
|---|---|
| `dvc init` | Make the current git repo a DVC project (creates `.dvc/`). Use `--subdir` inside a monorepo. |
| `dvc config --global core.analytics false` | Turn off anonymous usage statistics (or set `DVC_NO_ANALYTICS=1`). |
| `dvc remote add -d <name> <url>` | Add a remote (where data is pushed); `-d` makes it the default. Stored in `.dvc/config` (commit it). |
| `dvc remote modify --local <name> <key> <value>` | Remote setting kept out of git (credentials) in `.dvc/config.local`. |
| `dvc remote list` | Show configured remotes. |

## Track and share data

| Command | What it does |
|---|---|
| `dvc add <file-or-dir>` | Hash it, copy it into the cache, write `<name>.dvc`, gitignore the real file. Rerun after the data changes. |
| `dvc push` | Upload cached files to the remote. **Separate from `git push`.** |
| `dvc pull` | Download the files the current pointers refer to (= `dvc fetch` + `dvc checkout`). |
| `dvc checkout` | Make workspace files match the current pointers (after `git checkout`, `git restore`, ...). |
| `dvc status` | What changed locally vs. the pointers / `dvc.lock` (what `dvc repro` would rerun). |
| `dvc status --cloud` | What exists locally but hasn't been pushed. |
| `dvc diff [rev1] [rev2]` | Which tracked files were added / modified / deleted between versions. |

## Pipelines

| Command | What it does |
|---|---|
| `dvc dag` | Draw the stage graph from `dvc.yaml`. |
| `dvc repro` | Run stages whose deps/params changed, plus everything downstream; update `dvc.lock`. |
| `dvc params diff [rev1] [rev2]` | Parameter changes (default: last commit vs. workspace). |
| `dvc metrics diff [rev1] [rev2]` | Metric changes (default: last commit `HEAD` vs. current files `workspace`). |
| `dvc metrics show --all-tags` | One row of metrics per git tag. |
| `dvc plots diff <rev> -o <dir>` | HTML plots comparing a version with the current one. |

## Experiments

| Command | What it does |
|---|---|
| `dvc exp run -n <name> -S key=value` | Run the pipeline with overridden params, saved as a named experiment (not a commit). |
| `dvc exp run --queue -S 'key=a,b'` | Queue one run per value combination. |
| `dvc queue start -j 2` / `dvc queue status` | Run the queue (2 at a time) / check progress. |
| `dvc exp show --only-changed` | Table of all experiments: params and metrics. |
| `dvc exp apply <name>` | Load an experiment's results into the workspace (then `git commit` to promote it). |
| `dvc exp branch <name> <branch>` | Turn an experiment into a git branch. |

## Versions from other places

| Command | What it does |
|---|---|
| `dvc import <repo-url> <path> -o <out>` | Download data from another DVC repo (e.g. a data registry) and record its source + revision. |
| `dvc update <file>.dvc` | Move an imported dataset to the source's newer version. |
| `dvc get <repo-url> <path>` | Download without tracking the source. |
| `dvc.api.open/read/params_show/metrics_show(..., rev=...)` | Read any version from Python, no checkout needed. |

## Housekeeping

| Command | What it does |
|---|---|
| `dvc gc --all-tags --all-branches -f` | Delete cached files no tag/branch uses. (`-w` keeps only the current workspace: risky.) |
| `dvc install` | Git hooks: `git push` also runs `dvc push`, `git checkout` also runs `dvc checkout`. Not for `--subdir` projects. |

## Git commands used alongside

| Command | What it does |
|---|---|
| `git tag <name>` | Permanent, readable name for the current commit (e.g. `v1`). |
| `git checkout <tag-or-branch>` | Move code + pointers to that version (follow with `dvc checkout`). |
| `git restore .` | Discard uncommitted changes to git-tracked files (follow with `dvc checkout`). |
| `git log --oneline --decorate` | History, with tags shown. |

## The four files to know

| File | In git? | What it is |
|---|---|---|
| `data/raw.dvc` | yes | Pointer to a `dvc add`-ed file/folder: its md5 hash = the version's ID |
| `dvc.yaml` | yes | Pipeline definition (you write it) |
| `dvc.lock` | yes | Exact hashes of every dep/param/output from the last run (DVC writes it) |
| `.dvc/cache/` | no | The actual bytes, stored by hash; mirrored on the remote |
