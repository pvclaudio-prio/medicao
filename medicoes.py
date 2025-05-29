import streamlit as st
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io

st.set_page_config(page_title="Conciliação OCR", layout="wide")

# Menu lateral
menu = st.sidebar.radio("Navegar para:", [
    "📥 Upload de Arquivos",
    "🧾 OCR e Extração de Dados",
    "🤖 Fallback com GPT-4o",
    "📊 Visualização e Exportação"
])

# Execução de cada página
if menu == "📥 Upload de Arquivos":
    st.title("📥 Upload de Arquivos")

    uploaded_file = st.file_uploader("Selecione um PDF ou imagem (JPG, PNG)", type=["pdf", "png", "jpg", "jpeg"])

    if uploaded_file:
        file_name = uploaded_file.name
        file_bytes = uploaded_file.read()

        st.session_state['file_name'] = file_name
        st.session_state['file_ext'] = file_name.split(".")[-1].lower()

        imagens = []

        # Processamento de PDF em imagens
        if st.session_state['file_ext'] == "pdf":
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_bytes))
                imagens.append(img)

        # Upload direto de imagem
        else:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            imagens.append(img)

        # Armazena imagens renderizadas na sessão
        st.session_state['imagens'] = imagens

        st.success(f"✅ {len(imagens)} página(s) processada(s) com sucesso!")

        # Exibe as imagens renderizadas
        for i, img in enumerate(imagens):
            st.markdown(f"**Página {i+1}**")
            st.image(img, use_column_width=True)
    else:
        st.info("📂 Faça upload de um arquivo para visualizar.")

elif menu == "🧾 OCR e Extração de Dados":
    st.title("🧾 OCR e Extração de Dados")
    # A lógica de OCR será implementada aqui

elif menu == "🤖 Fallback com GPT-4o":
    st.title("🤖 Fallback com GPT-4o")
    # GPT irá auxiliar no parsing quando o OCR for insuficiente

elif menu == "📊 Visualização e Exportação":
    st.title("📊 Visualização e Exportação")
    # Exibição final com filtros + botão para CSV
