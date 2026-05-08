import streamlit as st
from utils.auth import get_all_users, delete_user

# auth check
if "user_id" not in st.session_state:
    st.warning("silakan login terlebih dahulu")
    st.stop()

if st.session_state.get("username") != "admin":
    st.error("Akses admin hanya untuk user 'admin'.")
    st.info("Login dengan akun admin untuk mengelola pengguna.")
    st.stop()

st.title("Admin Panel")
st.subheader("Kelola Akun Pengguna")

st.info(
    "Halaman ini hanya tersedia untuk akun admin. "
    "Gunakan untuk melihat dan menghapus akun terdaftar."
)

users = get_all_users()
if not users:
    st.info("Belum ada akun pengguna terdaftar.")
else:
    user_table = [
        {"id": row[0], "username": row[1], "created_at": row[2]}
        for row in users
    ]
    st.dataframe(user_table, use_container_width=True)

    # Filter usernames tanpa admin
    usernames = [row["username"] for row in user_table if row["username"] != "admin"]
    
    if not usernames:
        st.info("Tidak ada akun pengguna yang dapat dihapus.")
    else:
        selected_users = st.multiselect("Pilih username untuk dihapus (bisa banyak)", usernames)

        if st.button("Hapus akun pengguna terpilih", use_container_width=True):
            if not selected_users:
                st.warning("Silakan pilih setidaknya satu akun untuk dihapus.")
            else:
                deleted_count = 0
                failed_users = []
                for username in selected_users:
                    if delete_user(username):
                        deleted_count += 1
                    else:
                        failed_users.append(username)
                
                if deleted_count > 0:
                    st.success(f"{deleted_count} akun berhasil dihapus.")
                    st.rerun()
                if failed_users:
                    st.error(f"Gagal menghapus akun: {', '.join(failed_users)}")
