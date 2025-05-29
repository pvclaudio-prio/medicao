import streamlit as st

st.set_page_config(page_title="Conciliação OCR", layout="wide")

# Menu lateral
menu = st.sidebar.radio("Navegar para:", [
    "📥 Upload de Arquivos",
    "🧾 OCR e Extração de Dados",
    "🤖 Fallback com GPT-4o",
    "📊 Visualização e Exportação"
])

# Execução de cada página
if menu == "📥 Upload de Arquivos":
    st.title("📥 Upload de Arquivos")
    # A lógica dessa aba será inserida a seguir

elif menu == "🧾 OCR e Extração de Dados":
    st.title("🧾 OCR e Extração de Dados")
    # A lógica de OCR será implementada aqui

elif menu == "🤖 Fallback com GPT-4o":
    st.title("🤖 Fallback com GPT-4o")
    # GPT irá auxiliar no parsing quando o OCR for insuficiente

elif menu == "📊 Visualização e Exportação":
    st.title("📊 Visualização e Exportação")
    # Exibição final com filtros + botão para CSV
