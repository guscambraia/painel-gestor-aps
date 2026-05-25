import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import re
import math
import numpy as np

# ================= CONFIGURAÇÃO INICIAL =================
st.set_page_config(page_title="Gestor Proativo APS - Painel MS", layout="wide", page_icon="🏥")

# Constante de DDD para correção automática de telefones incompletos
DDD_PADRAO = "37" 

indicadores_chaves = ['gest', 'inf', 'mul', 'diab', 'hiper', 'idoso', 'cad', 'geral']
for ind in indicadores_chaves:
    if f'dados_{ind}' not in st.session_state:
        st.session_state[f'dados_{ind}'] = None

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""

# ================= SISTEMA DE AUTENTICAÇÃO =================
def verificar_login(usuario, senha):
    if "credentials" in st.secrets and "usernames" in st.secrets["credentials"]:
        usuarios_cadastrados = st.secrets["credentials"]["usernames"]
        if usuario in usuarios_cadastrados and usuarios_cadastrados[usuario] == senha:
            return True
    return False

if not st.session_state["autenticado"]:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.write("")
        st.write("")
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🏥 Gestor Proativo APS</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Acesso restrito à equipe de saúde</p>", unsafe_allow_html=True)
            
            usuario_input = st.text_input("Usuário")
            senha_input = st.text_input("Senha", type="password")
            
            if st.button("Entrar", use_container_width=True):
                if verificar_login(usuario_input, senha_input):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_atual"] = usuario_input
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos. Tente novamente.")
    st.stop()


# ================= BARRA LATERAL & UPLOAD EM LOTE =================
st.sidebar.markdown(f"👤 Logado como: **{st.session_state['usuario_atual']}**")
if st.sidebar.button("Sair do Sistema 🔒", use_container_width=True):
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 Filtro de Território")
st.session_state['microarea_filtro'] = st.sidebar.text_input("Filtrar por Microárea (Ex: 01, 02...)", placeholder="Deixe em branco para ver todas")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📥 Importação de Dados")
st.sidebar.info("Selecione **todos os arquivos CSV** do e-SUS de uma só vez e arraste aqui. O sistema vai organizá-los automaticamente nas abas!")
uploaded_files = st.sidebar.file_uploader("Arquivos CSV", accept_multiple_files=True, type=['csv'])

# ================= FUNÇÕES AUXILIARES =================
@st.cache_data(max_entries=10)
def carregar_dados_esus(uploaded_file):
    raw_bytes = uploaded_file.getvalue()
    try:
        texto = raw_bytes.decode('utf-8')
        encoding = 'utf-8'
    except:
        texto = raw_bytes.decode('latin-1')
        encoding = 'latin-1'
        
    linhas = texto.splitlines()
    header_idx = 0
    for i, linha in enumerate(linhas):
        if ("Nome;" in linha or "Nome cidadão;" in linha) and "Idade;" in linha:
            header_idx = i
            break
            
    uploaded_file.seek(0)
    df = pd.read_csv(uploaded_file, sep=';', skiprows=header_idx, encoding=encoding)
    df = df.dropna(subset=['Nome'])
    
    # Extração otimizada (vetorizada) da Idade
    if 'Idade' in df.columns:
        df['Idade_Anos'] = df['Idade'].astype(str).str.extract(r'(\d+) ano').fillna(0).astype(int)
    return df

def limpar_datas(df, colunas):
    for col in colunas:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col].astype(str).replace('-', pd.NA).str.strip(), format='%d/%m/%Y', errors='coerce')
    return df

def status_validade(data, meses_validade):
    if pd.isna(data): return "🔴 Faltante"
    hoje = datetime.today()
    validade = data + relativedelta(months=meses_validade)
    dias = (validade - hoje).days
    if dias < 0: return "🔴 Vencido"
    elif dias <= 30: return f"🟠 Atenção ({dias}d)"
    else: return "🟢 Em dia"

def checar_qtd(valor, minimo):
    try:
        if pd.isna(valor) or str(valor).strip() in ['-', '']: return "🔴 Faltante"
        val = int(float(str(valor).replace(',', '.')))
        return f"🟢 {val} (Ok)" if val >= minimo else f"🔴 {val} (Falta)"
    except:
        return "🔴 Erro"

def extrair_dias_vida(idade_str):
    if pd.isna(idade_str) or str(idade_str).strip() == '-': return 9999
    if 'dia' in str(idade_str):
        m = re.search(r'(\d+) dia', str(idade_str))
        return int(m.group(1)) if m else 9999
    elif 'mês' in str(idade_str) or 'mes' in str(idade_str):
        m = re.search(r'(\d+) m', str(idade_str))
        return int(m.group(1))*30 if m else 9999
    return 9999

