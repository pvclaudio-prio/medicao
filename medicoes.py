import streamlit as st
import pandas as pd
import numpy as np
import fitz  # PyMuPDF
import openai
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import json
from collections import defaultdict
import io

st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

def gerar_credenciais():
    try:
        private_key = st.secrets["google"]["private_key"].replace("\\n", "\n")
        info = {
            "type": st.secrets["google"]["type"],
            "project_id": st.secrets["google"]["project_id"],
            "private_key_id": st.secrets["google"]["private_key_id"],
            "private_key": private_key,
            "client_email": st.secrets["google"]["client_email"],
            "client_id": st.secrets["google"]["client_id"],
            "auth_uri": st.secrets["google"]["auth_uri"],
            "token_uri": st.secrets["google"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["google"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["google"]["client_x509_cert_url"],
            "universe_domain": st.secrets["google"]["universe_domain"]
        }
        return service_account.Credentials.from_service_account_info(info)
    except Exception as e:
        st.error(f"Erro ao gerar credenciais: {e}")
        st.stop()
        
def extrair_paginas_pdf(file_bytes, pagina_inicio, pagina_fim):
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc_original:
            num_paginas = len(doc_original)
            pdf_temp = fitz.open()
            for i in range(pagina_inicio - 1, min(pagina_fim, num_paginas)):
                pdf_temp.insert_pdf(doc_original, from_page=i, to_page=i)
            temp_bytes = pdf_temp.write()
            pdf_temp.close()
        return temp_bytes
    except Exception as e:
        st.error(f"Erro ao extrair páginas do PDF: {e}")
        return None

def processar_documento_documentai(pdf_bytes, processor_id, nome_doc):
    credentials = gerar_credenciais()
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)
    name = f"projects/{st.secrets['google']['project_id']}/locations/{st.secrets['google']['location']}/processors/{processor_id}"
    document = {"content": pdf_bytes, "mime_type": "application/pdf"}
    request = {"name": name, "raw_document": document}
    
    try:
        result = client.process_document(request=request)
    except Exception as e:
        st.error(f"❌ Erro ao processar documento '{nome_doc}':\n\n{e}")
        return []

    doc = result.document
    tabelas = []

    for page in doc.pages:
        for table in getattr(page, "tables", []):
            linhas = []
            header = getattr(table, "header_rows", [])
            body = getattr(table, "body_rows", [])
            for row in list(header) + list(body):
                linha = []
                for cell in row.cells:
                    if cell.layout.text_anchor.text_segments:
                        start = cell.layout.text_anchor.text_segments[0].start_index
                        end = cell.layout.text_anchor.text_segments[0].end_index
                        texto = doc.text[start:end].strip()
                        linha.append(texto)
                if linha:
                    linhas.append(linha)
            if linhas:
                tabelas.append({"documento": nome_doc, "tabela": linhas})

    return tabelas
    
def estruturar_boletim_conciliado(df_boletim_raw: pd.DataFrame, df_contrato: pd.DataFrame) -> pd.DataFrame:
    df_boletim = df_boletim_raw.copy()
    df_boletim['ITEM_DESCRICAO'] = df_boletim['ITEM_DESCRICAO'].str.upper().str.strip()
    df_contrato['DESCRICAO'] = df_contrato['DESCRICAO'].str.upper().str.strip()

    df_merged = df_boletim.merge(
        df_contrato,
        left_on="ITEM_DESCRICAO",
        right_on="DESCRICAO",
        how="left",
        suffixes=('', '_CONTRATO')
    )

    # Calcular totais por linha
    def calcular_total(row):
        return (
            (row.get('QTD_STANDBY', 0) or 0) * (row.get('VALOR_UNITARIO_STANDBY', 0) or 0) +
            (row.get('QTD_OPERACIONAL', 0) or 0) * (row.get('VALOR_UNITARIO_OPERACIONAL', 0) or 0) +
            (row.get('QTD_DOBRA', 0) or 0) * (row.get('VALOR_UNITARIO_DOBRA', 0) or 0)
        )

    df_merged['TOTAL_RECALCULADO'] = df_merged.apply(calcular_total, axis=1)

    # Flag de valores unitários divergentes
    df_merged['FLAG_VALOR_DIVERGENTE'] = (
        (np.round(df_merged['VALOR_UNITARIO_STANDBY'], 2) != np.round(df_merged['VALOR_STANDBY'], 2)) |
        (np.round(df_merged['VALOR_UNITARIO_OPERACIONAL'], 2) != np.round(df_merged['VALOR_UNITARIO'], 2))
    ).map({True: 'Sim', False: 'Não'})

    # Flag de total recalculado diferente
    df_merged['DIF_TOTAL'] = abs(df_merged['TOTAL_RECALCULADO'] - df_merged.get('TOTAL_COBRADO', 0))
    df_merged['FLAG_TOTAL_RECALCULADO_DIFERENTE'] = (df_merged['DIF_TOTAL'] > 1.0).map({True: 'Sim', False: 'Não'})

    # Flag de duplicidade de descrição
    df_merged['FLAG_DESCRICAO_DUPLICADA'] = df_merged.duplicated(subset=['DESCRICAO_COMPLETA'], keep=False).map({True: 'Sim', False: 'Não'})

    # Seleção de colunas finais (proteção se não existir)
    colunas_finais = [col for col in [
        'ITEM_DESCRICAO', 'DESCRICAO_COMPLETA', 'UNIDADE',
        'QTD_STANDBY', 'QTD_OPERACIONAL', 'QTD_DOBRA', 'QTD_TOTAL',
        'VALOR_UNITARIO_STANDBY', 'VALOR_STANDBY',
        'VALOR_UNITARIO_OPERACIONAL', 'VALOR_UNITARIO',
        'TOTAL_STANDBY', 'TOTAL_OPERACIONAL', 'TOTAL_DOBRA', 'TOTAL_COBRADO', 'TOTAL_RECALCULADO',
        'FLAG_VALOR_DIVERGENTE', 'FLAG_TOTAL_RECALCULADO_DIFERENTE', 'FLAG_DESCRICAO_DUPLICADA'
    ] if col in df_merged.columns]

    return df_merged[colunas_finais]

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
                try:
                    file_bytes = arquivo.read()
                    pdf_bytes = extrair_paginas_pdf(file_bytes, inicio, fim)
    
                    if pdf_bytes:
                        tabelas = processar_documento_documentai(pdf_bytes, processor_id, nome_doc)
                        tabelas_final.extend(tabelas)
                    else:
                        st.warning(f"⚠️ Não foi possível extrair as páginas de `{nome_doc}`.")
                except Exception as e:
                    st.error(f"❌ Falha ao processar `{nome_doc}`: {e}")
    
        if tabelas_final:
            st.success("✅ Processamento concluído!")
            st.session_state["tabelas_extraidas"] = tabelas_final
        else:
            st.warning("⚠️ Nenhuma tabela extraída com sucesso.")

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
