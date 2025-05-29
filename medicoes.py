import streamlit as st

st.set_page_config(page_title="Conciliação de Medições", layout="wide")
st.sidebar.image("PRIO_SEM_POLVO_PRIO_PANTONE_LOGOTIPO_Azul.png")

st.markdown("# 🔧 Sistema de Conciliação de Boletins de Medição")
st.markdown("""
Este sistema permite:
- Upload de contratos e boletins de medição
- Verificação de preços divergentes
- Detecção de duplicidades de profissionais
- Geração de relatório final com análises via IA (GPT-4o)
""")
