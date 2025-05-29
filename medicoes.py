import streamlit as st
import streamlit as st
import pdfplumber
import os
import tempfile

st.set_page_config(page_title="Conciliação de Medições", layout="wide")
st.sidebar.image("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

st.markdown("# 🔧 Sistema de Conciliação de Boletins de Medição")
st.markdown("""
Este sistema permite:
- Upload de contratos e boletins de medição
- Verificação de preços divergentes
- Detecção de duplicidades de profissionais
- Geração de relatório final com análises via IA (GPT-4o)
""")

st.set_page_config(page_title="Upload de Arquivos", layout="wide")

st.markdown("## 📤 Upload de Arquivos de Contrato e Boletins")

uploaded_files = st.file_uploader(
    "Envie os arquivos de contrato e boletins de medição (PDF)",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.success(f"{len(uploaded_files)} arquivo(s) carregado(s).")
    with st.expander("📋 Arquivos carregados"):
        for file in uploaded_files:
            st.write(f"- {file.name}")

    st.markdown("---")

    for file in uploaded_files:
        st.subheader(f"📄 {file.name}")

        # Grava o PDF temporariamente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file.read())
            tmp_path = tmp.name

        # Determina o tipo (Contrato ou Medição)
        tipo = "Contrato" if file.name.startswith("46") else "Boletim"
        st.markdown(f"**Classificação automática:** `{tipo}`")

        # Extrai texto bruto com pdfplumber
        with pdfplumber.open(tmp_path) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                texto_completo += page.extract_text() + "\n"

        st.text_area("📝 Pré-visualização do conteúdo (texto extraído)", texto_completo[:3000], height=300)

        os.unlink(tmp_path)  # Limpa o arquivo temporário
