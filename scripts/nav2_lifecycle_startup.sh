#!/usr/bin/env bash

start_lifecycle_with_retry() {
  local service_name="$1"
  local lifecycle_name="$2"
  local attempt

  for attempt in 1 2 3; do
    echo "Waiting for $lifecycle_name lifecycle manager service (attempt $attempt/3)..."
    if wait_for_service "$service_name"; then
      echo "Starting $lifecycle_name lifecycle (attempt $attempt/3)..."
      if call_startup "$service_name"; then
        return 0
      fi
      echo "$lifecycle_name lifecycle startup attempt $attempt/3 failed."
    else
      echo "$lifecycle_name lifecycle manager service readiness attempt $attempt/3 failed: $service_name"
    fi

    if [ "$attempt" -lt 3 ]; then
      echo "Retrying $lifecycle_name lifecycle startup in 2 seconds..."
      sleep 2
    fi
  done

  echo "$lifecycle_name lifecycle startup exhausted after 3 attempts: $service_name"
  return 1
}