def gerar_link_wpp_custom(telefone, mensagem):
    if pd.isna(telefone) or telefone == '-' or str(telefone).strip() == '': return None
    num = re.sub(r'\D', '', str(telefone))
    # Ajuste: Telefones fixos (8 dígitos) não recebem WPP. Apenas os de 9 dígitos recebem o DDD.
    if len(num) == 8: return None
    if len(num) == 9:
        num = DDD_PADRAO + num
    if len(num) < 10: return None
    return f"https://wa.me/55{num}?text={urllib.parse.quote(mensagem)}"

def interface_filtros_e_exportacao(df_view, colunas_status, chave, arquivo):
    if df_view is None or len(df_view) == 0:
        st.info("Nenhum dado carregado para esta aba. Utilize o painel de upload na barra lateral.")
        return None

    if 'microarea_filtro' in st.session_state and st.session_state['microarea_filtro'].strip() != "":
        if 'Microárea' in df_view.columns:
            df_view = df_view[df_view['Microárea'].astype(str).str.contains(st.session_state['microarea_filtro'].strip(), na=False)]

    df_view['Tem Pendência?'] = df_view[colunas_status].apply(
        lambda r: 'Sim' if any('🔴' in str(v) or '🟠' in str(v) or '🟡' in str(v) for v in r) else 'Não', axis=1
    )

    st.markdown("#### 🔍 Filtros e Ações Clínicas")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        status_geral = st.selectbox("Status Global:", ["Todos", "Somente com Pendências (🔴/🟠)", "Somente em Dia (🟢)"], key=f"stat_{chave}")
    
    with c2:
        opcoes_colunas = ["Todas as métricas"] + colunas_status
        filtro_especifico = st.selectbox("Filtrar Pendência Específica:", opcoes_colunas, key=f"col_{chave}")

    risco_filtro = "Todos"
    if 'Estratificação de risco cardiovascular' in df_view.columns:
        with c3:
            risco_filtro = st.selectbox("Risco Cardiovascular:", ["Todos", "Alto", "Moderado", "Baixo"], key=f"risco_{chave}")

    df_filtrado = df_view.copy()
    
    if status_geral == "Somente com Pendências (🔴/🟠)":
        df_filtrado = df_filtrado[df_filtrado['Tem Pendência?'] == 'Sim']
    elif status_geral == "Somente em Dia (🟢)":
        df_filtrado = df_filtrado[df_filtrado['Tem Pendência?'] == 'Não']

    if filtro_especifico != "Todas as métricas":
        df_filtrado = df_filtrado[df_filtrado[filtro_especifico].astype(str).str.contains('🔴|🟠', regex=True, na=False)]

    if risco_filtro != "Todos" and 'Estratificação de risco cardiovascular' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Estratificação de risco cardiovascular'].astype(str).str.contains(risco_filtro, na=False, case=False)]

    # ORDENAÇÃO INTELIGENTE
    if 'Estratificação de risco cardiovascular' in df_filtrado.columns:
        df_filtrado['Sort_Risco'] = df_filtrado['Estratificação de risco cardiovascular'].map({'Alto': 1, 'Moderado': 2, 'Baixo': 3}).fillna(4)
        df_filtrado = df_filtrado.sort_values(by=['Sort_Risco', 'Nome']).drop(columns=['Sort_Risco'])
    elif '🚨 Alerta DPP' in df_filtrado.columns:
        df_filtrado = df_filtrado.sort_values(by=['🚨 Alerta DPP', 'Nome'], ascending=[False, True])

    st.write("")
    c_exp1, c_exp2 = st.columns([3, 1])
    c_exp1.metric("Total de pacientes na lista abaixo:", len(df_filtrado))
    
    csv_data = df_filtrado.drop(columns=['Busca Ativa', 'Tem Pendência?'], errors='ignore').to_csv(index=False, sep=';').encode('latin-1', errors='ignore')
    c_exp2.download_button("📥 Exportar Lista (CSV)", data=csv_data, file_name=f"{arquivo}_{datetime.today().strftime('%d-%m-%Y')}.csv", mime="text/csv", key=f"dl_{chave}", use_container_width=True)
    
    df_filtrado = df_filtrado.drop(columns=['Tem Pendência?'])
    st.dataframe(df_filtrado, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)
    return df_filtrado


# ================= CÉREBRO CENTRAL (PROCESSAMENTO AUTOMÁTICO EM LOTE) =================
arquivos_mapeados = {k: None for k in indicadores_chaves}

