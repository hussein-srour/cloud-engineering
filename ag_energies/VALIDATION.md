# Validation

Validated in the supplied Linux cloud environment using Python 3.12, Python 3.14 and Chromium.

- **14 automated tests passed** on both Python versions, with no failed or skipped tests. Tests cover exact VAT and discount calculations, mixed taxable/exempt lines, fractional quantities, invalid inputs, three internal price categories, local item lookup, document create/edit/reload, PDF generation, saved item snapshots, backups and deletion recovery, local request controls, logo uploads, quotation/BOQ document types and legacy PDF refresh.
- Standard and Monochrome PDF designs generated successfully with 45-line, multipage documents and long descriptions/notes. Table headers repeat across pages. A seven-page document and twelve concurrent exports also passed.
- Text extracted from generated PDFs confirms internal Retail/Installer/Wholesale categories and Studio branding are absent. BOQ heading, currency, VAT, company details and totals were checked.
- The complete browser workflow passed: adding an item, typing to find it, keyboard selection, USD installer pricing, adjusting quantity, adding an exempt custom service, all VAT modes, percentage discount, saving/exporting PDFs, updating status/design, reloading persisted data, changing price levels and handling missing prices, and downloading a full backup ZIP. No JavaScript errors were observed.
- Layout was checked at desktop and mobile widths; no horizontal page overflow at 390px.
- The source install script was rerun successfully. A fresh server instance was started and returned the expected company details and empty local business database. Test/example data is not included in the application.
- Prebuilt dependency wheels for Windows x64 / Python 3.14 were downloaded successfully from PyPI. Windows and macOS launchers are included; actual Windows/macOS launch execution was not available in this Linux environment.

The sample PDF and screenshots supplied separately illustrate the app using demonstration customer/item details. The application starts with an empty item library and quotation list, and the provided AG Energies company information.
