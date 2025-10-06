import streamlit as st
import pandas as pd
import numpy as np
import fitz
from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import io
from PIL import Image
import pytesseract
import re
import ssl
import json
import time

# =========================
# CONFIGURAÇÃO GERAL
# =========================
st.set_page_config(page_title="Conciliação de Boletins", layout="wide")

# Permitir ambientes com SSL autossinado (quando necessário)
try:
    ssl._create_default_https_context = ssl._create_unverified_context  # [ALTERAÇÃO] evita falhas de SSL em algumas infraestruturas
except Exception:
    pass

# =========================
# FUNÇÕES DE SUPORTE (CREDENCIAIS E PDF)
# =========================

def gerar_credenciais():
    """Gera credenciais do Google a partir de st.secrets."""
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
            "universe_domain": st.secrets["google"].get("universe_domain", "googleapis.com"),
        }
        return service_account.Credentials.from_service_account_info(info)
    except Exception as e:
        st.error(f"Erro ao gerar credenciais: {e}")
        st.stop()


def extrair_paginas_pdf(file_bytes: bytes, pagina_inicio: int, pagina_fim: int) -> bytes | None:
    """Extrai intervalo [inicio, fim] (1-based) de um PDF e retorna bytes de um PDF temporário."""
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


# =========================
# EXTRAÇÃO (Document AI + OCR FALLBACK)
# =========================

def processar_documento_documentai(pdf_bytes: bytes, processor_id: str, nome_doc: str):
    """Processa um PDF no Document AI e retorna lista com {documento, tabela: DataFrame}."""
    credentials = gerar_credenciais()
    client = documentai.DocumentProcessorServiceClient(credentials=credentials)
    name = f"projects/{st.secrets['google']['project_id']}/locations/{st.secrets['google']['location']}/processors/{processor_id}"
    document = {"content": pdf_bytes, "mime_type": "application/pdf"}
    request = {"name": name, "raw_document": document}

    try:
        result = client.process_document(request=request)
    except Exception as e:
        st.warning(f"⚠️ Document AI falhou para '{nome_doc}'. Será utilizado OCR de fallback.\n{e}")
        return processar_documento_ocr_fallback(pdf_bytes, nome_doc)

    doc = result.document
    campos = {}

    # Tenta mapear entities -> colunas
    if getattr(doc, "entities", None):
        from collections import defaultdict
        tmp = defaultdict(list)
        for entity in doc.entities:
            field_name = (entity.type_ or "").strip().lower()
            value = (entity.mention_text or "").strip()
            if field_name:
                tmp[field_name].append(value)
        if tmp:
            df = pd.DataFrame.from_dict(tmp, orient="index").transpose()
            return [{"documento": nome_doc, "tabela": df}]

    # Se não há entities utilizáveis, usa texto plano
    textos = [layout.text_anchor.content for layout in getattr(doc, "text_styles", []) if getattr(layout, "text_anchor", None)]
    texto_concatenado = "\n".join(textos) if textos else getattr(doc, "text", "")
    if not texto_concatenado.strip():
        return processar_documento_ocr_fallback(pdf_bytes, nome_doc)

    df = normalizar_texto_para_dataframe(texto_concatenado)
    return [{"documento": nome_doc, "tabela": df}]


def processar_documento_ocr_fallback(pdf_bytes: bytes, nome_doc: str):
    """Fallback usando PyMuPDF -> imagens -> Tesseract -> texto -> normalização -> DataFrame."""
    try:
        linhas = []
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for p in doc:
                pix = p.get_pixmap(dpi=250)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                texto = pytesseract.image_to_string(img, lang="por")
                linhas.extend(texto.splitlines())
        df = normalizar_linhas_para_dataframe(linhas)
        return [{"documento": nome_doc, "tabela": df}]
    except Exception as e:
        st.error(f"❌ OCR fallback falhou para '{nome_doc}': {e}")
        return []


# =========================
# NORMALIZAÇÃO E LIMPEZAS
# =========================

COLUNAS_PADRAO = [
    'descricao', 'descricao_completa', 'unidade',
    'qtd_standby', 'qtd_operacional', 'qtd_dobra', 'qtd_total',
    'valor_unitario_standby', 'valor_unitario_operacional', 'valor_unitario_dobra',
    'total_standby', 'total_operacional', 'total_dobra', 'total_he', 'total_cobrado',
]

