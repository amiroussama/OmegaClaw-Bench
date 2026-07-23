"""T1.3 fixtures: repo/cwd specs for the scope_routing benchmark.

Deterministic repo topology exercised by the runner (which does the real
``git init`` + ``git remote add`` and the probing). Covers every routing rule
in ``scopes.resolve``/``project_key``:

  * distinct remotes (repo-a/-b/-c) -> distinct sha1(remote) keys;
  * a clone-equivalent checkout with repo-a's remote -> repo-a's key (the
    "clones/worktrees share an atomspace" contract);
  * a no-remote repo -> sha1(realpath) path key;
  * a non-git directory -> the GLOBAL scope.

Each repo is probed at its toplevel and several nested subdirs (walk-up), so
routing accuracy is measured over >=40 probes.
"""

SEED = 2204

# (name, remote|None, is_git). The clone shares repo-a's remote.
REPOS = [
    {"name": "repo-a", "remote": "https://example.test/org/repo-a.git", "git": True},
    {"name": "repo-b", "remote": "git@example.test:org/repo-b.git", "git": True},
    {"name": "repo-c", "remote": "https://example.test/org/repo-c.git", "git": True},
    {"name": "clone-a", "remote": "https://example.test/org/repo-a.git", "git": True,
     "same_key_as": "repo-a"},
    {"name": "noremote", "remote": None, "git": True},
    {"name": "plaindir", "remote": None, "git": False},   # not a repo -> global
]

# Nested subdirs created inside each repo; every one is a probe cwd (plus the
# repo toplevel), all of which must resolve to the repo's scope.
SUBDIRS = ["", "src", "src/pkg", "src/pkg/inner", "tests", "docs", "a/b/c", "deep/nested/dir"]


def summary():
    return {"seed": SEED, "repos": len(REPOS), "subdirs_per_repo": len(SUBDIRS),
            "probes": len(REPOS) * len(SUBDIRS)}


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))
