import io
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go

PHI_TABLE = [0, 5, 10, 15, 20, 25, 30, 35, 40]
N_GAMMA_TABLE = [0, 0.45, 1.22, 2.65, 5.39, 10.88, 22.4, 48.03, 109.41]


def get_n_gamma(phi: float) -> float:
    """Interpolate N_gamma based on internal friction angle phi."""
    if phi <= 0:
        return 0.0
    if phi >= 40:
        return 109.41
    return float(np.interp(phi, PHI_TABLE, N_GAMMA_TABLE))


def calculate_pile_capacity(general_inputs: dict, layers: list):
    """Performs pile capacity calculations per IS 2911 Part 1 Sec 2."""
    D = general_inputs['pile_diameter']
    A_p = math.pi * (D**2) / 4.0
    gamma_conc = general_inputs['gamma_concrete']
    fos = general_inputs['fos']

    K_i = 1.0
    N_c_default = 9.0

    cumulative_Qs_soil = 0.0
    cumulative_weight_soil = 0.0
    cumulative_PD = 0.0
    cumulative_PD_lim = 0.0

    soil_output_rows = []

    soil_layers = [l for l in layers if l['strata'] in ['Sand', 'Clay']]
    rock_layers = [l for l in layers if l['strata'] == 'Rock']

    # 1. SOIL CAPACITY CALCULATIONS
    for idx, layer in enumerate(soil_layers):
        depth_from = layer['from']
        depth_to = layer['to']
        thickness = abs(depth_to - depth_from)
        strata = layer['strata']
        gamma_sub = layer.get('submerged_unit_weight', 0.0)

        layer_PDi = gamma_sub * thickness
        cumulative_PD += layer_PDi

        if strata == 'Sand':
            phi = layer.get('phi', 0.0)
            if phi < 30:
                H_cr = 15.0 * D
            elif phi <= 40:
                H_cr = 17.5 * D
            else:
                H_cr = 20.0 * D

            delta_PD_lim = gamma_sub * H_cr
            cumulative_PD_lim += delta_PD_lim

            PD = min(cumulative_PD, cumulative_PD_lim)
            hcr_display = H_cr
            pd_lim_display = cumulative_PD_lim

            N_gamma = get_n_gamma(phi)
            N_q = 0.178 * math.exp(0.1609 * phi)
            delta = math.radians(phi)
            A_s = math.pi * D * thickness

            unit_end_bearing = (0.5 * D * gamma_sub * N_gamma) + (PD * N_q)
            Qb_layer = A_p * unit_end_bearing

            unit_skin_friction = K_i * PD * math.tan(delta)
            layer_Qs = unit_skin_friction * A_s
            cumulative_Qs_soil += layer_Qs

        else:  # Clay
            Cu = layer.get('Cu', 0.0)
            PD = cumulative_PD
            cumulative_PD_lim += layer_PDi

            hcr_display = 'N/A'
            pd_lim_display = 'N/A'

            if Cu < 40:
                alpha = 1.0
            elif 40 <= Cu <= 200:
                alpha = 0.23 + 0.77 * math.exp(-0.023 * (Cu - 40))
            else:
                alpha = 0.23

            A_s = math.pi * D * thickness
            unit_end_bearing = N_c_default * Cu
            Qb_layer = A_p * unit_end_bearing

            unit_skin_friction = alpha * Cu
            layer_Qs = unit_skin_friction * A_s
            cumulative_Qs_soil += layer_Qs

        layer_weight = gamma_conc * A_p * thickness
        cumulative_weight_soil += layer_weight

        Qu_comp_kN = cumulative_Qs_soil + Qb_layer
        Qu_comp_MN = Qu_comp_kN / 1000.0
        Qa_comp_MN = Qu_comp_MN / fos

        Qu_tens_kN = cumulative_weight_soil + cumulative_Qs_soil
        Qu_tens_MN = Qu_tens_kN / 1000.0
        Qa_tens_MN = Qu_tens_MN / fos

        soil_output_rows.append({
            'Depth (m)': depth_to,
            'Thickness (m)': thickness,
            'Strata': strata,
            'Uncapped PD (kN/m²)': cumulative_PD,
            'Critical Height Hcr (m)': hcr_display,
            'Cumulative PD Lim (kN/m²)': pd_lim_display,
            'Effective Overburden Pressure PD (kN/m²)': PD,
            'Unit Skin Friction (kPa)': unit_skin_friction,
            'Skin Friction Qs (kN)': cumulative_Qs_soil,
            'Unit End Bearing (kPa)': unit_end_bearing,
            'End Bearing Resistance Qb (kN)': Qb_layer,
            'Ultimate Bearing Resistance Qu (MN)': Qu_comp_MN,
            'Allowable Bearing Capacity Qa (MN)': Qa_comp_MN,
            'Ultimate Capacity Qu Tens (MN)': Qu_tens_MN,
            'Allowable Capacity Qa Tens (MN)': Qa_tens_MN,
        })

    soil_df = pd.DataFrame(soil_output_rows)

    # 2. ROCK SOCKET CALCULATIONS
    rock_summary = None

    if rock_layers:
        first_rock = rock_layers[0]
        rock_type = first_rock.get('rock_type', 1)

        if rock_type == 1:
            req_ls = 2.0 * D
            option_desc = f'Option 1 - Sound Rock (2D = {req_ls:.2f} m)'
        elif rock_type == 2:
            req_ls = 3.0 * D
            option_desc = f'Option 2 - Moderately Weathered (3D = {req_ls:.2f} m)'
        else:
            req_ls = 4.0 * D
            option_desc = f'Option 3 - Soft / Sedimentary Rock (4D = {req_ls:.2f} m)'

        socket_remaining = req_ls
        actual_ls = 0.0
        spanned_ucs_list = []
        Cu1_calc = first_rock.get('ucs_mpa', 0.0)

        for r_layer in rock_layers:
            if socket_remaining <= 0:
                break
            r_thick = abs(r_layer['to'] - r_layer['from'])
            penetration = min(socket_remaining, r_thick)
            r_ucs = r_layer.get('ucs_mpa', 0.0)

            spanned_ucs_list.append(r_ucs)
            actual_ls += penetration
            socket_remaining -= penetration
            Cu1_calc = r_ucs

        avg_ucs_mpa = (
            (sum(spanned_ucs_list) / len(spanned_ucs_list))
            if spanned_ucs_list
            else Cu1_calc
        )

        if rock_type == 1:
            qc_ton_m2 = avg_ucs_mpa * 101.97
            spacing = first_rock.get('spacing_discontinuities', '>300')
            N_j = 0.4 if spacing == '>300' else (0.25 if spacing == '100-300' else 0.1)
            N_d = 0.8 + 0.2 * (actual_ls / D)
            alpha_r = 5.0 / math.sqrt(avg_ucs_mpa) if avg_ucs_mpa > 0 else 0

            ed = first_rock.get('Ed', None)
            ei = first_rock.get('Ei', None)
            rqd = first_rock.get('rqd', 80)

            if ed and ei and ei != 0:
                j_val = ed / ei
            else:
                j_val = (
                    0.2
                    if rqd < 50
                    else (0.35 if rqd <= 75 else (0.65 if rqd <= 90 else 1.0))
                )

            beta_r = j_val**0.45
            Qu_rock_tons = (qc_ton_m2 * N_j * N_d * A_p) + (
                qc_ton_m2 * math.pi * D * actual_ls * alpha_r * beta_r
            )
            Qu_rock_MN = Qu_rock_tons * 0.00980665
            Qa_rock_MN = Qu_rock_MN / fos

            rock_summary = {
                'Rock Option': option_desc,
                'Socket Length Taken ls (m)': actual_ls,
                'qc - Compressive Strength (t/m²)': qc_ton_m2,
                'Nj - Discontinuity Factor': N_j,
                'Nd - Depth Factor': N_d,
                'alpha_r - Socket Friction Factor': alpha_r,
                'beta_r - Mass Factor': beta_r,
                'Ultimate Rock Capacity Qu (MN)': Qu_rock_MN,
                'Allowable Rock Capacity Qa (MN)': Qa_rock_MN,
            }
        else:
            Cu2_calc = avg_ucs_mpa
            Nc = 9.0
            alpha_rock = 0.9
            Qu_rock_MN = (Cu1_calc * Nc * A_p) + (
                alpha_rock * Cu2_calc * math.pi * D * actual_ls
            )
            Qa_rock_MN = Qu_rock_MN / fos

            rock_summary = {
                'Rock Option': option_desc,
                'Socket Length Taken ls (m)': actual_ls,
                'Cu1 - Base UCS (MPa)': Cu1_calc,
                'Cu2 - Avg UCS (MPa)': Cu2_calc,
                'Ultimate Rock Capacity Qu (MN)': Qu_rock_MN,
                'Allowable Rock Capacity Qa (MN)': Qa_rock_MN,
            }

    rock_df = pd.DataFrame([rock_summary]) if rock_summary else pd.DataFrame()
    return soil_df, rock_df


