import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import pytesseract
from PIL import Image
from io import BytesIO
from openai import OpenAI
import json
import time

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

# ============ FUNÇÕES DE CLASSIFICAÇÃO ============
def classificar_layout(texto):
    if "CATEGORIA" in texto and "R$" in texto:
        return "tabular_simples"
    elif "TOTAL DA MEDIÇÃO" in texto and texto.count("R$") > 10:
        return "tabular_complexo"
    else:
        return "imagem_timesheet"

# ============ PARSER PARA TABELA SIMPLES ============
def parse_tabular_simples(texto):
    linhas = texto.split('\n')
    padrao = re.compile(r'(\d+)\s+([A-Za-z \/]+)\s+([A-Za-z \/]+)\s+X\s+(\d+)\s+([\d\.,]+)\s+R\$\s+([\d\.,]+)')
    dados = []
    for linha in linhas:
        match = padrao.search(linha)
        if match:
            try:
                dados.append({
                    "função": match.group(2).strip(),
                    "nome": match.group(3).strip(),
                    "quantidade": int(match.group(4)),
                    "valor_unitario": float(match.group(5).replace(".", "").replace(",", ".")),
                    "valor_total": float(match.group(6).replace(".", "").replace(",", "."))
                })
            except:
                continue
    return pd.DataFrame(dados)

# ============ FUNÇÃO OCR ============
def extrair_texto_ocr(img_bytes):
    imagem = Image.open(BytesIO(img_bytes))
    return pytesseract.image_to_string(imagem, lang='por')

# ============ GPT-4o FALLBACK ============
def extrair_linhas_com_gpt(linhas):
    client = OpenAI(api_key=st.secrets["openai"]["api_key"])
    prompt_base = """
Você é um especialista em boletins de medição. Para cada linha, extraia um objeto JSON com os seguintes campos:
- função
- nome
- periodo_inicio: "YYYY-MM-DD"
- periodo_fim: "YYYY-MM-DD"
- quantidade: inteiro
- valor_unitario: float
- valor_total: float

Remova "R$", normalize números (ex: 8.312,50 para 8312.50) e padronize datas como 2024-09-17. O retorno deve ser JSON puro.
Exemplo:
1 Montador de Andaime Wesley dos Santos X 17/09 - 01/10 145 93,75 8.312,50

Saída:
[
  {
    "função": "Montador de Andaime",
    "nome": "Wesley dos Santos",
    "periodo_inicio": "2024-09-17",
    "periodo_fim": "2024-10-01",
    "quantidade": 145,
    "valor_unitario": 93.75,
    "valor_total": 8312.50
  }
]
Agora processe:
"""
    resultados = []
    for i in range(0, len(linhas), 5):
        lote = linhas[i:i+5]
        prompt = prompt_base + "\n".join(lote)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Você interpreta boletins de medição."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=1500
            )
            resposta = response.choices[0].message.content.strip()
            dados = json.loads(resposta)
            resultados.extend(dados)
        except Exception as e:
            st.error(f"Erro GPT no lote {i}-{i+5}: {e}")
        time.sleep(1)
    return pd.DataFrame(resultados)

# ============ INTERFACE STREAMLIT ============
menu = st.sidebar.radio("Navegação", ["📥 Upload PDF", "🔍 Análise e Parsing", "🤖 GPT Fallback", "🧾 OCR de Imagem"])

if menu == "📥 Upload PDF":
    st.title("📥 Upload de PDF de Medição")

    pdf_file = st.file_uploader("Selecione o PDF do Boletim", type="pdf")

    if pdf_file:
        # Armazenar bytes em session_state uma única vez
        if 'pdf_bytes' not in st.session_state or st.session_state.get('pdf_filename') != pdf_file.name:
            st.session_state['pdf_bytes'] = pdf_file.getvalue()
            st.session_state['pdf_filename'] = pdf_file.name

            # Leitura do conteúdo e classificação
            try:
                doc = fitz.open(stream=st.session_state['pdf_bytes'], filetype="pdf")
                texto_pdf = "\n".join([page.get_text() for page in doc])
                st.session_state['pdf_text'] = texto_pdf
                st.session_state['pdf_layout'] = classificar_layout(texto_pdf[:1000])
            except Exception as e:
                st.error(f"Erro ao processar o PDF: {e}")
        else:
            texto_pdf = st.session_state['pdf_text']

        # Exibição parcial
        st.subheader("📄 Pré-visualização do conteúdo extraído")
        st.text_area("Texto extraído das primeiras páginas:", texto_pdf[:2000], height=300)
        st.success(f"📌 Tipo de layout detectado: **{st.session_state['pdf_layout']}**")

    else:
        st.info("📂 Faça upload de um PDF para continuar.")

if menu == "🔍 Análise e Parsing":
    st.title("🔍 Parsing Estruturado do Boletim")
    if 'pdf_text' in st.session_state and 'pdf_layout' in st.session_state:
        texto = st.session_state['pdf_text']
        layout = st.session_state['pdf_layout']
        if layout == "tabular_simples":
            df = parse_tabular_simples(texto)
            if not df.empty:
                st.success(f"✅ {len(df)} registros extraídos com sucesso.")
                st.dataframe(df)
            else:
                st.warning("⚠️ Nenhuma linha foi extraída pelo parser tabular simples.")
        else:
            st.warning("⚠️ Tipo de layout diferente de 'tabular_simples'. Use o fallback com GPT-4o ou OCR.")
    else:
        st.info("📥 Faça o upload de um PDF na aba anterior.")

if menu == "🤖 GPT Fallback":
    st.title("🤖 GPT-4o para Parsing de Texto Ruim")
    if 'pdf_text' in st.session_state:
        texto = st.session_state['pdf_text']
        linhas = [l for l in texto.split("\n") if " X " in l and " - " in l]
        with st.spinner("Analisando com IA..."):
            df = extrair_linhas_com_gpt(linhas)
        st.success(f"Extração concluída com {len(df)} linhas.")
        st.dataframe(df)
    else:
        st.info("Envie um PDF na aba de Upload.")

if menu == "🧾 OCR de Imagem":
    st.title("🧾 OCR para Boletins em Imagem")
    img_file = st.file_uploader("Imagem escaneada ou captura (JPG/PNG)", type=["jpg", "png"])
    if img_file:
        texto = extrair_texto_ocr(img_file.read())
        st.text_area("Texto extraído:", texto, height=300)
