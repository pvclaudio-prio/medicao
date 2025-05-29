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
def extrair_linhas_boletim_robusto(texto):
    import re
    import pandas as pd
    from datetime import datetime

    linhas = texto.split("\n")
    registros = []

    def limpar_valor(v):
        # Remove R$, pontos decimais quebrados e transforma em float
        v = re.sub(r"[^\d,]", "", v)           # remove tudo exceto dígito e vírgula
        v = v.replace(",", ".")
        return float(v) if v else 0.0

    regex_linha = re.compile(
        r"""(?P<funcao>.+?)\s+
            (?P<nome>.+?)\s+X\s+
            (?P<periodo>\d{2}/\d{2}\s*-\s*\d{2}/\d{2})\s+
            (?P<qtd>\d+)\s+
            (?P<valor_unit>[\d\s\.,]+)\s+
            (?P<valor_total>[\d\s\.,]+)
        """,
        re.VERBOSE
    )

    linhas_com_match = 0
    for linha in linhas:
        linha = re.sub(r"R\$ ?", "", linha)                 # remove R$
        linha = re.sub(r"(\d)\s+(\d)", r"\1\2", linha)       # junta dígitos quebrados por espaço
        match = regex_linha.search(linha)
        if match:
            data_inicio, data_fim = None, None
            try:
                periodo = match.group("periodo")
                ini, fim = periodo.split("-")
                data_inicio = datetime.strptime(ini.strip() + "/2024", "%d/%m/%Y").date()
                data_fim = datetime.strptime(fim.strip() + "/2024", "%d/%m/%Y").date()
            except:
                pass

            registros.append({
                "função": match.group("funcao").strip(),
                "nome": match.group("nome").strip(),
                "quantidade": int(match.group("qtd")),
                "valor_unitário": limpar_valor(match.group("valor_unit")),
                "valor_total": limpar_valor(match.group("valor_total")),
                "período_inicio": data_inicio,
                "período_fim": data_fim,
                "tipo_linha": "normal"
            })
            linhas_com_match += 1
        else:
            st.text(f"❌ {linha}")

    st.success(f"✅ {linhas_com_match} linhas capturadas com sucesso.")
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

            df_medicao = extrair_linhas_boletim_robusto(texto_medicao)
            st.markdown("### 📊 Tabela Estruturada")
            st.dataframe(df_medicao)

            os.unlink(tmp_path)
