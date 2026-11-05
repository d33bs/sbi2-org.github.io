#!/usr/bin/env python3
"""Turn a live wget capture into a read-only subdirectory-safe static website."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import html
import json
import shutil
import posixpath
import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup

TRACKERS = ('stats.wp.com', 'google-analytics.com', 'googletagmanager.com', 'matomo.php', 'piwik.php')
FORM_HOSTS = ('jotform.com', 'typeform.com', 'formstack.com', 'forms.gle', 'forms.office.com', 'docs.google.com/forms')


def relative(page, target):
    return posixpath.relpath(str(target), str(page.parent))


def rewrite_reference(value, page, urls, source_url):
    if not value or value.startswith(('#', 'data:', 'mailto:', 'tel:')):
        return value
    parts = urlsplit(urljoin(source_url, value))
    canonical = urlunsplit(('https', parts.netloc.replace('www.', '', 1), parts.path, parts.query, ''))
    target = urls.get(canonical)
    if target is None and parts.query:
        target = urls.get(urlunsplit(('https', parts.netloc.replace('www.', '', 1), parts.path, '', '')))
    if target is None:
        return value
    path = quote(relative(page, target), safe="/@=:+!$&'()*,-._~")
    return path + ('#' + parts.fragment if parts.fragment else '')


def rewrite_css(source, page, urls, source_url):
    def replace(match):
        value = match[2].strip()
        return 'url("' + rewrite_reference(value, page, urls, source_url) + '")'
    return re.sub(r'url\(\s*([\'\"]?)(.*?)\1\s*\)', replace, source, flags=re.I)


def rewrite_html(source, page, urls, source_url, embedded=None):
    """Preserve public content while removing executable site/form integrations."""
    soup = BeautifulSoup(source, 'lxml')
    events = []
    for tag in list(soup.find_all('script')):
        tag.decompose()
    for tag in list(soup.find_all('form')):
        events.append({'page': page.as_posix(), 'kind': 'form', 'source': tag.get('action', source_url)})
        note = soup.new_tag('section', attrs={'class': 'backup-placeholder', 'role': 'note'})
        title = soup.new_tag('h2')
        title.string = 'Interactive form unavailable'
        note.append(title)
        paragraph = soup.new_tag('p')
        paragraph.string = 'Forms are disabled in this static backup. This placeholder is reserved for a future replacement; no information can be submitted here.'
        note.append(paragraph)
        tag.replace_with(note)
    for tag in list(soup.find_all('link')):
        if set(tag.get('rel', [])) & {'alternate', 'canonical', 'shortlink', 'profile', 'preconnect', 'dns-prefetch', 'modulepreload'} or tag.get('as') == 'script':
            tag.decompose()
    for tag in list(soup.find_all('iframe')):
        original = str(tag.get('src', '')).strip()
        if embedded and original in embedded:
            fragment = BeautifulSoup(embedded[original], 'lxml')
            tag.replace_with(fragment.find('section'))
            continue
        events.append({'page': page.as_posix(), 'kind': 'embed', 'source': original})
        note = soup.new_tag('section', attrs={'class': 'backup-placeholder', 'role': 'note'})
        heading = soup.new_tag('h2')
        heading.string = 'Embedded content not included'
        note.append(heading)
        paragraph = soup.new_tag('p')
        paragraph.string = 'This live embedded service is not part of the static backup. A replacement can be added later.'
        note.append(paragraph)
        if original.startswith('https://') and not any(host in original.lower() for host in FORM_HOSTS):
            link = soup.new_tag('a', href=original)
            link.string = 'View original embedded content (external)'
            note.append(link)
        tag.replace_with(note)
    for tag in soup.select('a[href]'):
        original = str(tag['href'])
        if urlsplit(original).scheme not in ('', 'http', 'https', 'mailto', 'tel'):
            events.append({'page': page.as_posix(), 'kind': 'unsupported-link', 'source': original})
            tag['href'] = '#'
            tag['title'] = 'Unavailable: the live source uses an unsupported URL scheme'
        elif any(host in original.lower() for host in FORM_HOSTS):
            events.append({'page': page.as_posix(), 'kind': 'external-form-link', 'source': original})
            tag['href'] = relative(page, '_archive/forms/index.html')
            tag['title'] = 'Interactive form unavailable in this static backup'
            tag['class'] = list(tag.get('class', [])) + ['backup-form-link']
    for tag in list(soup.find_all(['input', 'textarea', 'select'])):
        tag.decompose()
    for tag in list(soup.find_all(True)):
        if tag.attrs is None:
            continue
        if any(term in str(tag.get('src', '')).lower() for term in TRACKERS):
            tag.decompose()
            continue
        for attr in list(tag.attrs):
            if attr.lower().startswith('on'):
                del tag[attr]
        if tag.name == 'object' and tag.get('type') == 'application/pdf':
            tag.attrs.pop('hidden', None)
            tag.attrs.pop('data-wp-bind--hidden', None)
        if tag.name == 'img' and tag.get('loading') == 'lazy' and tag.find_parent(class_='wp-block-jetpack-slideshow'):
            # Our runtime toggles the `hidden` attribute (display:none) to switch
            # slides instead of Swiper's always-laid-out transform track, so a
            # native lazy fetch never fires until the slide is already current —
            # the image would be blank for the whole first paint of that slide.
            del tag['loading']
        attributes = ('href', 'src', 'poster', 'data-src') + (('data',) if tag.name == 'object' else ())
        for attr in attributes:
            if isinstance(tag.get(attr), str):
                tag[attr] = rewrite_reference(tag[attr], page, urls, source_url)
        if isinstance(tag.get('srcset'), str) and not tag['srcset'].startswith('data:'):
            candidates = []
            for candidate in tag['srcset'].split(','):
                bits = candidate.strip().split()
                if bits:
                    bits[0] = rewrite_reference(bits[0], page, urls, source_url)
                    candidates.append(' '.join(bits))
            tag['srcset'] = ', '.join(candidates)
        if tag.get('style'):
            tag['style'] = rewrite_css(tag['style'], page, urls, source_url)
        if tag.name == 'style' and tag.string:
            tag.string = rewrite_css(str(tag.string), page, urls, source_url)
    if soup.head is None:
        head = soup.new_tag('head')
        (soup.html or soup).insert(0, head)
    assert soup.head is not None
    for meta in list(soup.head.select('meta[name="robots"],meta[http-equiv="refresh"],meta[http-equiv="Content-Security-Policy"]')):
        meta.decompose()
    soup.head.append(soup.new_tag('meta', attrs={'name': 'robots', 'content': 'noindex, nofollow'}))
    soup.head.append(soup.new_tag('meta', attrs={'http-equiv': 'Content-Security-Policy', 'content': "default-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"}))
    soup.head.append(soup.new_tag('link', attrs={'rel': 'stylesheet', 'href': relative(page, '_archive/backup.css')}))
    body = soup.body or soup
    notice = soup.new_tag('aside', attrs={'class': 'backup-notice', 'role': 'note'})
    notice.string = 'Static backup of sbi2.org — forms are disabled. External services are not mirrored.'
    body.insert(0, notice)
    body.append(soup.new_tag('script', attrs={'src': relative(page, '_archive/runtime.js'), 'defer': ''}))
    return str(soup), events


def standalone(title, message):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title></head><body class="backup-standalone"><h1>{html.escape(title)}</h1><section class="backup-placeholder">{message}</section><p><a href="https://sbi2.org/">Backup home</a></p></body></html>'


def render_dataset(path, expected_count, fields):
    """Render only the explicitly identified fields of a public CSV export."""
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != fields:
            raise ValueError('Public export fields differ from the recorded visible columns')
        rows = list(reader)
    if len(rows) != expected_count:
        raise ValueError('Public export count differs from the displayed record count')
    parts = [f'<section class="backup-poster-directory" data-record-count="{len(rows)}"><h2>Poster abstracts — static directory</h2><p>{len(rows)} public poster records preserved in full. Expand a title to read its abstract. Live filters and editing are not included.</p>']
    for index, row in enumerate(rows, 1):
        title = row.get('Abstract Title') or row.get('Poster number & title') or f'Poster {index}'
        if row.get('Poster Number'):
            title = row['Poster Number'] + ' — ' + title
        parts.append(f'<details class="backup-poster" id="poster-{index}"><summary>{html.escape(title)}</summary><dl>')
        for field in fields:
            if field not in ('Abstract', 'Abstract Title', 'Poster number & title'):
                parts.append(f'<dt>{html.escape(field)}</dt><dd>{html.escape(row.get(field) or "")}</dd>')
        parts.append('</dl><div class="backup-abstract">' + html.escape(row.get('Abstract') or '') + '</div></details>')
    parts.append('</section>')
    return ''.join(parts)


def original_file(source):
    # wget can add .html after creating its .orig file (materials.orig).
    for candidate in (source.with_name(source.name + '.orig'), source.with_suffix('.orig')):
        if candidate.is_file():
            return candidate
    return source


def build_capture(capture, output):
    """Build exclusively from freshly captured public HTTP responses, not WP dumps."""
    capture, output = Path(capture).resolve(), Path(output).resolve()
    raw = capture / 'live'
    if not raw.is_dir() or output == raw or raw.is_relative_to(output):
        raise ValueError('Separate live-capture and output directories are required')
    discovery = json.loads((capture / 'discovery.json').read_text())
    origin = discovery['origin'].rstrip('/')
    files, raw_to_output = {}, {}
    for source in sorted(raw.rglob('*')):
        if source.is_file() and source.suffix != '.orig' and re.search(r'\.(html|css|png|jpe?g|gif|webp|svg|ico|woff2?|ttf|eot|otf|pdf|mp[34]|webm|ogg|wav)(?:@[^/]*)?$', source.name, re.I):
            rel = source.relative_to(raw)
            with source.open('rb') as stream:
                magic = stream.read(8)
            if source.suffix == '.html' and magic.startswith(b'%PDF-'):
                rel = rel.with_suffix('.pdf')
            elif source.suffix == '.html' and magic.startswith((b'wOF2', b'wOFF')):
                rel = rel.with_suffix('')
            files[rel] = source
            raw_to_output[source.relative_to(raw)] = rel
    urls, sources, redirects, errors = {}, {}, {}, []
    current = None
    for line in (capture / 'live-crawl.log').read_text(errors='replace').splitlines():
        request = re.match(r'^--\d{4}-.+--\s+(https?://\S+)$', line)
        if request:
            current = request[1]
        saved = re.search(r'Saving to: [‘\'](.+)[’\']', line)
        if saved and current:
            local = Path(saved[1]).resolve()
            if local.is_relative_to(raw):
                rel = raw_to_output.get(local.relative_to(raw))
                if rel in files:
                    urls[current] = rel
                    sources[rel] = current
        redirect = re.match(r'Location: (.+?) \[following\]', line)
        if redirect and current:
            redirects[current] = urljoin(current, redirect[1])
        status = re.search(r'awaiting response\.\.\. (\d{3})', line)
        if status and int(status[1]) >= 400 and current:
            errors.append({'url': current, 'status': int(status[1])})
    for rel, source in files.items():
        inferred = origin + '/' + rel.as_posix()
        urls.setdefault(inferred, rel)
        sources.setdefault(rel, inferred)
        if rel.name == 'index.html':
            urls.setdefault(origin + '/' + (rel.parent.as_posix().strip('.') + '/' if rel.parent != Path('.') else ''), rel)
        if rel.suffix == '.html':
            text = original_file(source).read_text(errors='replace')
            canonical = BeautifulSoup(text, 'lxml').find('link', rel='canonical')
            if canonical and canonical.get('href') and canonical['href'].startswith(origin) and rel.name == 'index.html':
                urls.setdefault(canonical['href'], rel)
    for _ in range(6):
        for old, new in redirects.items():
            if new in urls:
                urls[old] = urls[new]
    output.mkdir(parents=True, exist_ok=True)
    archive = output / '_archive'
    archive.mkdir(exist_ok=True)
    for name in ('runtime.js', 'backup.css'):
        shutil.copyfile(Path(__file__).with_name(name), archive / name)
    missing_image = Path('_archive/missing-image.svg')
    for error in errors:
        if re.search(r'\.(png|jpe?g|gif|webp|svg)(?:\?|$)', error['url'], re.I):
            urls[error['url']] = missing_image
    (output / missing_image).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300"><rect width="800" height="300" fill="#eef3f6"/><text x="400" y="150" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#324c5b">Image unavailable on the live site</text></svg>')
    # Give uncaptured same-site pages explicit notices instead of silently linking away.
    uncaptured = {}
    for rel, source in files.items():
        if rel.suffix != '.html':
            continue
        soup = BeautifulSoup(original_file(source).read_text(errors='replace'), 'lxml')
        for anchor in soup.select('a[href]'):
            target = urljoin(sources[rel], anchor['href']).split('#')[0]
            parts = urlsplit(target)
            if parts.netloc not in ('sbi2.org', 'www.sbi2.org') or target in urls:
                continue
            if parts.path.startswith(('/wp-json/', '/wp-admin/', '/wp-login.php')):
                urls[target] = Path('_archive/forms/index.html')
                continue
            if not parts.path or (Path(parts.path).suffix and Path(parts.path).suffix not in ('.html', '.php')):
                continue
            name = hashlib.sha256(target.encode()).hexdigest()[:12]
            fallback = Path('_archive/unavailable') / (name + '.html')
            urls[target] = fallback
            uncaptured[target] = fallback
    embedded, datasets = {}, []
    dataset_index = capture / 'embeds/index.json'
    if dataset_index.is_file():
        for dataset in json.loads(dataset_index.read_text()):
            source_csv = capture / dataset['csv']
            fragment = render_dataset(source_csv, dataset['expected_rows'], dataset['fields'])
            target_csv = Path('_archive') / ('posters-' + dataset['year'] + '.csv')
            download = relative(Path(dataset['page']), target_csv)
            fragment = fragment.replace('</section>', f'<p><a href="{download}">Download archived poster CSV</a></p></section>')
            embedded[dataset['source_url']] = fragment
            (output / target_csv).write_bytes(source_csv.read_bytes())
            datasets.append({**dataset, 'csv': target_csv.as_posix()})
    pages, events = [], []
    for rel, source in files.items():
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = original_file(source).read_bytes()
        if rel.suffix == '.html':
            text, notes = rewrite_html(content.decode('utf-8'), rel, urls, sources[rel], embedded)
            destination.write_text(text)
            events.extend(notes)
            pages.append({'path': rel.as_posix(), 'source_url': sources[rel], 'captured_file_sha256': hashlib.sha256(content).hexdigest()})
        elif rel.suffix == '.css':
            destination.write_text(rewrite_css(content.decode('utf-8'), rel, urls, sources[rel]))
        else:
            destination.write_bytes(content)
    document_routes = []
    for rel in files:
        if rel.name == 'index.pdf' and rel.with_suffix('.html') not in files:
            wrapper = rel.with_suffix('.html')
            message = f'<p>This live URL served a PDF. The document is preserved locally.</p><p><a href="{rel.name}">Open the original PDF</a></p><object type="application/pdf" data="{rel.name}" style="width:100%;height:85vh"><p>Use the PDF link above if your browser cannot display it here.</p></object>'
            text, _ = rewrite_html(standalone('Conference program (PDF)', message), wrapper, urls, sources[rel])
            (output / wrapper).write_text(text)
            document_routes.append({'path': wrapper.as_posix(), 'document': rel.as_posix(), 'source_url': sources[rel]})
    for url, rel in uncaptured.items():
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        page, _ = rewrite_html(standalone('Page not captured', f'<p>This page was not captured from the public live site. No older backup has been substituted.</p><p>Source: <code>{html.escape(url)}</code></p>'), rel, urls, origin + '/')
        destination.write_text(page)
    form_page = Path('_archive/forms/index.html')
    (output / form_page).parent.mkdir(parents=True, exist_ok=True)
    form_html, _ = rewrite_html(standalone('Interactive form unavailable', '<p>Membership, login, registration, contact submissions, and third-party forms are disabled in this static backup.</p><p>This is a placeholder for future replacement. No information can be submitted, and no registration or payment is processed.</p>'), form_page, urls, origin + '/')
    (output / form_page).write_text(form_html)
    manifest = {**discovery, 'source_kind': 'live-http-crawl', 'built_utc': datetime.now(timezone.utc).isoformat(),
                'pages': pages, 'document_routes': document_routes, 'embedded_datasets': datasets, 'interactive_placeholders': events, 'fetch_errors': errors,
                'uncaptured_links': [{'url': url, 'placeholder': path.as_posix()} for url, path in uncaptured.items()],
                'missing_seed_urls': [url for url in discovery['seed_urls'] if url not in urls or not (output / urls[url]).is_file()]}
    (archive / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('backup'))
    args = parser.parse_args()
    result = build_capture(args.capture, args.output)
    print(json.dumps({'pages': len(result['pages']), 'missing_seed_urls': result['missing_seed_urls'],
                      'placeholders': len(result['interactive_placeholders']), 'fetch_errors': result['fetch_errors'],
                      'uncaptured_links': result['uncaptured_links']}, indent=2))
