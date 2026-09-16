#!/bin/sh
# Rebuild MANIFEST.sha256 from staged content, never from the working tree.
#
# The obvious `git ls-files | xargs shasum -a 256` hashes whatever is on disk.
# When several people or sessions share one checkout, that captures someone
# else's unstaged edit and publishes a hash for a file version that was never
# committed, so `shasum -a 256 -c MANIFEST.sha256` fails on a fresh clone.
# `git cat-file blob :path` reads the index, which is exactly what the next
# commit will contain.
#
# Usage: stage your changes, run this, stage MANIFEST.sha256, then commit.
set -eu
cd "$(git rev-parse --show-toplevel)"
git ls-files | grep -v '^MANIFEST\.sha256$' | LC_ALL=C sort | while IFS= read -r file; do
  printf '%s  %s\n' "$(git cat-file blob ":$file" | shasum -a 256 | cut -d' ' -f1)" "$file"
done > MANIFEST.sha256
echo "MANIFEST.sha256: $(wc -l < MANIFEST.sha256 | tr -d ' ') entries from the index"
