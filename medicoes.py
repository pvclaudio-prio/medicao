from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st
import json

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍')
st.logo("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

st.write("🧪 Chave antes do replace:", repr(st.secrets["google"]["private_key"]))

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

def processar_documento_documentai(file, processor_id):
    credentials = gerar_credenciais()
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)

    name = f"projects/{st.secrets['google']['project_id']}/locations/{st.secrets['google']['location']}/processors/{processor_id}"

    document = {"content": file.read(), "mime_type": "application/pdf"}
    request = {"name": name, "raw_document": document}

    result = client.process_document(request=request)
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
            tabelas.append(linhas)
    return tabelas

# Upload do PDF e chamada da função
arquivo = st.file_uploader("Envie o contrato ou boletim PDF", type=["pdf"])
if arquivo:
    tabelas = processar_documento_documentai(arquivo, st.secrets["google"]["contract_processor"])
    st.write(tabelas)

try:
    result = client.process_document(request=request)
except Exception as e:
    st.error(f"Erro ao processar documento: {e}")
    st.stop()
