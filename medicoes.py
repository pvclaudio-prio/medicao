import streamlit as st
import pdfplumber
import tempfile
import os

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

menu = st.sidebar.radio("Navegar para:", [
    "📤 Upload de Arquivos",
    "🔍 Conciliação de Preços",
    "🧮 Verificação de Duplicidade",
    "🤖 Análise IA Red Flags",
    "📄 Relatório Final"
])

if menu == "📤 Upload de Arquivos":
    st.title("📤 Upload de Arquivos Separados")

    st.subheader("📑 Contratos")
    contratos_files = st.file_uploader(
        "Envie aqui os arquivos de contrato (ex: começam com 46)",
        type=["pdf"],
        accept_multiple_files=True,
        key="contratos"
    )

    st.subheader("📋 Boletins de Medição")
    medicoes_files = st.file_uploader(
        "Envie aqui os arquivos de boletins (MED, BMS, Invoice...)",
        type=["pdf"],
        accept_multiple_files=True,
        key="medicoes"
    )

    if contratos_files:
        st.success(f"🗂️ {len(contratos_files)} contrato(s) carregado(s)")
        for file in contratos_files:
            st.markdown(f"**📄 {file.name}**")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            with pdfplumber.open(tmp_path) as pdf:
                texto_contrato = "\n".join([page.extract_text() or "" for page in pdf.pages])
            st.text_area("📝 Conteúdo do contrato (preview)", texto_contrato[:1500], height=200)
            os.unlink(tmp_path)

    if medicoes_files:
        st.success(f"🗂️ {len(medicoes_files)} boletim(ns) carregado(s)")
        for file in medicoes_files:
            st.markdown(f"**📄 {file.name}**")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name
            with pdfplumber.open(tmp_path) as pdf:
                texto_medicao = "\n".join([page.extract_text() or "" for page in pdf.pages])
            st.text_area("📝 Conteúdo da medição (preview)", texto_medicao[:1500], height=200)
            os.unlink(tmp_path)
