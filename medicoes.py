import streamlit as st
import pandas as pd
import numpy as np
import fitz  # PyMuPDF
import openai
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import json
from collections import defaultdict
from io import BytesIO
import io

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

# === 📚 Menu lateral ===
st.sidebar.title("📁 Navegação")
pagina = st.sidebar.radio(
    "Escolha a funcionalidade:",
    [
        "📄 Upload de Documentos",
        "🔎 Visualização",
        "⚖️ Conciliação",
        "📤 Exportação"
    ]
)

if pagina == "📄 Upload de Documentos":
    st.header("📄 Upload de Documentos para Análise")

    # Seleção do tipo de processor
    tipo_processor = st.selectbox("🤖 Tipo de Processor do Document AI", options=["Form Parser", "Document OCR"])
    PROCESSOR_IDS = {
        "Form Parser": st.secrets["google"].get("form_parser_id"),
        "Document OCR": st.secrets["google"].get("contract_processor")
    }

    processor_id = PROCESSOR_IDS.get(tipo_processor)
    if not processor_id:
        st.error(f"❌ Processor ID não encontrado para o tipo selecionado: `{tipo_processor}`.")
        st.stop()

    # Uploads
    arquivos_boletim = st.file_uploader("📑 Boletins de Medição", type=["pdf"], accept_multiple_files=True)
    arquivos_contrato = st.file_uploader("📑 Contratos de Serviço", type=["pdf"], accept_multiple_files=True)

    intervalos_boletim = {}
    intervalos_contrato = {}

    # Intervalos de páginas
    if arquivos_boletim:
        st.subheader("🟢 Intervalos de Páginas - Boletins")
        for arquivo in arquivos_boletim:
            col1, col2 = st.columns(2)
            with col1:
                inicio = st.number_input(f"Início ({arquivo.name})", min_value=1, value=1, key=f"inicio_b_{arquivo.name}")
            with col2:
                fim = st.number_input(f"Fim ({arquivo.name})", min_value=inicio, value=inicio, key=f"fim_b_{arquivo.name}")
            intervalos_boletim[arquivo.name] = (inicio, fim)

    if arquivos_contrato:
        st.subheader("🟡 Intervalos de Páginas - Contratos")
        for arquivo in arquivos_contrato:
            col1, col2 = st.columns(2)
            with col1:
                inicio = st.number_input(f"Início ({arquivo.name})", min_value=1, value=1, key=f"inicio_c_{arquivo.name}")
            with col2:
                fim = st.number_input(f"Fim ({arquivo.name})", min_value=inicio, value=inicio, key=f"fim_c_{arquivo.name}")
            intervalos_contrato[arquivo.name] = (inicio, fim)

    if st.button("🚀 Processar Documentos"):
        st.subheader("🔎 Extração com Document AI")
        tabelas_final = []

        for arquivo in arquivos_boletim + arquivos_contrato:
            is_boletim = arquivo in arquivos_boletim
            nome_doc = arquivo.name
            inicio, fim = (
                intervalos_boletim[nome_doc] if is_boletim else intervalos_contrato[nome_doc]
            )

            with st.spinner(f"Processando {nome_doc}..."):
                pdf_bytes = extrair_paginas_pdf(arquivo, inicio, fim)
                tabelas = processar_documento_documentai(pdf_bytes, processor_id, nome_doc)
                tabelas_final.extend(tabelas)

        st.success("✅ Processamento concluído!")

        # Armazenar os resultados no session_state
        st.session_state["tabelas_extraidas"] = tabelas_final

