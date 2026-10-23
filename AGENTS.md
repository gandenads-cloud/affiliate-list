# AFS Parser Rule

## Rule utama
- Jangan mengubah logika parsing di `apps/order-parser.html` tanpa persetujuan eksplisit.
- Parser ini dipakai untuk data order berformat campuran dari marketplace.
- Prioritaskan kompatibilitas terhadap format lama dan format baru yang sudah terverifikasi.

## Format yang harus didukung
- Blok `Sampel gratis`
- Tanggal dengan pola seperti:
  - `10 mnt yang lalu`
  - `Kamis 13.52.15`
  - `16/10/2026 10:02:33`
- Username bisa muncul:
  - setelah kata `Sampel gratis` lalu diikuti `produk`
  - di baris terpisah sebelum `1 produk`
- Resi yang valid: `JY...`
- Status yang valid:
  - `Menunggu pengiriman`
  - `Menunggu pengambilan`
  - `Sedang transit`
  - `Terkirim`
  - `Belum Dibayar`
  - `Dibatalkan`

## Output wajib
Setiap data yang diparse harus menghasilkan kolom berikut:
- username
- id_pesanan
- nomor_resi
- tanggal_kirim
- status_pengiriman

## Behaviour yang disetujui
- Setelah parse, hasil harus langsung siap dipakai dalam format CSV.
- Setelah parse, hasil juga boleh otomatis disalin ke clipboard.
- Jangan mengubah struktur field atau logika pengambilan order ID yang sudah terbukti benar.

## Catatan penting
- Jika ada format data baru, perbaiki parsing dengan cara yang kompatibel, bukan mengganti logika lama.
- Jangan membuang data yang valid hanya karena pola baru muncul.
