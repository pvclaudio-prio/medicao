import os
import time
import pdfplumber
import streamlit as st
import google.generativeai as genai

st.set_page_config(layout='wide')
st.title('Análise dos Boletins de Medição 🕵️‍')
st.logo("logo-alura.png")

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-pro")

def agente_validador(tabela_medicao, precos_contrato):
    prompt = f"""
Você é um gerente financeiro especializado em auditorias de contratos.

# Objetivo
Analise os dados da medição extraídos de um PDF e compare com a base contratual fornecida. Aponte quaisquer divergências, como:
- Valores unitários diferentes do contrato
- Totais incorretos (quantidade x valor unitário)
- Possíveis duplicidades ou superfaturamentos

# Tabela de Preços Contratuais
{precos_contrato}

# Tabela de Medição
{tabela_medicao}
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro ao consultar o agente validador: {e}"

def agente_revisor(resposta_validador, tabela_medicao, precos_contrato):
    prompt = f"""
Você é um revisor técnico em auditoria de contratos. Sua tarefa é revisar a análise abaixo feita por um outro agente. 
Confira se a resposta está coerente com a tabela de medição e a base contratual fornecida. Corrija imprecisões, adicione detalhes se necessário 
e assegure a clareza e precisão antes do envio ao usuário final.

# Resposta do agente validador
{resposta_validador}

# Tabela de Medição
{tabela_medicao}

# Tabela de Preços Contratuais
{precos_contrato}
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro ao consultar o agente revisor: {e}"

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
                tabelas_extraidas.append({"pagina": i + 1, "conteudo": texto_tabela})
    return tabelas_extraidas

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

arquivo = st.file_uploader("📥 Insira o arquivo de medição (PDF)", type=["pdf"])
st.markdown("### 📄 Contratos do Fornecedor")
num_contratos = st.number_input("Quantos contratos o fornecedor possui?", min_value=1, max_value=10, step=1)
contratos = []
for i in range(num_contratos):
    contrato = st.file_uploader(f"Contrato {i+1}", type=["pdf"], key=f"contrato_{i}")
    if contrato:
        contratos.append(contrato)

if arquivo and contratos and st.button("Realizar Análise da Medição"):
    with st.spinner("⏳ Extraindo tabelas e realizando análise com os agentes Gemini..."):
        tabelas = extrair_tabelas_pdf(arquivo)
        respostas = []

        tabela_precos_global = {}
        for contrato in contratos:
            precos = extrair_precos_contrato(contrato)
            tabela_precos_global.update(precos)

        precos_texto = "\n".join([f"{k}: R$ {v:.2f}" for k, v in tabela_precos_global.items()])

        for tabela in tabelas:
            raw = agente_validador(tabela["conteudo"], precos_texto)
            resposta = agente_revisor(raw, tabela["conteudo"], precos_texto)
            bloco = f"📄 **Página {tabela['pagina']}**\n\n{resposta}"
            respostas.append(bloco)

        resultado_final = "\n\n---\n\n".join(respostas)

    def stream_data():
        for word in resultado_final.split(" "):
            yield word + " "
            time.sleep(0.01)

    st.markdown("### 🧠 Resultado da Análise")
    st.write_stream(stream_data)
