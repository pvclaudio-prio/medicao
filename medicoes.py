from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st
import fitz
import tempfile
import io
import pandas as pd
import openai

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍')
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
        for table in page.tables:
            linhas = []
            for row in table.header_rows + table.body_rows:
                linha = []
                for cell in row.cells:
                    if cell.layout.text_anchor.text_segments:
                        start = cell.layout.text_anchor.text_segments[0].start_index
                        end = cell.layout.text_anchor.text_segments[0].end_index
                        texto = doc.text[start:end].strip()
                        linha.append(texto)
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

# Uploads
st.header("📁 Upload de Arquivos")
arquivos_boletim = st.file_uploader("📤 Boletins de Medição", type=["pdf"], accept_multiple_files=True)
arquivos_contrato = st.file_uploader("📤 Contratos de Serviço", type=["pdf"], accept_multiple_files=True)

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
    processor_id = PROCESSOR_IDS.get(processor_type)
    if not processor_id:
        st.error(f"Nenhum processor configurado para o tipo selecionado: {processor_type}")
        st.stop()
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

    for tabela_info in tabelas_final:
        st.markdown(f"#### 📄 Documento: `{tabela_info['documento']}`")
        df = pd.DataFrame(tabela_info["tabela"])
        st.dataframe(df)

    if tabelas_final:
        if st.button("🔍 Analisar Conciliação com GPT-4o"):
            with st.spinner("Consultando GPT-4o..."):
                textos_para_analise = ""
                for t in tabelas_final:
                    df = pd.DataFrame(t["tabela"])
                    textos_para_analise += f"Documento: {t['documento']}\n"
                    textos_para_analise += df.to_csv(index=False)
                    textos_para_analise += "\n"

                prompt = f"""
Você é um auditor especializado em contratos de prestação de serviço.
A seguir estão dados extraídos de contratos e boletins de medição.
Analise os dados, identifique possíveis inconsistências e aponte observações relevantes.

{textos_para_analise}
"""
                try:
                    response = openai.ChatCompletion.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Você é um auditor de contratos de serviços."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2,
                        max_tokens=1500,
                    )
                    resultado = response["choices"][0]["message"]["content"]
                    st.markdown("### 💬 Resultado da Conciliação")
                    st.markdown(resultado)
                except Exception as e:
                    st.error(f"Erro ao consultar GPT-4o: {e}")
