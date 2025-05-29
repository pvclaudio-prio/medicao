
import pdfplumber
import openai
from dotenv import load_dotenv
import os
import streamlit as st
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
import ssl
import urllib3

ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Layout do Streamlit
st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍♂️')

class SSLIgnoreAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super(SSLIgnoreAdapter, self).init_poolmanager(*args, **kwargs)

session = requests.Session()
session.verify = False 
session.mount("https://", SSLIgnoreAdapter())

openai.requestssession = session

# Carrega a chave da API
load_dotenv()
API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = API_KEY

# Função para extrair tabelas do PDF
def extrair_tabelas_pdf(caminho_pdf):
    tabelas_extraidas = []

    with pdfplumber.open(caminho_pdf) as pdf:
        for i, pagina in enumerate(pdf.pages):
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                texto_tabela = "\n".join([
                    "\t".join([str(cell) if cell is not None else "" for cell in row])
                    for row in tabela
                ])
                tabelas_extraidas.append({
                    "pagina": i + 1,
                    "conteudo": texto_tabela
                })

    return tabelas_extraidas

# Função para enviar para o GPT
def enviar_para_gpt(tabela_texto, instrucoes="Analise os dados da tabela:"):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system",
             "content":
                 """Você é um gerente financeiro especializado em dados extraídos de PDFs.

                 #Objetivos

                 Você é responsável por identificar indícios de superfaturamento e medições em duplicidade.

                 Exemplos de medição em duplicidade:
                     Paulo Sergio Gomes Junior: valores duplicados nos registros 26 e 32 (R$ 13.527,50) e nos adicionais 22 e 28 (R$ 7.407,89), totalizando R$ 20.935,39.
                     Adriano Rangel: valores duplicados nos registros 84 e 95 (R$ 8.312,50) e nos adicionais 73 e 84 (R$ 3.562,49), totalizando R$ 11.874,99.
                     Milton Pereira da Silva: valores duplicados nos registros 44 e 47 (R$ 13.527,50) e nos adicionais 39 e 42 (R$ 5.797,48), totalizando R$ 19.324,98.
                     Marcos de Almeida Rangel: valores duplicados nos registros 85 e 94 (R$ 13.527,50) e nos adicionais 74 e 83 (R$ 3.381,86), totalizando R$ 16.909,30.
                     Rafael Ferreira Macedo: valores duplicados nos registros 09 e 110, totalizando R$ 29.400,00.
                     Silverio Silva Santos: valores duplicados nos registros 90 e 93 (R$ 11.025,00) e nos adicionais 79 e 82 (R$ 6.300,00), totalizando R$ 17.325,00.
                 """},
            {"role": "user", "content": f"{instrucoes}\n\n{tabela_texto}"}
        ],
        temperature=0.2
    )
    return response.choices[0].message["content"]

def revisar_resposta_gpt(texto_analisado, instrucoes="Revise o texto abaixo, melhorando a clareza, organização e formato sem alterar o conteúdo técnico."):
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system",
             "content": 
                 """Você é um revisor técnico especializado em documentos financeiros, auditorias de contratos e análises de medições. 
                 Sua tarefa é revisar textos gerados por um agente anterior, ajustando formatação, ortografia e estrutura textual para maior clareza,
                 mantendo o conteúdo técnico e os apontamentos como foram detectados."""},
            {"role": "user", "content": f"{instrucoes}\n\n{texto_analisado}"}
        ],
        temperature=0.1
    )
    return response.choices[0].message["content"]

# Função para extrair preços dos contratos
def extrair_precos_contrato(pdf_file):
    precos = {}

    with pdfplumber.open(pdf_file) as pdf:
        for pagina in pdf.pages:
            tabelas = pagina.extract_tables()
            for tabela in tabelas:
                for row in tabela:
                    if row and len(row) >= 2:
                        funcao = str(row[0]).strip().upper()
                        try:
                            valor = float(str(row[1]).replace("R$", "").replace(".", "").replace(",", "."))
                            precos[funcao] = valor
                        except:
                            continue
    return precos

# Função para validar valores com contrato
def validar_medicao_com_contrato(tabela_medido, precos_contratuais):
    resultados = []

    for row in tabela_medido.split("\n"):
        colunas = row.split("\t")
        if len(colunas) >= 4:
            funcao = colunas[0].strip().upper()
            try:
                qtd = int(colunas[1])
                unit = float(colunas[2].replace(",", "."))
                total = float(colunas[3].replace(",", "."))

                total_calculado = round(qtd * unit, 2)
                contrato_unitario = precos_contratuais.get(funcao)

                inconsistencias = []

                if total_calculado != round(total, 2):
                    inconsistencias.append(f"❗ Total inconsistente: {qtd} x {unit} = {total_calculado}, mas consta {total}")

                if contrato_unitario and contrato_unitario != round(unit, 2):
                    inconsistencias.append(f"❗ Valor unitário difere do contrato: contrato={contrato_unitario}, medido={unit}")

                if inconsistencias:
                    resultados.append(f"🔍 {funcao}\n" + "\n".join(inconsistencias))

            except:
                continue
    return resultados

st.logo("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

# Upload do PDF de medição
arquivo = st.file_uploader("📥 Insira o arquivo de medição (PDF)", type=["pdf"])

# Upload dos contratos
st.markdown("### 📄 Contratos do Fornecedor")
num_contratos = st.number_input("Quantos contratos o fornecedor possui?", min_value=1, max_value=10, step=1)
contratos = []
for i in range(num_contratos):
    contrato = st.file_uploader(f"Contrato {i+1}", type=["pdf"], key=f"contrato_{i}")
    if contrato:
        contratos.append(contrato)

# Botão para iniciar análise
if arquivo and contratos and st.button("Realizar Análise da Medição"):

    with st.spinner("⏳ Extraindo tabelas e realizando análise com o GPT..."):
        tabelas = extrair_tabelas_pdf(arquivo)
        respostas = []
        resumo_inconsistencias = []

        # Unificar as tabelas de preço dos contratos
        tabela_precos_global = {}
        for contrato in contratos:
            precos = extrair_precos_contrato(contrato)
            tabela_precos_global.update(precos)

        # Análise por tabela de medição
        for tabela in tabelas:
            resposta_raw = enviar_para_gpt(tabela["conteudo"])
            resposta = revisar_resposta_gpt(resposta_raw)
            inconsistencias = validar_medicao_com_contrato(tabela["conteudo"], tabela_precos_global)


            bloco = f"📄 **Página {tabela['pagina']}**\n\n{resposta}"
            if inconsistencias:
                bloco += "\n\n### 🚨 Inconsistências Detectadas\n" + "\n".join(inconsistencias)
                resumo_inconsistencias.extend([
                    f"📄 Página {tabela['pagina']} - {item}" for item in inconsistencias
                ])
            respostas.append(bloco)

        resultado_final = "\n\n---\n\n".join(respostas)

        if resumo_inconsistencias:
            sumario = "\n".join(resumo_inconsistencias)
            resultado_final += "\n\n---\n\n## 📌 **Sumário Final de Inconsistências**\n\n" + sumario
        else:
            resultado_final += "\n\n---\n\n✅ Nenhuma inconsistência detectada entre a medição e os contratos."

    # Mostrar com animação de escrita
    def stream_data():
        for word in resultado_final.split(" "):
            yield word + " "
            time.sleep(0.01)

    st.markdown("### 🧠 Resultado da Análise")
    st.write_stream(stream_data)
