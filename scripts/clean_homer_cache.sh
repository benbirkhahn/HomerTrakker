#!/bin/bash

# Script to clean HomerTrakker cache
CACHE_DIR="/Users/benbirkhahn/HomerTrakker/.homer_cache"

# Remove all cached files
rm -rf "$CACHE_DIR"/*

# Recreate cache directory
mkdir -p "$CACHE_DIR"

echo "HomerTrakker cache cleaned."