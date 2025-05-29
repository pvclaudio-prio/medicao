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
def extrair_linhas_boletim_flexivel(texto):

    linhas = texto.split("\n")
    registros = []

    def limpar_num(valor):
        valor = re.sub(r"[^\d,]", "", valor)  # remove tudo exceto números e vírgula
        valor = valor.replace(",", ".")
        return float(valor) if valor else 0.0

    def extrair_datas(bloco):
        try:
            periodo_match = re.search(r"(\d{2}/\d{2})\s*-\s*(\d{2}/\d{2})", bloco)
            if periodo_match:
                data_ini, data_fim = periodo_match.groups()
                data_ini = datetime.strptime(f"{data_ini}/2024", "%d/%m/%Y").date()
                data_fim = datetime.strptime(f"{data_fim}/2024", "%d/%m/%Y").date()
                return data_ini, data_fim
        except:
            return None, None
        return None, None

    linhas_com_match = 0
    for linha in linhas:
        linha = re.sub(r"R\$ ?", "", linha)
        linha = re.sub(r"(\d)\s+(\d)", r"\1\2", linha)  # junta dígitos quebrados por espaço
        linha = linha.strip()

        # Processa somente linhas com " X " e " - "
        if " X " in linha and "-" in linha and "/" in linha:
            try:
                partes = linha.split(" X ")
                pre_x = partes[0].strip()
                pos_x = partes[1].strip()

                # extrai nome e função da parte antes do X
                tokens_pre = pre_x.split()
                nome = " ".join(tokens_pre[1:])  # ignora o número do item
                funcao = " ".join(tokens_pre[1:-3]) if len(tokens_pre) > 4 else nome

                # extrai período
                data_ini, data_fim = extrair_datas(pos_x)

                # tenta extrair os 3 últimos números: quantidade, unitário, total
                numeros = re.findall(r"[\d\.]*\d,\d{2}", pos_x)
                if len(numeros) >= 3:
                    qtd, unit, total = numeros[-3:]
                    registros.append({
                        "função": funcao.strip(),
                        "nome": nome.strip(),
                        "quantidade": int(float(limpar_num(qtd))),
                        "valor_unitário": limpar_num(unit),
                        "valor_total": limpar_num(total),
                        "período_inicio": data_ini,
                        "período_fim": data_fim,
                        "tipo_linha": "normal"
                    })
                    linhas_com_match += 1
                else:
                    st.text(f"❌ Falha: valores ausentes — {linha}")
            except Exception as e:
                st.text(f"❌ Erro: {e} — linha: {linha}")

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

            df_medicao = extrair_linhas_boletim_flexivel(texto_medicao)
            st.markdown("### 📊 Tabela Estruturada")
            st.dataframe(df_medicao)

            os.unlink(tmp_path)
