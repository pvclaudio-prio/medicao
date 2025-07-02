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
from PIL import Image
import pytesseract
import re

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
    campos = defaultdict(list)

    for entity in doc.entities:
        field_name = entity.type_.lower()
        value = entity.mention_text.strip() if entity.mention_text else ""
        campos[field_name].append(value)

    if not campos:
        st.warning(f"⚠️ Nenhum campo encontrado para o documento: {nome_doc}")
        return []

    # Conversão para DataFrame estruturado por linha
    df = pd.DataFrame.from_dict(campos, orient="index").transpose()
    return [{"documento": nome_doc, "tabela": df}]
    
def estruturar_boletim_conciliado(df_boletim_raw: pd.DataFrame, df_contrato: pd.DataFrame) -> pd.DataFrame:
    df_boletim = df_boletim_raw.copy()
    df_contrato = df_contrato.copy()

    # 🔹 Remover registros irrelevantes do boletim
    df_boletim = df_boletim[~df_boletim["descricao"].str.upper().str.strip().eq("DIÁRIA (EQUIPAMENTO)")]

    # 🔹 Criar chave de conciliação (descricao + unidade), padronizado em caixa alta e removendo espaços
    df_boletim["chave_conciliacao"] = (
        df_boletim["descricao"].str.strip().str.upper() + " - " + df_boletim["unidade"].str.strip().str.upper()
    )
    df_contrato["chave_conciliacao"] = (
        df_contrato["descricao_completa"].str.strip().str.upper() + " - " + df_contrato["unidade"].str.strip().str.upper()
    )

    # 🔹 Merge entre boletim e contrato pela chave
    df_merged = df_boletim.merge(
        df_contrato,
        on="chave_conciliacao",
        how="left",
        suffixes=('', '_contrato')
    )

    # 🔹 Conversão segura para float
    colunas_float = [
        'qtd_standby', 'qtd_operacional', 'qtd_dobra',
        'valor_unitario_standby', 'valor_unitario_operacional', 'valor_unitario_dobra',
        'total_standby', 'total_operacional', 'total_dobra', 'total_cobrado',
        'valor_unitario', 'valor_standby'
    ]
    for col in colunas_float:
        if col in df_merged.columns:
            df_merged[col] = pd.to_numeric(df_merged[col], errors="coerce")

    # 🔹 Cálculo do total recalculado
    df_merged["total_recalculado"] = (
        (df_merged["qtd_standby"].fillna(0) * df_merged["valor_unitario_standby"].fillna(0)) +
        (df_merged["qtd_operacional"].fillna(0) * df_merged["valor_unitario_operacional"].fillna(0)) +
        (df_merged["qtd_dobra"].fillna(0) * df_merged["valor_unitario_dobra"].fillna(0))
    )

    # 🔹 Flags de divergência
    df_merged["flag_valor_divergente"] = (
        (np.round(df_merged["valor_unitario_standby"], 2) != np.round(df_merged["valor_standby"], 2)) |
        (np.round(df_merged["valor_unitario_operacional"], 2) != np.round(df_merged["valor_unitario"], 2))
    ).map({True: "Sim", False: "Não"})

    df_merged["dif_total"] = abs((df_merged["total_recalculado"] - df_merged["total_cobrado"]).fillna(0))
    df_merged["flag_total_recalculado_diferente"] = (df_merged["dif_total"] > 1).map({True: "Sim", False: "Não"})

    df_merged["flag_descricao_duplicada"] = df_merged.duplicated(subset=["descricao_completa"], keep=False).map({True: "Sim", False: "Não"})

    # 🔹 Seleção de colunas finais
    colunas_finais = [
        'descricao', 'descricao_completa', 'unidade',
        'qtd_standby', 'qtd_operacional', 'qtd_dobra', 'qtd_total',
        'valor_unitario_standby', 'valor_standby',
        'valor_unitario_operacional', 'valor_unitario',
        'total_standby', 'total_operacional', 'total_dobra',
        'total_cobrado', 'total_recalculado',
        'flag_valor_divergente', 'flag_total_recalculado_diferente', 'flag_descricao_duplicada'
    ]
    colunas_existentes = [col for col in colunas_finais if col in df_merged.columns]

    return df_merged[colunas_existentes]

