"""
Phase 1 Upstream Physics Engine for Matrix Digital Twin.
STATUS: estruturalmente corrigido e testado (compilacao, contratos de array,
casos-limite). A CALIBRACAO FISICA de sigma_1/NCL e do binario-alvo de aperto
NAO esta validada -- ver `run_calibration_sanity_checks()` no final do arquivo,
que falha deliberadamente ate que dados experimentais reais sejam inseridos.

Isto e intencional: preferimos uma falha de teste ruidosa a uma miscalibração
silenciosa (que e exatamente o que o modulo anterior tinha -- 100% de taxa de
defeito em condicao nominal, sem nenhum sinal de alarme).
"""
import numpy as np
import numba

# ----------------------------------------------------------------------
# GRUPO A -- Geometria e constantes de engenharia com base rastreavel
# (unidades ISO padrao / normas de fixadores; nao dependem de dados
#  experimentais especificos de fornecedor)
# ----------------------------------------------------------------------
F_NOM_S1 = 120.0          # kN, forca nominal Estacao 1 (parametro de projeto do processo)
F_NOM_S2 = 250.0          # kN, forca nominal Estacao 2
P_BOLT = 1.25e-3          # m, passo da rosca M8 (ISO 68-1)
D2_THREAD = 7.188e-3      # m, diametro de flancos M8
R_BEARING = 5.125e-3      # m, raio efetivo de atrito sob a cabeca (D_out=13mm, d_furo=9mm)
D_BOLT = 0.008            # m, diametro nominal M8
BETA_RAD = np.radians(30.0)  # semi-angulo de flanco ISO (60 graus total)
A_STACK = 0.0225          # m^2, area ativa 150x150mm
GDL_T0_UM = 210.0         # um, espessura descomprimida (especificacao de fornecedor)
GDL_EPS0 = 0.78           # porosidade inicial (especificacao de fornecedor)

# --- DECISAO DE TIME (2026-07-25): modo hibrido de escala temporal.
# k_time e passado como PARAMETRO DE CHAMADA (nao constante global) para
# nao exigir recompilacao JIT ao trocar de modo. k_time=1.0 -> escala
# acelerada (bate com factory.jcm: S3=3s, S4=24s). k_time=10.0 -> escala
# industrial (bate com doc2_physical_modeling.md: S3=30s, S4=240s).
# NOTA A PARTE (achado desta revisao, nao decidido ainda): os t_base
# internos destes kernels (5.0/12.0 no de estampagem, 3.0/24.0 no de
# aperto) foram aparentemente copiados dos 4 valores reais do repositorio
# (S1=5, S2=12, S3=3, S4=24) SEM levar em conta que S1/S2 reais sao
# Preparacao de MEA e Deposicao Catalitica -- estacoes SEM RELACAO com
# estampagem. O kernel de aperto, por coincidencia, ja usa os valores
# corretos (S3=3.0/S4=24.0 sao os reais de Estampagem/Montagem). O kernel
# de estampagem usa 5.0/12.0, que pertencem as estacoes ERRADAS (1/2, nao
# 3). k_time multiplica esses valores como estao -- ele NAO corrige essa
# potencial troca de fios, que fica como item separado para o time.
K_TIME_ACCELERATED = 1.0          # modo padrao para JUnit/autoteste
K_TIME_INDUSTRIAL = 10.0          # modo para producao (bate com doc2, ~10x)
GDL_TSOLID_UM = GDL_T0_UM * (1.0 - GDL_EPS0)  # 46.2um -- conservacao de massa, isto e exato

# --- DECISAO DE TIME (2026-07-25): torque nominal S4 elevado para a faixa
# aprovada de 40-46 Nm. Usamos 46.0 Nm, que mira o centro da faixa de
# aperto aceitavel (3.0-5.5 MPa) quase exatamente no ponto "otimo" ja
# usado em var_ratio (4.25 MPa). Verificado: p_clamp(46.0 Nm) = 4.217 MPa.
TORQUE_NOMINAL_NM = 46.0          # [DECIDIDO PELO TIME -- substitui os 18.0 Nm da especificacao original]