if uploaded_files:
    for f in uploaded_files:
        nome = f.name.upper()
        if "GESTA" in nome or "PUERPERIO" in nome: arquivos_mapeados['gest'] = f
        elif "DESENVOLVIMENTO" in nome or "INFAN" in nome: arquivos_mapeados['inf'] = f
        elif "MULHER" in nome: arquivos_mapeados['mul'] = f
        elif "DIABETES" in nome: arquivos_mapeados['diab'] = f
        elif "HIPERTENSAO" in nome: arquivos_mapeados['hiper'] = f
        elif "IDOSO" in nome: arquivos_mapeados['idoso'] = f
        elif "VINCULADOS" in nome or "CADASTRO" in nome: arquivos_mapeados['cad'] = f
        elif "GERAIS" in nome or "SAUDE" in nome: arquivos_mapeados['geral'] = f

# PROCESSAMENTO: POPULAÇÃO GERAL (NOVA ABA)
if arquivos_mapeados['geral'] is not None and st.session_state['dados_geral'] is None:
    df = carregar_dados_esus(arquivos_mapeados['geral'])
    colunas_data_geral = ['Data do último atendimento individual', 'Data da última visita domiciliar']
    df = limpar_datas(df, colunas_data_geral)
    
    if 'Data do último atendimento individual' in df.columns:
        df['[Status] Cons. (12m)'] = df['Data do último atendimento individual'].apply(lambda x: status_validade(x, 12))
    else:
        df['[Status] Cons. (12m)'] = "⚪ N/A"
        
    if 'Data da última visita domiciliar' in df.columns:
        df['[Status] VD ACS (6m)'] = df['Data da última visita domiciliar'].apply(lambda x: status_validade(x, 6))
    else:
        df['[Status] VD ACS (6m)'] = "⚪ N/A"

    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! Vimos que faz um tempo desde sua última avaliação na unidade de saúde. Podemos agendar um check-up?"), axis=1)
    
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade_Anos'] if 'Idade_Anos' in df.columns else ['Nome']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_geral'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: GESTANTES (NOTA C3)
if arquivos_mapeados['gest'] is not None and st.session_state['dados_gest'] is None:
    df = carregar_dados_esus(arquivos_mapeados['gest'])
    df = limpar_datas(df, ['DPP'])
    if 'DPP' in df.columns:
        df['Dias_Parto'] = (df['DPP'] - datetime.today()).dt.days
        df['🚨 Alerta DPP'] = df['Dias_Parto'].apply(lambda x: "⚠️ Iminente (≤30d)" if pd.notna(x) and 0 <= x <= 30 else ("⚪ N/A"))
        
    df['IG_Num'] = df['IG (DUM) (semanas)'].apply(lambda x: int(float(str(x).replace(',', '.'))) if pd.notna(x) and str(x).strip() not in ['-', ''] else 0)
    df['[Status] Estado'] = df['IG_Num'].apply(lambda x: "🤰 Gestante" if 0 < x <= 42 else ("👶 Puérpera" if x >= 43 else "📋 Pós-parto / Sem IG"))
    
    df['[Status] Captação (≤12 sem)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos até 12 semanas no pré-natal', 0), 1) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
    df['[Status] Consultas (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos no pré-natal', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
    df['[Status] PA (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de medições de pressão arterial', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
    df['[Status] Peso/Altura (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de medições simultâneas de peso e altura', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
    df['[Status] VD ACS Gestação (≥3)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de visitas domiciliares no pré-natal', 0), 3) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
    df['[Status] Vacina dTpa'] = df.apply(lambda r: "⚪ N/A" if r['[Status] Estado'] == "🤰 Gestante" and r['IG_Num'] < 20 else ("🟢 Ok" if pd.notna(r.get('dTpa')) and r.get('dTpa') != '-' else "🔴 Pendente"), axis=1)
    df['[Status] Testes 1ºTri'] = df.apply(lambda r: "🟢 Ok" if (str(r.get('Exame de HIV no primeiro trimestre', '')).strip().upper() == 'SIM' and str(r.get('Exame de Sífilis no primeiro trimestre', '')).strip().upper() == 'SIM') else "🔴 Pendente", axis=1)
    df['[Status] Testes 3ºTri'] = df.apply(lambda r: "🟢 Ok" if (str(r.get('Exame de HIV no terceiro trimestre', '')).strip().upper() == 'SIM' and str(r.get('Exame de Sífilis no terceiro trimestre', '')).strip().upper() == 'SIM') else "🔴 Pendente", axis=1)
    df['[Status] Cons. Puerpério'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos no puerpério', 0), 1) if r['[Status] Estado'] == "👶 Puérpera" else "⚪ N/A", axis=1)
    df['[Status] VD Puerpério'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de visitas domiciliares no puerpério', 0), 1) if r['[Status] Estado'] == "👶 Puérpera" else "⚪ N/A", axis=1)
    df['[Status] Odonto Gestação'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos odontológicos', 0), 1) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)

    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! A equipe de saúde avaliou seu pré-natal/puerpério e notamos algumas atualizações necessárias. Podemos agendar?"), axis=1)
    
    cols_status = [c for c in df.columns if '[Status]' in c and c != '[Status] Estado']
    cols_view = ['Nome', '[Status] Estado', 'IG (DUM) (semanas)']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    if '🚨 Alerta DPP' in df.columns: cols_view.append('🚨 Alerta DPP')
    st.session_state['dados_gest'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: CRIANÇAS (NOTA C2)
if arquivos_mapeados['inf'] is not None and st.session_state['dados_inf'] is None:
    df = carregar_dados_esus(arquivos_mapeados['inf'])
    df['[Status] 1ª Cons. (≤30 dias)'] = df['Idade na primeira consulta'].apply(lambda x: "🟢 Ok" if extrair_dias_vida(x) <= 30 else "🔴 Atrasada/Não feita")
    df['[Status] Consultas (≥9)'] = df['Quantidade de consultas até 24 meses'].apply(lambda x: checar_qtd(x, 9))
    df['[Status] Peso/Altura (≥9)'] = df['Quantidade de medições de peso/altura simultâneas até 24 meses'].apply(lambda x: checar_qtd(x, 9))
    df['[Status] Visita ACS (≥2)'] = df['Quantidade de visitas domiciliares até os 24 meses de idade'].apply(lambda x: checar_qtd(x, 2))
    df['[Status] Vacinas Básicas'] = df.apply(lambda r: "🟢 Ok" if pd.notna(r.get('Poliomielite')) and r.get('Poliomielite') != '-' else "🔴 Incompleta", axis=1)
    
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá, responsável por {r['Nome']}! Identificamos vacinas ou consultas de desenvolvimento infantil pendentes."), axis=1)
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_inf'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: MULHER E PREVENÇÃO DE CÂNCER (NOTA C7)
if arquivos_mapeados['mul'] is not None and st.session_state['dados_mul'] is None:
    df = carregar_dados_esus(arquivos_mapeados['mul'])
    df = limpar_datas(df, ['Exame de rastreamento de câncer de colo de útero data última avaliação', 'Exame de rastreamento de câncer de mama data Última avaliação', 'Data da última consulta de saúde sexual e reprodutiva'])
    df['[Status] Preventivo (25-64a)'] = df.apply(lambda r: status_validade(r['Exame de rastreamento de câncer de colo de útero data última avaliação'], 36) if 25 <= r.get('Idade_Anos', 0) <= 64 else "⚪ N/A", axis=1)
    df['[Status] Mamografia (50-69a)'] = df.apply(lambda r: status_validade(r.get('Exame de rastreamento de câncer de mama data Última avaliação'), 24) if 50 <= r.get('Idade_Anos', 0) <= 69 else "⚪ N/A", axis=1)
    df['[Status] Vacina HPV (9-14a)'] = df.apply(lambda r: ("🟢 Ok" if str(r.get('HPV', '-')).strip() not in ['-', ''] and pd.notna(r.get('HPV')) else "🔴 Pendente") if 9 <= r.get('Idade_Anos', 0) <= 14 else "⚪ N/A", axis=1)
    df['[Status] Saúde Reprod. (14-69a)'] = df.apply(lambda r: status_validade(r['Data da última consulta de saúde sexual e reprodutiva'], 12) if 14 <= r.get('Idade_Anos', 0) <= 69 else "⚪ N/A", axis=1)
    
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! A equipe de saúde solicita seu retorno para atualizar exames preventivos."), axis=1)
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_mul'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: DIABETES (NOTA C4)
if arquivos_mapeados['diab'] is not None and st.session_state['dados_diab'] is None:
    df = carregar_dados_esus(arquivos_mapeados['diab'])
    df = limpar_datas(df, ['Data do último atendimento individual', 'Data da última medição de pressão arterial', 'Data da ultima medição de peso e altura', 'Data da última avaliação de hemoglobina glicada', 'Data da avaliação dos pés'])
    df['[Status] Consulta (6m)'] = df.get('Data do último atendimento individual', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 6))
    df['[Status] PA (6m)'] = df.get('Data da última medição de pressão arterial', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 6))
    df['[Status] Peso/Altura (12m)'] = df.get('Data da ultima medição de peso e altura', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 12))
    df['[Status] VD ACS (12m)'] = df.get('Quantidade de visitas domiciliares', pd.Series([0]*len(df))).apply(lambda x: checar_qtd(x, 2))
    df['[Status] HbA1c (12m)'] = df.get('Data da última avaliação de hemoglobina glicada', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 12))
    df['[Status] Pé Diabético (12m)'] = df.get('Data da avaliação dos pés', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 12)) 
    
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! Verificamos pendências de consultas e exames do seu acompanhamento de saúde."), axis=1)
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_diab'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: HIPERTENSÃO (NOTA C5)
if arquivos_mapeados['hiper'] is not None and st.session_state['dados_hiper'] is None:
    df = carregar_dados_esus(arquivos_mapeados['hiper'])
    df = limpar_datas(df, ['Data do último atendimento individual', 'Data da última medição de pressão arterial', 'Data da ultima medição de peso e altura'])
    df['[Status] Consulta (6m)'] = df.get('Data do último atendimento individual', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 6))
    df['[Status] PA (6m)'] = df.get('Data da última medição de pressão arterial', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 6))
    df['[Status] Peso/Altura (12m)'] = df.get('Data da ultima medição de peso e altura', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 12))
    df['[Status] VD ACS (12m)'] = df.get('Quantidade de visitas domiciliares', pd.Series([0]*len(df))).apply(lambda x: checar_qtd(x, 2))
    
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! Precisamos medir sua pressão e atualizar seu cadastro clínico."), axis=1)
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_hiper'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: IDOSO (NOTA C6)
if arquivos_mapeados['idoso'] is not None and st.session_state['dados_idoso'] is None:
    df = carregar_dados_esus(arquivos_mapeados['idoso'])
    df = limpar_datas(df, ['Data do último atendimento individual'])
    df['[Status] Consulta (12m)'] = df.get('Data do último atendimento individual', pd.Series([pd.NA]*len(df))).apply(lambda x: status_validade(x, 12))
    df['[Status] Peso/Altura (12m)'] = df.get('Registros de peso e altura simultâneos nos últimos 12 meses', pd.Series([0]*len(df))).apply(lambda x: checar_qtd(x, 1))
    df['[Status] VD ACS (12m)'] = df.get('Quantidade de visitas domiciliares', pd.Series([0]*len(df))).apply(lambda x: checar_qtd(x, 2))
    df['[Status] Influenza (12m)'] = df.apply(lambda r: "🟢 Ok" if str(r.get('Influenza (últimos 12 meses)', '-')).strip().upper() == 'SIM' else "🔴 Faltante", axis=1)
    
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r.get('Telefone celular', ''), f"Olá {r['Nome']}! Temos consultas preventivas pendentes para agendar para você."), axis=1)
    cols_status = [c for c in df.columns if '[Status]' in c]
    cols_view = ['Nome', 'Idade']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    st.session_state['dados_idoso'] = df[cols_view + cols_status + ['Busca Ativa']].copy()