# 3. LATERAL CAPACITY MODULE
def get_h_from_n(n_val: float) -> float:
    """Interpolates modulus of subgrade reaction constant (h) in kN/m3 from SPT-N value."""
    n_pts = [0.0, 4.0, 10.0, 35.0, 50.0]
    h_pts = [0.2, 0.2, 1.4, 5.0, 12.0]
    if n_val <= 0:
        h_base = 0.2
    elif n_val >= 50:
        h_base = 12.0
    else:
        h_base = float(np.interp(n_val, n_pts, h_pts))
    return h_base * 1000.0


def get_k1_from_qu(qu_val: float) -> float:
    """Interpolates subgrade reaction k1 in kN/m3 from qu (kPa)."""
    qu_pts = [25.0, 50.0, 100.0, 200.0, 400.0, 800.0]
    k1_pts = [4.5, 9.0, 18.0, 36.0, 72.0, 144.0]
    if qu_val <= 25.0:
        k1_base = 4.5
    else:
        k1_base = float(np.interp(qu_val, qu_pts, k1_pts))
    return k1_base * 1000.0


def calculate_lateral_capacity(general_inputs: dict, lateral_inputs: dict):
    """Computes Depth of Fixity (Zf/Lf), Lateral Load (H), and Moment (MF) per Word specifications."""
    D = general_inputs['pile_diameter']
    fck = lateral_inputs['fck']
    L1 = lateral_inputs.get('L1', 0.0)
    strata_type = lateral_inputs['strata_type']
    delta_allow_mm = lateral_inputs.get('allowable_deflection_mm', 5.0)
    delta_m = delta_allow_mm / 1000.0

    # Pile Rigidity
    E_c = 5000.0 * math.sqrt(fck) * 1000.0  # kN/m2
    I_p = (math.pi * (D**4)) / 64.0  # m4
    EI = E_c * I_p  # kN.m2

    # Head fixity condition
    is_fixed = L1 == 0.0
    head_condition = (
        'Fixed Head (L1 = 0 m)' if is_fixed else f'Free Head (L1 = {L1:.2f} m)'
    )

    if 'Sand' in strata_type:
        N_val = lateral_inputs.get('avg_n_value', 15.0)
        eta_h = get_h_from_n(N_val)
        T = (EI / eta_h) ** (1.0 / 5.0)
        x_ratio = L1 / T

        if is_fixed:
            Lf_over_T = 1.85 + 0.35 * math.exp(-0.65 * x_ratio)
        else:
            Lf_over_T = 1.76 + 0.14 * math.exp(-0.45 * x_ratio)

        Zf = Lf_over_T * T
        stiffness_name = 'Stiffness Factor T'
        stiffness_val = T
        subgrade_name = 'Modulus of Subgrade Reaction ηh'
        subgrade_val = f'{eta_h:.1f} kN/m³'
    else:
        cu = lateral_inputs.get('cu_val_kpa', 50.0)
        qu = 2.0 * cu
        k1 = get_k1_from_qu(qu)
        K = (0.3 * k1) / (1.5 * D)
        R = (EI / (K * D)) ** (1.0 / 4.0)
        x_ratio = L1 / R

        if is_fixed:
            Lf_over_R = 1.45 + 0.70 * math.exp(-0.62 * x_ratio)
        else:
            Lf_over_R = 1.32 + 0.30 * math.exp(-0.52 * x_ratio)

        Zf = Lf_over_R * R
        stiffness_name = 'Stiffness Factor R'
        stiffness_val = R
        subgrade_name = 'Modulus of Subgrade Reaction K'
        subgrade_val = f'{K:.1f} kN/m³'

    Le = L1 + Zf

    # Lateral Capacity & Moment
    if is_fixed:
        H_design_kN = (12.0 * EI * delta_m) / (Le**3) if Le > 0 else 0.0
        MF_kN_m = H_design_kN * Le
    else:
        H_design_kN = (3.0 * EI * delta_m) / (Le**3) if Le > 0 else 0.0
        MF_kN_m = (H_design_kN * Le) / 2.0

    lateral_summary = {
        'Parameter': [
            'Depth of Fixity, Zf',
            'Permissible Deflection',
            'Lateral Load Capacity, H',
            'Max Bending Moment, MF',
            'Pile Head Condition',
            'Pile Diameter (D)',
            'Characteristic Strength (fck)',
            'Flexural Rigidity (EI)',
            subgrade_name,
            stiffness_name,
            'Free Standing Length (L1)',
            'Equivalent Cantilever Length (Le = L1 + Zf)',
        ],
        'Value': [
            f'{Zf:.3f} m',
            f'{delta_allow_mm:.1f} mm',
            f'{H_design_kN:.2f} kN',
            f'{MF_kN_m:.2f} kN·m',
            head_condition,
            f'{D:.3f} m',
            f'{fck:.1f} N/mm²',
            f'{EI:.2f} kN·m²',
            subgrade_val,
            f'{stiffness_val:.3f} m',
            f'{L1:.2f} m',
            f'{Le:.3f} m',
        ],
    }

    lateral_df = pd.DataFrame(lateral_summary)
    return lateral_df, Zf, H_design_kN, delta_allow_mm, head_condition, MF_kN_m