COLUNAS_MONETARIAS = [
    'valor_unitario_standby', 'valor_unitario_operacional', 'valor_unitario_dobra',
    'total_standby', 'total_operacional', 'total_dobra', 'total_he', 'total_cobrado'
]


def limpar_moeda(valor):
    if pd.isna(valor):
        return None
    s = str(valor).upper()
    s = re.sub(r"[^\d,\.]", "", s)
    # normaliza último ponto como decimal
    s = s.replace(",", ".")
    partes = s.split(".")
    if len(partes) > 2:
        s = "".join(partes[:-1]) + "." + partes[-1]
    try:
        return float(s)
    except Exception:
        return None


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    for col in COLUNAS_PADRAO:
        if col not in df.columns:
            df[col] = None
    df = df[COLUNAS_PADRAO]
    for col in COLUNAS_MONETARIAS:
        if col in df.columns:
            df[col] = df[col].apply(limpar_moeda)
    return df


def normalizar_texto_para_dataframe(texto: str) -> pd.DataFrame:
    """Heurística simples: quebra por linhas e tenta separar por ; ou múltiplos espaços."""
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    return normalizar_linhas_para_dataframe(linhas)


def normalizar_linhas_para_dataframe(linhas: list[str]) -> pd.DataFrame:
    # Tenta detectar separador
    registros = []
    for l in linhas:
        if ";" in l:
            partes = [p.strip() for p in l.split(";")]
        else:
            partes = re.split(r"\s{2,}", l.strip())
        if len(partes) >= 3:
            registros.append(partes)
    if not registros:
        return pd.DataFrame(columns=COLUNAS_PADRAO)

    # monta DF bruto e renomeia colunas (best-effort)
    df = pd.DataFrame(registros)
    # mapeamento best-effort
    mapping = {
        0: 'descricao', 1: 'descricao_completa', 2: 'unidade',
        3: 'qtd_standby', 4: 'qtd_operacional', 5: 'qtd_dobra', 6: 'qtd_total',
        7: 'valor_unitario_standby', 8: 'valor_unitario_operacional', 9: 'valor_unitario_dobra',
        10: 'total_standby', 11: 'total_operacional', 12: 'total_dobra', 13: 'total_he', 14: 'total_cobrado',
    }
    df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    df = normalizar_colunas(df)
    return df


# =========================
# CONCILIAÇÃO (BOLETIM x CONTRATO)
# =========================

