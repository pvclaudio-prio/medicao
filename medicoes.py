import streamlit as st
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
import io
import pytesseract
import pandas as pd
from PIL import Image, ImageEnhance
import streamlit as st

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

if menu == "🧾 OCR e Extração de Dados":
    st.title("🧾 OCR e Extração de Dados")

    if 'imagens' not in st.session_state:
        st.warning("⚠️ Nenhuma imagem carregada. Volte à aba anterior e faça o upload de um arquivo.")
    else:
        imagens = st.session_state['imagens']
        textos_ocr = []
        dados_linhas = []

        for idx, imagem in enumerate(imagens):
            st.markdown(f"### Página {idx+1}")
            st.image(imagem, use_column_width=True)

            # Pré-processamento simples
            imagem_cinza = imagem.convert("L")  # escala de cinza
            imagem_contraste = ImageEnhance.Contrast(imagem_cinza).enhance(2)

            # OCR com pytesseract
            texto = pytesseract.image_to_string(imagem_contraste, lang="por")
            textos_ocr.append(texto)

            # Exibição para debug
            with st.expander(f"📄 Texto OCR da Página {idx+1}"):
                st.text(texto)

            # Separação básica por linhas com heurística: manter linhas com números
            for linha in texto.split("\n"):
                if any(char.isdigit() for char in linha) and len(linha.strip()) > 10:
                    dados_linhas.append(linha.strip())

        # Exibir linhas brutas detectadas
        if dados_linhas:
            df_raw = pd.DataFrame(dados_linhas, columns=["linha_ocr"])
            st.session_state['df_raw_ocr'] = df_raw
            st.success(f"✅ {len(dados_linhas)} linhas detectadas contendo dados.")
            st.dataframe(df_raw)
        else:
            st.warning("⚠️ Nenhuma linha com dados foi detectada.")

elif menu == "🤖 Fallback com GPT-4o":
    st.title("🤖 Fallback com GPT-4o")
    # GPT irá auxiliar no parsing quando o OCR for insuficiente

elif menu == "📊 Visualização e Exportação":
    st.title("📊 Visualização e Exportação")
    # Exibição final com filtros + botão para CSV