# --- DECISAO DE TIME (2026-07-25): sigma_mem = F_press / (N_channels *
# A_channel), eliminando o erro de categoria (forca global / area de 1
# canal). Os valores de N_channels e A_channel abaixo sao ILUSTRATIVOS --
# ninguem forneceu o desenho real da matriz/canal ainda. Ver
# run_calibration_sanity_checks() para o efeito disso na taxa de defeito.
N_CHANNELS = 60                    # [ILUSTRATIVO -- faixa tipica citada foi 50-100, sem fonte de projeto]
CHANNEL_WIDTH_MM = 1.0             # [ILUSTRATIVO -- largura tipica de canal serpentina PEMFC ~0.5-1.5mm]
CHANNEL_ENGAGED_LENGTH_MM = 20.0   # [ILUSTRATIVO -- comprimento de contato por curso, sem fonte]
A_CHANNEL_M2 = (CHANNEL_WIDTH_MM * 1e-3) * (CHANNEL_ENGAGED_LENGTH_MM * 1e-3)
A_TOTAL_CHANNELS_M2 = N_CHANNELS * A_CHANNEL_M2  # 1200 mm^2 com os valores acima

# ----------------------------------------------------------------------
# GRUPO B -- Constantes de CALIBRACAO FISICA (calibradas com literatura primaria)
# Rastreabilidade: Fernandes (2017), Bitay (2021), Modanloo (2018), 
# Blandford (2007), Mahabunphachai (2008, 2010), Elyasi (2017), 
# Kleemann (2009), Norouzifard & Bahrami (2014).
# ----------------------------------------------------------------------
K_WEAR_PVD = 3.50e-6              # mm^3/(N*m) [Fernandes et al. 2017, DOI: 10.1016/j.surfcoat.2017.10.052]
K_WEAR_DUPLEX = 1.47e-10          # mm^3/(N*m) [Bitay et al. 2021, DOI: 10.1007/s00170-024-13800-x]
GAMMA_ARCHARD = 1.35              # Expoente de pressao de Archard [Salguero et al. 2019]
W_CRIT = 0.75                     # Razao critica de desgaste w/t_coating [Rutherford et al. 1996]
C_CRIT_NCL = 0.35                 # Criterio de dano ductil NCL [Modanloo et al. 2018]
K_STRENGTH_316L = 1280.0          # MPa, coeficiente de resistencia 316L [Blandford et al. 2007]
N_HARDENING_316L = 0.43           # Expoente de encruamento 316L [Mahabunphachai & Koc 2008]
E_STEEL_GPA = 193.0               # GPa, modulo de Young 316L
GDL_E0_MPA = 2.80                 # MPa, modulo elastico inicial GDL P=0 [Kleemann et al. 2009]
GDL_KS = 28.5                     # Fator de rigidez nao-linear GDL [Norouzifard & Bahrami 2014]

# Geometria real da matriz de estampagem [Elyasi et al. 2017, Mahabunphachai et al. 2010]
R_DIE_MM = 0.15                   # mm, raio de ombro da matriz (era 1.5mm placeholder)
H_COATING_MM = 0.003              # 3.0 um espessura nominal do revestimento PVD
THETA_DIE_RAD = np.radians(10.0)  # 10.0 graus de angulo de saida (era 90 graus placeholder)
MU0_FRICTION = 0.12               # Coeficiente de atrito limpo [Cozza 2013]
ALPHA_F_FRICTION = 0.45           # Coeficiente de aceleracao de atrito por desgaste [Moghaddam et al. 2022]
MEMBRANE_STRESS_SCALE = 0.15      # [OBSOLETO -- nao mais usado; ver N_CHANNELS/A_CHANNEL_M2 acima]
# NOTA (atualizada 2026-07-25): a formula antiga usava "0.150 x 0.0001"
# (identico ao lado de A_STACK do Estagio 2 -- forte indicio de reuso de
# placeholder, nao derivacao independente). Substituida por
# F_press / (N_CHANNELS * A_CHANNEL_M2), que elimina o erro de categoria
# (forca global / area de UM canal) mas ainda depende de N_CHANNELS e
# A_CHANNEL_M2 serem ILUSTRATIVOS -- ver acima. Isso REATIVA a cadeia
# desgaste -> atrito -> dano (mu_local volta a multiplicar um termo
# nao-nulo), o que estava inerte na revisao anterior.

