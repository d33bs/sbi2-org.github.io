# Static backup of sbi2.org

This directory is a fresh copy of the public live website captured on
November 5, 2026. It was not built from the WordPress/Updraft database backup
or the analytics recovery in `wp_backup/`.

## What is included

- All 103 entries in the live page, member, and publication sitemaps, plus
  additional linked pages: 115 captured HTML pages in total.
- Original styling, images, fonts, and 13 local PDF documents, including the
  November 2026 Boston conference program.
- The 2026 and 2025 public poster directories as static expandable abstracts:
  48 and 57 records respectively. Full CSV exports are under `_archive/`.
- Relative navigation and asset links, so the same files work at `/backup/`,
  a GitHub project-site prefix, or another static hosting path.
- Local mobile-menu, submenu, and image-slideshow behavior without WordPress.

Membership, login, registration, contact, and submission forms are disabled
and replaced by visible placeholders. Third-party form links lead to a local
placeholder instead of accepting submissions or payments. No login-gated
content was accessed. External websites, social accounts, Google Drive files,
and other outbound resources remain external links rather than being copied.

The original site's scripts, trackers, inline event handlers, and backend
integrations are removed. A restrictive content-security policy blocks form
submission, network/API calls, and external scripts/frames. The backup is
marked `noindex, nofollow` and displays a notice identifying it as a static copy.

## Preview locally

From the repository root:

    python3 -m http.server 8080 --bind 127.0.0.1 --directory backup

Then open `http://127.0.0.1:8080/`. This serves only the public static copy;
do not serve the repository root, which also contains private backup data.

No build step is required. When included in a GitHub Pages deployment of this
repository, the copy is available under the site's `/backup/` path. The existing
root page and Pages configuration are not changed by this snapshot.

## Checks and provenance

- `_archive/manifest.json`: live source URLs, capture time, sitemap coverage,
  original page fingerprints, public poster exports, and deferred actions.
- `_archive/verification.json`: full offline HTML/CSS reference checks.
- `_archive/browser-verification.json`: representative browser checks.
- `_archive/http-verification.json`: local HTTP checks at a project-site prefix.
- `../tools/live_site_backup/`: sanitizer, presentation templates, tests,
  and verification script.

Run the automated checks from the repository root:

    python3 tools/live_site_backup/test_mirror.py
    node --test tools/live_site_backup/test_runtime.cjs
    python3 tools/live_site_backup/verify.py backup --report backup/_archive/verification.json

## Known source limitations

One venue image returns HTTP 404 on the live site. It is replaced with an
explicit unavailable-image notice, not an image recovered from an older backup.
The exact URL is recorded in `_archive/manifest.json`.

An original contact link uses the unsupported `mailton:` scheme. It is
neutralized with an explanation rather than silently changing the source
address; the original value is retained in the manifest.

Live search/filtering, accounts, payments, form processing, and automatic
future updates are not implemented. PDF rendering depends on the browser;
local document/download links remain available. This is a dated static
snapshot, not a replacement WordPress installation.
