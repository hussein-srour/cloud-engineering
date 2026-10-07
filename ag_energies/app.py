"""AG Energies quotations and bills of quantities. Run the included launcher."""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template, request, send_file
    from PIL import Image, UnidentifiedImageError
    from waitress import serve
except ModuleNotFoundError as error:
    print(f'Missing application dependency: {error.name}.\n'
          'On Windows, double-click Start Windows.bat to install and start the app.\n'
          'In VS Code, select .venv\\Scripts\\python.exe as the Python interpreter.\n'
          'For manual setup: python -m pip install -r requirements.txt', file=sys.stderr)
    raise SystemExit(2) from None

from documents import build_pdf
from storage import DEFAULT_TERMS, PRICE_LEVELS, Store, ValidationError, calculate, desktop_folder
PDF_LAYOUT_VERSION = '2026-10-refined-v1'


def create_app(data_dir=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=5 * 1024 * 1024)
    store = Store(data_dir or os.environ.get('AG_ENERGIES_DATA_DIR') or desktop_folder() / 'AG Energies')
    token = secrets.token_urlsafe(32)
    app.extensions['store'] = store
    app.config['AG_TOKEN'] = token

    @app.before_request
    def local_only():
        if request.host.split(':')[0] not in ('localhost', '127.0.0.1'):
            return jsonify(error='This application accepts local requests only.'), 403
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            if not secrets.compare_digest(request.headers.get('X-AG-Token', ''), token):
                return jsonify(error='Please refresh the app before saving.'), 403
            if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
                return jsonify(error='This request must come from the local app.'), 403

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ValidationError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error=str(error.args[0])), 404

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error='The upload is too large. Choose an image smaller than 5 MB.'), 413

    @app.errorhandler(500)
    def unexpected(error):
        return jsonify(error='The operation could not be completed. Your saved data is still in the Desktop folder. Check the terminal for details.'), 500

    def payload():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValidationError('Please provide valid form data.')
        return value

    def current_logo():
        custom = store.folder / 'logo.png'
        bundled = Path(app.static_folder) / 'logo.png'
        return custom if custom.exists() else bundled if bundled.exists() else None

    def pdf(quote):
        target = store.folder / 'Quotations' / (quote['number'] + '.pdf')
        build_pdf(quote, quote['company_snapshot'], current_logo(), target)
        target.with_suffix('.layout').write_text(PDF_LAYOUT_VERSION, encoding='utf-8')
        return target

    @app.get('/')
    def index():
        return render_template('index.html', csrf_token=token)

    @app.get('/api/bootstrap')
    def bootstrap():
        return jsonify(company=store.company(), items=store.items(), quotes=store.quotes(), data_dir=str(store.folder),
                       defaults={'vat_rate': '18', 'terms': DEFAULT_TERMS}, price_levels=list(PRICE_LEVELS),
                       currency_labels={'TSH': 'TSh', 'USD': 'USD'}, logo_exists=current_logo() is not None)

    @app.get('/api/logo')
    def logo():
        path = current_logo()
        if path is None:
            raise KeyError('Logo not found.')
        return send_file(path)

    @app.post('/api/logo')
    def upload_logo():
        upload = request.files.get('logo')
        if not upload:
            raise ValidationError('Choose a PNG or JPG logo.')
        try:
            with Image.open(upload.stream) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 16000000:
                    raise ValidationError('Choose a PNG, JPG or WebP image up to 16 megapixels.')
                source.load()
                image = source.convert('RGBA')
                image.thumbnail((1400, 1400))
                temporary = store.folder / 'logo-upload.tmp'
                image.save(temporary, format='PNG')
                temporary.replace(store.folder / 'logo.png')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValidationError('This image could not be read. Choose a different PNG or JPG.') from None
        return jsonify(ok=True)

    @app.get('/api/items')
    def items():
        return jsonify(store.items(request.args.get('q', '')))

    @app.post('/api/items')
    def add_item():
        return jsonify(store.save_item(payload())), 201

    @app.put('/api/items/<int:item_id>')
    def edit_item(item_id):
        return jsonify(store.save_item(payload(), item_id))

    @app.delete('/api/items/<int:item_id>')
    def delete_item(item_id):
        store.delete_item(item_id)
        return jsonify(ok=True)

    @app.get('/api/quotes')
    def quotes():
        return jsonify(store.quotes())

    @app.get('/api/quotes/<int:quote_id>')
    def get_quote(quote_id):
        return jsonify(store.quote(quote_id))

    @app.post('/api/calculate')
    def totals():
        return jsonify(calculate(payload()))

    @app.post('/api/quotes')
    def add_quote():
        quote = store.save_quote(payload())
        pdf(quote)
        return jsonify(quote), 201

    @app.put('/api/quotes/<int:quote_id>')
    def edit_quote(quote_id):
        quote = store.save_quote(payload(), quote_id)
        pdf(quote)
        return jsonify(quote)

    @app.delete('/api/quotes/<int:quote_id>')
    def delete_quote(quote_id):
        quote = store.quote(quote_id)
        store.backup()
        store.delete_quote(quote_id)
        (store.folder / 'Quotations' / (quote['number'] + '.pdf')).unlink(missing_ok=True)
        (store.folder / 'Quotations' / (quote['number'] + '.layout')).unlink(missing_ok=True)
        return jsonify(ok=True)

    @app.get('/api/quotes/<int:quote_id>/pdf')
    def get_pdf(quote_id):
        quote = store.quote(quote_id)
        target = store.folder / 'Quotations' / (quote['number'] + '.pdf')
        version_file = target.with_suffix('.layout')
        if not target.exists() or not version_file.exists() or version_file.read_text(encoding='utf-8') != PDF_LAYOUT_VERSION:
            pdf(quote)
        return send_file(target, mimetype='application/pdf', as_attachment=request.args.get('download') == '1', download_name=target.name)

    @app.put('/api/company')
    def company():
        return jsonify(store.save_company(payload()))

    @app.get('/api/backup')
    def backup():
        import zipfile
        database = store.backup()
        target = store.folder / 'Backups' / database.with_suffix('.zip').name
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(database, 'ag_energies.sqlite3')
            custom_logo = store.folder / 'logo.png'
            if custom_logo.exists():
                archive.write(custom_logo, 'logo.png')
            for path in (store.folder / 'Quotations').glob('*.pdf'):
                archive.write(path, 'Quotations/' + path.name)
        return send_file(target, as_attachment=True, download_name=target.name)

    return app


def main():
    parser = argparse.ArgumentParser(description='AG Energies Quotations')
    parser.add_argument('--data-dir', help='Override the Desktop/AG Energies storage folder')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    app = create_app(args.data_dir)
    address = f'http://127.0.0.1:{args.port}'
    print(f'\nAG Energies Quotations\nData folder: {app.extensions["store"].folder}\nOpen: {address}\nKeep this window open. Press Ctrl+C to stop.\n', flush=True)
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(address)).start()
    serve(app, host='127.0.0.1', port=args.port, threads=4)


if __name__ == '__main__':
    main()