# PROCESSAMENTO: CADASTRO
if arquivos_mapeados['cad'] is not None and st.session_state['dados_cad'] is None:
    df = carregar_dados_esus(arquivos_mapeados['cad'])
    df = limpar_datas(df, ['Última atualização cadastral'])
    df['[Status] Atualização'] = df['Última atualização cadastral'].apply(lambda x: status_validade(x, 24))
    df['[Status] Documento'] = df['CPF/CNS'].apply(lambda x: "🔴 Sem CPF/CNS" if pd.isna(x) or str(x).strip() == '-' else "🟢 Ok")
    df['[Status] Telefone'] = df['Telefone celular'].apply(lambda x: "🔴 Sem Número" if pd.isna(x) or str(x).strip() == '-' else "🟢 Ok")
    df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], f"Olá {r['Nome']}! Seu cadastro do SUS está vencido ou incompleto. Mande um 'Oi' para atualizarmos."), axis=1)
    cols_status = ['[Status] Atualização', '[Status] Documento', '[Status] Telefone']
    cols_view = ['Nome']
    if 'Microárea' in df.columns: cols_view.append('Microárea')
    cols_view.extend(['CPF/CNS', 'Telefone celular'])
    st.session_state['dados_cad'] = df[cols_view + cols_status + ['Busca Ativa']].copy()


