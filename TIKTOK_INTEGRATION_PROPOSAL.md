# Proposal Integrasi TikTok API untuk Affiliate App

## 1. Ringkasan

Integrasi TikTok akan dibangun sebagai backend adapter yang aman dan idempotent untuk menyinkronkan profil kreator serta video yang memang diizinkan oleh API TikTok yang aktif di akun pemilik aplikasi.

Prinsip utama:
- Tidak mengasumsikan satu API key bisa membaca semua profil TikTok publik.
- Menggunakan akses yang benar-benar tersedia pada akun/app yang sudah disetujui.
- Memetakan data ke schema aplikasi yang sudah ada.
- Menjaga data CRM, kontak, dan shipment tetap aman dari overwrite.
- Menyimpan metrik hanya bila endpoint yang aktif mengembalikannya.

## 2. Status akses TikTok yang valid

### 2.1 TikTok for Developers API

Cocok untuk:
- profil/metadata akun yang telah mengotorisasi aplikasi,
- video milik pengguna yang sedang login/diotorisasi,
- metrik video yang dikembalikan oleh endpoint yang disetujui.

Prasyarat:
- OAuth user authorization
- scope yang sesuai, misalnya `video.list`
- token pengguna bukan token seller
- tidak otomatis mengakses semua username publik

### 2.2 TikTok Shop Affiliate Creator API

Cocok untuk:
- data creator affiliate TikTok Shop,
- data creator yang terkait dengan shop yang terhubung,
- data yang hanya tersedia setelah creator authorization dan seller/shop scope aktif.

Prasyarat:
- creator authorization aktif
- shop affiliate integration aktif
- token creator dan seller tidak boleh dipertukarkan

### 2.3 Kesimpulan implementasi

Implementasi harus dibangun sebagai adapter conditional:
- bila akses `tiktok_for_developers` aktif, gunakan endpoint video/user yang sesuai;
- bila akses `tiktok_shop_affiliate` aktif, gunakan endpoint creator affiliate yang sesuai;
- bila scope belum aktif, jalankan mode `not_available` dan catat keterbatasan dalam job summary.

## 3. Data awal yang tersedia di aplikasi

Berdasarkan proposal, struktur aplikasi saat ini sudah memiliki:
- `affiliators`
- `affiliator_handles`
- `vts`
- tabel pendukung seperti `agreements`, `activity_logs`, `creator_product_statuses`, dan lainnya.

Data yang tersedia pada file ekspor saat ini:
- `storage/app/exports/affiliators-all.csv` berisi 11.681 baris
- 2 creator sudah memiliki metrik video
- sebagian besar data tidak selalu memiliki platform ID atau metrik lengkap

Ini berarti sinkronisasi harus siap menangani data parsial dan tidak memaksa seluruh dataset harus terpenuhi di satu batch.

## 4. Model data target

### 4.1 Tabel `affiliators`

Schema utama tetap dipertahankan, dengan status CRM dan sample workflow tetap dipelihara.

Kolom inti:
- `id` PK
- `name`
- `brand`
- `primary_platform` default `tiktok_shop`
- `tier`
- `content_categories`
- `phone`, `email`
- `shipping_address`
- `recipient_name`
- `pic_user_id`
- `stage`, `stage_since`
- `followup_at`, `followup_note`
- `source` default `manual_outreach`
- `joined_at`
- `notes`
- `created_at`, `updated_at`
- `contact_list`, `manager`
- `contact_status` default `contacted`
- `fit_checked`, `invited`, `deal_confirmed`
- `sample_requested`, `sample_shipped`, `sample_received`
- `vt_posted`

### 4.2 Tabel `affiliator_handles`

Kolom utama:
- `id`
- `affiliator_id` FK
- `platform`
- `platform_id`
- `handle`
- `profile_url`
- `followers`
- `followers_checked_at`

Index unik yang sudah ada:
- (`platform`, `handle`)
- (`platform`, `platform_id`)

Aturan match kreator:
1. cocokkan berdasarkan `platform_id` jika tersedia;
2. fallback ke `handle` bila `platform_id` kosong atau belum ada;
3. tidak membuat duplikat kreator bila identitas cocok.

### 4.3 Tabel `vts`

Kolom utama:
- `id`
- `affiliator_id`
- `platform`
- `url` unique
- `title_or_caption`
- `live_at`
- `has_boost`
- `boost_code`
- `boost_checked_at`
- `views`
- `gmv`
- `commission`
- `metrics_updated_at`
- `counts_to_agreement`
- `data_source`
- `notes`
- `created_at`, `updated_at`
- `agreement_id`