if pagina == "🔎 Visualização":
    st.header("🔎 Visualização das Tabelas Extraídas")

    # Verifica se há dados extraídos
    if "tabelas_extraidas" not in st.session_state:
        st.warning("⚠️ Nenhuma tabela foi processada ainda. Vá para '📄 Upload de Documentos' e clique em 'Processar Documentos'.")
        st.stop()

    # === Base oficial de contrato ===
    df_contrato = pd.DataFrame([
        {"ID_ITEM": "1.1", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "Operador Técnico", "UNIDADE": "Diária", "VALOR_UNITARIO": 1672.00, "VALOR_STANDBY": 1337.60},
        {"ID_ITEM": "1.2", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "Técnico Especializado (Supervisor)", "UNIDADE": "Diária", "VALOR_UNITARIO": 1995.00, "VALOR_STANDBY": 1596.00},
        {"ID_ITEM": "2.1", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "Flanges Kit", "UNIDADE": "Diária", "VALOR_UNITARIO": 475.00, "VALOR_STANDBY": 403.75},
        {"ID_ITEM": "2.2", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "Chemical Cleaning Equipment (EX)", "UNIDADE": "Diária", "VALOR_UNITARIO": 807.50, "VALOR_STANDBY": 686.38},
        {"ID_ITEM": "2.3", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "Hydrojetting Equipment", "UNIDADE": "Diária", "VALOR_UNITARIO": 1795.50, "VALOR_STANDBY": 1526.18},
        {"ID_ITEM": "3.1", "REFERENCIA": "MOB/DESMOB", "DESCRICAO": "Pessoal", "UNIDADE": "Evento", "VALOR_UNITARIO": 1850.00, "VALOR_STANDBY": 1850.00},
        {"ID_ITEM": "3.2", "REFERENCIA": "MOB/DESMOB", "DESCRICAO": "Equipamento", "UNIDADE": "Evento", "VALOR_UNITARIO": 3350.00, "VALOR_STANDBY": 3350.00},
    ])

    # === Organização das tabelas ===
    tabelas_extraidas = st.session_state["tabelas_extraidas"]
    tabelas_tratadas = defaultdict(list)

    for tabela_info in tabelas_extraidas:
        nome_doc = tabela_info["documento"]
        df_raw = pd.DataFrame(tabela_info["tabela"])

        with st.spinner(f"🧠 Organizando tabelas de {nome_doc} com GPT..."):
            df_tratada = organizar_tabela_com_gpt(nome_doc, df_raw)
            tabelas_tratadas[nome_doc].append(df_tratada)

    # Armazenar para etapas seguintes
    st.session_state["tabelas_tratadas"] = tabelas_tratadas
    st.session_state["df_contrato"] = df_contrato  # salva para reutilização em outras páginas

    # Exibição por documento
    for nome_doc, lista_df in tabelas_tratadas.items():
        try:
            df_unificado = pd.concat(lista_df, ignore_index=True)
            st.markdown(f"### 📄 Documento: <span style='color:green'><b>{nome_doc}</b></span>", unsafe_allow_html=True)
            st.dataframe(df_unificado)
        except Exception as e:
            st.warning(f"⚠️ Erro ao unificar tabelas do documento `{nome_doc}`: {e}")

if pagina == "⚖️ Conciliação":
    st.header("⚖️ Conciliação entre Boletins e Contrato")

    if "tabelas_tratadas" not in st.session_state:
        st.warning("⚠️ Nenhum dado tratado disponível. Vá para '🔎 Visualização' primeiro.")
        st.stop()

    tabelas_tratadas = st.session_state["tabelas_tratadas"]
    nomes_docs = list(tabelas_tratadas.keys())

    if not nomes_docs:
        st.info("Nenhum documento disponível.")
        st.stop()

    doc_selecionado = st.selectbox("📄 Selecione o documento para conciliação:", nomes_docs)

    try:
        df_boletim = pd.concat(tabelas_tratadas[doc_selecionado], ignore_index=True)
        df_conciliado = estruturar_boletim_conciliado(df_boletim, df_contrato)

        st.subheader(f"📋 Resultado da Conciliação: {doc_selecionado}")
        st.dataframe(df_conciliado)

        # Filtros opcionais
        if st.checkbox("🔍 Mostrar apenas divergências"):
            df_filtrado = df_conciliado[
                (df_conciliado["FLAG_VALOR_DIVERGENTE"] == "Sim") |
                (df_conciliado["FLAG_TOTAL_RECALCULADO_DIFERENTE"] == "Sim") |
                (df_conciliado["FLAG_DESCRICAO_DUPLICADA"] == "Sim")
            ]
            st.dataframe(df_filtrado)

        st.session_state["df_conciliado_atual"] = df_conciliado

    except Exception as e:
        st.error(f"Erro ao realizar conciliação: {e}")
if pagina == "📤 Exportação":
    st.header("📤 Exportação dos Resultados de Conciliação")

    if "df_conciliado_atual" not in st.session_state:
        st.warning("⚠️ Nenhuma conciliação disponível. Vá para a aba ⚖️ Conciliação para gerar os resultados.")
        st.stop()

    df_export = st.session_state["df_conciliado_atual"]

    st.subheader("📈 Visualização Final")
    st.dataframe(df_export)

    st.subheader("📥 Baixar Resultado em Excel")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="Conciliação", index=False)
        writer.close()

    st.download_button(
        label="📤 Baixar Arquivo Excel",
        data=buffer,
        file_name="resultado_conciliacao.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