# ================= INTERFACE EM ABAS =================
tabs = st.tabs([
    "📊 Dashboard Geral",
    "🤰 Gestantes", 
    "👶 Crianças", 
    "👩 Mulher", 
    "🩸 Diabetes", 
    "🫀 Hipertensão", 
    "👵 Idoso", 
    "📋 Cadastros",
    "🏥 População Geral"
])

# ----------------- 0. DASHBOARD GERAL -----------------
with tabs[0]:
    st.header("📊 Painel Analítico e Previsão de Metas (MS)")
    
    # 🚨 UTI DA APS: CENTRAL DE ALERTAS
    alertas_html = ""
    qtd_alertas = 0
    
    if st.session_state['dados_gest'] is not None:
        df_g = st.session_state['dados_gest']
        if '🚨 Alerta DPP' in df_g.columns:
            n_partos = len(df_g[df_g['🚨 Alerta DPP'].astype(str).str.contains('Iminente', na=False)])
            if n_partos > 0:
                alertas_html += f"<li>⚠️ <b>{n_partos} Gestante(s)</b> com parto previsto para os próximos 30 dias. Cheque a aba Gestantes!</li>"
                qtd_alertas += n_partos

    for ind in ['diab', 'hiper']:
        if st.session_state[f'dados_{ind}'] is not None:
            df_c = st.session_state[f'dados_{ind}']
            if 'Estratificação de risco cardiovascular' in df_c.columns:
                cols_stat = [c for c in df_c.columns if '[Status]' in c]
                df_c['Tem Pendência'] = df_c[cols_stat].apply(lambda r: True if any('🔴' in str(v) for v in r) else False, axis=1)
                n_altorisco = len(df_c[(df_c['Estratificação de risco cardiovascular'].astype(str).str.contains('Alto', na=False, case=False)) & (df_c['Tem Pendência'] == True)])
                if n_altorisco > 0:
                    nome_doenca = "Diabéticos" if ind == 'diab' else "Hipertensos"
                    alertas_html += f"<li>🚨 <b>{n_altorisco} {nome_doenca}(s) de ALTO RISCO CARDIOVASCULAR</b> com exames ou consultas atrasadas.</li>"
                    qtd_alertas += n_altorisco

    if qtd_alertas > 0:
        st.markdown(f"""
        <div style='background-color: #ffe6e6; border-left: 5px solid #ff4d4d; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>
            <h4 style='color: #cc0000; margin-top: 0;'>🚨 Prioridades Clínicas Imediatas (Ação Necessária)</h4>
            <ul style='color: #990000; margin-bottom: 0;'>
                {alertas_html}
            </ul>
        </div>
        """, unsafe_allow_html=True)
    else:
        # AQUI FOI CORRIGIDO O KEY ERROR USANDO f'dados_{k}'
        if any(st.session_state[f'dados_{k}'] is not None for k in indicadores_chaves):
            st.success("✅ Nenhum alerta clínico crítico identificado nas planilhas no momento.")


    # DICIONÁRIO DO DASHBOARD (MÉTRICAS ATUALIZADAS C2 AO C7)
    estrutura_dashboard = {
        'gest': {
            'titulo': "🤰 C3: Cuidado na Gestação e Puerpério",
            'metricas': [
                ('[Status] Captação (≤12 sem)', '1ª Consulta (≤12 sem)', 10, '1ª consulta pré-natal até a 12ª semana.'),
                ('[Status] Consultas (≥7)', 'Consultas (≥7)', 9, 'Pelo menos 07 consultas durante a gestação.'),
                ('[Status] PA (≥7)', 'Aferição de PA (≥7)', 9, 'Pelo menos 07 registros de aferição de pressão.'),
                ('[Status] Peso/Altura (≥7)', 'Peso e Altura (≥7)', 9, 'Pelo menos 07 registros simultâneos de peso e altura.'),
                ('[Status] VD ACS Gestação (≥3)', 'Visitas ACS Gestação (≥3)', 9, 'Pelo menos 03 VD após a primeira consulta.'),
                ('[Status] Vacina dTpa', 'Vacina dTpa (≥20 sem)', 9, 'Vacina dTpa registrada a partir da 20ª semana.'),
                ('[Status] Testes 1ºTri', 'Testes 1º Trimestre', 9, 'Sífilis, HIV, Hepatites B e C no 1º trimestre.'),
                ('[Status] Testes 3ºTri', 'Testes 3º Trimestre', 9, 'Sífilis e HIV no 3º trimestre.'),
                ('[Status] Cons. Puerpério', 'Consulta Puerpério', 9, 'Pelo menos 01 consulta no puerpério.'),
                ('[Status] VD Puerpério', 'Visita ACS Puerpério', 9, 'Pelo menos 01 VD no puerpério.'),
                ('[Status] Odonto Gestação', 'Avaliação Odontológica', 9, 'Pelo menos 01 atividade de saúde bucal na gestação.')
            ]
        },
        'inf': {
            'titulo': "👶 C2: Desenvolvimento Infantil",
            'metricas': [
                ('[Status] 1ª Cons. (≤30 dias)', '1ª Consulta (≤30 dias)', 20, '1ª consulta médica ou enf. até 30 dias de vida.'),
                ('[Status] Consultas (≥9)', 'Consultas de Rotina (≥9)', 20, 'Pelo menos 09 consultas até dois anos de vida.'),
                ('[Status] Peso/Altura (≥9)', 'Peso e Altura (≥9)', 20, 'Pelo menos 09 registros de peso e altura.'),
                ('[Status] Visita ACS (≥2)', 'Visita ACS (≥2)', 20, '2 visitas ACS (1ª até 30d, 2ª até 6 meses).'),
                ('[Status] Vacinas Básicas', 'Esquema Vacinal', 20, 'Vacinas: dTpa/Penta/VIP, SCR, VPC.')
            ]
        },
        'mul': {
            'titulo': "👩 C7: Prevenção de Câncer e Saúde Mulher",
            'metricas': [
                ('[Status] Preventivo (25-64a)', 'Citopatológico (25-64a)', 20, '1 exame preventivo a cada 36 meses.'),
                ('[Status] Mamografia (50-69a)', 'Mamografia (50-69a)', 20, '1 mamografia de rastreio a cada 24 meses.'),
                ('[Status] Vacina HPV (9-14a)', 'Vacina HPV (9-14a)', 30, '01 dose da vacina HPV para 09 a 14 anos.'),
                ('[Status] Saúde Reprod. (14-69a)', 'Saúde Reprodutiva', 30, 'Atendimento de saúde sexual e reprodutiva nos últimos 12m.')
            ]
        },
        'diab': {
            'titulo': "🩸 C4: Pessoa com Diabetes",
            'metricas': [
                ('[Status] Consulta (6m)', 'Consulta Semestral', 20, 'Pelo menos 01 consulta nos últimos 6 meses.'),
                ('[Status] PA (6m)', 'Aferição de PA (6m)', 15, 'Pelo menos 01 aferição de PA nos últimos 6 meses.'),
                ('[Status] Peso/Altura (12m)', 'Peso e Altura (12m)', 15, 'Pelo menos 01 registro de peso e altura em 12 meses.'),
                ('[Status] VD ACS (12m)', 'Visitas ACS (≥2 em 12m)', 20, 'Pelo menos 02 VD com intervalo mínimo de 30 dias.'),
                ('[Status] HbA1c (12m)', 'Hemoglobina Glicada', 15, '1 exame de HbA1c nos últimos 12 meses.'),
                ('[Status] Pé Diabético (12m)', 'Avaliação dos Pés', 15, '1 avaliação dos pés nos últimos 12 meses.')
            ]
        },
        'hiper': {
            'titulo': "🫀 C5: Pessoa com Hipertensão",
            'metricas': [
                ('[Status] Consulta (6m)', 'Consulta Semestral', 25, 'Pelo menos 01 consulta nos últimos 6 meses.'),
                ('[Status] PA (6m)', 'Aferição de PA (6m)', 25, 'Pelo menos 01 aferição de PA nos últimos 6 meses.'),
                ('[Status] Peso/Altura (12m)', 'Peso e Altura (12m)', 25, 'Pelo menos 01 registro de peso e altura em 12 meses.'),
                ('[Status] VD ACS (12m)', 'Visitas ACS (≥2 em 12m)', 25, 'Pelo menos 02 VD com intervalo mínimo de 30 dias.')
            ]
        },
        'idoso': {
            'titulo': "👵 C6: Pessoa Idosa",
            'metricas': [
                ('[Status] Consulta (12m)', 'Consulta Anual', 25, 'Pelo menos 01 consulta nos últimos 12 meses.'),
                ('[Status] Peso/Altura (12m)', 'Peso e Altura (12m)', 25, 'Pelo menos 01 registro de peso e altura em 12 meses.'),
                ('[Status] VD ACS (12m)', 'Visitas ACS (≥2 em 12m)', 25, 'Pelo menos 02 VD com intervalo mínimo de 30 dias.'),
                ('[Status] Influenza (12m)', 'Vacina Influenza (12m)', 25, '01 dose da vacina contra influenza nos últimos 12 meses.')
            ]
        }
    }
    
    col_dash1, col_dash2 = st.columns(2)
    
    for idx, (chave, dados_ind) in enumerate(estrutura_dashboard.items()):
        alvo_col = col_dash1 if idx % 2 == 0 else col_dash2
        
        with alvo_col:
            with st.container(border=True):
                st.markdown(f"<h3 style='margin-bottom: 0px;'>{dados_ind['titulo']}</h3>", unsafe_allow_html=True)
                df_atual = st.session_state[f'dados_{chave}']
                
                if df_atual is not None and 'microarea_filtro' in st.session_state and st.session_state['microarea_filtro'].strip() != "":
                    if 'Microárea' in df_atual.columns:
                        df_atual = df_atual[df_atual['Microárea'].astype(str).str.contains(st.session_state['microarea_filtro'].strip(), na=False)]

                if df_atual is not None and len(df_atual) > 0:
                    st.write("")
                    for col_status, label, peso, regra in dados_ind['metricas']:
                        if col_status in df_atual.columns:
                            df_elegivel = df_atual[~df_atual[col_status].astype(str).str.contains('⚪', na=False)]
                            total_elegivel = len(df_elegivel)
                            if total_elegivel > 0:
                                em_dia = len(df_elegivel[df_elegivel[col_status].astype(str).str.contains('🟢', na=False)])
                                perc_cobertura = em_dia / total_elegivel
                                
                                meta_pct = 0.75 
                                meta_pacientes = math.ceil(total_elegivel * meta_pct)
                                faltam_meta = max(0, meta_pacientes - em_dia)
                                texto_meta = "🎯 **Meta Atingida!**" if perc_cobertura >= meta_pct else f"📉 Faltam **{faltam_meta}** pacientes para atingir a meta ótima"
                                
                                st.markdown(f"**{label}** (Peso na nota: {peso}pts)")
                                st.caption(f"🎯 *Regra:* {regra}")
                                
                                cor_barra = "#2E8B57" if perc_cobertura >= 0.75 else ("#DAA520" if perc_cobertura >= 0.50 else "#DC143C")
                                st.markdown(f"""
                                <div style="width: 100%; background-color: #e0e0e0; border-radius: 5px;">
                                  <div style="width: {perc_cobertura*100}%; height: 10px; background-color: {cor_barra}; border-radius: 5px;"></div>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                c_met1, c_met2 = st.columns([1, 2])
                                c_met1.metric(label="Cobertura", value=f"{perc_cobertura*100:.1f}%")
                                c_met2.markdown(f"<small>Elegíveis: {total_elegivel} | Em dia: {em_dia}<br>{texto_meta}</small>", unsafe_allow_html=True)
                                st.write("") 
                else:
                    st.info("Faça o upload do CSV correspondente na barra lateral.")

# ----------------- OUTRAS ABAS (RENDERIZAÇÃO) -----------------
with tabs[1]:
    st.header("🤰 Cuidado da Gestante e Puérpera")
    cols = [c for c in st.session_state['dados_gest'].columns if '[Status]' in c] if st.session_state['dados_gest'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_gest'], cols, 'gest', 'Gestantes')

with tabs[2]:
    st.header("👶 Desenvolvimento Infantil (Puericultura)")
    cols = [c for c in st.session_state['dados_inf'].columns if '[Status]' in c] if st.session_state['dados_inf'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_inf'], cols, 'inf', 'Criancas')

with tabs[3]:
    st.header("👩 Prevenção de Câncer e Saúde da Mulher")
    cols = [c for c in st.session_state['dados_mul'].columns if '[Status]' in c] if st.session_state['dados_mul'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_mul'], cols, 'mul', 'Mulher')

with tabs[4]:
    st.header("🩸 Diabetes Mellitus")
    cols = [c for c in st.session_state['dados_diab'].columns if '[Status]' in c] if st.session_state['dados_diab'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_diab'], cols, 'diab', 'Diabetes')

with tabs[5]:
    st.header("🫀 Hipertensão Arterial")
    cols = [c for c in st.session_state['dados_hiper'].columns if '[Status]' in c] if st.session_state['dados_hiper'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_hiper'], cols, 'hiper', 'Hipertensao')

with tabs[6]:
    st.header("👵 Pessoa Idosa")
    cols = [c for c in st.session_state['dados_idoso'].columns if '[Status]' in c] if st.session_state['dados_idoso'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_idoso'], cols, 'idoso', 'Idoso')

with tabs[7]:
    st.header("📋 Auditoria de Cadastros (Qualidade de Dados)")
    cols = [c for c in st.session_state['dados_cad'].columns if '[Status]' in c] if st.session_state['dados_cad'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_cad'], cols, 'cad', 'Cadastros')

with tabs[8]:
    st.header("🏥 Condições Clínicas Gerais (População)")
    st.markdown("Monitoramento de últimas consultas e visitas domiciliares de rotina para todos os cidadãos.")
    cols = [c for c in st.session_state['dados_geral'].columns if '[Status]' in c] if st.session_state['dados_geral'] is not None else []
    interface_filtros_e_exportacao(st.session_state['dados_geral'], cols, 'geral', 'Populacao_Geral')