Catatan penting:
- `gmv` dan `commission` hanya diisi bila API yang aktif memang mengembalikannya.
- bila endpoint tidak memberi metrik, nilai lama tetap dipertahankan dan tidak diubah menjadi `0` atau `null` secara paksa.
- struktur yang disarankan untuk masa depan:
  - `platform_video_id`
  - `likes`
  - `comments`
  - `shares`
  - unique composite index (`platform`, `platform_video_id`)
  - `url` tetap dipertahankan sebagai URL tampilan

## 5. Pemetaan data API ke schema aplikasi

| Data dari API | Kolom aplikasi |
|---|---|
| TikTok creator/user ID | `affiliator_handles.platform_id` |
| Username/handle | `affiliator_handles.handle` |
| URL profil | `affiliator_handles.profile_url` |
| Followers | `affiliator_handles.followers` |
| Waktu cek followers | `affiliator_handles.followers_checked_at` |
| Video ID | `vts.platform_video_id` (usulan migrasi) |
| URL video | `vts.url` |
| Caption/judul | `vts.title_or_caption` |
| Waktu terbit | `vts.live_at` |
| Views | `vts.views` |
| Likes | `vts.likes` (usulan migrasi) |
| Komentar | `vts.comments` (usulan migrasi) |
| Shares | `vts.shares` (usulan migrasi) |
| GMV | `vts.gmv` |
| Komisi | `vts.commission` |
| Waktu update metrik | `vts.metrics_updated_at` |
| Sumber data | `vts.data_source = tiktok_api` |

## 6. Payload contoh yang dipakai untuk fixture

Berikut payload dummy yang valid untuk testing logic adapter sebelum data nyata masuk:

```json
[
  {"affiliator_id":1001,"platform":"tiktok_shop","platform_id":"tt_demo_001","handle":"creator_demo_01","profile_url":"https://www.tiktok.com/@creator_demo_01","followers":12500,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000001","url":"https://www.tiktok.com/@creator_demo_01/video/7000000000000000001","title_or_caption":"Demo video 01","live_at":"2026-10-20","views":18400,"likes":920,"comments":42,"shares":71,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1002,"platform":"tiktok_shop","platform_id":"tt_demo_002","handle":"creator_demo_02","profile_url":"https://www.tiktok.com/@creator_demo_02","followers":28400,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000002","url":"https://www.tiktok.com/@creator_demo_02/video/7000000000000000002","title_or_caption":"Demo video 02","live_at":"2026-10-19","views":32600,"likes":1740,"comments":88,"shares":139,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1003,"platform":"tiktok_shop","platform_id":"tt_demo_003","handle":"creator_demo_03","profile_url":"https://www.tiktok.com/@creator_demo_03","followers":47300,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000003","url":"https://www.tiktok.com/@creator_demo_03/video/7000000000000000003","title_or_caption":"Demo video 03","live_at":"2026-10-18","views":51200,"likes":2880,"comments":126,"shares":205,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1004,"platform":"tiktok_shop","platform_id":"tt_demo_004","handle":"creator_demo_04","profile_url":"https://www.tiktok.com/@creator_demo_04","followers":68900,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000004","url":"https://www.tiktok.com/@creator_demo_04/video/7000000000000000004","title_or_caption":"Demo video 04","live_at":"2026-10-17","views":76400,"likes":4200,"comments":203,"shares":310,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1005,"platform":"tiktok_shop","platform_id":"tt_demo_005","handle":"creator_demo_05","profile_url":"https://www.tiktok.com/@creator_demo_05","followers":91200,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000005","url":"https://www.tiktok.com/@creator_demo_05/video/7000000000000000005","title_or_caption":"Demo video 05","live_at":"2026-10-16","views":105000,"likes":6310,"comments":274,"shares":482,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1006,"platform":"tiktok_shop","platform_id":"tt_demo_006","handle":"creator_demo_06","profile_url":"https://www.tiktok.com/@creator_demo_06","followers":118000,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000006","url":"https://www.tiktok.com/@creator_demo_06/video/7000000000000000006","title_or_caption":"Demo video 06","live_at":"2026-10-15","views":138000,"likes":8240,"comments":359,"shares":671,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1007,"platform":"tiktok_shop","platform_id":"tt_demo_007","handle":"creator_demo_07","profile_url":"https://www.tiktok.com/@creator_demo_07","followers":154000,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000007","url":"https://www.tiktok.com/@creator_demo_07/video/7000000000000000007","title_or_caption":"Demo video 07","live_at":"2026-10-14","views":176000,"likes":10900,"comments":486,"shares":903,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1008,"platform":"tiktok_shop","platform_id":"tt_demo_008","handle":"creator_demo_08","profile_url":"https://www.tiktok.com/@creator_demo_08","followers":207000,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000008","url":"https://www.tiktok.com/@creator_demo_08/video/7000000000000000008","title_or_caption":"Demo video 08","live_at":"2026-10-13","views":224000,"likes":13800,"comments":621,"shares":1140,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1009,"platform":"tiktok_shop","platform_id":"tt_demo_009","handle":"creator_demo_09","profile_url":"https://www.tiktok.com/@creator_demo_09","followers":263000,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000009","url":"https://www.tiktok.com/@creator_demo_09/video/7000000000000000009","title_or_caption":"Demo video 09","live_at":"2026-10-12","views":293000,"likes":17600,"comments":814,"shares":1490,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}},
  {"affiliator_id":1010,"platform":"tiktok_shop","platform_id":"tt_demo_010","handle":"creator_demo_10","profile_url":"https://www.tiktok.com/@creator_demo_10","followers":318000,"followers_checked_at":"2026-10-23","video":{"platform_video_id":"7000000000000000010","url":"https://www.tiktok.com/@creator_demo_10/video/7000000000000000010","title_or_caption":"Demo video 10","live_at":"2026-10-11","views":351000,"likes":21400,"comments":1020,"shares":1880,"gmv":null,"commission":null,"metrics_updated_at":"2026-10-23","data_source":"tiktok_api"}}
]
```