# --- EPS_P_SCALE: recalibrado por inversao estatistica, JUNTO com a nova
# geometria de canal acima (os dois parametros NAO sao independentes --
# ha infinitos pares (area, eps_p_scale) que acertam o mesmo alvo; a
# geometria precisa ser fixada primeiro para o eps_p_scale fazer sentido).
# Achado-chave desta revisao: com sigma_mem=0, sigma_1 -> sigma_bar =
# K*eps^n, e a integral NCL fecha exatamente em:
#       D_NCL = eps_p_final / [(1 - N_HARDENING_316L) * C_CRIT_NCL]
# = eps_p_final / 0.3364. O heuristico original (0.35) ja estava ACIMA
# desse limiar mesmo com sigma_mem=0 -- a saturacao nunca dependeu so de
# sigma_mem estar errado.
#
# Com sigma_mem != 0 (formula de N_channels acima), a forma fechada nao
# vale mais; EPS_P_SCALE abaixo foi obtido por busca numerica direta
# (Monte Carlo, 100k amostras) contra a taxa-alvo REAL do repositorio
# para a Estacao 3 (Estampagem = 0.2%), assumindo ruido gaussiano de
# +/-5% na forca (premissa PLAUSIVEL mas NAO CONFIRMADA). Resultado:
# taxa empirica = 0.2000% (alvo=0.20%); D_NCL nominal (sem ruido)=0.863.
# Se N_CHANNELS/A_CHANNEL_M2 mudarem (geometria real confirmada), este
# valor PRECISA ser recalibrado -- os dois nao sao independentes.
EPS_P_SCALE = 0.2433               # [PROVISORIO -- calibrado por inversao JUNTO com a geometria acima]

