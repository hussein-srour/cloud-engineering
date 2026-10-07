import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from PIL import Image

from app import create_app
from storage import Store, ValidationError, calculate


def quotation(**changes):
    value = {
        'client_name': 'Test Customer', 'client_address': 'Dar es Salaam',
        'issue_date': '2026-10-06', 'valid_until': '2026-10-20',
        'currency': 'TSH', 'price_level': 'installer', 'vat_mode': 'exclusive',
        'vat_rate': '18', 'discount': '0', 'status': 'Draft', 'theme': 'signature',
        'lines': [{'item_id': None, 'name': 'Solar panel', 'quantity': '2',
                   'unit_price': '100', 'taxable': True, 'unit': 'pcs', 'description': '550W'}],
    }
    value.update(changes)
    return value


class CalculationTests(unittest.TestCase):
    def test_exclusive_mixed_tax_and_discount(self):
        data = quotation(discount='10')
        data['lines'].append({'name': 'Exempt service', 'quantity': '1', 'unit_price': '50', 'taxable': False})
        value = calculate(data)
        self.assertEqual(value['totals'], {'subtotal': '250.00', 'discount_amount': '25.00',
                                          'taxable_base': '180.00', 'net': '225.00', 'vat': '32.40', 'total': '257.40'})

    def test_inclusive_extracts_vat_after_discount(self):
        data = quotation(vat_mode='inclusive', discount='10')
        data['lines'][0]['unit_price'] = '118'
        value = calculate(data)
        self.assertEqual(value['totals']['total'], '212.40')
        self.assertEqual(value['totals']['net'], '180.00')
        self.assertEqual(value['totals']['vat'], '32.40')

    def test_no_vat_and_fractional_quantity_rounding(self):
        data = quotation(vat_mode='none')
        data['lines'][0].update(quantity='0.125', unit_price='0.12')
        value = calculate(data)
        self.assertEqual(value['totals']['subtotal'], '0.02')
        self.assertEqual(value['totals']['vat'], '0.00')
        self.assertEqual(value['totals']['total'], '0.02')

    def test_full_discount_zero_total(self):
        value = calculate(quotation(discount='100', vat_mode='inclusive'))
        self.assertEqual(value['totals']['total'], '0.00')
        self.assertEqual(value['totals']['vat'], '0.00')

    def test_invalid_numbers_and_inputs_are_rejected(self):
        for value in ['NaN', 'Infinity', '-1', '1e100', True, '']:
            data = quotation(); data['lines'][0]['unit_price'] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                calculate(data)
        for changes in [{'currency':'EUR'}, {'vat_mode':'bogus'}, {'discount':'101'}, {'vat_rate':'-1'}]:
            with self.assertRaises(ValidationError): calculate(quotation(**changes))
        data = quotation(); data['lines'][0]['quantity'] = '0.0001'
        with self.assertRaises(ValidationError): calculate(data)
        data['lines'][0]['quantity'] = '1'; data['lines'][0]['taxable'] = 'false'
        with self.assertRaises(ValidationError): calculate(data)


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(self.temp.name)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.headers = {'X-AG-Token': self.app.config['AG_TOKEN']}

    def tearDown(self):
        self.temp.cleanup()

    def item(self):
        return {'name': 'Solar panel 550W', 'unit': 'pcs', 'taxable': True,
                'price_retail_tsh': '300000', 'price_retail_usd': '125',
                'price_installer_tsh': '260000', 'price_installer_usd': '110',
                'price_wholesale_tsh': '240000', 'price_wholesale_usd': None}

    def post(self, url, value):
        return self.client.post(url, json=value, headers=self.headers)

    def test_empty_start_company_and_local_lookup(self):
        bootstrap = self.client.get('/api/bootstrap').json
        self.assertEqual(bootstrap['items'], [])
        self.assertEqual(bootstrap['quotes'], [])
        self.assertEqual(bootstrap['company']['tin'], '130-471-412')
        saved = self.post('/api/items', self.item())
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json['price_installer_tsh'], '260000.00')
        self.assertIsNone(saved.json['price_wholesale_usd'])
        self.assertEqual(len(self.client.get('/api/items?q=SOLAR').json), 1)
        self.assertEqual(self.client.get('/api/items?q=not-found').json, [])
        self.assertEqual(self.post('/api/items', self.item()).status_code, 400)

    def test_quote_pdf_persistence_snapshot_and_update(self):
        item = self.post('/api/items', self.item()).json
        data = quotation(currency='USD')
        data['lines'][0].update(item_id=item['id'], unit_price='110', name=item['name'])
        result = self.post('/api/quotes', data)
        self.assertEqual(result.status_code, 201, result.json)
        q = result.json
        self.assertEqual(q['totals']['total'], '259.60')
        self.assertTrue((Path(self.temp.name) / 'Quotations' / (q['number']+'.pdf')).exists())
        pdf = self.client.get(f'/api/quotes/{q["id"]}/pdf?download=1')
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertIn('attachment', pdf.headers['Content-Disposition'])
        pdf.close()
        self.client.delete(f'/api/items/{item["id"]}', headers=self.headers)
        reloaded = Store(self.temp.name).quote(q['id'])
        self.assertEqual(reloaded['lines'][0]['unit_price'], '110.00')
        self.assertEqual(reloaded['company_snapshot']['name'], 'AG Energies Company Limited')
        data.update(status='Accepted', theme='minimal', discount='5')
        edited = self.client.put(f'/api/quotes/{q["id"]}', json=data, headers=self.headers)
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json['number'], q['number'])
        self.assertEqual(edited.json['totals']['total'], '246.62')
        self.assertEqual(self.client.get('/api/quotes').json[0]['status'], 'Accepted')

    def test_server_recalculates_and_invalid_dates(self):
        data = quotation(); data['totals'] = {'total': '0'}
        saved = self.post('/api/quotes', data)
        self.assertEqual(saved.json['totals']['total'], '236.00')
        for changes in [{'client_name':''}, {'valid_until':'2026-01-01'}, {'issue_date':'invalid'}, {'price_level':'invalid'}, {'lines':[]}]:
            result = self.post('/api/quotes', quotation(**changes))
            self.assertEqual(result.status_code, 400, result.json)

    def test_backup_and_delete_recovery(self):
        q = self.post('/api/quotes', quotation()).json
        backup = self.client.get('/api/backup')
        self.assertEqual(backup.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(backup.data))
        backup.close()
        self.assertIn('ag_energies.sqlite3', archive.namelist())
        self.assertIn('Quotations/'+q['number']+'.pdf', archive.namelist())
        restore = Path(self.temp.name) / 'restore.sqlite3'
        restore.write_bytes(archive.read('ag_energies.sqlite3'))
        with sqlite3.connect(restore) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM quotes').fetchone()[0], 1)
        result = self.client.delete(f'/api/quotes/{q["id"]}', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/quotes').json, [])
        self.assertEqual(self.client.get(f'/api/quotes/{q["id"]}').status_code, 404)

    def test_security_token_host_and_origin(self):
        self.assertEqual(self.client.post('/api/items', json=self.item()).status_code, 403)
        self.assertEqual(self.client.post('/api/items', json=self.item(), headers={**self.headers,'Origin':'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/bootstrap', headers={'Host':'evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/items', json=self.item(), headers={**self.headers,'Origin':'http://localhost'}).status_code, 201)

    def test_logo_upload_and_invalid_image(self):
        image = Image.new('RGBA', (20,20), (0,0,255,255)); buffer = io.BytesIO(); image.save(buffer, format='PNG'); buffer.seek(0)
        response = self.client.post('/api/logo', data={'logo':(buffer,'logo.png')}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        with self.client.get('/api/logo') as logo:
            self.assertEqual(logo.status_code, 200)
        invalid = self.client.post('/api/logo', data={'logo':(io.BytesIO(b'invalid'), 'fake.png')}, headers=self.headers)
        self.assertEqual(invalid.status_code, 400)

    def test_long_multipage_pdf_both_themes(self):
        data = quotation()
        data['notes'] = '<script>invalid()</script> & customer notes\n' + 'Long notes. ' * 100
        data['lines'] = [{**data['lines'][0], 'name': f'Panel {index}', 'description': ('Detailed specifications & features. ' * 6)} for index in range(45)]
        for theme in ['signature','minimal']:
            result = self.post('/api/quotes', {**data, 'theme':theme})
            self.assertEqual(result.status_code, 201, result.json)
            pdf = self.client.get(f'/api/quotes/{result.json["id"]}/pdf')
            self.assertGreater(len(pdf.data), 20000)
            pdf.close()


if __name__ == '__main__':
    unittest.main()