def generate_excel_report(
    general_inputs: dict,
    layers: list,
    soil_df: pd.DataFrame,
    rock_df: pd.DataFrame,
) -> bytes:
    """Generates multi-sheet Excel file."""
    output = io.BytesIO()
    cleaned_layer_inputs = []
    for l in layers:
        item = {
            'From (m)': l.get('from'),
            'To (m)': l.get('to'),
            'Strata': l.get('strata'),
        }
        if l['strata'] in ['Sand', 'Clay']:
            item['Submerged Unit Weight γ\' (kN/m³)'] = l.get(
                'submerged_unit_weight', ''
            )
        if l['strata'] == 'Sand':
            item['Phi (deg)'] = l.get('phi', '')
        elif l['strata'] == 'Clay':
            item['Cu (kPa)'] = l.get('Cu', '')
        elif l['strata'] == 'Rock':
            item['Rock Type'] = l.get('rock_type', '')
            item['UCS (MPa)'] = l.get('ucs_mpa', '')
        cleaned_layer_inputs.append(item)

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame([general_inputs]).to_excel(
            writer, sheet_name='Sheet1_GeneralInputs', index=False
        )
        pd.DataFrame(cleaned_layer_inputs).to_excel(
            writer, sheet_name='Sheet1_LayerInputs', index=False
        )
        if not soil_df.empty:
            soil_df.to_excel(writer, sheet_name='Sheet2_SoilResults', index=False)
        if not rock_df.empty:
            rock_df.to_excel(writer, sheet_name='Sheet3_RockAnalysis', index=False)

    return output.getvalue()


