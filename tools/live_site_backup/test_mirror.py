"""Regression fixtures are synthetic; captured website content is not fabricated."""
from pathlib import Path
import unittest
from bs4 import BeautifulSoup


class StaticMirrorTests(unittest.TestCase):
    def test_form_is_replaced_without_loading_original_scripts(self):
        self.assertTrue(Path(__file__).with_name('mirror.py').exists(), 'Static-page sanitizer is not implemented')
        import mirror
        self.assertTrue(hasattr(mirror, 'rewrite_html'), 'Static-page sanitizer is not implemented')
        source = '''<html><head><title>Contact</title><script src="https://stats.wp.com/x.js"></script></head>
        <body><h1>Contact us</h1><form action="/submit" method="POST"><input name="email"><button>Send</button></form>
        <script>fetch('/wp-json/');</script><img src="https://stats.wp.com/pixel.gif" onload="track()"></body></html>'''
        html, events = mirror.rewrite_html(source, Path('contact/index.html'), {}, 'https://sbi2.org/contact/')
        result = BeautifulSoup(html, 'html.parser')
        self.assertEqual(len(result.select('form,input,textarea,select')), 0)
        self.assertIn('form', [event['kind'] for event in events])
        self.assertIn('Interactive form unavailable', result.get_text())
        self.assertIn('Contact us', result.get_text())
        self.assertNotIn('stats.wp.com', html)
        self.assertNotIn('onload=', html)
        self.assertEqual([x.get('src') for x in result.find_all('script')], ['../_archive/runtime.js'])


    def test_original_site_references_work_from_any_hosting_prefix(self):
        import mirror
        urls = {
            'https://sbi2.org/about-us/': Path('about-us/index.html'),
            'https://sbi2.org/wp-content/photo.jpg': Path('wp-content/photo.jpg'),
            'https://sbi2.org/style.css?ver=1': Path('style.css@ver=1.css'),
        }
        source = '''<html><head><link rel="stylesheet" href="https://sbi2.org/style.css?ver=1">
        <style>.hero { background:url('/wp-content/photo.jpg') }</style></head><body>
        <a href="/about-us/#team">About us</a><a href="https://example.org/">External</a>
        <img src="/wp-content/photo.jpg" srcset="https://sbi2.org/wp-content/photo.jpg 800w">
        </body></html>'''
        html, _ = mirror.rewrite_html(source, Path('contact/index.html'), urls, 'https://sbi2.org/contact/')
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(soup.find('a')['href'], '../about-us/index.html#team')
        self.assertEqual(soup.find('img')['src'], '../wp-content/photo.jpg')
        self.assertEqual(soup.find('img')['srcset'], '../wp-content/photo.jpg 800w')
        self.assertIn('../wp-content/photo.jpg', soup.find('style').get_text())
        self.assertEqual(soup.find('link')['href'], '../style.css@ver=1.css')
        self.assertIn('https://example.org/', html)


    def test_external_forms_and_embeds_become_placeholders_but_pdfs_remain(self):
        import mirror
        source = '''<html><head><link rel="alternate" href="/wp-json/"><link rel="preconnect" href="https://stats.wp.com"></head><body>
        <a href="https://www.jotform.com/form/123">Vendor registration</a>
        <iframe src="https://airtable.com/embed/public-directory"></iframe>
        <object type="application/pdf" data="../program.pdf"><a href="../program.pdf">Program</a></object>
        </body></html>'''
        html, events = mirror.rewrite_html(source, Path('conference/index.html'), {}, 'https://sbi2.org/conference/')
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(soup.find('a')['href'], '../_archive/forms/index.html')
        self.assertEqual(len(soup.find_all('iframe')), 0)
        self.assertEqual(soup.find('object')['data'], '../program.pdf')
        self.assertIn('embed', [e['kind'] for e in events])
        self.assertIn('external-form-link', [e['kind'] for e in events])
        self.assertNotIn('/wp-json/', html)
        self.assertNotIn('stats.wp.com', html)


    def test_builds_a_capture_with_provenance_and_no_original_script_files(self):
        import json
        import tempfile
        import mirror
        self.assertTrue(hasattr(mirror, 'build_capture'), 'Capture builder is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / 'capture'
            raw = capture / 'live'
            raw.mkdir(parents=True)
            (raw / 'about').mkdir()
            (raw / 'index.html').write_text('<html><head><title>Home</title><link rel="stylesheet" href="/style.css"></head><body><a href="/about/">About</a><script src="track.js"></script></body></html>')
            (raw / 'about/index.html').write_text('<html><head><title>About</title></head><body><h1>About our society</h1><form><input></form></body></html>')
            (raw / 'style.css').write_text('body { color: black; }')
            (raw / 'track.js').write_text('throw new Error("Do not copy");')
            sources = {'index.html': 'https://sbi2.org/', 'about/index.html': 'https://sbi2.org/about/', 'style.css': 'https://sbi2.org/style.css', 'track.js': 'https://sbi2.org/track.js'}
            log = '\n'.join(f'--2026-11-05 00:00:00--  {url}\nSaving to: ‘{raw / name}’' for name, url in sources.items())
            (capture / 'live-crawl.log').write_text(log)
            (capture / 'discovery.json').write_text(json.dumps({'origin': 'https://sbi2.org', 'captured_utc': '2026-11-05T00:00:00Z', 'seed_urls': ['https://sbi2.org/', 'https://sbi2.org/about/']}))
            output = root / 'backup'
            result = mirror.build_capture(capture, output)
            self.assertTrue((output / 'index.html').exists())
            self.assertTrue((output / '_archive/runtime.js').exists())
            self.assertFalse((output / 'track.js').exists())
            self.assertEqual(result['source_kind'], 'live-http-crawl')
            self.assertEqual(len(result['pages']), 2)
            self.assertEqual(result['missing_seed_urls'], [])
            self.assertIn('about/index.html', (output / 'index.html').read_text())
            self.assertEqual(len(BeautifulSoup((output / 'about/index.html').read_text(), 'html.parser').find_all('form')), 0)


    def test_mislabeled_binary_responses_keep_their_real_file_type(self):
        import json
        import tempfile
        import mirror
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'capture'
            raw = capture / 'live'
            (raw / 'program').mkdir(parents=True)
            pdf = b'%PDF-1.4\n%\xf6\xe4\xfc\xdf\nTest fixture only'
            font = b'wOF2\x00\x01\xff\xfeTest fixture only'
            (raw / 'program/index.html').write_bytes(pdf)
            (raw / 'Inter.woff2.html').write_bytes(font)
            (capture / 'discovery.json').write_text(json.dumps({'origin': 'https://sbi2.org', 'captured_utc': '2026-11-05T00:00:00Z', 'seed_urls': ['https://sbi2.org/program/']}))
            (capture / 'live-crawl.log').write_text(f'--2026-11-05 00:00:00--  https://sbi2.org/program/\nSaving to: ‘{raw / "program/index.html"}’\n--2026-11-05 00:00:01--  https://sbi2.org/Inter.woff2\nSaving to: ‘{raw / "Inter.woff2.html"}’')
            output = Path(directory) / 'backup'
            mirror.build_capture(capture, output)
            self.assertEqual((output / 'program/index.pdf').read_bytes(), pdf)
            self.assertEqual((output / 'Inter.woff2').read_bytes(), font)
            self.assertTrue((output / 'program/index.html').is_file(), 'Original directory route needs a local PDF wrapper')
            self.assertIn('index.pdf', (output / 'program/index.html').read_text())


    def test_verifier_catches_missing_assets_prefix_escapes_and_forms(self):
        import tempfile
        self.assertTrue(Path(__file__).with_name('verify.py').exists(), 'Static verification is not implemented')
        from verify import verify_tree
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<html><body><a href="missing/index.html">Missing</a><img src="/root.png"><form></form><script>unsafe()</script></body></html>')
            (root / 'root.png').write_bytes(b'test fixture only')
            report = verify_tree(root)
            self.assertEqual(len(report['missing_references']), 1)
            self.assertEqual(len(report['root_relative_references']), 1)
            self.assertEqual(report['form_count'], 1)
            self.assertEqual(len(report['unsafe_scripts']), 1)


    def test_pdf_objects_are_local_and_malformed_original_schemes_are_disabled(self):
        import mirror
        original = 'mailton:info@sbi2.org'
        source = f'<html><body><object type="application/pdf" data="https://sbi2.org/program.pdf"></object><a href="{original}">Contact</a></body></html>'
        text, events = mirror.rewrite_html(source, Path('program/index.html'), {'https://sbi2.org/program.pdf': Path('program.pdf')}, 'https://sbi2.org/program/')
        soup = BeautifulSoup(text, 'html.parser')
        self.assertEqual(soup.find('object')['data'], '../program.pdf')
        self.assertEqual(soup.find('a')['href'], '#')
        self.assertIn(original, [event['source'] for event in events])


    def test_pdf_preview_does_not_depend_on_removed_wordpress_scripts(self):
        import mirror
        source = '<html><body><object type="application/pdf" data="program.pdf" hidden data-wp-bind--hidden="!state.hasPdfPreview"></object></body></html>'
        text, _ = mirror.rewrite_html(source, Path('index.html'), {}, 'https://sbi2.org/')
        pdf = BeautifulSoup(text, 'html.parser').find('object')
        self.assertNotIn('hidden', pdf.attrs)
        self.assertNotIn('data-wp-bind--hidden', pdf.attrs)


    def test_public_poster_csv_is_rendered_in_full_and_safely_escaped(self):
        import csv
        import tempfile
        import mirror
        self.assertTrue(hasattr(mirror, 'render_dataset'), 'Public poster rendering is not implemented')
        fields = ['Poster Number', 'Applicant Name', 'Abstract Title', 'Abstract', 'Category']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'posters.csv'
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(zip(fields, ['1', 'A scientist', 'Real title', '<script>Text, not code</script>\nSecond paragraph', 'Analysis'])))
            rendered = mirror.render_dataset(path, 1, fields)
            soup = BeautifulSoup(rendered, 'html.parser')
            self.assertEqual(len(soup.select('details.backup-poster')), 1)
            self.assertEqual(len(soup.find_all('script')), 0)
            self.assertIn('Second paragraph', soup.get_text())
            self.assertIn('Text, not code', soup.get_text())
            with self.assertRaises(ValueError):
                mirror.render_dataset(path, 2, fields)


if __name__ == '__main__':
    unittest.main()
