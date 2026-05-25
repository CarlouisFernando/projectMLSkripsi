import streamlit as st
from PIL import Image

# auth check
if "user_id" not in st.session_state:
    st.warning("Silahkan Login Terlebih Dahulu")
    st.stop()

st.title("About")

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    st.image("image/untar png.png", width=150)

st.write("""
Aplikasi ini dikembangkan untuk mendukung proses forecasting harga emas Antam menggunakan beberapa pendekatan metode, yaitu:

- SARIMAX
- Hybrid SARIMAX-XGBoost
- Hybrid SARIMAX-LightGBM

""")

st.subheader("Info Pembuat")
st.markdown("""
Carlouis Fernando Hariyadi (535220156) merupakan mahasiswa Universitas Tarumanagara jurusan Teknik Informatika yang berfokus pada bidang Data Science dan predictive analytics. Aplikasi ini dikembangkan untuk membantu investor maupun masyarakat umum dalam menentukan keputusan investasi emas melalui prediksi harga emas Antam berbasis data.

Prediksi dilakukan menggunakan pendekatan multivariate time series dengan memanfaatkan beberapa indikator ekonomi, seperti kurs USD/IDR, harga XAU/USD, inflasi, dan BI Rate. Model yang digunakan meliputi SARIMAX, Hybrid SARIMAX-XGBoost, serta Hybrid SARIMAX-LightGBM untuk menghasilkan prediksi yang lebih akurat dan adaptif terhadap perubahan kondisi ekonomi.

Pengembangan aplikasi ini dilakukan di bawah bimbingan dosen Universitas Tarumanagara, yaitu Bapak Tri Sutrisno, S.Si., M.Sc. dan Bapak Irvan Lewenusa, S.Kom., M.Kom.
""")