def create_plots(soil_df: pd.DataFrame):
    """Generates Plotly graphs for soil performance profile starting exactly from (0, 0)."""
    if soil_df.empty:
        empty_fig = go.Figure()
        return empty_fig, empty_fig, empty_fig

    max_d = float(soil_df['Depth (m)'].max())
    max_depth_limit = max_d * 1.05 if max_d > 0 else 10.0

    depth_pts = [0.0] + soil_df['Depth (m)'].tolist()
    skin_pts = [0.0] + soil_df['Unit Skin Friction (kPa)'].tolist()
    qb_pts = [0.0] + soil_df['End Bearing Resistance Qb (kN)'].tolist()
    qu_comp_pts = [0.0] + soil_df['Ultimate Bearing Resistance Qu (MN)'].tolist()
    qu_tens_pts = [0.0] + soil_df['Ultimate Capacity Qu Tens (MN)'].tolist()

    def apply_chart_borders(fig, title, x_label):
        fig.update_layout(
            title=dict(
                text=f'<b>{title}</b>',
                x=0.5,
                xanchor='center',
                y=0.01,
                yanchor='bottom',
                font=dict(size=14, color='#1e3c72'),
            ),
            yaxis_title='Depth in Soil (m)',
            plot_bgcolor='white',
            margin=dict(l=50, r=40, t=50, b=65),
        )
        fig.update_xaxes(
            title=dict(text=x_label, font=dict(size=12)),
            side='top',
            rangemode='tozero',
            showline=True,
            linewidth=1.5,
            linecolor='black',
            mirror=True,
            gridcolor='#f0f0f0',
        )
        fig.update_yaxes(
            range=[max_depth_limit, 0.0],
            showline=True,
            linewidth=1.5,
            linecolor='black',
            mirror=True,
            gridcolor='#f0f0f0',
        )

    fig1 = go.Figure()
    fig1.add_trace(
        go.Scatter(
            x=skin_pts,
            y=depth_pts,
            mode='lines+markers',
            name='Unit Skin Friction',
            line=dict(color='#1e3c72', width=2),
        )
    )
    apply_chart_borders(
        fig1, 'Unit Skin Friction vs Depth', 'Unit Skin Friction (kPa)'
    )

    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=qb_pts,
            y=depth_pts,
            mode='lines+markers',
            name='End Bearing (Qb)',
            line=dict(color='#ff7f0e', width=2),
        )
    )
    apply_chart_borders(
        fig2, 'Ultimate End Bearing Resistance vs Depth', 'Qb (kN)'
    )

    fig3 = go.Figure()
    fig3.add_trace(
        go.Scatter(
            x=qu_comp_pts,
            y=depth_pts,
            mode='lines+markers',
            name='Compression (Qu)',
            line=dict(color='#2ca02c', width=2),
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=qu_tens_pts,
            y=depth_pts,
            mode='lines+markers',
            name='Tension (Qu)',
            line=dict(color='#d62728', width=2, dash='dash'),
        )
    )
    apply_chart_borders(
        fig3, 'Ultimate Soil Pile Capacity vs Depth', 'Capacity (MN)'
    )

    return fig1, fig2, fig3
