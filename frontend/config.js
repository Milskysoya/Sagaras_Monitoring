// Hanya ANON key (read-only berkat RLS). Jangan pernah taruh service_role key di sini.
// Kosongkan kedua nilai untuk menjalankan mode DEMO (data simulasi di browser).
export const SUPABASE_URL = "https://okiyuqhnjrjdcdifjvvp.supabase.co";
export const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9raXl1cWhuanJqZGNkaWZqdnZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMzOTQyMjIsImV4cCI6MjEwODk3MDIyMn0.6SA6rvgU4uq4QjQsI3UV9-c91gITb9zp1zQMszYSda4";

export const TABLE = "mission_logs";
export const BUCKET = "mission_images";
export const MAX_POINTS = 200;       // titik lintasan maksimum di chart
export const IMAGE_POLL_MS = 3000;   // refresh gambar tiap 3 detik
