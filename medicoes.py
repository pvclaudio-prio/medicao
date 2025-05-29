import streamlit as st
import pdfplumber
import tempfile
import os
import re
import pandas as pd
from datetime import datetime
from openai import OpenAI
import json
import time

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

#--------------------------------------
#FUNÇÕES
#---------------------------------------
def extrair_texto_pdf(pdf_file):
    with fitz.open(stream=pdf_file.getvalue(), filetype="pdf") as doc:
        texto = "\n".join([page.get_text() for page in doc])
    return texto

def extrair_linhas_boletim_flexivel(texto):
    linhas = texto.split("\n")
    colunas_esperadas = ["função", "nome", "período", "quantidade", "valor_unitario", "valor_total"]
    dados = []
    for linha in linhas:
        if " X " in linha and " - " in linha:
            partes = linha.split(" X ")
            if len(partes) < 2:
                continue
            parte1, parte2 = partes
            tokens = parte2.split()
            if len(tokens) < 4:
                continue
            nome = parte1.strip().split(maxsplit=1)[-1].strip()
            periodo = tokens[0] + " - " + tokens[2] if "-" in tokens[1] else tokens[0]
            quantidade = tokens[-3].replace(".", "").replace(",", ".")
            valor_unitario = tokens[-2].replace(".", "").replace(",", ".")
            valor_total = tokens[-1].replace(".", "").replace(",", ".")
            funcao_tokens = parte1.strip().split()[1:-1]
            funcao = " ".join(funcao_tokens)
            try:
                dados.append({
                    "função": funcao,
                    "nome": nome,
                    "período": periodo,
                    "quantidade": float(quantidade),
                    "valor_unitario": float(valor_unitario),
                    "valor_total": float(valor_total)
                })
            except:
                continue
    return pd.DataFrame(dados)

def extrair_linhas_com_gpt(linhas_ruins):
    client = OpenAI(api_key=st.secrets["openai"]["api_key"])
    resultados = []

    prompt_base = """
Você é um especialista em boletins de medição. Dado um conjunto de linhas desformatadas, extraia os dados com os campos:

- função
- nome
- período_inicio (formato YYYY-MM-DD)
- período_fim (formato YYYY-MM-DD)
- quantidade (número)
- valor_unitario (float)
- valor_total (float)

Exemplo de entrada:
1 Montador de Andaime Wesley dos Santos X 17/09 - 01/10 145 93,75 8.312,50

Saída:
[
  {
    "função": "Montador de Andaime",
    "nome": "Wesley dos Santos",
    "período_inicio": "2024-09-17",
    "período_fim": "2024-10-01",
    "quantidade": 145,
    "valor_unitario": 93.75,
    "valor_total": 8312.50
  }
]

Agora processe as seguintes linhas:
"""
    batch_size = 5
    for i in range(0, len(linhas_ruins), batch_size):
        lote = linhas_ruins[i:i + batch_size]
        conteudo = prompt_base + "\n".join(lote)
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Você é um assistente que interpreta boletins de medição."},
                    {"role": "user", "content": conteudo}
                ],
                temperature=0,
                max_tokens=1500
            )
            resposta = response.choices[0].message.content.strip()
            dados_json = json.loads(resposta)
            resultados.extend(dados_json)
        except Exception as e:
            st.error(f"Erro no lote {i}-{i+batch_size}: {e}")
        time.sleep(1)
    return pd.DataFrame(resultados)
#---------------------------------------
#MENU
#---------------------------------------

menu = st.sidebar.radio("Navegar para:", [
    "🏠 Dashboard",
    "📤 Upload de Documentos",
    "🔍 Conciliação de Valores",
    "📑 Verificar Duplicidade",
    "🤖 Análise com IA",
    "📊 Relatório Final"
])

#---------------------------------------
#UPLOAD DE ARQUIVOS
#---------------------------------------

if menu == "📤 Upload de Documentos":
    st.title("📤 Upload de Documentos de Medição e Contrato")

    col1, col2 = st.columns(2)
    with col1:
        pdf_medicao = st.file_uploader("📄 Enviar Boletim de Medição (PDF)", type="pdf", key="medicao")
    with col2:
        pdf_contrato = st.file_uploader("📄 Enviar Tabela de Contrato (PDF)", type="pdf", key="contrato")

    usar_gpt = st.checkbox("🧠 Usar GPT-4o para extrair linhas com IA", value=True)

    if pdf_medicao:
        texto_medicao = extrair_texto_pdf(pdf_medicao)
        df_medicao_tradicional = extrair_linhas_boletim_flexivel(texto_medicao)

        linhas_ruins = [linha for linha in texto_medicao.split('\n') if " X " in linha and " - " in linha]

        if df_medicao_tradicional.empty or usar_gpt:
            with st.spinner("🧠 Extraindo informações com inteligência artificial..."):
                df_medicao = extrair_linhas_com_gpt(linhas_ruins)
                erros = len(linhas_ruins) - len(df_medicao)
                st.success(f"✅ Medição processada com sucesso — {len(df_medicao)} linhas extraídas. ❌ {erros} falhas não interpretadas.")
                st.dataframe(df_medicao)
        else:
            st.success(f"✅ Medição extraída com sucesso — {len(df_medicao_tradicional)} linhas.")
            st.dataframe(df_medicao_tradicional)

    if pdf_contrato:
        st.info("📎 O parser para contratos será implementado em etapa futura.")

elif menu == "🏠 Dashboard":
    st.title("🏠 Dashboard de Conciliação")
    st.info("Em construção.")

elif menu == "🔍 Conciliação de Valores":
    st.title("🔍 Conciliação de Valores entre Medição e Contrato")
    st.info("Em construção.")

elif menu == "📑 Verificar Duplicidade":
    st.title("📑 Verificação de Duplicidade de Funcionários")
    st.info("Em construção.")

elif menu == "🤖 Análise com IA":
    st.title("🤖 Análise de Riscos com IA")
    st.info("Em construção.")

elif menu == "📊 Relatório Final":
    st.title("📊 Relatório Final de Red Flags")
    st.info("Em construção.")
