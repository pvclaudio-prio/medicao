import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import os

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

# -----------------------------------
# 🎛️ MENU LATERAL
# -----------------------------------
menu = st.sidebar.radio("📂 Navegar para:", [
    "📤 Upload e Classificação",
    "📊 Visualização dos Dados",
    "📑 Conciliação com Contrato",
    "🧠 IA: Análise de Anomalias",
    "📄 Geração de Relatório"
])

st.title("📑 Sistema de Conciliação de Boletins de Medição")

# -----------------------------------
# FUNÇÕES AUXILIARES
# -----------------------------------
def extrair_texto_fitz(uploaded_file):
    try:
        with fitz.open(stream=uploaded_file.read(), filetype="pdf") as doc:
            texto = "\n".join([page.get_text() for page in doc])
        return texto
    except Exception as e:
        return f"Erro ao extrair texto com fitz: {e}"

def classificar_documento(texto):
    texto_baixo = texto.lower()
    if "boletim de medição" in texto_baixo or "medição nº" in texto_baixo:
        return "Boletim de Medição"
    elif "invoice" in texto_baixo or "nota fiscal" in texto_baixo:
        return "Nota Fiscal / Invoice"
    elif "itens de consumo" in texto_baixo or "quantidade solicitada" in texto_baixo:
        return "Lista de Materiais"
    else:
        return "Outro"

# -----------------------------------
# 📤 UPLOAD E CLASSIFICAÇÃO
# -----------------------------------
if menu == "📤 Upload e Classificação":
    st.header("📤 Upload de Documentos")
    pdf_file = st.file_uploader("Enviar arquivo PDF", type="pdf")

    if pdf_file is not None:
        with st.spinner("🔍 Analisando o documento..."):
            texto = extrair_texto_fitz(pdf_file)
            tipo = classificar_documento(texto[:1000])

        st.success(f"✅ Documento classificado como: **{tipo}**")
        with st.expander("📄 Visualizar conteúdo bruto (início)"):
            st.text(texto[:1500])

elif menu == "📊 Visualização dos Dados":
    st.header("📊 Visualização dos Dados Estruturados")
    st.info("Visualização por categoria: mão de obra, equipamentos, materiais e eventos.")

elif menu == "📑 Conciliação com Contrato":
    st.header("📑 Conciliação entre Boletim e Contrato")
    st.info("Comparação de quantidades, valores e datas com o contrato vigente.")

elif menu == "🧠 IA: Análise de Anomalias":
    st.header("🧠 Análise de Red Flags com IA")
    st.info("Identificação de padrões suspeitos e inconsistências.")

elif menu == "📄 Geração de Relatório":
    st.header("📄 Geração Automática de Relatório")
    st.info("Resumo executivo com análise técnica e recomendações.")
