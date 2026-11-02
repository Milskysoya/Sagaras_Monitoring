# Varuna ASV – Monitoring (backend + frontend)

```
Pixhawk --MAVLink--> Jetson (telemetry_publisher.py) --> Supabase (mission_logs + mission_images)
                                                              |  realtime INSERT + polling gambar
                                                              v
                                                  frontend/ (index.html, anon key, read-only)
```

## 1. Supabase
1. Buat project, buka **SQL Editor**, jalankan `schema.sql`.
2. Catat **Project URL**, **anon key** (untuk frontend) dan **service_role key** (untuk Jetson saja).

## 2. Backend (Jetson)
```bash
cd backend
pip install -r requirements.txt --break-system-packages
cp .env.example .env     # isi SUPABASE_URL & SUPABASE_SERVICE_KEY
python telemetry_publisher.py run --simulate --dry-run   # tes tanpa hardware & tanpa internet
python telemetry_publisher.py run --simulate             # tes kirim ke Supabase
python telemetry_publisher.py run                        # telemetri nyata dari Pixhawk
python telemetry_publisher.py capture surface            # foto permukaan -> bucket
python telemetry_publisher.py capture underwater         # foto bawah air -> bucket
```
Dari program vision/misi: `from telemetry_publisher import set_score, add_score, set_geotag, upload_image`,
atau tulis `mission_state.json` (`{"score": 20, "position": "A3"}`) yang dibaca tiap siklus.
Nama file gambar harus mengandung `surface` / `underwater` (frontend juga menerima `green` / `blue`).

Kalibrasi kolam lewat `POOL_ORIGIN_LAT/LON` dan `POOL_SIZE_M` agar x,y (0–25) cocok dengan lintasan.

## 3. Frontend
Isi `frontend/config.js` (URL + **anon** key), lalu hosting folder `frontend/` (Netlify/Vercel/GitHub Pages).
Lokal: `cd frontend && python -m http.server 8000`. Jika config kosong, jalan **mode DEMO**.
Taruh `Varuna.ico` dan `Varuna.jpg` di folder frontend. Tombol "B" menuju `ArkawiraB.html` (belum dibuat).

## Catatan
- Service key tidak boleh ada di frontend atau repo publik.
- Teks Bab 2.8/2.9 proposal masih menyebut Firebase, sedangkan pseudocode & kode ini memakai Supabase; samakan salah satunya.


## link 
https://supabase.com/dashboard/project/okiyuqhnjrjdcdifjvvp