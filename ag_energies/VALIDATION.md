# Validation

Validated in the supplied Linux cloud environment using Python 3.12 and Chromium.

- **12 automated tests passed**, with no failed or skipped tests. Tests cover exact VAT and discount calculations, mixed taxable/exempt lines, fractional quantities, invalid inputs, three item price levels, local item lookup, quote create/edit/reload, PDF generation, snapshots after item deletion, backups and deletion recovery, local request controls, and logo uploads.
- Both Signature and Minimal PDF designs generated successfully with 45-line, multipage quotations and long descriptions/notes. Table headers repeat across pages.
- The complete browser workflow passed: adding an item, typing to find it, keyboard selection, USD installer pricing, adjusting quantity, adding an exempt custom service, all VAT modes, percentage discount, saving/exporting PDFs, updating status/design, reloading persisted data, changing price levels and handling missing prices, and downloading a full backup ZIP. No JavaScript errors were observed.
- Layout was checked at desktop and mobile widths; no horizontal page overflow at 390px.
- The source install script was rerun successfully. A fresh server instance was started and returned the expected company details and empty local business database. Test/example data is not included in the application.
- Windows and macOS launchers are included; actual Windows/macOS launch execution was not available in this environment. Their operation requires a local Python 3.10+ installation.

The sample PDF and screenshots supplied separately illustrate the app using demonstration customer/item details. The application starts with an empty item library and quotation list, and the provided AG Energies company information.
