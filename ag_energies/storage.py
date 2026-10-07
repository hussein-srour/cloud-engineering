"""Local SQLite storage and exact, server-side quotation calculations."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal('0.01')
COMPANY = {
    'name': 'AG Energies Company Limited',
    'address': 'APT 002, BLK 201, Nkurumah Street, Ilala District',
    'location': 'Dar es Salaam 8812, Tanzania',
    'tin': '130-471-412', 'vrn': '40-032998-G',
    'email': '', 'phone': '', 'website': '',
}
DEFAULT_TERMS = 'Prices are valid until the date shown above. Delivery and payment terms are subject to agreement.'
PRICE_LEVELS = ('retail', 'installer', 'wholesale')


class ValidationError(ValueError):
    pass


def text(value, label, required=False, maximum=2000):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValidationError(f'{label} must be text.')
    value = value.strip()
    if required and not value:
        raise ValidationError(f'{label} is required.')
    if len(value) > maximum:
        raise ValidationError(f'{label} is too long (maximum {maximum} characters).')
    return value


def number(value, label, minimum=Decimal('0'), maximum=Decimal('1000000000000')):
    try:
        if isinstance(value, bool) or len(str(value)) > 40:
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < minimum or result > maximum:
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f'{label} must be a number between {minimum} and {maximum}.') from None
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def amount(value):
    return format(money(value), '.2f')


def boolean(value, label):
    if not isinstance(value, bool):
        raise ValidationError(f'{label} must be yes or no.')
    return value


def desktop_folder():
    """Find the real Desktop, including Windows OneDrive redirects."""
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        # CSIDL_DESKTOPDIRECTORY; SHGetFolderPath honours redirected desktops.
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
        if result == 0 and buffer.value:
            return Path(buffer.value)
    if os.name != 'nt':
        config = Path.home() / '.config/user-dirs.dirs'
        if config.is_file():
            for line in config.read_text().splitlines():
                if line.startswith('XDG_DESKTOP_DIR='):
                    value = line.split('=', 1)[1].strip().strip('"').replace('$HOME', str(Path.home()))
                    path = Path(value)
                    if path.is_absolute():
                        return path
    return Path.home() / 'Desktop'


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValidationError('A quotation object is required.')
    currency = payload.get('currency', 'TSH')
    mode = payload.get('vat_mode', 'exclusive')
    if currency not in ('TSH', 'USD'):
        raise ValidationError('Choose TSh or USD.')
    if mode not in ('exclusive', 'inclusive', 'none'):
        raise ValidationError('Choose a valid VAT treatment.')
    rate = number(payload.get('vat_rate', '18'), 'VAT rate', maximum=Decimal('100'))
    discount = number(payload.get('discount', '0'), 'Discount', maximum=Decimal('100'))
    rows = payload.get('lines', [])
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValidationError('A quotation supports up to 200 items.')
    lines = []
    subtotal = Decimal('0')
    discount_amount = Decimal('0')
    tax_total = Decimal('0')
    taxable_base = Decimal('0')
    net_total = Decimal('0')
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError('Invalid quotation item.')
        name = text(row.get('name'), 'Item name', required=True, maximum=180)
        quantity = number(row.get('quantity', '1'), 'Quantity', minimum=Decimal('0.001'), maximum=Decimal('1000000'))
        if quantity != quantity.quantize(Decimal('0.001')):
            raise ValidationError('Quantity supports up to three decimal places.')
        unit_price = money(number(row.get('unit_price', '0'), 'Unit price'))
        taxable = boolean(row.get('taxable', True), 'VAT eligibility')
        listed = money(quantity * unit_price)
        reduction = money(listed * discount / 100)
        discounted = listed - reduction
        tax = Decimal('0')
        net = discounted
        if taxable and mode != 'none':
            if mode == 'inclusive':
                tax = money(discounted * rate / (100 + rate))
                net = discounted - tax
            else:
                tax = money(discounted * rate / 100)
            taxable_base += net
        subtotal += listed
        discount_amount += reduction
        net_total += net
        tax_total += tax
        item_id = row.get('item_id')
        if item_id is not None and (not isinstance(item_id, int) or isinstance(item_id, bool) or item_id < 1):
            raise ValidationError('Invalid catalogue item ID.')
        lines.append({
            'item_id': item_id, 'name': name,
            'description': text(row.get('description'), 'Item description', maximum=1000),
            'unit': text(row.get('unit', 'pcs'), 'Unit', maximum=30),
            'quantity': str(quantity), 'unit_price': amount(unit_price),
            'taxable': taxable, 'listed_amount': amount(listed), 'discount_amount': amount(reduction),
            'net': amount(net), 'vat': amount(tax), 'total': amount(net + tax),
        })
    return {'lines': lines, 'totals': {
        'subtotal': amount(subtotal), 'discount_amount': amount(discount_amount),
        'taxable_base': amount(taxable_base), 'net': amount(net_total),
        'vat': amount(tax_total), 'total': amount(net_total + tax_total),
    }}


class Store:
    def __init__(self, folder):
        self.folder = Path(folder).expanduser().resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / 'Quotations').mkdir(exist_ok=True)
        (self.folder / 'Backups').mkdir(exist_ok=True)
        self.path = self.folder / 'ag_energies.sqlite3'
        existed = self.path.exists()
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    sku TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL,
                    price_retail_tsh TEXT, price_retail_usd TEXT,
                    price_installer_tsh TEXT, price_installer_usd TEXT,
                    price_wholesale_tsh TEXT, price_wholesale_usd TEXT,
                    taxable INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
            ''')
            conn.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('company', json.dumps(COMPANY)))
        if existed:
            target = self.folder / 'Backups' / f'ag_energies-{date.today().isoformat()}.sqlite3'
            if not target.exists():
                self.backup(target)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def company(self):
        with self.connect() as conn:
            row = conn.execute('SELECT value FROM settings WHERE key=?', ('company',)).fetchone()
        return json.loads(row[0])

    def save_company(self, payload):
        if not isinstance(payload, dict):
            raise ValidationError('Company details are required.')
        company = {key: text(payload.get(key, ''), key.title(), required=key == 'name', maximum=500)
                   for key in COMPANY}
        with self.connect() as conn:
            conn.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(company), 'company'))
        return company

    @staticmethod
    def item(row):
        result = dict(row)
        result['taxable'] = bool(result['taxable'])
        return result

    def items(self, query=''):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM items ORDER BY name COLLATE NOCASE').fetchall()
        query = query.strip().casefold()
        return [self.item(row) for row in rows if not query or query in
                (' '.join([row['name'], row['sku'], row['category']])).casefold()]

    def save_item(self, payload, item_id=None):
        if not isinstance(payload, dict):
            raise ValidationError('Item details are required.')
        item = {
            'name': text(payload.get('name'), 'Item name', required=True, maximum=180),
            'sku': text(payload.get('sku'), 'SKU', maximum=80),
            'category': text(payload.get('category'), 'Category', maximum=80),
            'description': text(payload.get('description'), 'Description', maximum=1000),
            'unit': text(payload.get('unit', 'pcs'), 'Unit', required=True, maximum=30),
            'taxable': boolean(payload.get('taxable', True), 'VAT eligibility'),
        }
        for level in PRICE_LEVELS:
            for currency in ('tsh', 'usd'):
                key = f'price_{level}_{currency}'
                value = payload.get(key)
                item[key] = None if value in ('', None) else amount(number(value, f'{level.title()} {currency.upper()} price'))
        if all(item[f'price_{level}_{currency}'] is None for level in PRICE_LEVELS for currency in ('tsh', 'usd')):
            raise ValidationError('Enter at least one price for a price level and currency.')
        now = datetime.now().isoformat(timespec='seconds')
        try:
            with self.connect() as conn:
                if item_id is None:
                    cols = list(item) + ['created_at', 'updated_at']
                    cursor = conn.execute(f'INSERT INTO items ({",".join(cols)}) VALUES ({",".join("?" for _ in cols)})',
                                          list(item.values()) + [now, now])
                    item_id = cursor.lastrowid
                else:
                    cursor = conn.execute(f'UPDATE items SET {",".join(k+"=?" for k in item)},updated_at=? WHERE id=?',
                                          list(item.values()) + [now, item_id])
                    if cursor.rowcount == 0:
                        raise KeyError('Item not found.')
                return self.item(conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone())
        except sqlite3.IntegrityError:
            raise ValidationError('An item with this name already exists. Edit it instead.') from None

    def delete_item(self, item_id):
        with self.connect() as conn:
            if conn.execute('DELETE FROM items WHERE id=?', (item_id,)).rowcount == 0:
                raise KeyError('Item not found.')

    def quotes(self):
        with self.connect() as conn:
            rows = conn.execute('SELECT * FROM quotes ORDER BY id DESC').fetchall()
        results = []
        for row in rows:
            q = json.loads(row['payload'])
            results.append({k: q.get(k) for k in ('id', 'number', 'title', 'client_name', 'currency', 'status', 'issue_date', 'valid_until')} |
                           {'document_type': q.get('document_type', 'quotation')} |
                           {'total': q['totals']['total'], 'updated_at': row['updated_at']})
        return results

    def quote(self, quote_id):
        with self.connect() as conn:
            row = conn.execute('SELECT payload FROM quotes WHERE id=?', (quote_id,)).fetchone()
        if row is None:
            raise KeyError('Quotation not found.')
        return json.loads(row[0])

    def save_quote(self, payload, quote_id=None):
        computed = calculate(payload)
        if not computed['lines']:
            raise ValidationError('Add at least one item before saving.')
        quote = {key: text(payload.get(key, ''), key.replace('_', ' ').title(),
                           required=key == 'client_name', maximum=4000 if key in ('terms', 'notes') else 500)
                 for key in ('title', 'client_name', 'client_address', 'client_email', 'client_phone', 'notes', 'terms')}
        for key in ('issue_date', 'valid_until'):
            try:
                raw = payload.get(key, '')
                if not isinstance(raw, str) or date.fromisoformat(raw).isoformat() != raw:
                    raise ValueError
                quote[key] = raw
            except (ValueError, TypeError):
                raise ValidationError(f'{key.replace("_", " ").title()} must be a valid date.') from None
        if quote['valid_until'] < quote['issue_date']:
            raise ValidationError('Valid until must be on or after the issue date.')
        quote.update({k: payload.get(k, default) for k, default in
                      [('currency', 'TSH'), ('price_level', 'retail'), ('vat_mode', 'exclusive'), ('status', 'Draft'), ('theme', 'signature'), ('document_type', 'quotation')]})
        if quote['document_type'] not in ('quotation', 'boq'):
            raise ValidationError('Choose Quotation or Bill of quantities.')
        if quote['price_level'] not in PRICE_LEVELS:
            raise ValidationError('Choose a valid price level.')
        if quote['status'] not in ('Draft', 'Sent', 'Accepted', 'Declined'):
            raise ValidationError('Choose a valid quotation status.')
        if quote['theme'] not in ('signature', 'minimal'):
            raise ValidationError('Choose a valid quotation design.')
        quote['vat_rate'] = str(number(payload.get('vat_rate', '18'), 'VAT rate', maximum=Decimal('100')))
        quote['discount'] = str(number(payload.get('discount', '0'), 'Discount', maximum=Decimal('100')))
        quote.update(computed)
        quote['company_snapshot'] = self.company()
        now = datetime.now().isoformat(timespec='seconds')
        with self.connect() as conn:
            if quote_id is None:
                cursor = conn.execute('INSERT INTO quotes (payload,created_at,updated_at) VALUES (?,?,?)', ('{}', now, now))
                quote_id = cursor.lastrowid
                quote['number'] = f'AG-{date.today().year}-{quote_id:04d}'
            else:
                row = conn.execute('SELECT number FROM quotes WHERE id=?', (quote_id,)).fetchone()
                if row is None:
                    raise KeyError('Quotation not found.')
                quote['number'] = row[0]
            quote['id'] = quote_id
            conn.execute('UPDATE quotes SET number=?,payload=?,updated_at=? WHERE id=?',
                         (quote['number'], json.dumps(quote, ensure_ascii=False), now, quote_id))
        return quote

    def delete_quote(self, quote_id):
        with self.connect() as conn:
            if conn.execute('DELETE FROM quotes WHERE id=?', (quote_id,)).rowcount == 0:
                raise KeyError('Quotation not found.')

    def backup(self, target=None):
        target = Path(target or self.folder / 'Backups' / f'ag_energies-{datetime.now():%Y%m%d-%H%M%S-%f}.sqlite3')
        with self.connect() as source:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        return target
