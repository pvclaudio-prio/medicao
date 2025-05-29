import streamlit as st
import pdfplumber
import tempfile
import os
import re
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

#--------------------------------------
#FUNÇÕES
#---------------------------------------
def extrair_linhas_boletim_debug(texto):
    import re
    import pandas as pd
    from datetime import datetime

    linhas = texto.split("\n")
    registros = []

    # Regex atual (padrão esperado)
    regex_linha = re.compile(
        r"(?P<funcao>.+?)\s+(?P<nome>[\w\s\.]+?)\s+X\s+(?P<qtd>\d+)\s+R\$ ?(?P<valor_unit>[\d\.,]+)\s+R\$ ?(?P<valor_total>[\d\.,]+)"
    )

    regex_periodo = re.compile(r"(\d{2}/\d{2})\s*-\s*(\d{2}/\d{2})")

    periodo_padrao = None
    total_linhas = 0
    linhas_com_match = 0
    linhas_sem_match = []

    for linha in linhas:
        total_linhas += 1
        st.code(linha, language="text")

        match = regex_linha.search(linha)
        if match:
            linhas_com_match += 1
            periodo = regex_periodo.search(linha)
            if periodo:
                data_ini, data_fim = periodo.groups()
                ano_ref = "2024"
                data_inicio = datetime.strptime(f"{data_ini}/{ano_ref}", "%d/%m/%Y").date()
                data_fim = datetime.strptime(f"{data_fim}/{ano_ref}", "%d/%m/%Y").date()
                periodo_padrao = (data_inicio, data_fim)
            elif periodo_padrao:
                data_inicio, data_fim = periodo_padrao
            else:
                data_inicio = data_fim = None

            registros.append({
                "função": match.group("funcao").strip(),
                "nome": match.group("nome").strip(),
                "quantidade": int(match.group("qtd")),
                "valor_unitário": float(match.group("valor_unit").replace(".", "").replace(",", ".")),
                "valor_total": float(match.group("valor_total").replace(".", "").replace(",", ".")),
                "período_inicio": data_inicio,
                "período_fim": data_fim,
                "tipo_linha": "normal"
            })
        else:
            linhas_sem_match.append(linha)

    st.markdown(f"✅ **{linhas_com_match} de {total_linhas} linhas** capturadas com sucesso.")
    if linhas_sem_match:
        st.markdown("⚠️ **Linhas sem correspondência com o padrão:**")
        for linha in linhas_sem_match:
            st.text(f"❌ {linha}")

    return pd.DataFrame(registros)

#---------------------------------------
#MENU
#---------------------------------------

menu = st.sidebar.radio("Navegar para:", [
    "📤 Upload de Arquivos",
    "🔍 Conciliação de Preços",
    "🧮 Verificação de Duplicidade",
    "🤖 Análise IA Red Flags",
    "📄 Relatório Final"
])

#---------------------------------------
#UPLOAD DE ARQUIVOS
#---------------------------------------

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

            df_medicao = extrair_linhas_boletim_debug(texto_medicao)
            st.markdown("### 📊 Tabela Estruturada")
            st.dataframe(df_medicao)

            os.unlink(tmp_path)
