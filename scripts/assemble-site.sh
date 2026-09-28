#!/bin/sh
set -eu

output="${1:-dist}"
test -f "$output/app/index.html"
mkdir -p "$output/assets"

install -m 0644 site/site.css "$output/site.css"
install -m 0644 site/robots.txt "$output/robots.txt"
# A custom domain belongs to the upstream site, not to forks.
if [ "${OCS_SITE_URL:-https://www.opencadstudio.com}" = "https://www.opencadstudio.com" ]; then
  install -m 0644 site/CNAME "$output/CNAME"
else
  rm -f "$output/CNAME"
fi
install -m 0644 site/workspace.png "$output/og.png"
install -m 0644 site/workspace.png "$output/assets/workspace.png"
install -m 0644 site/modeling.png "$output/assets/modeling.png"
python3 scripts/build-site.py "$output"
