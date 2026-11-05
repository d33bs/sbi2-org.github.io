# Live WordPress static mirror

These helpers produced `backup/` from the public live sbi2.org site, not from
a database dump. Python requires Beautiful Soup (`beautifulsoup4`) and `lxml`.
Node is used only for presentation-runtime regression tests.

## Pipeline

1. Fetch the live `robots.txt` and `sitemap_index.xml`, then every child sitemap.
   Record the unique `<url><loc>` entries in `seeds.txt` and `discovery.json`.
   Do not include image-sitemap `<image:loc>` values as page seeds.
2. Use GNU wget to fetch those URLs and recursively follow same-site links and
   page requisites. Respect robots, avoid admin/API/action endpoints, and use
   bounded timeouts/retries and a small request delay.
3. Download the public poster views using Airtable's visible Download CSV
   action. Record the displayed record count, visible fields, live source URL,
   timestamp, and CSV path in `embeds/index.json`. Do not use private APIs or
   collect hidden fields. Current exports contain 48 and 57 public records.
4. Run `mirror.py`, then all tests and `verify.py`, then browser/HTTP checks.

The capture layout expected by `mirror.py` is:

    capture/
      discovery.json       origin, captured_utc, seed_urls; optional sitemap metadata
      seeds.txt
      live/                original wget capture, including .orig files
      live-crawl.log       wget request, redirect, save-path, and error log
      embeds/index.json    optional public export provenance
      embeds/<year>/*.csv

The raw capture is temporary local working data, not needed to host `backup/`,
and is deliberately not committed. It may be pruned after the generated static
copy has been verified. To update later, create a new capture from the current
live sitemaps rather than rebuilding from an older capture or substituting
WordPress backups.

## Downloader options used

With CAPTURE pointing at the capture directory containing fresh seeds:

    wget --compression=auto --recursive --level=inf --page-requisites \
      --convert-links --backup-converted --adjust-extension \
      --no-host-directories --directory-prefix="$CAPTURE/live" \
      --domains=sbi2.org,www.sbi2.org --https-only \
      --timeout=20 --tries=2 --wait=0.12 --max-redirect=5 --quota=700m \
      --restrict-file-names=windows \
      --reject-regex='(/wp-json/|/wp-admin/|/wp-login\.php|/xmlrpc\.php|/feed/?|[?&](s|replytocom|rest_route|action|redirect_to)=)' \
      --user-agent='curl/8.7.1' --input-file="$CAPTURE/seeds.txt" \
      --output-file="$CAPTURE/live-crawl.log"

The live server rejected the default Python requests user-agent but accepted
ordinary curl/wget requests. No authentication or challenge bypass was used.
The crawl completed with wget exit 8 because one source image returned 404;
all sitemap entries were captured. Inspect every failure rather than treating
either a downloader exit code or the presence of files as sufficient proof.

## Build and verify

    python3 tools/live_site_backup/mirror.py --capture "$CAPTURE" --output backup
    python3 tools/live_site_backup/test_mirror.py
    node --test tools/live_site_backup/test_runtime.cjs
    python3 tools/live_site_backup/verify.py backup --report backup/_archive/verification.json

Rebuilding overwrites generated files. Review changes before committing.
Do not commit the raw capture or `.orig` files. Edit sanitizer/templates, not
the generated copies, when fixing presentation behavior.

The sanitizer removes original JavaScript and form controls, preserves safe
content and PDFs, rewrites references to relative local paths, renders checked
public CSV exports with HTML escaping, and records uncaptured links explicitly.
It recognizes a PDF and a WOFF2 font that the live server mislabeled as HTML.
It also handles wget's `materials.orig` versus `materials.html.orig` naming.

Browser checks should block the live host and verify desktop/mobile menus,
slideshows, forms, poster details, and representative page layouts. Test both
`/backup/` and a project prefix such as `/sbi2-org.github.io/backup/`.
Use an isolated preview root containing only the public mirror. Check port
ownership before starting a server; an older server can otherwise make health
checks appear to succeed while serving the wrong directory.