## 7. Rekomendasi migrasi database

### 7.1 Migration minimum yang disarankan

```sql
ALTER TABLE affiliator_handles
  ADD COLUMN IF NOT EXISTS platform_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS profile_url VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS followers INTEGER NULL,
  ADD COLUMN IF NOT EXISTS followers_checked_at DATE NULL;
```

Jika schema belum lengkap di project yang berjalan, pastikan kolom ini tersedia sebelum sync.

### 7.2 Migration yang direkomendasikan untuk data video yang lebih lengkap

```sql
ALTER TABLE vts
  ADD COLUMN IF NOT EXISTS platform_video_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS likes INTEGER NULL,
  ADD COLUMN IF NOT EXISTS comments INTEGER NULL,
  ADD COLUMN IF NOT EXISTS shares INTEGER NULL;
```

Index yang disarankan:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_vts_platform_video_id
  ON vts (platform, platform_video_id);
```

Catatan:
- `url` tetap dipertahankan sebagai fallback unique key saat `platform_video_id` belum tersedia.
- jangan mengubah field `gmv` dan `commission` menjadi `0` saat API tidak mengembalikan data.

## 8. Flow kerja sinkronisasi

### 8.1 Alur utama

1. Ambil daftar creator dari database yang sudah ada.
2. Cek status API dan scope aktif.
3. Validasi token dan refresh token.
4. Ambil user data / creator profile / video dari endpoint yang diizinkan.
5. Match creator berdasarkan `platform_id`, fallback `handle`.
6. Upsert ke `affiliator_handles`.
7. Upsert video ke `vts` berdasarkan `platform_video_id` bila tersedia; fallback ke `url`.
8. Simpan metrics hanya bila API memberikannya.
9. Catat hasil batch: sukses, skip, error, not_available.
10. Simpan log tanpa menulis token atau secret ke log.

### 8.2 Idempotency

- `upsert` berdasarkan primary key atau unique key.
- `platform + platform_id` untuk creator handle.
- `platform + platform_video_id` untuk video; fallback `url` jika kolom baru belum ada.
- update hanya field yang diizinkan, tanpa menimpa data CRM dan shipment.

### 8.3 Batch safety

- per creator tidak membatalkan batch seluruhnya,
- retry dengan backoff,
- pagination handling,
- rate limit handling,
- invalid/expired token ditangani terpisah.

## 9. Environment dan credential

Simpan di environment/config secret manager, bukan di source code atau CSV.

Contoh variabel:

```env
TIKTOK_APP_ID=...
TIKTOK_APP_SECRET=...
TIKTOK_REDIRECT_URI=https://app.example.com/tiktok/callback
TIKTOK_ACCESS_TOKEN=...
TIKTOK_REFRESH_TOKEN=...
TIKTOK_TOKEN_EXPIRES_AT=...
TIKTOK_API_MODE=tiktok_shop_affiliate
TIKTOK_SCOPE=video.list,affiliate.read
```

Prinsip keamanan:
- tidak menaruh secret di log, export CSV, atau tabel profil kreator,
- gunakan secret store / environment manager,
- masukkan payload token hanya pada secure backend service.

## 10. OAuth / callback / authorization

1. Generate auth URL sesuai API TikTok yang aktif.
2. Simpan state nonce untuk CSRF validation.
3. Callback harus verifikasi `state` dan `code`.
4. Simpan token refresh dengan expiry.
5. Revoke/rotate token bila perlu sesuai policy API.
6. Catat last_sync_at dan source endpoint.

## 11. Kebutuhan operasional

### 11.1 Ringkasan batch

Setiap batch harus menghasilkan ringkasan seperti:
- total_creators
- updated_creators
- skipped_creators
- failed_creators
- total_videos
- updated_videos
- failed_videos
- not_available_fields
- rate_limited
- invalid_token

### 11.2 Penanganan error

- `invalid_grant` -> refresh token atau reauthorize
- `rate_limited` -> backoff and retry
- `scope_missing` -> catat error dan jangan klaim data tidak tersedia tanpa info yang jelas
- `creator_not_authorized` -> skip dengan reason
- `field_not_returned_by_api` -> biarkan nilai lama tetap utuh

## 12. Kriteria penerimaan

- Satu kreator yang sudah terhubung diperbarui berdasarkan ID TikTok; fallback handle tidak membuat duplikat.
- Satu video tidak terduplikasi ketika batch yang sama dijalankan ulang.
- Data API dipetakan ke tabel yang sesuai.
- GMV/komisi yang sudah ada tetap utuh bila API tidak mengirim nilainya.
- Pagination, rate limit, token invalid, dan error per creator ditangani dengan ringkasan batch.
- Kredensial tidak tampil di log/export.
- Instruksi konfigurasi dan scheduler disiapkan.

## 13. Jawaban terhadap pertanyaan yang perlu dikonfirmasi sebelum coding

### 13.1 Jenis API yang sudah aktif

Belum bisa dipastikan tanpa konfirmasi dari pihak pemilik aplikasi. Yang benar adalah:
- jika TikTok for Developers aktif, gunakan user/video authorization flow;
- jika TikTok Shop Affiliate Creator API aktif, gunakan creator shop auth flow;
- bila belum ada salah satunya, implementasi harus masuk mode `adapter ready` dan menunggu aktivasi.

### 13.2 Scope/permission

Setidaknya perlu dikonfirmasi:
- `video.list` atau scope video yang sesuai
- `affiliate.read` / creator affiliate scope
- apakah follower data tersedia
- apakah video metric seperti views/likes/comments/shares tersedia
- apakah GMV dan commission tersedia pada endpoint yang aktif

### 13.3 Target dataset

- target utama: kreator yang telah mengotorisasi aplikasi
- target tambahan: creator yang terhubung ke shop affiliate yang sesuai
- tidak boleh mengasumsikan seluruh profil TikTok publik bisa diambil dengan satu API key

### 13.4 Frekuensi sync

Disarankan:
- sync harian untuk profile dan metrik basic,
- sync real-time/berjadwal untuk update creator aktif,
- batch sesuai kapasitas rate limit dan jumlah creator per run.

## 14. Rekomendasi implementasi teknis

### 14.1 Struktur backend

- `App\Services\TikTok\TikTokAuthService`
- `App\Services\TikTok\TikTokCreatorSyncService`
- `App\Services\TikTok\TikTokVideoSyncService`
- `App\Services\TikTok\TikTokClient`
- `App\Services\TikTok\TikTokNormalizer`
- `App\Services\TikTok\TikTokBatchSummary`

### 14.2 Adapter strategy

```text
TikTokClient
  ├── DevelopersAdapter
  │   ├── fetchCreatorProfile()
  │   ├── fetchCreatorVideos()
  │   └── fetchVideoMetrics()
  └── ShopAffiliateAdapter
      ├── fetchCreatorHandles()
      ├── fetchAffiliateProfile()
      └── fetchAffiliateVideos()
