import streamlit as st
import pdfplumber
import tempfile
import os

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

# MENU LATERAL CUSTOMIZADO
menu = st.sidebar.radio("Navegar para:", [
    "📤 Upload de Arquivos",
    "🔍 Conciliação de Preços",
    "🧮 Verificação de Duplicidade",
    "🤖 Análise IA Red Flags",
    "📄 Relatório Final"
])

# 📤 ETAPA 1 — Upload de Arquivos
if menu == "📤 Upload de Arquivos":
    st.title("📤 Upload de Arquivos de Contrato e Boletins")

    uploaded_files = st.file_uploader(
        "Envie os arquivos de contrato e boletins de medição (PDF)",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:
        st.success(f"{len(uploaded_files)} arquivo(s) carregado(s).")
        for file in uploaded_files:
            st.subheader(f"📄 {file.name}")
            tipo = "Contrato" if file.name.startswith("46") else "Boletim"
            st.markdown(f"**Classificação automática:** `{tipo}`")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name

            with pdfplumber.open(tmp_path) as pdf:
                texto_completo = "\n".join([page.extract_text() or "" for page in pdf.pages])

            st.text_area("📝 Pré-visualização do conteúdo (texto extraído)", texto_completo[:3000], height=300)
            os.unlink(tmp_path)

# 🔍 ETAPA 2 — Conciliação de Preços
elif menu == "🔍 Conciliação de Preços":
    st.title("🔍 Conciliação de Preços")
    st.warning("Funcionalidade em desenvolvimento. Aguarde a próxima etapa.")

# 🧮 ETAPA 3 — Verificação de Duplicidade
elif menu == "🧮 Verificação de Duplicidade":
    st.title("🧮 Verificação de Duplicidade")
    st.warning("Funcionalidade em desenvolvimento. Aguarde a próxima etapa.")

# 🤖 ETAPA 4 — Análise IA Red Flags
elif menu == "🤖 Análise IA Red Flags":
    st.title("🤖 Análise Inteligente de Red Flags")
    st.warning("Funcionalidade em desenvolvimento. Aguarde a próxima etapa.")

# 📄 ETAPA 5 — Relatório Final
elif menu == "📄 Relatório Final":
    st.title("📄 Relatório Final")
    st.warning("Funcionalidade em desenvolvimento. Aguarde a próxima etapa.")
