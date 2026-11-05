#!/usr/bin/env python3
"""Check every generated page, active asset reference, and CSS URL offline."""
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit
from bs4 import BeautifulSoup


def verify_tree(root):
    root = Path(root).resolve()
    result: dict[str, Any] = {key: [] for key in ('missing_references', 'root_relative_references',
              'external_assets', 'live_site_links', 'unsafe_scripts', 'event_handlers', 'missing_fragments')}
    result.update({'checked_utc': datetime.now(timezone.utc).isoformat(), 'form_count': 0,
                   'local_references_checked': 0, 'html_pages': 0, 'css_files': 0})
    parsed = {}
    def read_html(file):
        if file not in parsed:
            parsed[file] = BeautifulSoup(file.read_text(), 'lxml')
        return parsed[file]
    def check(value, page, kind):
        if not value or value.startswith(('data:', 'mailto:', 'tel:')):
            return
        parts = urlsplit(value)
        detail = {'page': page.as_posix(), 'reference': value, 'kind': kind}
        if parts.scheme in ('http', 'https') or parts.netloc:
            if kind != 'a':
                result['external_assets'].append(detail)
            elif parts.netloc in ('sbi2.org', 'www.sbi2.org'):
                result['live_site_links'].append(detail)
            return
        if parts.scheme:
            result['unsafe_scripts'].append(detail)
            return
        if value.startswith('/'):
            result['root_relative_references'].append(detail)
        path = unquote(urlsplit(urljoin('/' + page.as_posix(), value)).path)
        target = (root / path.lstrip('/')).resolve()
        if not target.is_relative_to(root):
            result['missing_references'].append(detail)
            return
        if target.is_dir():
            target /= 'index.html'
        result['local_references_checked'] += 1
        if not target.is_file():
            result['missing_references'].append(detail)
        elif kind == 'a' and parts.fragment and target.suffix == '.html':
            fragment = unquote(parts.fragment)
            document = read_html(target)
            if not document.find(id=fragment) and not document.find('a', attrs={'name': fragment}):
                result['missing_fragments'].append(detail)
    def css_references(text, page):
        for match in re.finditer(r'url\(\s*([\'\"]?)(.*?)\1\s*\)', text, re.I):
            check(match[2].strip(), page, 'css-url')
        for match in re.finditer(r'@import\s+[\'\"]([^\'\"]+)[\'\"]', text, re.I):
            check(match[1], page, 'css-import')
    for file in sorted(root.rglob('*')):
        if not file.is_file():
            continue
        page = file.relative_to(root)
        if file.suffix == '.css':
            result['css_files'] += 1
            css_references(file.read_text(), page)
        elif file.suffix == '.html':
            result['html_pages'] += 1
            soup = read_html(file)
            result['form_count'] += len(soup.find_all('form'))
            for tag in soup.find_all(True):
                for attr in ('href', 'src', 'poster'):
                    if isinstance(tag.get(attr), str):
                        check(tag[attr], page, tag.name)
                if tag.name in ('object', 'embed') and tag.get('data'):
                    check(tag['data'], page, tag.name)
                if tag.get('srcset') and not tag['srcset'].startswith('data:'):
                    for candidate in tag['srcset'].split(','):
                        if candidate.strip():
                            check(candidate.strip().split()[0], page, 'srcset')
                if tag.get('style'):
                    css_references(tag['style'], page)
                if tag.name == 'style':
                    css_references(tag.get_text(), page)
                if tag.name == 'script':
                    src = tag.get('src', '')
                    local = (file.parent / unquote(urlsplit(src).path)).resolve() if src else None
                    if local != root / '_archive/runtime.js':
                        result['unsafe_scripts'].append({'page': page.as_posix(), 'source': src or 'inline'})
                for attr in tag.attrs:
                    if attr.lower().startswith('on'):
                        result['event_handlers'].append({'page': page.as_posix(), 'attribute': attr})
    for key in ('missing_references', 'external_assets', 'root_relative_references', 'live_site_links', 'missing_fragments'):
        result[key] = [json.loads(item) for item in sorted(set(json.dumps(x, sort_keys=True) for x in result[key]))]
    result['ok'] = not any(result[key] for key in ('missing_references', 'root_relative_references', 'external_assets', 'live_site_links', 'unsafe_scripts', 'event_handlers', 'form_count', 'missing_fragments'))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify_tree(args.directory)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: (len(value) if isinstance(value, list) else value) for key, value in report.items()}, indent=2))
    raise SystemExit(0 if report['ok'] else 1)