```

### 14.3 Rule utama

- Hanya pakai endpoint yang benar-benar aktif.
- Tidak mengklaim akses yang belum disetujui.
- Jaga data CRM dan shipment tetap tidak berubah.
- Semua update harus idempotent.

## 15. Kesimpulan

Implementasi yang benar adalah implementasi adapter modular dengan pengendalian access yang eksplisit berdasarkan API dan scope yang memang aktif. Struktur data yang sudah dibuat oleh aplikasi sudah cukup untuk menyimpan profile dan video TikTok, dengan penyesuaian kecil pada `platform_video_id`, `likes`, `comments`, dan `shares` bila endpoint yang aktif memproduksi metrik tersebut.

Semua data dummy dan contoh payload di atas sudah disiapkan sebagai fixture validasi, sedangkan data nyata aplikasi saat ini baru mencakup 11.681 baris ekspor dengan 2 creator yang sudah punya metrik video. Karena itu, logika sinkronisasi harus didesain untuk data parsial, bukan data yang selalu lengkap.

Langkah berikutnya yang paling penting adalah konfirmasi jenis API yang aktif, scope yang sudah disetujui, dan apakah akses yang tersedia mencakup follower, video, atau GMV/komisi. Setelah itu, adapter dan migrasi dapat dibuat sesuai kebutuhan aktual.
