from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import streamlit as st
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
            header = list(table.header_rows) if table.header_rows else []
            body = list(table.body_rows) if table.body_rows else []
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

def gerar_prompt_conciliacao_openai(df_boletim, df_contrato):
    boletim_texto = df_boletim.to_string(index=False)
    contrato_texto = df_contrato.to_string(index=False)

    prompt = f"""
Você é um auditor financeiro especialista em contratos de prestação de serviço.

Compare as duas tabelas abaixo e aponte inconsistências como:
- Valor unitário diferente do contrato
- Total incorreto (quantidade × valor unitário)
- Cobranças não previstas no contrato
- Possíveis duplicidades

# Tabela contratual:
{contrato_texto}

# Boletim de medição:
{boletim_texto}

Retorne uma análise clara e objetiva com recomendações.
"""

    return prompt

st.subheader("📤 Envio de Documentos")
arquivo_boletim = st.file_uploader("📄 Envie o Boletim de Medição (PDF)", type=["pdf"], key="boletim")
arquivo_contrato = st.file_uploader("📑 Envie o Contrato (PDF)", type=["pdf"], key="contrato")

df_boletim = None
df_contrato = None

# ID do processor
processor_id = st.secrets["google"]["form_parser_id"]

if arquivo_boletim:
    tabelas_boletim = processar_documento_documentai(arquivo_boletim, processor_id)
    if tabelas_boletim and len(tabelas_boletim[0]) > 1:
        colunas = tabelas_boletim[0][0]
        linhas = tabelas_boletim[0][1:]
        df_boletim = pd.DataFrame(linhas, columns=colunas)
        st.subheader("📊 Boletim de Medição")
        st.dataframe(df_boletim)

if arquivo_contrato:
    tabelas_contrato = processar_documento_documentai(arquivo_contrato, processor_id)
    if tabelas_contrato and len(tabelas_contrato[0]) > 1:
        colunas = tabelas_contrato[0][0]
        linhas = tabelas_contrato[0][1:]
        df_contrato = pd.DataFrame(linhas, columns=colunas)
        st.subheader("📋 Tabela do Contrato")
        st.dataframe(df_contrato)

if df_boletim is not None and df_contrato is not None:
    if st.button("🔍 Analisar Conciliação com GPT-4o"):
        with st.spinner("Consultando GPT-4o..."):
            prompt = gerar_prompt_conciliacao_openai(df_boletim, df_contrato)
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
else:
    st.info("Por favor, envie **ambos os documentos** para realizar a análise.")
