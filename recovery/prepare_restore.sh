#!/bin/zsh
# Prepare a fresh, paused checkout. Never installs/loads a scheduler or runs a pipeline.
set -eu
app_root="${0:A:h:h}"
restore_python="${HOMER_RESTORE_PYTHON:-python3.13}"
install_dependencies=0
case "${1:---offline}" in
  --offline) ;;
  --install-dependencies) install_dependencies=1 ;;
  *) print -u2 'Usage: prepare_restore.sh [--offline|--install-dependencies]'; exit 2 ;;
esac
command -v "$restore_python" >/dev/null || { print -u2 'Install Python 3.13 or set HOMER_RESTORE_PYTHON to its executable.'; exit 1; }
"$restore_python" -m venv "$app_root/twitter_bot_env"
if [[ ! -f "$app_root/.homer.env" ]]; then
  cp "$app_root/.homer.env.example" "$app_root/.homer.env"
  chmod 600 "$app_root/.homer.env"
fi
mkdir -p "$app_root/config" "$app_root/logs"
if (( install_dependencies )); then
  "$app_root/twitter_bot_env/bin/python3" -m pip install -r "$app_root/requirements-runtime.lock.txt"
fi
print 'Prepared paused checkout; no scheduler, workflow, OAuth, queue or publishing was run.'
print 'Run recovery tests and restore secure private inputs before any activation.'