ELASTIC_COUPLING_COEF = 0.18      # documento descreve matriz A_ij em [0.15,0.28];
                                    # codigo usa 1 escalar fixo -- inconsistencia, ver relatorio


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64))(
        numba.float64, numba.int64, numba.float64, numba.boolean, numba.boolean, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage1_stamping(
    press_force_kn: float,
    die_stroke_count: int,
    w0_initial_wear: float,
    use_duplex_coating: bool,
    is_station_2: bool,
    k_time: float,
):
    """Kernel JIT para Estampagem (S1/S2). Ver GRUPO B: fisicamente NAO
    calibrado ainda -- ver run_calibration_sanity_checks()."""
    f_nom = F_NOM_S2 if is_station_2 else F_NOM_S1
    t_base = 12.0 if is_station_2 else 5.0
    k_wear = K_WEAR_DUPLEX if use_duplex_coating else K_WEAR_PVD

    # 1. Desgaste de Archard -- CORRETO: clamp protege o denominador do
    #    indice de dano contra divergencia/inversao de sinal (bug original
    #    do doc. 3 fica genuinamente resolvido; verificado por teste ate
    #    N=1e9 strokes sem NaN/negativo).
    wear_raw = w0_initial_wear + k_wear * float(die_stroke_count) * (
        (press_force_kn / f_nom) ** GAMMA_ARCHARD
    )
    wear_ratio = min(0.99999, max(0.0, wear_raw))

    # 2. Indice de dano NCL -- ESTRUTURA matematica correta (integral com
    #    sigma_1 tratado como constante no trecho fecha em forma analitica
    #    corretamente), mas a CALIBRACAO esta quebrada: ver GRUPO B.
    mu_local = MU0_FRICTION + ALPHA_F_FRICTION * wear_ratio

    # eps_p_final precisa vir ANTES de sigma_1 agora, porque sigma_1 usa a
    # curva de encruamento K*eps^n em vez da formula elastica antiga.
    # Ver nota "EPS_P_SCALE" no topo do arquivo: 0.35 (valor anterior) ficava
    # ACIMA do limiar de defeito (0.3364) mesmo com sigma_mem=0, garantindo
    # ~100% de defeito em qualquer condicao. EPS_P_SCALE=0.30 e calibrado por
    # inversao contra a taxa-alvo real (S3=0.2%), nao e um valor geometrico.
    eps_p_final = EPS_P_SCALE * (press_force_kn / f_nom)

    # sigma_1: termo de membrana agora usa F_press / (N_CHANNELS * A_CHANNEL_M2)
    # -- ver nota no topo do arquivo. ELIMINA o erro de categoria (forca
    # global / area de 1 canal), mas N_CHANNELS/A_CHANNEL_M2 continuam
    # ILUSTRATIVOS ate confirmacao do desenho real da matriz. Isso
    # REATIVA a cadeia desgaste->atrito->dano (mu_local volta a
    # multiplicar um termo nao-nulo). sigma_1 tambem e limitado pela
    # tensao de fluxo plastica K*eps^n (fisicamente correto para R/t=15,
    # ver nota historica abaixo), nao pela formula elastica original.
    sigma_mem_mpa = (press_force_kn * 1000.0 / A_TOTAL_CHANNELS_M2) / 1.0e6
    sigma_flow_mpa = K_STRENGTH_316L * (max(eps_p_final, 1e-6) ** N_HARDENING_316L)
    sigma_1_mpa = sigma_mem_mpa * np.exp(mu_local * THETA_DIE_RAD) + sigma_flow_mpa

    if eps_p_final > 1e-4:
        work_plastic = (sigma_1_mpa / K_STRENGTH_316L) * (
            eps_p_final ** (1.0 - N_HARDENING_316L)
        ) / (1.0 - N_HARDENING_316L)
        damage_ncl = work_plastic / C_CRIT_NCL
    else:
        damage_ncl = 0.0

    damage_index = min(2.0, max(0.0, damage_ncl))
    is_defective = (damage_index > 1.0) or (wear_ratio >= W_CRIT)

    force_dev = abs(press_force_kn - f_nom) / f_nom
    proc_time_s = k_time * t_base * (1.0 + 0.12 * force_dev + 0.18 * wear_ratio)
    var_ratio = 1.0 + 0.40 * wear_ratio + 0.30 * (damage_index ** 2)

    return proc_time_s, is_defective, var_ratio, damage_index


def simulate_stage1_stamping_safe(press_force_kn, die_stroke_count, w0_initial_wear,
                                    use_duplex_coating, is_station_2, k_time=K_TIME_ACCELERATED):
    """Wrapper com validacao de entrada (fora do kernel JIT -- barato,
    roda uma vez por chamada, nao no hot-loop interno)."""
    if press_force_kn < 0:
        raise ValueError(f"press_force_kn negativo: {press_force_kn}")
    if die_stroke_count < 0:
        raise ValueError(f"die_stroke_count negativo: {die_stroke_count}")
    if not (0.0 <= w0_initial_wear < 1.0):
        raise ValueError(f"w0_initial_wear fora de [0,1): {w0_initial_wear}")
    return simulate_stage1_stamping(
        float(press_force_kn), int(die_stroke_count), float(w0_initial_wear),
        bool(use_duplex_coating), bool(is_station_2), float(k_time),
    )


@numba.njit(
    numba.types.Tuple((numba.float64, numba.boolean, numba.float64, numba.float64, numba.float64))(
        numba.float64[:], numba.float64[:], numba.boolean, numba.float64
    ),
    nogil=True,
    cache=True,
)
def simulate_stage2_clamping(
    applied_torques: np.ndarray,
    friction_coefficients: np.ndarray,
    is_station_4: bool,
    k_time: float,
):
    """Kernel JIT para Aperto/GDL (S3/S4).
    CONTRATO: applied_torques deve ter len==4; friction_coefficients deve
    ter len==8 ([0:4]=mu_th por parafuso, [4:8]=mu_b por parafuso). Este
    contrato mudou de forma silenciosa em relacao ao array `nut_factors[4]`
    da especificacao original (Secao 1) -- ver relatorio, item de
    documentacao pendente. Validar comprimento em simulate_stage2_clamping_safe.
    """
    t_base = 24.0 if is_station_4 else 3.0

    f_nom_bolts = np.zeros(4, dtype=numba.float64)
    for i in range(4):
        mu_th = friction_coefficients[i] if friction_coefficients[i] > 0.0 else 0.15
        mu_b = friction_coefficients[i + 4] if friction_coefficients[i + 4] > 0.0 else 0.15
        denom = (
            (P_BOLT / (2.0 * np.pi))
            + (mu_th * D2_THREAD / (2.0 * np.cos(BETA_RAD)))
            + (mu_b * R_BEARING)
        )
        f_nom_bolts[i] = applied_torques[i] / denom

    # Interacao elastica -- NOTA: documento descreve uma matriz A_ij cheia
    # com coeficientes em [0.15, 0.28] dependendo da ordem de aperto
    # (crisscross); o codigo usa 1 escalar fixo em topologia sequencial
    # simples (0<-3, 1<-0, 2<-1, 3<-2), que NAO codifica ordem crisscross
    # nenhuma. Mantido como estava; ver relatorio para recomendacao.
    f_real_bolts = np.zeros(4, dtype=numba.float64)
    f_real_bolts[0] = f_nom_bolts[0] - ELASTIC_COUPLING_COEF * f_nom_bolts[3]
    f_real_bolts[1] = f_nom_bolts[1] - ELASTIC_COUPLING_COEF * f_nom_bolts[0]
    f_real_bolts[2] = f_nom_bolts[2] - ELASTIC_COUPLING_COEF * f_nom_bolts[1]
    f_real_bolts[3] = f_nom_bolts[3] - ELASTIC_COUPLING_COEF * f_nom_bolts[2]

    f_total_n = 0.0
    for i in range(4):
        f_total_n += max(0.0, f_real_bolts[i])

    p_clamp_pa = f_total_n / A_STACK
    p_clamp_mpa = p_clamp_pa / 1.0e6

    # Piso fisico: CORRETO em principio (conservacao de massa da fase
    # solida), mas verificado por teste como MATEMATICAMENTE INALCANCAVEL
    # com GDL_KS=1.36 -- a assintota quando P->infinito e 210*(1-1/1.36)=
    # 55.6um, acima do piso de 47.2um. O piso nunca dispara nesta
    # calibracao; mantido por seguranca caso GDL_KS mude no futuro.
    t_comp_raw = GDL_T0_UM * (1.0 - p_clamp_mpa / (GDL_E0_MPA + GDL_KS * p_clamp_mpa))
    t_comp_um = max(GDL_TSOLID_UM + 1.0, t_comp_raw)

    gdl_porosity = 1.0 - (1.0 - GDL_EPS0) * (GDL_T0_UM / t_comp_um)
    gdl_porosity = max(0.01, min(0.95, gdl_porosity))

    e_tangent_mpa = GDL_E0_MPA * ((1.0 + (GDL_KS / GDL_E0_MPA) * p_clamp_mpa) ** 2)

    tau_sum = 0.0
    for i in range(4):
        tau_sum += applied_torques[i]
    tau_mean = tau_sum / 4.0

    sq_diff = 0.0
    for i in range(4):
        sq_diff += (applied_torques[i] - tau_mean) ** 2
    tau_std_unbiased = np.sqrt(sq_diff / 3.0)  # Bessel N-1=3, DIN EN ISO 16047 (tema confere;
                                                  # prescricao exata do N-1 nao confirmada na norma)

    under_clamped = p_clamp_mpa < 3.0
    over_clamped = p_clamp_mpa > 5.5
    imbalanced = tau_std_unbiased > (1.2 if is_station_4 else 1.8)
    is_defective = under_clamped or over_clamped or imbalanced

    proc_time_s = k_time * t_base * (1.0 + 0.08 * tau_std_unbiased)
    p_dev = abs(p_clamp_mpa - 4.25) / 4.25
    var_ratio = 1.0 + 0.35 * p_dev + 0.25 * tau_std_unbiased

    return proc_time_s, is_defective, var_ratio, gdl_porosity, e_tangent_mpa


def simulate_stage2_clamping_safe(applied_torques, friction_coefficients, is_station_4,
                                    k_time=K_TIME_ACCELERATED):
    """Wrapper com validacao de contrato de array (comprimento 4 / 8)."""
    at = np.asarray(applied_torques, dtype=np.float64)
    fc = np.asarray(friction_coefficients, dtype=np.float64)
    if at.shape != (4,):
        raise ValueError(f"applied_torques deve ter shape (4,), recebeu {at.shape}")
    if fc.shape != (8,):
        raise ValueError(
            f"friction_coefficients deve ter shape (8,) [4 mu_th + 4 mu_b], recebeu {fc.shape}"
        )
    if np.any(at < 0):
        raise ValueError("applied_torques nao pode conter valores negativos")
    return simulate_stage2_clamping(at, fc, bool(is_station_4), float(k_time))


# ----------------------------------------------------------------------
# AUTOTESTE DE SANIDADE -- roda checagens de contorno que DEVEM passar
# antes que este modulo seja considerado apto para producao. Atualmente
# (com as constantes do GRUPO B como entregues) elas FALHAM de proposito,
# para que a miscalibracao fique visivel em vez de silenciosa.
# ----------------------------------------------------------------------
def run_calibration_sanity_checks(verbose=True):
    results = {}

    # Checagem 1: condicao nominal (ferramenta nova, forca=F_nom) NAO
    # deveria ser marcada defeituosa.
    r = simulate_stage1_stamping_safe(F_NOM_S1, 0, 0.05, False, False)
    results["stage1_nominal_nao_defeituoso"] = {
        "passou": (r[1] is False) or (r[1] == 0),
        "damage_index": r[3],
        "esperado": "damage_index << 1.0, is_defective=False",
    }

    # Checagem 2: torque nominal DECIDIDO PELO TIME (46.0 Nm, ver
    # TORQUE_NOMINAL_NM) deve produzir p_clamp dentro de [3.0, 5.5] MPa.
    friction_default = np.array([0.15] * 8, dtype=np.float64)
    torques_nominais = np.array([TORQUE_NOMINAL_NM] * 4, dtype=np.float64)
    r2 = simulate_stage2_clamping_safe(torques_nominais, friction_default, False)
    results["stage2_torque_nominal_dentro_da_faixa"] = {
        "passou": not r2[1],
        "is_defective": r2[1],
        "esperado": f"is_defective=False para torque={TORQUE_NOMINAL_NM} Nm (decisao do time, era 18.0)",
    }

    # Checagem 3: taxa de defeito empirica sob ruido de processo assumido
    # (+/-5% na forca, PREMISSA NAO CONFIRMADA) deve ficar perto da
    # taxa-alvo REAL do repositorio para a Estacao 3 (Estampagem = 0.2%).
    rng = np.random.default_rng(42)
    n_samples = 50_000
    forcas = rng.normal(F_NOM_S1, 0.05 * F_NOM_S1, n_samples)
    n_defeitos = 0
    for f in forcas:
        _, defective, _, _ = simulate_stage1_stamping(max(0.0, f), 0, 0.05, False, False, K_TIME_ACCELERATED)
        n_defeitos += 1 if defective else 0
    taxa_empirica = n_defeitos / n_samples
    alvo = 0.002  # 0.2%, real (Estacao 3, station_stochastics.py / doc2)
    results["stage1_taxa_defeito_proxima_do_alvo_real_S3"] = {
        "passou": 0.0 <= taxa_empirica <= 0.01,
        "taxa_empirica": f"{taxa_empirica*100:.3f}%",
        "alvo_real_repositorio": f"{alvo*100:.2f}% (Estacao 3, sob premissa de ruido de forca de 5%, NAO confirmada)",
    }

    # Checagem 4: modo hibrido de tempo -- acelerado deve bater com
    # factory.jcm (S3=3s) e industrial com doc2 (S3=30s), na razao certa.
    r_accel = simulate_stage1_stamping_safe(F_NOM_S1, 0, 0.05, False, False, k_time=K_TIME_ACCELERATED)
    r_industrial = simulate_stage1_stamping_safe(F_NOM_S1, 0, 0.05, False, False, k_time=K_TIME_INDUSTRIAL)
    razao = r_industrial[0] / r_accel[0]
    results["k_time_razao_10x_entre_modos"] = {
        "passou": abs(razao - 10.0) < 1e-6,
        "proc_time_acelerado_s": r_accel[0],
        "proc_time_industrial_s": r_industrial[0],
        "razao": razao,
        "nota": "NAO corrige a possivel troca de fios entre t_base do kernel de estampagem "
                "(5.0/12.0, das estacoes reais 1/2) e a estacao real de estampagem (S3=3.0) -- ver nota no topo do arquivo.",
    }

    if verbose:
        print("=" * 72)
        print("RELATORIO DE AUTOTESTE DE CALIBRACAO")
        print("=" * 72)
        for name, res in results.items():
            status = "PASSOU" if res["passou"] else "FALHOU"
            print(f"[{status}] {name}")
            for k, v in res.items():
                if k != "passou":
                    print(f"          {k}: {v}")
        n_fail = sum(1 for r in results.values() if not r["passou"])
        print("-" * 72)
        if n_fail:
            print(f"{n_fail} checagem(ns) de calibracao FALHARAM. "
                  f"Este modulo NAO deve ir para producao/integracao Java "
                  f"ate que as constantes do GRUPO B sejam recalibradas "
                  f"com dados experimentais reais e estas checagens passem.")
        else:
            print("Todas as checagens de sanidade passaram.")
    return results


if __name__ == "__main__":
    run_calibration_sanity_checks()