def estruturar_boletim_conciliado(df_boletim_raw: pd.DataFrame, df_contrato: pd.DataFrame) -> pd.DataFrame:
    df_boletim = df_boletim_raw.copy()
    df_contrato = df_contrato.copy()

    # [ALTERAÇÃO] remove linhas irrelevantes conhecidas
    if {"descricao"}.issubset(df_boletim.columns):
        df_boletim = df_boletim[~df_boletim["descricao"].fillna("").str.upper().str.strip().isin(["DIÁRIA (EQUIPAMENTO)", "PRODUTO QUÍMICO"])].copy()

    # chaves de conciliação
    def chave(df, dcol, ucol):
        return df[dcol].fillna("").astype(str).str.strip().str.upper() + " - " + df[ucol].fillna("").astype(str).str.strip().str.upper()

    df_boletim["chave_conciliacao"] = chave(df_boletim, "descricao", "unidade")
    # [ALTERAÇÃO] permite bases de contrato com nomes diversos
    if "descricao_completa" not in df_contrato.columns and "DESCRICAO_COMPLETA" in df_contrato.columns:
        df_contrato = df_contrato.rename(columns={"DESCRICAO_COMPLETA": "descricao_completa"})

    df_contrato["chave_conciliacao"] = chave(df_contrato, "descricao_completa", "unidade")

    df_merged = df_boletim.merge(
        df_contrato,
        on="chave_conciliacao",
        how="left",
        suffixes=("", "_contrato"),
    )

    # Conversão segura
    colunas_float = [
        'qtd_standby', 'qtd_operacional', 'qtd_dobra', 'qtd_total',
        'valor_unitario_standby', 'valor_unitario_operacional', 'valor_unitario_dobra',
        'total_standby', 'total_operacional', 'total_dobra', 'total_he', 'total_cobrado',
        'valor_unitario', 'valor_standby'
    ]
    for col in colunas_float:
        if col in df_merged.columns:
            df_merged[col] = pd.to_numeric(df_merged[col], errors="coerce")

    # total recalculado
    df_merged["total_recalculado"] = (
        (df_merged["qtd_total"].fillna(0) * df_merged["valor_unitario_standby"].fillna(0)) +
        (df_merged["qtd_total"].fillna(0) * df_merged["valor_unitario_operacional"].fillna(0)) +
        (df_merged["qtd_dobra"].fillna(0) * df_merged["valor_unitario_dobra"].fillna(0)) +
        df_merged["total_he"].fillna(0)
    )

    # flags
    df_merged["flag_valor_divergente"] = (
        (np.round(df_merged["valor_unitario_standby"], 2) > np.round(df_merged.get("valor_standby", np.nan), 2)) |
        (np.round(df_merged["valor_unitario_operacional"], 2) > np.round(df_merged.get("valor_unitario", np.nan), 2))
    ).fillna(False).map({True: "Sim", False: "Não"})

    df_merged["flag_total_recalculado_diferente"] = (
        (df_merged["total_recalculado"].fillna(0) < df_merged["total_cobrado"].fillna(0))
    ).map({True: "Sim", False: "Não"})

    if {"descricao", "descricao_completa"}.issubset(df_merged.columns):
        df_merged["flag_descricao_duplicada"] = df_merged.duplicated(
            subset=["descricao", "descricao_completa"], keep=False
        ).map({True: "Sim", False: "Não"})
    else:
        df_merged["flag_descricao_duplicada"] = "Não"

    return df_merged


# =========================
# MULTIAGENTES (NORMALIZAÇÃO → CATÁLOGO → VALIDAÇÃO → REDFLAGS)
# =========================
# Observação: mantemos dependência leve de LLM sem alterar seu backend. A função abaixo aceita qualquer cliente compatível
# com a API de ChatCompletion.create(model=..., messages=[...]).


