#!/bin/sh

# Regenerate .env.example from .env
awk -F= '
/^[[:space:]]*#/ { next }
/^[[:space:]]*$/ { next }
{
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1)
  print $1 "="
}
' .env > .env.example

# Add the updated file automatically
git add .env.example