def organizar_tabela_com_gpt(nome_doc, df_raw):
    try:
        import openai
        openai.api_key = st.secrets["openai"]["OPENAI_API_KEY"]

        tabela_texto = df_raw.to_csv(index=False, sep=";")

        prompt = f"""
Você é um assistente especialista em estruturação de boletins de medição. Abaixo está uma tabela extraída de OCR. Organize os dados no formato JSON com colunas padronizadas como:

["ITEM_DESCRICAO", "DESCRICAO_COMPLETA", "UNIDADE", "QTD_STANDBY", "QTD_OPERACIONAL", "QTD_DOBRA", "QTD_TOTAL", "VALOR_UNITARIO_STANDBY", "VALOR_UNITARIO_OPERACIONAL", "VALOR_UNITARIO_DOBRA", "TOTAL_STANDBY", "TOTAL_OPERACIONAL", "TOTAL_DOBRA", "TOTAL_COBRADO"]

Se algum campo não existir, preencha com 0 ou string vazia.

Documento: {nome_doc}
Tabela extraída:
{tabela_texto}
"""

        resposta = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4000
        )

        conteudo = resposta.choices[0].message["content"].strip()

        if not conteudo.startswith("[") and not conteudo.startswith("{"):
            st.error(f"⚠️ Resposta inesperada da OpenAI para `{nome_doc}`:\n\n{conteudo}")
            return df_raw

        dados = json.loads(conteudo)
        df_tratado = pd.DataFrame(dados)
        return df_tratado

    except json.JSONDecodeError as e:
        st.error(f"Erro ao decodificar JSON da resposta do GPT para `{nome_doc}`: {e}")
        return df_raw
    except Exception as e:
        st.error(f"Erro ao organizar tabela com GPT para o documento `{nome_doc}`: {e}")
        return df_raw

