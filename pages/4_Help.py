import streamlit as st

# auth check
if "user_id" not in st.session_state:
    st.warning("silakan login terlebih dahulu")
    st.stop()

st.title("Help / Manual Penggunaan")
st.caption("Panduan langkah demi langkah untuk menggunakan fitur prediksi harga emas Antam")

st.markdown("## 1. Masuk ke Aplikasi")
st.write("- Buka halaman `Login` dan masukkan kredensial yang valid.\n- Setelah login berhasil, akan terlihat halaman `Home`, `Prediction`, `About`, dan `Help` di sidebar streamlit")

st.markdown("## 2. Cek Overview di Home")
st.write(
    "Di halaman `Home`, akan terlihat ringkasan model dan performa. "
    "Halaman ini membantu memastikan bahwa model-model forecasting telah tersedia dan siap digunakan"
)

st.markdown("## 3. Menyiapkan Data Historis")
st.write(
    "Pada halaman `Prediction`, gunakan bagian `setup data historis` terlebih dahulu. "
    "Pilih `start date` dan `end date`, lalu klik `initialize historical data` untuk mengunduh dan menyimpan data harga emas Antam dan kurs USD/IDR"
)
st.write("**Note: Data historis ini diperlukan sebagai input utama model prediksi**")

st.markdown("## 4. Upload Data Variabel Eksternal")
st.write(
    "Jika anda sudah memiliki data `xau/usd`, `inflasi yoy`, dan `BI 7DRR Rate` terbaru, upload file-file tersebut di bagian `update data static manual per variabel`. "
    "Sistem akan otomatis membaca dan menyimpan setiap file ke database internal aplikasi"
)

st.markdown("### 4.1 XAU/USD")
st.write(
    "- Klik `upload xau/usd` dan pilih file CSV atau Excel\n"
    "- Setelah file dipilih, klik `update xau/usd`\n"
    "- Sistem akan mem-parsing data dan menyimpannya sebagai input variabel eksternal untuk model"
)

st.markdown("### 4.2 Inflasi YoY")
st.write(
    "- Klik `upload inflasi` dan pilih file yang berisi data inflasi year-over-year\n"
    "- Klik `update inflasi` setelah file terupload\n"
    "- Pastikan data tanggal dan nilai inflasi tersedia agar model dapat menggunakannya")

st.markdown("### 4.3 BI Rate")
st.write(
    "- Klik `upload bi rate` dan pilih file BI 7DRR Rate dalam format CSV atau Excel\n"
    "- Klik `update bi rate` untuk menyimpan data\n"
    "- Data BI rate digunakan sebagai variabel eksogen tambahan yang mempengaruhi prediksi harga emas")

st.markdown("## 5. Memperbarui Data Terbaru")
st.write(
    "Jika sudah memiliki data historis, gunakan tombol `update data` untuk mengambil data Antam dan USD/IDR terbaru. "
    "Fitur ini akan menambahkan data baru ke tabel yang sudah ada")

st.markdown("## 6. Menjalankan Prediksi")
st.write(
    "- Pilih horizon prediksi yang diinginkan, misalnya H+1 sampai H+7\n"
    "- Klik tombol `run prediction`\n"
    "- Aplikasi akan menjalankan forecasting menggunakan tiga metode: SARIMAX, Hybrid SARIMAX-XGBoost, dan Hybrid SARIMAX-LightGBM")

st.markdown("## 7. Memeriksa Hasil Prediksi")
st.write(
    "Setelah prediksi selesai, halaman akan menampilkan:"
)
st.write(
    "- Tabel hasil prediksi untuk setiap model\n"
    "- Grafik harga aktual dan grafik prediksi forward\n"
    "- Tabel metrik evaluasi model untuk horizon yang dipilih\n"
    "- Informasi model terbaik berdasarkan RMSE"
)

st.markdown("## 8. Menyimpan Hasil")
st.write(
    "Gunakan tombol `download csv`, `download excel`, atau `download zip` untuk menyimpan hasil prediksi. "
    "File zip berisi output prediksi dan visualisasi yang dihasilkan")

st.markdown("## 9. Riwayat Prediksi")
st.write(
    "Di bagian paling bawah halaman `Prediction`, anda dapat melihat riwayat prediksi anda. "
    "Riwayat ini mencatat tanggal run, horizon, dan rentang data yang digunakan")

st.markdown("## 10. Tips Penting")
st.write(
    "- Pastikan data historis dan data variabel eksternal selalu lengkap sebelum menjalankan prediksi\n"
    "- Jika muncul peringatan data kosong, kembali ke bagian `setup data historis` atau `update data static manual per variabel`\n"
    "- Gunakan tombol `reset` jika ingin mengosongkan hasil prediksi dan memilih horizon baru")

st.info("Jika anda ingin penjelasan lebih detail tentang format file input, siapkan contoh file dan upload di halaman Prediction")
