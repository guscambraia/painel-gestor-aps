import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import urllib.parse
import re
import math

# ================= CONFIGURAÇÃO INICIAL =================
st.set_page_config(page_title="Gestor Proativo APS - Painel MS", layout="wide", page_icon="🏥")

# Inicializar o Session State para armazenar os DADOS COMPLETOS e o STATUS DE LOGIN
indicadores_chaves = ['gest', 'inf', 'mul', 'diab', 'hiper', 'idoso']
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


# ================= BARRA LATERAL =================
st.sidebar.markdown(f"👤 Logado como: **{st.session_state['usuario_atual']}**")
if st.sidebar.button("Sair do Sistema 🔒", use_container_width=True):
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📍 Filtro de Território")
st.session_state['microarea_filtro'] = st.sidebar.text_input("Filtrar por Microárea (Ex: 01, 02...)", placeholder="Deixe em branco para ver todas")


# ================= FUNÇÕES AUXILIARES DE BACKEND =================
@st.cache_data
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
    
    def extrair_anos(idade_str):
        if pd.isna(idade_str): return 0
        match = re.search(r'(\d+) ano', str(idade_str))
        return int(match.group(1)) if match else 0
    
    if 'Idade' in df.columns:
        df['Idade_Anos'] = df['Idade'].apply(extrair_anos)
        
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
    if len(num) < 10: return None
    return f"https://wa.me/55{num}?text={urllib.parse.quote(mensagem)}"

# ================= NOVA INTERFACE DE FILTROS =================
def interface_filtros_e_exportacao(df_view, colunas_status, chave, arquivo):
    # 1. Filtro Global de Microárea
    if 'microarea_filtro' in st.session_state and st.session_state['microarea_filtro'].strip() != "":
        if 'Microárea' in df_view.columns:
            df_view = df_view[df_view['Microárea'].astype(str).str.contains(st.session_state['microarea_filtro'].strip(), na=False)]

    df_view['Tem Pendência?'] = df_view[colunas_status].apply(
        lambda r: 'Sim' if any('🔴' in str(v) or '🟠' in str(v) or '🟡' in str(v) for v in r) else 'Não', axis=1
    )

    st.markdown("#### 🔍 Filtros de Visualização")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        status_geral = st.selectbox("Status Global:", ["Todos", "Somente com Pendências (🔴)", "Somente em Dia (🟢)"], key=f"stat_{chave}")
    
    with c2:
        opcoes_colunas = ["Todas as métricas"] + colunas_status
        filtro_especifico = st.selectbox("Filtrar Pendência Específica:", opcoes_colunas, key=f"col_{chave}")

    risco_filtro = "Todos"
    if 'Estratificação de risco cardiovascular' in df_view.columns:
        with c3:
            risco_filtro = st.selectbox("Risco Cardiovascular:", ["Todos", "Alto", "Moderado", "Baixo"], key=f"risco_{chave}")

    # Aplicação dos Filtros
    df_filtrado = df_view.copy()
    
    if status_geral == "Somente com Pendências (🔴)":
        df_filtrado = df_filtrado[df_filtrado['Tem Pendência?'] == 'Sim']
    elif status_geral == "Somente em Dia (🟢)":
        df_filtrado = df_filtrado[df_filtrado['Tem Pendência?'] == 'Não']

    if filtro_especifico != "Todas as métricas":
        df_filtrado = df_filtrado[df_filtrado[filtro_especifico].astype(str).str.contains('🔴|🟠', regex=True, na=False)]

    if risco_filtro != "Todos" and 'Estratificação de risco cardiovascular' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['Estratificação de risco cardiovascular'].astype(str).str.contains(risco_filtro, na=False, case=False)]

    # Ordenação Inteligente (Priorização Clínica)
    if 'Estratificação de risco cardiovascular' in df_filtrado.columns:
        df_filtrado['Sort_Risco'] = df_filtrado['Estratificação de risco cardiovascular'].map({'Alto': 1, 'Moderado': 2, 'Baixo': 3}).fillna(4)
        df_filtrado = df_filtrado.sort_values(by=['Sort_Risco', 'Nome']).drop(columns=['Sort_Risco'])
    elif '🚨 Alerta DPP' in df_filtrado.columns:
        df_filtrado = df_filtrado.sort_values(by=['🚨 Alerta DPP', 'Nome'], ascending=[False, True])

    # Exportação e Resumo
    st.write("")
    c_exp1, c_exp2 = st.columns([3, 1])
    c_exp1.metric("Total de pacientes na lista abaixo:", len(df_filtrado))
    
    csv_data = df_filtrado.drop(columns=['Busca Ativa', 'Tem Pendência?'], errors='ignore').to_csv(index=False, sep=';').encode('latin-1', errors='ignore')
    c_exp2.download_button("📥 Exportar Lista (CSV)", data=csv_data, file_name=f"{arquivo}_{datetime.today().strftime('%d-%m-%Y')}.csv", mime="text/csv", key=f"dl_{chave}", use_container_width=True)
    
    return df_filtrado.drop(columns=['Tem Pendência?'])

