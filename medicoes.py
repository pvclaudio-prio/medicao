from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍')
st.logo("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

def processar_documento_documentai(file, processor_id, tipo="boletim"):
    # Carrega configurações
    project_id = st.secrets["google"]["project_id"]
    location = st.secrets["google"]["location"]
    credentials_path = st.secrets["google"]["credentials_path"]

    # Cria cliente autenticado
    creds = service_account.Credentials.from_service_account_file(credentials_path)
    client = documentai.DocumentProcessorServiceClient(credentials=creds)

    # Monta o nome do processador
    name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    # Lê o conteúdo do arquivo enviado pelo usuário (Streamlit file_uploader)
    document = {
        "content": file.read(),
        "mime_type": "application/pdf"
    }

    # Envia o documento para processamento
    request = {
        "name": name,
        "raw_document": document
    }
    result = client.process_document(request=request)
    doc = result.document

    # Extrair as tabelas OCR
    tabelas_extraidas = []
    for page in doc.pages:
        for table in page.tables:
            linhas = []
            for row in table.header_rows + table.body_rows:
                celulas = []
                for cell in row.cells:
                    segmentos = cell.layout.text_anchor.text_segments
                    if segmentos:
                        start = int(segmentos[0].start_index)
                        end = int(segmentos[0].end_index)
                        texto = doc.text[start:end].strip()
                        celulas.append(texto)
                    else:
                        celulas.append("")
                linhas.append(celulas)
            tabelas_extraidas.append(linhas)

    return tabelas_extraidas

arquivo = st.file_uploader("Envie o contrato ou boletim PDF", type=["pdf"])
if arquivo:
    tabelas = processar_documento_documentai(arquivo, st.secrets["google"]["contract_processor"])
    st.write(tabelas)

