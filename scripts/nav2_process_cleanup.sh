#!/usr/bin/env bash

stop_nav2_process_group() {
  local process_group="$1"
  [[ "$process_group" =~ ^[1-9][0-9]*$ ]] || return 1

  # The launch parent can exit before a composed node. Check the entire group
  # during shutdown so survivors cannot leak DDS services into the next run.
  kill -TERM -- "-$process_group" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! kill -0 -- "-$process_group" 2>/dev/null; then
      return 0
    fi
    sleep 0.25
  done

  if kill -0 -- "-$process_group" 2>/dev/null; then
    echo "Nav2 process group did not stop after SIGTERM; sending SIGKILL..."
    kill -KILL -- "-$process_group" 2>/dev/null || true
  fi
}
