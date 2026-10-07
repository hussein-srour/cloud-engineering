# AG Energies Quotation Studio

A professional Python quotation application for **AG Energies Company Limited**. Runs locally in your browser, with a Python backend and a SQLite database. No account or subscription is required. After the first dependency installation it works offline; there are no external fonts, scripts or web services.

## Start on your computer

1. Install **Python 3.10 or newer** from https://www.python.org/downloads/ (on Windows, tick **Add Python to PATH**).
2. Extract the downloaded ZIP to your Desktop. Keep all the application files together.
3. On Windows, double-click **Start Windows.bat**. On macOS, run **Start Mac.command**. The first start downloads dependencies; allow it to finish.
4. The app opens in your browser. Keep the terminal window open while using it. Press **Ctrl+C** in that window to stop.

On macOS, if the command file is not executable, open Terminal in this folder and run:

```sh
chmod +x "Start Mac.command"
./"Start Mac.command"
```

On Linux, run `bash start_linux.sh`. Install your distribution's `python3-venv` package if venv support is missing.

If the browser does not open, enter `http://127.0.0.1:8765` on your computer. This is a local application address. If the port is occupied, stop the other copy of the app, or start manually with `python app.py --port 8766` using the installed virtual environment's Python.

## Where your details are saved

The first launch creates **Desktop/AG Energies/** on the computer running the app. Windows redirected/OneDrive Desktop folders and Linux XDG desktop folders are supported.

```text
Desktop/AG Energies/
  ag_energies.sqlite3     Item library, quotations and company details
  Quotations/            Automatically created quotation PDFs
  Backups/               Daily database backups and full backup ZIPs
  logo.png               Your logo, if you upload a replacement
```

The database is the source of truth. Closing or restarting the app preserves your items and quotations. Use **Back up workspace** to download a ZIP containing the database, quotation PDFs and custom logo. Copy backups to another drive regularly. The app makes one database backup each day it starts with an existing database, and a backup before deleting a quotation. These are local files; it does not upload them.

To restore a full backup: stop the app, preserve the current **AG Energies** folder somewhere safe, then extract the backup into **Desktop/AG Energies/** so that `ag_energies.sqlite3` is directly inside that folder. Restart the app. Do not replace the live database while the app is running.

To choose a different location, use `python app.py --data-dir "path/to/folder"` or set `AG_ENERGIES_DATA_DIR`. Use a folder you can write to. Shared multi-user or network deployment is outside this app's scope.

## Your daily workflow

1. **Item library → Add item**: save a name, SKU, description, unit, category, VAT eligibility and prices. Each item has **Retail, Installer and Wholesale** price levels, each with separate **TSh and USD** fields. At least one price is required; leave unavailable prices blank.
2. **New quotation**: enter the customer and dates, then select a currency and price level. Type an item name or SKU in the search box to see local catalogue suggestions. Use the arrow keys and Enter, or click a suggestion.
3. Adjust quantities and prices, remove lines or add custom items. Changing currency or price level prompts before replacing catalogue prices. There is **no automatic exchange-rate conversion**. Missing prices must be filled in explicitly. Review custom-item prices when changing currency.
4. Choose **VAT on top**, **VAT included**, or **No VAT**. Each line has a VAT checkbox for mixed taxable and exempt items. The initial VAT rate is **18%**, and it can be changed for each quotation. Confirm the rate and tax treatment appropriate to the transaction.
5. Optional percentage discount, notes, payment/delivery terms, status and either **Signature** or **Minimal** PDF design.
6. Click **Save & preview PDF**. A sequential `AG-YYYY-0001` number is assigned, the quotation is saved in the database, and its branded A4 PDF is created in the Quotations folder. Download/share/print from the browser's PDF viewer. Save with Ctrl+S or Cmd+S in the editor. Changes are saved when you click Save; the editor warns before leaving unsaved work.
7. Reopen, copy, edit or delete saved quotations from the Quotations page. Statuses are labels you manage manually; choosing Sent does not send any email.

Item changes and deletions do not alter previously saved quotations. Saved quotation lines are snapshots. Company information is captured when a quotation is saved; existing PDFs retain it until that quotation is edited and saved again. The supplied logo has been cleaned onto a transparent background for use on white pages; replace it at **Company & settings → Choose logo** if you prefer the exact original image.

## Calculation rules

All authoritative amounts are calculated on the Python server with `Decimal`, rounded half-up to two decimal places, per line. Quantities allow three decimal places.

- Line listed amount = quantity × unit price, rounded to cents.
- Percentage discount is applied and rounded on each line before VAT.
- **VAT on top**: the discounted line amount is net. VAT is added only to taxable lines.
- **VAT included**: the discounted line amount is gross on taxable lines; VAT = gross × rate / (100 + rate), rounded. Net = gross − VAT. Exempt lines have no VAT.
- **No VAT**: net and total are the discounted amount; VAT is zero on every line.
- Quote totals sum the rounded line amounts. Both TSh and USD use two displayed decimal places. The PDF table shows listed amounts before discount; the summary shows discount, VAT and final total.

## Manual development setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
.venv/bin/python -m unittest discover -s tests -v
```

On Windows, use `.venv\Scripts\python.exe` instead. The application uses Flask, Waitress, ReportLab and Pillow. It binds only to `127.0.0.1`; state-changing requests require a per-session token. Don't change the bind address to expose it to the Internet.

The application and dependencies are installed in the extracted application folder. Your business data stays separately in the Desktop folder. Updating the application does not require overwriting that data folder. Python virtual environments are machine-specific; don't transfer a `.venv` folder from another computer.

The bundled DejaVu fonts are distributed under the license in `static/fonts/LICENSE.txt`. Generated branding follows the supplied AG Energies logo. Company address, TIN and VRN are prefilled exactly from the provided details; optional email, phone and website are left empty.
