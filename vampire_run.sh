#!/usr/bin/env bash

if (( $# < 1 )); then
  echo "Usage: $0 PROBLEM_LIST.txt [VAMPIRE_OPTIONS...]" >&2
  exit 2
fi

list=$1
shift
vampire="$(dirname -- "${BASH_SOURCE[0]}")/build/vampire"
jobs=${VAMPIRE_JOBS:-76}

if [[ ! -r "$list" ]]; then
  exit 2
fi

if [[ ! -x "$vampire" ]]; then
  exit 2
fi

if [[ ! "$jobs" =~ ^[1-9][0-9]*$ ]]; then
  exit 2
fi

if ! log_dir=$(mktemp -d "$PWD/vampire-logs.XXXXXX"); then
  exit 2
fi

echo "Parallel jobs: $jobs; logs: $log_dir" >&2
logs=()
running=0

for problem in $(cat "$list"); do
  printf -v log '%s/%08d.log' "$log_dir" "${#logs[@]}"
  logs+=("$log")

  (
    "$vampire" "$@" --input_file "$problem" </dev/null > "$log" 2>&1

    # Exit 1 means unsolved, not a runner failure.
    if (( $? > 1 )); then
      touch "$log_dir/failed"
    fi

  ) &

  running=$((running + 1))

  if (( running >= jobs )); then
    wait -n
    running=$((running - 1))
  fi

done

wait

if ! cat -- "${logs[@]}" </dev/null; then
  exit 2
fi

if [[ -e "$log_dir/failed" ]]; then
  exit 1
fi
