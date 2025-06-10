from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍')
st.logo("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

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

    try:
        result = client.process_document(request=request)
    except Exception as e:
        st.error(f"❌ Erro ao processar documento:\n\n{e}")
        st.stop()

    doc = result.document
    tabelas = []

    for page in doc.pages:
        for table in page.tables:
            linhas = []
            header = table.header_rows or []
            body = table.body_rows or []
            for row in header + body:
                linha = []
                for cell in row.cells:
                    segmentos = cell.layout.text_anchor.text_segments
                    if segmentos:
                        start = int(segmentos[0].start_index or 0)
                        end = int(segmentos[0].end_index or 0)
                        texto = doc.text[start:end].strip()
                        linha.append(texto)
                    else:
                        linha.append("")
                linhas.append(linha)
            tabelas.append(linhas)

    return tabelas

# Escolha do tipo de documento
tipo = st.radio("Tipo de documento", ["Boletim de Medição", "Contrato"])

# Seleção do processor
if tipo == "Boletim de Medição":
    processor_id = st.secrets["google"]["form_parser_id"]
else:
    processor_id = st.secrets["google"]["contract_processor"]

# Upload e chamada
arquivo = st.file_uploader("Envie o contrato ou boletim PDF", type=["pdf"])
if arquivo:
    tabelas = processar_documento_documentai(arquivo, processor_id)
    st.write(tabelas)
