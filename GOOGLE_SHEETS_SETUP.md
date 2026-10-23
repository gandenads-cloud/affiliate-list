# Google Sheets Integration for Order Parser

## 1) Buat Apps Script
1. Buka: https://script.google.com/
2. Buat project baru.
3. Salin semua isi file `google-apps-script.js` ke Apps Script editor.
4. Simpan dengan nama seperti `Order Parser to Sheet`.

## 2) Deploy sebagai Web App
1. Klik `Deploy` > `New deployment`.
2. Type: `Web app`.
3. Atur:
   - Execute as: `Me`
   - Who has access: `Anyone`
4. Klik `Deploy`.
5. Salin URL web app yang muncul.

## 3) Pakai di halaman parser
1. Buka halaman parser di `apps/order-parser.html`.
2. Masukkan URL web app di field `URL Apps Script`.
3. Klik `Kirim ke spreadsheet`.

## 4) Target sheet
Spreadsheet target sudah ditentukan di script:
- Spreadsheet ID: `1LH8vtd84Ahpsu2uErW-RVW1XOxMp5lMLRGmoJtGC-9Y`
- Sheet: `Sheet1`

Data akan ditambahkan ke baris baru dengan kolom:
- username
- id_pesanan
- nomor_resi
- tanggal_kirim
- status_pengiriman

## Catatan
- Pengiriman dari browser ke Apps Script memerlukan URL web app yang sudah di-deploy dengan akses `Anyone`.
- Jika ingin nama sheet lain, ubah nilai `SHEET_NAME` di `google-apps-script.js`.
