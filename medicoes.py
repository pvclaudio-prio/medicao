from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st
import fitz
import pandas as pd
import openai
from io import StringIO
from collections import defaultdict
import json

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️')
st.logo("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

openai.api_key = st.secrets["openai"]["OPENAI_API_KEY"]

def gerar_credenciais():
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

def extrair_paginas_pdf(file, pagina_inicio, pagina_fim):
    doc_original = fitz.open(stream=file.read(), filetype="pdf")
    pdf_temp = fitz.open()
    for i in range(pagina_inicio - 1, pagina_fim):
        pdf_temp.insert_pdf(doc_original, from_page=i, to_page=i)
    temp_bytes = pdf_temp.write()
    return temp_bytes

def organizar_tabela_com_gpt(documento_nome: str, df: pd.DataFrame) -> pd.DataFrame:
    tabela_json = df.fillna("").to_dict(orient="records")

    prompt = f"""
Você é um especialista em auditoria de documentos técnicos. Abaixo está uma tabela extraída de um PDF.

Tarefa:
1. Classifique a tabela como:
   - Boletim de Medição Padrão
   - Boletim de Medição - Adicionais
   - Tabela de Contrato

2. Padronize e retorne o conteúdo como uma lista JSON com colunas claras e uniformes conforme os padrões:
   - Boletim padrão: FUNÇÃO, NOME, CATEGORIA, PERÍODO, QUANTIDADE, VALOR UNITÁRIO, TOTAL
   - Adicionais: FUNÇÃO, NOME, HORAS, VALOR/HORA, DOBRA, TOTAL
   - Contrato: ITEM, FUNÇÃO, FORMATO, QUANTIDADE, VALOR DA DIÁRIA

```json
{json.dumps(tabela_json, indent=2, ensure_ascii=False)}
```
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Você é um assistente que organiza tabelas extraídas de documentos."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
    
        json_content = response.choices[0].message["content"]
    
        # Extrair somente a parte JSON da resposta
        json_inicio = json_content.find("[")
        json_fim = json_content.rfind("]") + 1
        json_puro = json_content[json_inicio:json_fim]
    
        return pd.DataFrame(json.loads(json_puro))
    
    except Exception as e:
        st.warning(f"⚠️ GPT retornou uma resposta que não pôde ser convertida em DataFrame: {e}")
        return df

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

# Escolha do tipo de processor
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
st.header("📁 Upload de Arquivos")
arquivos_boletim = st.file_uploader("📄 Boletins de Medição", type=["pdf"], accept_multiple_files=True)
arquivos_contrato = st.file_uploader("📄 Contratos de Serviço", type=["pdf"], accept_multiple_files=True)

intervalos_boletim = {}
intervalos_contrato = {}

if arquivos_boletim:
    st.subheader("Intervalos de Páginas - Boletins")
    for arquivo in arquivos_boletim:
        col1, col2 = st.columns(2)
        with col1:
            inicio = st.number_input(f"Página inicial ({arquivo.name})", min_value=1, value=1, key=f"inicio_b_{arquivo.name}")
        with col2:
            fim = st.number_input(f"Página final ({arquivo.name})", min_value=inicio, value=inicio, key=f"fim_b_{arquivo.name}")
        intervalos_boletim[arquivo.name] = (inicio, fim)

if arquivos_contrato:
    st.subheader("Intervalos de Páginas - Contratos")
    for arquivo in arquivos_contrato:
        col1, col2 = st.columns(2)
        with col1:
            inicio = st.number_input(f"Página inicial ({arquivo.name})", min_value=1, value=1, key=f"inicio_c_{arquivo.name}")
        with col2:
            fim = st.number_input(f"Página final ({arquivo.name})", min_value=inicio, value=inicio, key=f"fim_c_{arquivo.name}")
        intervalos_contrato[arquivo.name] = (inicio, fim)

if st.button("🚀 Processar Documentos"):
    st.subheader("🔎 Extração de Tabelas")
    tabelas_final = []

    if arquivos_boletim:
        for arquivo in arquivos_boletim:
            with st.spinner(f"Processando {arquivo.name}..."):
                inicio, fim = intervalos_boletim[arquivo.name]
                pdf_bytes = extrair_paginas_pdf(arquivo, inicio, fim)
                tabelas = processar_documento_documentai(pdf_bytes, processor_id, arquivo.name)
                tabelas_final.extend(tabelas)

    if arquivos_contrato:
        for arquivo in arquivos_contrato:
            with st.spinner(f"Processando {arquivo.name}..."):
                inicio, fim = intervalos_contrato[arquivo.name]
                pdf_bytes = extrair_paginas_pdf(arquivo, inicio, fim)
                tabelas = processar_documento_documentai(pdf_bytes, processor_id, arquivo.name)
                tabelas_final.extend(tabelas)

    st.success("✅ Processamento concluído!")

    documentos_agrupados = defaultdict(list)
    for tabela_info in tabelas_final:
        df_raw = pd.DataFrame(tabela_info["tabela"])
        df_tratado = organizar_tabela_com_gpt(tabela_info["documento"], df_raw)
        documentos_agrupados[tabela_info['documento']].append(df_tratado)

    for nome_doc, lista_df in documentos_agrupados.items():
        try:
            df_unificado = pd.concat(lista_df, ignore_index=True)
            st.markdown(f"### 📄 Documento: <span style='color:green'><b>{nome_doc}</b></span>", unsafe_allow_html=True)
            st.dataframe(df_unificado)
        except Exception as e:
            st.warning(f"⚠️ Não foi possível unificar tabelas do documento `{nome_doc}`: {e}")