def agente_normalizador(openai_client, nome_doc: str, df_raw: pd.DataFrame) -> pd.DataFrame:
    """Pede ao LLM para reestruturar a tabela em COLUNAS_PADRAO. Retorna DF padronizado."""
    try:
        tabela_texto = df_raw.to_csv(index=False, sep=";")
        prompt = f"""
Você é um agente NORMALIZADOR. Reestruture a tabela OCR abaixo no JSON com colunas exatamente:
{COLUNAS_PADRAO}
- Use string vazia para texto ausente e 0 para números ausentes.
- NUNCA adicione colunas extras.

Documento: {nome_doc}
Tabela extraída (CSV ;):
{tabela_texto}
"""
        resp = openai_client.ChatCompletion.create(
            model=st.secrets["openai"].get("model", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=4000,
        )
        conteudo = resp.choices[0].message["content"].strip()
        dados = json.loads(conteudo)
        df = pd.DataFrame(dados)
        return normalizar_colunas(df)
    except Exception:
        # fallback: usa normalização heurística
        return normalizar_colunas(df_raw)


def agente_catalogador(openai_client, df_norm: pd.DataFrame) -> pd.DataFrame:
    """Gera uma coluna 'categoria_catalogo' (profissional, equipamento, mobilização etc.) para apoiar conferências."""
    df = df_norm.copy()
    try:
        linhas = df[['descricao', 'descricao_completa', 'unidade']].fillna("").astype(str).agg(" | ".join, axis=1).tolist()
        bloco = "\n".join(f"- {l}" for l in linhas[:120])  # limite de contexto
        prompt = f"""
Você é um agente CATALOGADOR. Para cada linha a seguir, classifique em UMA categoria entre:
["PROFISSIONAL", "EQUIPAMENTO", "MOB/DESMOB", "INSUMO", "OUTROS"].
Responda APENAS como JSON com uma lista de strings na mesma ordem das linhas.
Linhas:\n{bloco}
"""
        resp = openai_client.ChatCompletion.create(
            model=st.secrets["openai"].get("model", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=800,
        )
        cats = json.loads(resp.choices[0].message["content"].strip())
        df["categoria_catalogo"] = cats + ["OUTROS"] * max(0, len(df) - len(cats))
    except Exception:
        df["categoria_catalogo"] = "OUTROS"
    return df


def agente_validador_redflags(openai_client, df_conciliado: pd.DataFrame, df_suporte: pd.DataFrame | None = None) -> pd.DataFrame:
    """Compara indicadores e emite redflags estruturadas, incluindo divergência de valor hora vs documentação suporte."""
    df = df_conciliado.copy()

    # [ALTERAÇÃO] regra programática de divergência de valor-hora usando documentação suporte
    if df_suporte is not None and not df_suporte.empty:
        # cria chave compatível
        def chave(df, dcol, ucol):
            return df[dcol].fillna("").astype(str).str.strip().str.upper() + " - " + df[ucol].fillna("").astype(str).str.strip().str.upper()
        df_suporte = df_suporte.copy()
        df_suporte["chave_conciliacao"] = chave(df_suporte, "descricao_completa", "unidade")
        cols_map = {
            "valor_unitario_operacional": "valor_unitario_operacional_suporte",
            "valor_unitario_standby": "valor_unitario_standby_suporte",
        }
        df_sup_mini = df_suporte[["chave_conciliacao", "valor_unitario_operacional", "valor_unitario_standby"]].rename(columns=cols_map)
        df = df.merge(df_sup_mini, on="chave_conciliacao", how="left")

        # gera flag de divergência de hora (operacional e standby)
        df["flag_valor_hora_operacional_suporte"] = (
            np.round(df.get("valor_unitario_operacional"), 2) != np.round(df.get("valor_unitario_operacional_suporte"), 2)
        ).fillna(False).map({True: "Sim", False: "Não"})
        df["flag_valor_hora_standby_suporte"] = (
            np.round(df.get("valor_unitario_standby"), 2) != np.round(df.get("valor_unitario_standby_suporte"), 2)
        ).fillna(False).map({True: "Sim", False: "Não"})

    # [ALTERAÇÃO] sumarização com LLM (opcional) para relatório objetivo
    try:
        resumo_prompt = {
            "role": "user",
            "content": (
                "Você é um agente VALIDADOR. Dado o JSON de linhas conciliadas, aponte redflags objetivas em bullets. "
                "Foque em: (1) valor hora divergente vs contrato e vs suporte, (2) total recalculado < total cobrado, "
                "(3) possíveis duplicidades. Responda em 5 bullets no máximo.\n\n" +
                df.head(60).to_json(orient="records", force_ascii=False)
            ),
        }
        import openai as _openai
        _openai.api_key = st.secrets["openai"]["OPENAI_API_KEY"]
        resp = _openai.ChatCompletion.create(
            model=st.secrets["openai"].get("model", "gpt-4o"),
            messages=[{"role": "system", "content": "Você é um auditor técnico em contratos."}, resumo_prompt],
            temperature=0.2,
            max_tokens=900,
        )
        st.session_state["resumo_validacao"] = resp.choices[0].message["content"]
    except Exception:
        st.session_state["resumo_validacao"] = ""

    return df


# =========================
# INTERFACE
# =========================

st.sidebar.title("📁 Navegação")
pagina = st.sidebar.radio(
    "Escolha a funcionalidade:",
    [
        "📄 Upload de Documentos",
        "🔎 Visualização",
        "⚖️ Conciliação",
        "📤 Exportação",
    ],
)

# -------------------------
# UPLOAD
# -------------------------
if pagina == "📄 Upload de Documentos":
    st.header("📄 Upload de Documentos para Análise")

    tipo_processor = st.selectbox(
        "🤖 Tipo de Processor do Document AI",
        options=["Form Parser", "Document OCR", "Custom Extractor"],
    )

    PROCESSOR_IDS = {
        "Form Parser": st.secrets["google"].get("form_parser_id"),
        "Document OCR": st.secrets["google"].get("contract_processor"),
        "Custom Extractor": st.secrets["google"].get("custom_extractor_id", "1dc31710a97ca033"),
    }

    processor_id = PROCESSOR_IDS.get(tipo_processor)
    if not processor_id:
        st.error(f"❌ Processor ID não encontrado para o tipo selecionado: `{tipo_processor}`.")
        st.stop()

    colA, colB, colC = st.columns(3)
    with colA:
        arquivos_boletim = st.file_uploader("📑 Boletins de Medição", type=["pdf"], accept_multiple_files=True)
    with colB:
        arquivos_contrato = st.file_uploader("📑 Contratos de Serviço", type=["pdf"], accept_multiple_files=True)
    with colC:
        arquivos_suporte = st.file_uploader("🧾 Documentação Suporte (ordens, e-mails, planilhas em PDF)", type=["pdf"], accept_multiple_files=True)

    def montar_intervalos(label, arquivos):
        intervalos = {}
        if arquivos:
            st.subheader(label)
            for arquivo in arquivos:
                c1, c2 = st.columns(2)
                with c1:
                    inicio = st.number_input(f"Início ({arquivo.name})", min_value=1, value=1, key=f"ini_{label}_{arquivo.name}")
                with c2:
                    fim = st.number_input(f"Fim ({arquivo.name})", min_value=inicio, value=inicio, key=f"fim_{label}_{arquivo.name}")
                intervalos[arquivo.name] = (inicio, fim)
        return intervalos

    intervalos_boletim = montar_intervalos("🟢 Intervalos de Páginas - Boletins", arquivos_boletim)
    intervalos_contrato = montar_intervalos("🟡 Intervalos de Páginas - Contratos", arquivos_contrato)
    intervalos_suporte = montar_intervalos("🔵 Intervalos de Páginas - Suporte", arquivos_suporte)

    if st.button("🚀 Processar Documentos"):
        st.subheader("🔎 Extração com Document AI / OCR")
        tabelas_final = []

        todos = []
        for a in arquivos_boletim or []:
            todos.append((a, intervalos_boletim.get(a.name), "boletim"))
        for a in arquivos_contrato or []:
            todos.append((a, intervalos_contrato.get(a.name), "contrato"))
        for a in arquivos_suporte or []:
            todos.append((a, intervalos_suporte.get(a.name), "suporte"))

        for arquivo, intervalo, tipo in todos:
            nome_doc = arquivo.name
            (inicio, fim) = intervalo or (1, 1)
            with st.spinner(f"Processando {tipo.upper()}: {nome_doc}..."):
                try:
                    file_bytes = arquivo.read()
                    pdf_bytes = extrair_paginas_pdf(file_bytes, inicio, fim)
                    if not pdf_bytes:
                        st.warning(f"⚠️ Não foi possível extrair as páginas de `{nome_doc}`.")
                        continue
                    res = processar_documento_documentai(pdf_bytes, processor_id, nome_doc)
                    for item in res:
                        item["tipo"] = tipo
                    tabelas_final.extend(res)
                except Exception as e:
                    st.error(f"❌ Falha ao processar `{nome_doc}`: {e}")

        if not tabelas_final:
            st.warning("⚠️ Nenhuma tabela extraída com sucesso.")
        else:
            st.success("✅ Processamento concluído!")
            st.session_state["tabelas_extraidas"] = tabelas_final

# -------------------------
# VISUALIZAÇÃO
# -------------------------
if pagina == "🔎 Visualização":
    st.header("🔎 Visualização das Tabelas Extraídas")
    if "tabelas_extraidas" not in st.session_state:
        st.warning("⚠️ Nenhuma tabela foi processada ainda. Vá para '📄 Upload de Documentos' e clique em 'Processar Documentos'.")
        st.stop()

    tabelas_extraidas = st.session_state["tabelas_extraidas"]

    # aplica normalização por tipo
    agrupado: dict[str, list[pd.DataFrame]] = {"boletim": [], "contrato": [], "suporte": []}
    for item in tabelas_extraidas:
        nome_doc = item["documento"]
        df_raw = item["tabela"] if isinstance(item.get("tabela"), pd.DataFrame) else pd.DataFrame()
        if df_raw.empty:
            continue
        df_norm = normalizar_colunas(df_raw)
        agrupado[item.get("tipo", "boletim")].append(df_norm)

    for tipo, lista in agrupado.items():
        if not lista:
            continue
        df_unificado = pd.concat(lista, ignore_index=True)
        st.markdown(f"### 📄 {tipo.upper()}")
        st.dataframe(df_unificado)
        st.session_state[f"df_{tipo}_unificado"] = df_unificado

# -------------------------
# CONCILIAÇÃO / VALIDAÇÃO
# -------------------------
if pagina == "⚖️ Conciliação":
    st.header("⚖️ Conciliação entre Boletins, Contrato e Suporte")

    # Base de contrato (fallback) se usuário não carregou uma
    if "df_contrato_unificado" not in st.session_state:
        df_contrato = pd.DataFrame([
            {"ID_ITEM": "1.1", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "DIÁRIA DE OPERADOR TÉCNICO", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 1672.00, "VALOR_STANDBY": 1337.60},
            {"ID_ITEM": "1.2", "REFERENCIA": "PROFISSIONAL", "DESCRICAO": "DIÁRIA DE SUPERVISOR", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 1995.00, "VALOR_STANDBY": 1596.00},
            {"ID_ITEM": "2.1", "REFERENCIA": "LOCAÇÃO DE EQUIPAMENTOS", "DESCRICAO": "DIÁRIA (EQUIPAMENTO)", "UNIDADE": "DIÁRIA", "VALOR_UNITARIO": 475.00, "VALOR_STANDBY": 403.75},
            {"ID_ITEM": "3.1", "REFERENCIA": "MOB/DESMOB", "DESCRICAO": "MOBILIZAÇÃO", "UNIDADE": "EVENTO", "VALOR_UNITARIO": 1850.00, "VALOR_STANDBY": 1850.00},
        ])
        df_contrato = df_contrato.rename(columns={
            "REFERENCIA": "descricao",
            "DESCRICAO": "descricao_completa",
            "UNIDADE": "unidade",
            "VALOR_STANDBY": "valor_standby",
            "VALOR_UNITARIO": "valor_unitario",
        })
        st.session_state["df_contrato_unificado"] = normalizar_colunas(df_contrato)

    if "df_boletim_unificado" not in st.session_state:
        st.warning("⚠️ Carregue e visualize Boletins na aba anterior.")
        st.stop()

    df_boletim = st.session_state["df_boletim_unificado"]
    df_contrato = st.session_state["df_contrato_unificado"]
    df_suporte = st.session_state.get("df_suporte_unificado", pd.DataFrame())

    df_conciliado = estruturar_boletim_conciliado(df_boletim, df_contrato)

    # Multiagentes (opcional) — normalizador e catalogador sobre boletim
    try:
        import openai as _openai
        _openai.api_key = st.secrets["openai"]["OPENAI_API_KEY"]
        df_norm = agente_normalizador(_openai, "BOLETIM", df_boletim)
        df_categ = agente_catalogador(_openai, df_norm)
        st.session_state["df_boletim_categorizado"] = df_categ
    except Exception:
        st.session_state["df_boletim_categorizado"] = df_boletim

    # Validador + RedFlags incluindo comparação com suporte
    df_validado = agente_validador_redflags(_openai, df_conciliado, df_suporte if not df_suporte.empty else None)

    st.subheader("📋 Resultado da Conciliação e Validação")
    st.dataframe(df_validado)

    st.markdown("### 🚩 Redflags (resumo do agente)")
    resumo = st.session_state.get("resumo_validacao", "")
    if resumo:
        st.markdown(resumo)
    else:
        st.info("Nenhum resumo disponível.")

    if st.checkbox("🔍 Mostrar apenas divergências"):
        cols_flags = [c for c in df_validado.columns if str(c).startswith("flag_")]
        mask = np.any(df_validado[cols_flags].eq("Sim"), axis=1) if cols_flags else pd.Series(False, index=df_validado.index)
        st.dataframe(df_validado[mask])

    st.session_state["df_conciliado_atual"] = df_validado

# -------------------------
# EXPORTAÇÃO
# -------------------------
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
        # writer.save() não é necessário com context manager
    st.download_button(
        label="📤 Baixar Arquivo Excel",
        data=buffer.getvalue(),
        file_name=nome_arquivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