def limpar_moeda(valor):
    if pd.isna(valor):
        return None
    valor = str(valor).upper()
    valor = re.sub(r"[^\d,\.]", "", valor)  # remove letras e símbolos
    valor = valor.replace(",", ".")

    # Se houver mais de um ponto, assume que o último é o separador decimal
    partes = valor.split(".")
    if len(partes) > 2:
        valor = "".join(partes[:-1]) + "." + partes[-1]

    try:
        return float(valor)
    except:
        return None
        
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
    tipo_processor = st.selectbox("🤖 Tipo de Processor do Document AI", options=["Form Parser", "Document OCR", "Custom Extractor"])
    PROCESSOR_IDS = {
        "Form Parser": st.secrets["google"].get("form_parser_id"),
        "Document OCR": st.secrets["google"].get("contract_processor"),
        "Custom Extractor": "1dc31710a97ca033",
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

    if "tabelas_extraidas" not in st.session_state:
        st.warning("⚠️ Nenhuma tabela foi processada ainda. Vá para '📄 Upload de Documentos' e clique em 'Processar Documentos'.")
        st.stop()

    tabelas_extraidas = st.session_state["tabelas_extraidas"]
    tabelas_tratadas = {}

    for tabela_info in tabelas_extraidas:
        nome_doc = tabela_info["documento"]
        df_raw = tabela_info["tabela"]

        # Verificação básica
        if not isinstance(df_raw, pd.DataFrame):
            st.warning(f"⚠️ O conteúdo extraído do documento `{nome_doc}` não é um DataFrame.")
            continue

        if df_raw.empty:
            st.warning(f"⚠️ Tabela vazia no documento `{nome_doc}`.")
            continue

        # Padronização e verificação de colunas
        colunas_padrao = [
            'descricao', 'descricao_completa', 'unidade',
            'qtd_standby', 'qtd_operacional', 'qtd_dobra', 'qtd_total',
            'valor_unitario_standby', 'valor_unitario_operacional', 'valor_unitario_dobra',
            'total_standby', 'total_operacional', 'total_dobra',
            'total_cobrado'
        ]
        df_raw.columns = [col.lower().strip() for col in df_raw.columns]

        for col in colunas_padrao:
            if col not in df_raw.columns:
                df_raw[col] = None

        df_final = df_raw[colunas_padrao]

        # Limpeza dos campos monetários
        colunas_monetarias = [
            'valor_unitario_standby',
            'valor_unitario_operacional',
            'valor_unitario_dobra',
            'total_standby',
            'total_operacional',
            'total_dobra',
            'total_cobrado'
        ]

        for col in colunas_monetarias:
            if col in df_final.columns:
                try:
                    df_final[col] = df_final[col].apply(limpar_moeda)
                except Exception as e:
                    st.warning(f"Erro ao limpar coluna {col}: {e}")
     
        if nome_doc not in tabelas_tratadas:
            tabelas_tratadas[nome_doc] = []
        
        tabelas_tratadas[nome_doc].append(df_final)

    # Salva no session state para conciliação posterior
    st.session_state["tabelas_tratadas"] = tabelas_tratadas

    # Exibição
    for nome_doc, lista_df in tabelas_tratadas.items():
        try:
            df_unificado = pd.concat(lista_df, ignore_index=True)
            st.markdown(f"### 📄 Documento: <span style='color:green'><b>{nome_doc}</b></span>", unsafe_allow_html=True)
            st.dataframe(df_unificado)
        except Exception as e:
            st.warning(f"⚠️ Erro ao exibir tabelas de `{nome_doc}`: {e}")

if pagina == "⚖️ Conciliação":
    st.header("⚖️ Conciliação entre Boletins e Contrato")

    df_contrato = pd.DataFrame([
        {"ID_ITEM": "1.1", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "DIÁRIA DE OPERADOR TÉCNICO", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 1672.00, "VALOR_STANDBY": 1337.60},
        {"ID_ITEM": "1.2", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "DIÁRIA DE SUPERVISOR", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 1995.00, "VALOR_STANDBY": 1596.00},
        {"ID_ITEM": "2.1", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "DIÁRIA (EQUIPAMENTO)", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 475.00, "VALOR_STANDBY": 403.75},
        {"ID_ITEM": "2.2", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "DIÁRIA (EQUIPAMENTO)", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 807.50, "VALOR_STANDBY": 686.38},
        {"ID_ITEM": "2.3", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "DIÁRIA (EQUIPAMENTO)", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 1795.50, "VALOR_STANDBY": 1526.18},
        {"ID_ITEM": "3.1", "REFERENCIA": "MOB/DESMOB", "DESCRICAO": "MOBILIZAÇÃO", "UNIDADE": "EVENTO", "VALOR_UNITARIO": 1850.00, "VALOR_STANDBY": 1850.00},
        {"ID_ITEM": "3.2", "REFERENCIA": "MOB/DESMOB", "DESCRICAO": "MOBILIZAÇÃO DE EQUIPAMENTO", "UNIDADE": "EVENTO", "VALOR_UNITARIO": 3350.00, "VALOR_STANDBY": 3350.00},
    ])

    df_contrato = df_contrato.rename(columns={
        "REFERENCIA": "descricao",
        "DESCRICAO": "descricao_completa",
        "UNIDADE": "unidade",
        "QTD_STANDBY": "qtd_standby",
        "QTD_OPERACIONAL": "qtd_operacional",
        "QTD_DOBRA": "qtd_dobra",
        "QTD_TOTAL": "qtd_total",
        "VALOR_STANDBY": "valor_standby",
        "VALOR_UNITARIO": "valor_unitario",
        "VALOR_UNITARIO_DOBRA": "valor_unitario_dobra",
        "TOTAL_STANDBY": "total_standby",
        "TOTAL_OPERACIONAL": "total_operacional",
        "TOTAL_DOBRA": "total_dobra",
        "TOTAL_COBRADO": "total_cobrado"
    })
    
    st.session_state["df_contrato"] = df_contrato

    if "tabelas_tratadas" not in st.session_state or "df_contrato" not in st.session_state:
        st.warning("⚠️ Dados não disponíveis. Vá para as abas anteriores e processe os documentos.")
        st.stop()

    tabelas_tratadas = st.session_state["tabelas_tratadas"]
    df_contrato = st.session_state["df_contrato"]
    nomes_docs = list(tabelas_tratadas.keys())

    if not nomes_docs:
        st.info("Nenhum documento tratado disponível.")
        st.stop()

    doc_selecionado = st.selectbox("📄 Selecione o documento para conciliação:", nomes_docs)

    try:
        df_boletim = pd.concat(tabelas_tratadas[doc_selecionado], ignore_index=True)
        df_conciliado = estruturar_boletim_conciliado(df_boletim, df_contrato)

        st.subheader(f"📋 Resultado da Conciliação: {doc_selecionado}")
        st.dataframe(df_conciliado)

        if st.checkbox("🔍 Mostrar apenas divergências"):
            df_filtrado = df_conciliado[
                (df_conciliado["flag_valor_divergente"] == "Sim") |
                (df_conciliado["flag_total_recalculado_diferente"] == "Sim") |
                (df_conciliado["flag_descricao_duplicada"] == "Sim")
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

    nome_arquivo = st.text_input("📂 Nome do arquivo Excel", value="resultado_conciliacao.xlsx")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, sheet_name="Conciliação", index=False)
        writer.close()

    st.download_button(
        label="📤 Baixar Arquivo Excel",
        data=buffer.getvalue(),
        file_name=nome_arquivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