# ================= INTERFACE PRINCIPAL EM ABAS =================
tabs = st.tabs([
    "📊 Dashboard Geral",
    "🤰 Gestantes", 
    "👶 Crianças", 
    "👩 Mulher", 
    "🩸 Diabetes", 
    "🫀 Hipertensão", 
    "👵 Idoso", 
    "📋 Cadastros", 
    "🏥 Saúde Geral"
])

# ----------------- 0. DASHBOARD GERAL -----------------
with tabs[0]:
    st.header("📊 Painel Analítico e Previsão de Metas (MS)")
    st.markdown("Cálculo baseado no **Novo Cofinanciamento da APS (Portaria 3.493/2024)**. O painel prevê o esforço necessário para atingir o parâmetro **Ótimo (75%)**.")
    
    estrutura_dashboard = {
        'gest': {
            'titulo': "🤰 C3: Gestantes e Puérperas",
            'metricas': [
                ('[Status] Captação (≤12 sem)', '(A) Captação Precoce (Peso: 10 pts)', 10),
                ('[Status] Consultas (≥7)', '(B) Consultas Pré-natal (Peso: 9 pts)', 9),
                ('[Status] PA (≥7)', '(C) Aferição de PA (Peso: 9 pts)', 9),
                ('[Status] Peso/Altura (≥7)', '(D) Medição Peso/Altura (Peso: 9 pts)', 9),
                ('[Status] VD ACS Gestação (≥3)', '(E) Visitas ACS Gestação (Peso: 9 pts)', 9),
                ('[Status] Vacina dTpa', '(F) Vacinação dTpa (Peso: 9 pts)', 9),
                ('[Status] Testes 1ºTri', '(G) Testes 1º Tri (Peso: 9 pts)', 9),
                ('[Status] Testes 3ºTri', '(H) Testes 3º Tri (Peso: 9 pts)', 9),
                ('[Status] Cons. Puerpério', '(I) Consulta Puerpério (Peso: 9 pts)', 9),
                ('[Status] VD Puerpério', '(J) Visita ACS Puerpério (Peso: 9 pts)', 9),
                ('[Status] Odonto Gestação', '(K) Atendimento Odontológico (Peso: 9 pts)', 9)
            ]
        },
        'inf': {
            'titulo': "👶 C2: Desenvolvimento Infantil",
            'metricas': [
                ('[Status] 1ª Cons. (≤30 dias)', '(A) 1ª Consulta até 30 dias (Peso: 20 pts)', 20),
                ('[Status] Consultas (≥9)', '(B) Consultas de Rotina (Peso: 20 pts)', 20),
                ('[Status] Peso/Altura (≥9)', '(C) Peso e Altura (Peso: 20 pts)', 20),
                ('[Status] Visita ACS (≥2)', '(D) Visitas Domiciliares (Peso: 20 pts)', 20),
                ('[Status] Vacinas Básicas', '(E) Esquema Vacinal (Peso: 20 pts)', 20)
            ]
        },
        'mul': {
            'titulo': "👩 C7: Saúde da Mulher",
            'metricas': [
                ('[Status] Preventivo (25-64a)', '(A) Citopatológico (Peso: 30 pts)', 30),
                ('[Status] Saúde Reprod. (14-69a)', '(B) Saúde Sexual/Reprodutiva (Peso: 30 pts)', 30),
                ('[Status] Mamografia (50-69a)', '(C) Mamografia (Peso: 20 pts)', 20),
                ('[Status] Vacina HPV (9-14a)', '(D) Vacina HPV (Peso: 20 pts)', 20)
            ]
        },
        'diab': {
            'titulo': "🩸 C4: Diabetes Mellitus",
            'metricas': [
                ('[Status] HbA1c (12m)', '(E) Hemoglobina Glicada (Peso: 20 pts)', 20),
                ('[Status] Pé Diabético (12m)', '(F) Rastreio do Pé Diabético (Peso: 20 pts)', 20),
                ('[Status] Peso/Altura (12m)', '(C) Peso e Altura (Peso: 20 pts)', 20),
                ('[Status] Visitas ACS (≥2)', '(D) Visitas ACS (Peso: 40 pts)', 40)
            ]
        },
        'hiper': {
            'titulo': "🫀 C5: Hipertensão Arterial",
            'metricas': [
                ('[Status] Consulta e PA (6m)', '(A/B) Consulta e PA Semestral (Peso: 50 pts)', 50),
                ('[Status] Peso/Altura (12m)', '(C) Peso e Altura Anual (Peso: 25 pts)', 25),
                ('[Status] Visitas ACS', '(D) Visitas ACS (Peso: 25 pts)', 25)
            ]
        },
        'idoso': {
            'titulo': "👵 C6: Pessoa Idosa",
            'metricas': [
                ('[Status] Avaliação AMPI (12m)', '(A) Avaliação AMPI (Peso: 30 pts)', 30),
                ('[Status] Influenza (12m)', '(D) Vacina Influenza (Peso: 30 pts)', 30),
                ('[Status] Peso/Altura (≥2)', '(B) Peso e Altura (Peso: 20 pts)', 20),
                ('[Status] Visitas ACS (≥2)', '(C) Visitas ACS (Peso: 20 pts)', 20)
            ]
        }
    }
    
    def classificar_desempenho(nota):
        if nota >= 75: return "🔵 ÓTIMO", "#0047AB"
        elif nota >= 50: return "🟢 BOM", "#2E8B57"
        elif nota >= 25: return "🟡 SUFICIENTE", "#DAA520"
        else: return "🔴 REGULAR", "#DC143C"

    col_dash1, col_dash2 = st.columns(2)
    
    for idx, (chave, dados_ind) in enumerate(estrutura_dashboard.items()):
        alvo_col = col_dash1 if idx % 2 == 0 else col_dash2
        
        with alvo_col:
            with st.container(border=True):
                st.markdown(f"<h3 style='margin-bottom: 0px;'>{dados_ind['titulo']}</h3>", unsafe_allow_html=True)
                df_atual = st.session_state[f'dados_{chave}']
                
                # Se o filtro de microárea estiver ativo, refletimos no dashboard também
                if df_atual is not None and 'microarea_filtro' in st.session_state and st.session_state['microarea_filtro'].strip() != "":
                    if 'Microárea' in df_atual.columns:
                        df_atual = df_atual[df_atual['Microárea'].astype(str).str.contains(st.session_state['microarea_filtro'].strip(), na=False)]

                if df_atual is not None and len(df_atual) > 0:
                    nota_final_indicador = 0
                    st.write("")
                    
                    for col_status, label, peso in dados_ind['metricas']:
                        if col_status in df_atual.columns:
                            df_elegivel = df_atual[~df_atual[col_status].astype(str).str.contains('⚪', na=False)]
                            total_elegivel = len(df_elegivel)
                            
                            if total_elegivel > 0:
                                em_dia = len(df_elegivel[df_elegivel[col_status].astype(str).str.contains('🟢', na=False)])
                                
                                perc_cobertura = em_dia / total_elegivel
                                pontos_ganhos = perc_cobertura * peso
                                nota_final_indicador += pontos_ganhos
                                
                                # LÓGICA DE CÁLCULO DE META (75%)
                                meta_pct = 0.75 
                                meta_pacientes = math.ceil(total_elegivel * meta_pct)
                                faltam_meta = meta_pacientes - em_dia
                                
                                if perc_cobertura >= meta_pct:
                                    texto_meta = "🎯 **Meta Atingida! (≥ 75%)**"
                                else:
                                    texto_meta = f"📉 Faltam **{faltam_meta}** pacientes para atingir a meta ótima (75%)"
                                
                                st.markdown(f"**{label}**")
                                st.progress(min(perc_cobertura, 1.0))
                                
                                c_met1, c_met2 = st.columns([1, 2])
                                c_met1.metric(label="Cobertura Atual", value=f"{perc_cobertura*100:.1f}%")
                                
                                c_met2.markdown(f"<small>Elegíveis: {total_elegivel} | Em dia: {em_dia}<br>{texto_meta}</small>", unsafe_allow_html=True)
                                
                                nome_indicador_curto = label.split(' (')[0].replace("(A)", "").replace("(B)", "").strip()
                                faltam_total = total_elegivel - em_dia
                                if faltam_total > 0:
                                    with st.expander(f"📋 Ver todos os {faltam_total} pendentes para {nome_indicador_curto}"):
                                        df_pendentes = df_elegivel[df_elegivel[col_status].astype(str).str.contains('🔴|🟠', regex=True, na=False)]
                                        cols_mostrar = ['Nome']
                                        if 'Idade' in df_pendentes.columns: cols_mostrar.append('Idade')
                                        if '🚨 Alerta DPP' in df_pendentes.columns: cols_mostrar.append('🚨 Alerta DPP')
                                        if 'Estratificação de risco cardiovascular' in df_pendentes.columns: cols_mostrar.append('Estratificação de risco cardiovascular')
                                        if 'Busca Ativa' in df_pendentes.columns: cols_mostrar.append('Busca Ativa')
                                        
                                        st.dataframe(
                                            df_pendentes[cols_mostrar],
                                            column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")},
                                            hide_index=True, use_container_width=True
                                        )
                                st.write("") 
                    
                    status_texto, cor = classificar_desempenho(nota_final_indicador)
                    st.markdown(f"""
                    <div style='padding: 12px; border-radius: 8px; border: 2px solid {cor}; background-color: {cor}15; margin-top: 5px;'>
                        <h4 style='margin:0; color: {cor}; text-align: center; font-size: 1.2rem;'>PROJEÇÃO DE NOTA: {nota_final_indicador:.1f} / 100</h4>
                        <p style='margin:0; color: {cor}; text-align: center; font-weight: bold; font-size: 1rem;'>DESEMPENHO {status_texto}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.info("Aguardando carregamento da planilha ou filtro não encontrou pacientes.")
                    
# ----------------- 1. GESTANTE E PUÉRPERA -----------------
with tabs[1]:
    st.header("🤰 Cuidado da Gestante e Puérpera")
    file_gest = st.file_uploader("Carregue GESTAÇÃO E PUERPERIO.csv", key="gest")
    if file_gest:
        df = carregar_dados_esus(file_gest)
        
        # ALERTA DE PARTO IMINENTE (DPP)
        df = limpar_datas(df, ['DPP'])
        if 'DPP' in df.columns:
            df['Dias_Parto'] = (df['DPP'] - datetime.today()).dt.days
            df['🚨 Alerta DPP'] = df['Dias_Parto'].apply(lambda x: "⚠️ Iminente (≤30d)" if pd.notna(x) and 0 <= x <= 30 else ("⚪ N/A"))
            
        df['IG_Num'] = df['IG (DUM) (semanas)'].apply(obter_ig_num := lambda x: int(float(str(x).replace(',', '.'))) if pd.notna(x) and str(x).strip() not in ['-', ''] else 0)
        df['[Status] Estado'] = df['IG_Num'].apply(lambda x: "🤰 Gestante" if 0 < x <= 42 else ("👶 Puérpera" if x >= 43 else "📋 Pós-parto / Sem IG"))
        
        df['[Status] Consultas (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos no pré-natal', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        df['[Status] Captação (≤12 sem)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos até 12 semanas no pré-natal', 0), 1) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        df['[Status] PA (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de medições de pressão arterial', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        df['[Status] Peso/Altura (≥7)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de medições simultâneas de peso e altura', 0), 7) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        df['[Status] VD ACS Gestação (≥3)'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de visitas domiciliares no pré-natal', r.get('Quantidade de visitas domiciliares', 0)), 3) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        df['[Status] Vacina dTpa'] = df.apply(lambda r: "⚪ N/A" if r['[Status] Estado'] == "🤰 Gestante" and r['IG_Num'] < 20 else ("🟢 Ok" if pd.notna(r.get('dTpa')) and r.get('dTpa') != '-' else "🔴 Pendente"), axis=1)

        def testes_1tri(r):
            if r['[Status] Estado'] != "🤰 Gestante": return "⚪ N/A"
            hiv = str(r.get('Exame de HIV no primeiro trimestre', '')).strip().upper() == 'SIM'
            sifilis = str(r.get('Exame de Sífilis no primeiro trimestre', r.get('Exame de Sifilis no primeiro trimestre', ''))).strip().upper() == 'SIM'
            hep_b = str(r.get('Exame de Hepatite B no primeiro trimestre', '')).strip().upper() == 'SIM'
            hep_c = str(r.get('Exame de Hepatite C no primeiro trimestre', '')).strip().upper() == 'SIM'
            return "🟢 Ok" if (hiv and sifilis and hep_b and hep_c) else "🔴 Pendente"
            
        df['[Status] Testes 1ºTri'] = df.apply(testes_1tri, axis=1)

        def testes_3tri(r):
            if r['[Status] Estado'] != "🤰 Gestante": return "⚪ N/A"
            hiv = str(r.get('Exame de HIV no terceiro trimestre', '')).strip().upper() == 'SIM'
            sifilis = str(r.get('Exame de Sífilis no terceiro trimestre', r.get('Exame de Sifilis no terceiro trimestre', ''))).strip().upper() == 'SIM'
            return "🟢 Ok" if (hiv and sifilis) else "🔴 Pendente"
            
        df['[Status] Testes 3ºTri'] = df.apply(testes_3tri, axis=1)
        
        df['[Status] Cons. Puerpério'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos no puerpério', 0), 1) if r['[Status] Estado'] == "👶 Puérpera" else "⚪ N/A", axis=1)
        df['[Status] VD Puerpério'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de visitas domiciliares no puerpério', 0), 1) if r['[Status] Estado'] == "👶 Puérpera" else "⚪ N/A", axis=1)
        df['[Status] Odonto Gestação'] = df.apply(lambda r: checar_qtd(r.get('Quantidade de atendimentos odontológicos no pré-natal', r.get('Quantidade de atendimentos odontológicos', 0)), 1) if r['[Status] Estado'] == "🤰 Gestante" else "⚪ N/A", axis=1)
        
        def construir_mensagem_customizada(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Captação (≤12 sem)', '')): pendencias.append("primeira consulta até a 12ª semana")
            if "🔴" in str(row.get('[Status] Consultas (≥7)', '')): pendencias.append("consultas mínimas de pré-natal")
            if "🔴" in str(row.get('[Status] PA (≥7)', '')): pendencias.append("aferição de pressão arterial")
            if "🔴" in str(row.get('[Status] Peso/Altura (≥7)', '')): pendencias.append("registros de peso e altura")
            if "🔴" in str(row.get('[Status] VD ACS Gestação (≥3)', '')): pendencias.append("visitas do agente de saúde em casa")
            if "🔴" in str(row.get('[Status] Vacina dTpa', '')): pendencias.append("vacina dTpa (tétano e coqueluche)")
            if "🔴" in str(row.get('[Status] Testes 1ºTri', '')): pendencias.append("testes rápidos do 1º trimestre (incluindo Hepatites)")
            if "🔴" in str(row.get('[Status] Testes 3ºTri', '')): pendencias.append("testes rápidos do 3º trimestre")
            if "🔴" in str(row.get('[Status] Odonto Gestação', '')): pendencias.append("avaliação com o dentista")
            if "🔴" in str(row.get('[Status] Cons. Puerpério', '')): pendencias.append("consulta pós-parto na unidade")
            if "🔴" in str(row.get('[Status] VD Puerpério', '')): pendencias.append("visita pós-parto do agente de saúde")
            
            if not pendencias: 
                return f"Olá {row['Nome']}, aqui é da equipe de saúde! Todos os seus registros estão atualizados no sistema. Parabéns pelo cuidado!"
            
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá {row['Nome']}, aqui é da equipe de saúde! Verificamos no sistema que faltam atualizar os seguintes itens: {itens_texto}. Vamos agendar para regularizar?"
            
        df['Msg_Texto'] = df.apply(construir_mensagem_customizada, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'IG (DUM) (semanas)']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        if '🚨 Alerta DPP' in df.columns: cols_view.append('🚨 Alerta DPP')
            
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_gest'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'gest', 'Gestantes')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 2. DESENVOLVIMENTO INFANTIL -----------------
with tabs[2]:
    st.header("👶 Desenvolvimento Infantil (Puericultura)")
    file_inf = st.file_uploader("Carregue DESENVOLVIMENTO INFANTIL.csv", key="inf")
    if file_inf:
        df = carregar_dados_esus(file_inf)
        df['[Status] 1ª Cons. (≤30 dias)'] = df['Idade na primeira consulta'].apply(lambda x: "🟢 Ok" if extrair_dias_vida(x) <= 30 else "🔴 Atrasada/Não feita")
        df['[Status] Consultas (≥9)'] = df['Quantidade de consultas até 24 meses'].apply(lambda x: checar_qtd(x, 9))
        df['[Status] Peso/Altura (≥9)'] = df['Quantidade de medições de peso/altura simultâneas até 24 meses'].apply(lambda x: checar_qtd(x, 9))
        df['[Status] Visita ACS (≥2)'] = df['Quantidade de visitas domiciliares até os 24 meses de idade'].apply(lambda x: checar_qtd(x, 2))
        
        def checar_vacinas(r):
            v_penta = pd.notna(r.get('Difteria, Tétano, Pertusis, Hepatite B, Haemophilus Influenza B', pd.NA)) and r['Difteria, Tétano, Pertusis, Hepatite B, Haemophilus Influenza B'] != '-'
            v_polio = pd.notna(r.get('Poliomielite', pd.NA)) and r['Poliomielite'] != '-'
            v_scr = pd.notna(r.get('Sarampo, Caxumba, Rubéola', pd.NA)) and r['Sarampo, Caxumba, Rubéola'] != '-'
            v_pneumo = pd.notna(r.get('Pneumocócica', pd.NA)) and r['Pneumocócica'] != '-'
            return "🟢 Ok" if (v_penta and v_polio and v_scr and v_pneumo) else "🔴 Incompleta"
            
        df['[Status] Vacinas Básicas'] = df.apply(checar_vacinas, axis=1)
        
        def construir_mensagem_infantil(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] 1ª Cons. (≤30 dias)', '')): pendencias.append("o registro da primeira consulta")
            if "🔴" in str(row.get('[Status] Consultas (≥9)', '')): pendencias.append("as consultas de puericultura")
            if "🔴" in str(row.get('[Status] Peso/Altura (≥9)', '')): pendencias.append("o acompanhamento de peso e altura")
            if "🔴" in str(row.get('[Status] Visita ACS (≥2)', '')): pendencias.append("as visitas do Agente Comunitário")
            if "🔴" in str(row.get('[Status] Vacinas Básicas', '')): pendencias.append("o esquema de vacinas básicas")
            nome_crianca = str(row.get('Nome', 'o bebê')).strip()
            if not pendencias: return f"Olá, responsável por {nome_crianca}! A caderneta está em dia no nosso sistema. Parabéns!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá, responsável por {nome_crianca}! Verificamos no sistema que precisamos atualizar: {itens_texto}. Podemos agendar um horário?"

        df['Msg_Texto'] = df.apply(construir_mensagem_infantil, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_inf'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'inf', 'Criancas')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 3. SAÚDE DA MULHER -----------------
with tabs[3]:
    st.header("👩 Prevenção de Câncer e Saúde da Mulher")
    file_mulher = st.file_uploader("Carregue SAUDE DA MULHER.csv", key="mul")
    if file_mulher:
        df = carregar_dados_esus(file_mulher)
        df = limpar_datas(df, ['Exame de rastreamento de câncer de colo de útero data última avaliação', 'Exame de rastreamento de câncer de mama data Última avaliação', 'Data da última consulta de saúde sexual e reprodutiva'])
        
        df['[Status] Preventivo (25-64a)'] = df.apply(lambda r: status_validade(r['Exame de rastreamento de câncer de colo de útero data última avaliação'], 36) if 25 <= r['Idade_Anos'] <= 64 else "⚪ N/A", axis=1)
        df['[Status] Mamografia (50-69a)'] = df.apply(lambda r: status_validade(r.get('Exame de rastreamento de câncer de mama data Última avaliação'), 24) if 50 <= r['Idade_Anos'] <= 69 else "⚪ N/A", axis=1)
        df['[Status] Vacina HPV (9-14a)'] = df.apply(lambda r: ("🟢 Ok" if str(r.get('HPV', '-')).strip() not in ['-', ''] and pd.notna(r.get('HPV')) else "🔴 Pendente") if 9 <= r['Idade_Anos'] <= 14 else "⚪ N/A", axis=1)
        df['[Status] Saúde Reprod. (14-69a)'] = df.apply(lambda r: status_validade(r['Data da última consulta de saúde sexual e reprodutiva'], 12) if 14 <= r['Idade_Anos'] <= 69 else "⚪ N/A", axis=1)
        
        def construir_mensagem_mulher(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Preventivo (25-64a)', '')): pendencias.append("o preventivo (Papanicolau)")
            if "🔴" in str(row.get('[Status] Mamografia (50-69a)', '')): pendencias.append("a mamografia de rotina")
            if "🔴" in str(row.get('[Status] Vacina HPV (9-14a)', '')): pendencias.append("a vacinação contra o HPV")
            if "🔴" in str(row.get('[Status] Saúde Reprod. (14-69a)', '')): pendencias.append("a consulta anual de saúde da mulher")
            nome = str(row.get('Nome', '')).strip()
            saudacao = f"Olá, responsável por {nome}" if row['Idade_Anos'] <= 14 else f"Olá {nome}"
            if not pendencias: return f"{saudacao}! Seus exames preventivos estão em dia. Parabéns pelo cuidado!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"{saudacao}! Verificamos no sistema que está na hora de atualizar: {itens_texto}. Vamos agendar um horário?"

        df['Msg_Texto'] = df.apply(construir_mensagem_mulher, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_mul'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'mul', 'SaudeMulher')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 4. DIABETES -----------------
with tabs[4]:
    st.header("🩸 Diabetes Mellitus")
    file_diab = st.file_uploader("Carregue DIABETES.csv", key="diab")
    if file_diab:
        df = carregar_dados_esus(file_diab)
        df = limpar_datas(df, ['Data da última avaliação de hemoglobina glicada', 'Data da avaliação dos pés', 'Data da ultima medição de peso e altura'])
        
        df['[Status] HbA1c (12m)'] = df['Data da última avaliação de hemoglobina glicada'].apply(lambda x: status_validade(x, 12))
        df['[Status] Pé Diabético (12m)'] = df['Data da avaliação dos pés'].apply(lambda x: status_validade(x, 12)) 
        df['[Status] Peso/Altura (12m)'] = df['Data da ultima medição de peso e altura'].apply(lambda x: status_validade(x, 12))
        df['[Status] Visitas ACS (≥2)'] = df['Quantidade de visitas domiciliares'].apply(lambda x: checar_qtd(x, 2))
        
        def construir_mensagem_diabetes(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] HbA1c (12m)', '')): pendencias.append("o exame de Hemoglobina Glicada (HbA1c)")
            if "🔴" in str(row.get('[Status] Pé Diabético (12m)', '')): pendencias.append("o exame clínico dos pés")
            if "🔴" in str(row.get('[Status] Peso/Altura (12m)', '')): pendencias.append("a medição de peso e altura")
            if "🔴" in str(row.get('[Status] Visitas ACS (≥2)', '')): pendencias.append("as visitas do Agente Comunitário")
            nome = str(row.get('Nome', '')).strip()
            if not pendencias: return f"Olá {nome}! Seu acompanhamento do diabetes está em dia. Parabéns!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá {nome}! Verificamos no sistema que está na hora de atualizar: {itens_texto}. Vamos agendar um horário?"

        df['Msg_Texto'] = df.apply(construir_mensagem_diabetes, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        if 'Estratificação de risco cardiovascular' in df.columns: cols_view.append('Estratificação de risco cardiovascular')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_diab'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'diab', 'Diabetes')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 5. HIPERTENSÃO -----------------
with tabs[5]:
    st.header("🫀 Hipertensão Arterial")
    file_hiper = st.file_uploader("Carregue HIPERTENSAO.csv", key="hiper")
    if file_hiper:
        df = carregar_dados_esus(file_hiper)
        df = limpar_datas(df, ['Data da última medição de pressão arterial', 'Data da ultima medição de peso e altura'])
        
        df['[Status] Consulta e PA (6m)'] = df['Data da última medição de pressão arterial'].apply(lambda x: status_validade(x, 6))
        df['[Status] Peso/Altura (12m)'] = df['Data da ultima medição de peso e altura'].apply(lambda x: status_validade(x, 12))
        
        def avaliar_visita_acs(row):
            if 'Quantidade de visitas domiciliares' in row and pd.notna(row['Quantidade de visitas domiciliares']) and str(row['Quantidade de visitas domiciliares']).strip() != '-':
                try:
                    val = int(float(str(row['Quantidade de visitas domiciliares']).replace(',', '.')))
                    return "🟢 Ok" if val >= 2 else "🔴 Pendente"
                except:
                    pass
            col_meses = 'Meses desde a última visita domiciliar'
            if col_meses in row and pd.notna(row[col_meses]) and str(row[col_meses]).strip() != '-':
                try:
                    val = int(float(str(row[col_meses]).replace(',', '.')))
                    return "🟢 Ok" if val <= 6 else "🔴 Pendente"
                except:
                    pass
            return "🔴 Pendente"
            
        df['[Status] Visitas ACS'] = df.apply(avaliar_visita_acs, axis=1)
        
        def construir_mensagem_hipertensao(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Consulta e PA (6m)', '')): pendencias.append("a aferição da pressão arterial (semestral)")
            if "🔴" in str(row.get('[Status] Peso/Altura (12m)', '')): pendencias.append("a medição de peso e altura")
            if "🔴" in str(row.get('[Status] Visitas ACS', '')): pendencias.append("a visita do Agente Comunitário")
            nome = str(row.get('Nome', '')).strip()
            if not pendencias: return f"Olá {nome}! Seu acompanhamento da pressão está em dia. Parabéns!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá {nome}! Verificamos no sistema que precisamos atualizar: {itens_texto}. Vamos agendar um horário?"

        df['Msg_Texto'] = df.apply(construir_mensagem_hipertensao, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        if 'Estratificação de risco cardiovascular' in df.columns: cols_view.append('Estratificação de risco cardiovascular')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_hiper'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'hiper', 'Hipertensao')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 6. PESSOA IDOSA -----------------
with tabs[6]:
    st.header("👵 Pessoa Idosa")
    file_idoso = st.file_uploader("Carregue IDOSO.csv", key="idoso")
    if file_idoso:
        df = carregar_dados_esus(file_idoso)
        df = limpar_datas(df, ['IVCF-20 Data do registro'])
        
        df['[Status] Avaliação AMPI (12m)'] = df['IVCF-20 Data do registro'].apply(lambda x: status_validade(x, 12))
        df['[Status] Influenza (12m)'] = df.apply(lambda r: "🟢 Ok" if str(r.get('Influenza (últimos 12 meses)', '-')).strip().upper() == 'SIM' else "🔴 Faltante", axis=1)
        df['[Status] Peso/Altura (≥2)'] = df['Registros de peso e altura simultâneos nos últimos 12 meses'].apply(lambda x: checar_qtd(x, 2))
        df['[Status] Visitas ACS (≥2)'] = df['Quantidade de visitas domiciliares'].apply(lambda x: checar_qtd(x, 2))
        
        def construir_mensagem_idoso(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Avaliação AMPI (12m)', '')): pendencias.append("a avaliação anual de saúde (AMPI/IVCF-20)")
            if "🔴" in str(row.get('[Status] Influenza (12m)', '')): pendencias.append("a dose anual da vacina contra a gripe")
            if "🔴" in str(row.get('[Status] Peso/Altura (≥2)', '')): pendencias.append("a atualização de peso e altura")
            if "🔴" in str(row.get('[Status] Visitas ACS (≥2)', '')): pendencias.append("as visitas do Agente Comunitário")
            nome = str(row.get('Nome', '')).strip()
            if not pendencias: return f"Olá {nome}! Seu acompanhamento preventivo está em dia. Parabéns!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá {nome}! Verificamos no sistema que está na hora de atualizar: {itens_texto}. Vamos agendar um horário?"

        df['Msg_Texto'] = df.apply(construir_mensagem_idoso, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = [c for c in df.columns if '[Status]' in c]
        
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        st.session_state['dados_idoso'] = df_view.copy()
        
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'idoso', 'Idoso')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 7. CADASTROS E VÍNCULOS -----------------
with tabs[7]:
    st.header("📋 Auditoria de Cadastros (Qualidade de Dados)")
    file_cad = st.file_uploader("Carregue CIDADÃOS VINCULADOS.csv", key="cad")
    if file_cad:
        df = carregar_dados_esus(file_cad)
        df = limpar_datas(df, ['Última atualização cadastral'])
        
        df['[Status] Atualização'] = df['Última atualização cadastral'].apply(lambda x: status_validade(x, 24))
        df['[Status] Documento'] = df['CPF/CNS'].apply(lambda x: "🔴 Sem CPF/CNS" if pd.isna(x) or str(x).strip() == '-' else "🟢 Ok")
        df['[Status] Telefone'] = df['Telefone celular'].apply(lambda x: "🔴 Sem Número" if pd.isna(x) or str(x).strip() == '-' else "🟢 Ok")
        
        def construir_mensagem_cadastros(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Atualização', '')): pendencias.append("a renovação do seu cadastro (vencido há 2 anos)")
            if "🔴" in str(row.get('[Status] Documento', '')): pendencias.append("o número do seu CPF ou Cartão do SUS")
            nome = str(row.get('Nome', '')).strip()
            if not pendencias: return f"Olá {nome}! Seu cadastro está em dia. Obrigado!"
            itens_texto = pendencias[0] if len(pendencias) == 1 else ", ".join(pendencias[:-1]) + " e " + pendencias[-1]
            return f"Olá {nome}! Verificamos que o seu cadastro no SUS está incompleto e precisamos atualizar: {itens_texto}. Você poderia nos enviar por aqui?"

        df['Msg_Texto'] = df.apply(construir_mensagem_cadastros, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = ['[Status] Atualização', '[Status] Documento', '[Status] Telefone']
        cols_view = ['Nome']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        cols_view.extend(['CPF/CNS', 'Telefone celular'])
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'cad', 'Auditoria_Cadastros')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)

# ----------------- 8. ACOMPANHAMENTO GERAL -----------------
with tabs[8]:
    st.header("🏥 Saúde Geral e Prevenção de Faltosos")
    file_geral = st.file_uploader("Carregue CONDIÇÕES GERAIS DE SAUDE.csv", key="geral")
    if file_geral:
        df = carregar_dados_esus(file_geral)
        
        col_med = 'Meses desde o último atendimento médico'
        col_enf = 'Meses desde o último atendimento de enfermagem'
        col_vd = 'Meses desde a última visita domiciliar'
        
        for c in [col_med, col_enf, col_vd]:
            df[c] = pd.to_numeric(df[c].astype(str).replace('-', '999'), errors='coerce')
        
        def verificar_sumico(row):
            med = row[col_med] if pd.notna(row[col_med]) else 999
            enf = row[col_enf] if pd.notna(row[col_enf]) else 999
            if med == 999 and enf == 999: return "🔴 Nunca atendido"
            elif med >= 15 and enf >= 15: return "🔴 Ausente ≥ 15 meses"
            else: return "🟢 Em dia"
            
        df['[Status] Vínculo Clínico'] = df.apply(verificar_sumico, axis=1)
        df['[Status] Visita ACS'] = df[col_vd].apply(lambda x: "🔴 S/ Visita ≥ 12 meses" if x >= 12 else "🟢 Ok")

        def construir_mensagem_geral(row):
            pendencias = []
            if "🔴" in str(row.get('[Status] Vínculo Clínico', '')): pendencias.append("uma consulta de rotina médica ou de enfermagem")
            if "🔴" in str(row.get('[Status] Visita ACS', '')): pendencias.append("a visita do seu Agente Comunitário de Saúde")
            nome = str(row.get('Nome', '')).strip()
            if not pendencias: return f"Olá {nome}! Tudo bem? Passando para desejar uma ótima semana!"
            itens_texto = " e ".join(pendencias)
            return f"Olá {nome}! Sentimos sua falta na unidade! Verificamos que precisamos atualizar: {itens_texto}. Vamos agendar um momento?"
            
        df['Msg_Texto'] = df.apply(construir_mensagem_geral, axis=1)
        df['Busca Ativa'] = df.apply(lambda r: gerar_link_wpp_custom(r['Telefone celular'], r['Msg_Texto']), axis=1)
        
        cols_status = ['[Status] Vínculo Clínico', '[Status] Visita ACS']
        cols_view = ['Nome', 'Idade']
        if 'Microárea' in df.columns: cols_view.append('Microárea')
        
        df_view = df[cols_view + cols_status + ['Busca Ativa']]
        df_final = interface_filtros_e_exportacao(df_view, cols_status, 'geral', 'Faltosos_e_Visitas')
        st.dataframe(df_final, column_config={"Busca Ativa": st.column_config.LinkColumn("📲 Busca Ativa", display_text="📲 Contatar")}, hide_index=True, use_container_width=True)
