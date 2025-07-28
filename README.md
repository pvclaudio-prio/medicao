# 📊 Sistema de Conciliação de Boletins de Medição com Contratos

Este projeto é uma aplicação interativa desenvolvida com **Streamlit** para realizar a **conciliação automatizada** entre boletins de medição extraídos de documentos PDF e contratos previamente definidos. Ele utiliza OCR avançado (Google Document AI), técnicas de limpeza de dados, inteligência artificial (OpenAI GPT-4o) e validação cruzada com regras de negócio.

---

## 🚀 Funcionalidades

O sistema está dividido em quatro páginas principais acessíveis pelo menu lateral:

### 📄 1. Upload de Documentos

- Upload de múltiplos arquivos PDF dos boletins e contratos.
- Escolha do tipo de *processor* do Google Document AI:
  - Form Parser
  - Document OCR
  - Custom Extractor
- Definição dos intervalos de páginas para extração.
- Processamento e estruturação automática via Document AI.
- Armazenamento das tabelas extraídas em cache (session state).

### 🔎 2. Visualização

- Exibição tabular dos dados extraídos.
- Padronização das colunas para conciliação.
- Conversão e limpeza de campos monetários.
- Validação da estrutura para evitar erros posteriores.

### ⚖️ 3. Conciliação

- Carregamento automático de uma base contratual fixa.
- Comparação dos dados extraídos com os dados de contrato.
- Regras aplicadas:
  - Comparação de valores unitários.
  - Recalculo de totais com base nas quantidades.
  - Detecção de descrições duplicadas.
- Aplicação de **flags de inconsistência**:
  - `flag_valor_divergente`
  - `flag_total_recalculado_diferente`
  - `flag_descricao_duplicada`
- **Análise automatizada por IA** (GPT-4o):
  - Revisão técnica das inconsistências.
  - Geração de sumário executivo dividido em:
    - Inconsistências de valor
    - Duplicidades
    - Recomendação técnica

### 📤 4. Exportação

- Visualização final da base conciliada.
- Nomeação personalizada do arquivo.
- Exportação em formato `.xlsx` com download imediato.

---

## 🧠 Tecnologias Utilizadas

- [Streamlit](https://streamlit.io) – Interface interativa.
- [Google Document AI](https://cloud.google.com/document-ai) – Extração de texto via OCR.
- [OpenAI GPT-4o](https://platform.openai.com/docs/models/gpt-4o) – Inteligência artificial para organização e análise.
- [Pandas](https://pandas.pydata.org) – Manipulação de dados.
- [NumPy](https://numpy.org) – Operações numéricas.
- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) – Manipulação de PDFs.
- [Tesseract OCR (via pytesseract)](https://github.com/madmaze/pytesseract) – Reconhecimento de caracteres (OCR alternativo).

---

## 🔐 Requisitos de Autenticação

O sistema utiliza autenticação por credenciais privadas para acessar a API do Google:

- As credenciais devem estar armazenadas em `st.secrets["google"]` no formato padrão de service account.

Exemplo de `.streamlit/secrets.toml`:
```toml
[google]
type = "service_account"
project_id = "seu-projeto"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
form_parser_id = "..."
contract_processor = "..."
