#!/usr/bin/env bash
set -euo pipefail

installer="./napcat-installer.sh"

if [ ! -f "${installer}" ]; then
  echo "Napcat installer is not bundled in this sanitized repository." >&2
  echo "Place a trusted installer at ${installer}, then run this script again." >&2
  exit 1
fi

chmod +x "${installer}"
exec bash "${installer}" --docker n --cli y "${@}"
