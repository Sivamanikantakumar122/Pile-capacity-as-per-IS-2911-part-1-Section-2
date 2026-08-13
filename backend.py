import math
import io
import pandas as pd
import numpy as np
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
    """
    Performs pile capacity calculations per IS 2911 Part 1 Sec 2.
    - Option 1: Displays qc (in t/m2) calculated from simple average UCS over spanned socket length.
    - Option 2 & 3: Displays Cu1 (Base UCS) and Cu2 (Avg UCS over socket).
    """
    D = general_inputs['pile_diameter']
    A_p = math.pi * (D ** 2) / 4.0
    gamma_conc = general_inputs['gamma_concrete']
    fos = general_inputs['fos']

    K_i = 1.0
    N_c_default = 9.0

    cumulative_Qs_soil = 0.0
    cumulative_weight_soil = 0.0
    cumulative_PD = 0.0       # Uncapped cumulative overburden pressure
    cumulative_PD_lim = 0.0   # Cumulative limit overburden pressure

    soil_output_rows = []

    # Filter layers into Soil and Rock groups
    soil_layers = [l for l in layers if l['strata'] in ['Sand', 'Clay']]
    rock_layers = [l for l in layers if l['strata'] == 'Rock']

    # ==========================================
    # 1. SOIL CAPACITY CALCULATIONS
    # ==========================================
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

            hcr_display = "N/A"
            pd_lim_display = "N/A"

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
            'Allowable Capacity Qa Tens (MN)': Qa_tens_MN
        })

    soil_df = pd.DataFrame(soil_output_rows)

    # ==========================================
    # 2. ROCK SOCKET CAPACITY CALCULATIONS
    # ==========================================
    rock_summary = None

    if rock_layers:
        first_rock = rock_layers[0]
        rock_type = first_rock.get('rock_type', 1)

        # Target socket length required based on option
        if rock_type == 1:
            req_ls = 2.0 * D
            option_desc = f"Option 1 - Sound Rock (2D = {req_ls:.2f} m)"
        elif rock_type == 2:
            req_ls = 3.0 * D
            option_desc = f"Option 2 - Moderately Weathered (3D = {req_ls:.2f} m)"
        else:
            req_ls = 4.0 * D
            option_desc = f"Option 3 - Soft / Sedimentary Rock (4D = {req_ls:.2f} m)"

        # Calculate actual socket length taken (stop at req_ls)
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
            Cu1_calc = r_ucs  # Last rock layer reached defines Cu1 at base for Opt 2/3

        # Simple Arithmetic Average across spanned rock layers
        avg_ucs_mpa = (sum(spanned_ucs_list) / len(spanned_ucs_list)) if spanned_ucs_list else Cu1_calc

        # --- OPTION 1 LOGIC ---
        if rock_type == 1:
            qc_ton_m2 = avg_ucs_mpa * 101.97  # Convert average UCS in MPa to t/m2

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
                j_val = 0.2 if rqd < 50 else (0.35 if rqd <= 75 else (0.65 if rqd <= 90 else 1.0))

            beta_r = j_val ** 0.45
            
            # Qu = qc * Nj * Nd * Ap + qc * pi * D * ls * alpha_r * beta_r (in tons)
            Qu_rock_tons = (qc_ton_m2 * N_j * N_d * A_p) + (qc_ton_m2 * math.pi * D * actual_ls * alpha_r * beta_r)
            Qu_rock_MN = Qu_rock_tons * 0.00980665
            Qa_rock_MN = Qu_rock_MN / fos

            # Option 1 output dictionary (qc instead of Cu1 and Cu2)
            rock_summary = {
                'Rock Option': option_desc,
                'Socket Length Taken ls (m)': actual_ls,
                'qc - Compressive Strength (t/m²)': qc_ton_m2,
                'Ultimate Rock Capacity Qu (MN)': Qu_rock_MN,
                'Allowable Rock Capacity Qa (MN)': Qa_rock_MN
            }

        # --- OPTIONS 2 & 3 LOGIC (UNTOUCHED) ---
        else:
            Cu2_calc = avg_ucs_mpa
            Nc = 9.0
            alpha_rock = 0.9
            Qu_rock_MN = (Cu1_calc * Nc * A_p) + (alpha_rock * Cu2_calc * math.pi * D * actual_ls)
            Qa_rock_MN = Qu_rock_MN / fos

            rock_summary = {
                'Rock Option': option_desc,
                'Socket Length Taken ls (m)': actual_ls,
                'Cu1 - Base UCS (MPa)': Cu1_calc,
                'Cu2 - Avg UCS (MPa)': Cu2_calc,
                'Ultimate Rock Capacity Qu (MN)': Qu_rock_MN,
                'Allowable Rock Capacity Qa (MN)': Qa_rock_MN
            }

    rock_df = pd.DataFrame([rock_summary]) if rock_summary else pd.DataFrame()

    return soil_df, rock_df


def generate_excel_report(general_inputs: dict, layers: list, soil_df: pd.DataFrame, rock_df: pd.DataFrame) -> bytes:
    """Generates multi-sheet Excel file with strictly isolated Soil and Rock sheets."""
    output = io.BytesIO()

    cleaned_layer_inputs = []
    for l in layers:
        item = {
            'From (m)': l.get('from'),
            'To (m)': l.get('to'),
            'Strata': l.get('strata')
        }
        if l['strata'] in ['Sand', 'Clay']:
            item['Submerged Unit Weight γ\' (kN/m³)'] = l.get('submerged_unit_weight', '')
        if l['strata'] == 'Sand':
            item['Phi (deg)'] = l.get('phi', '')
        elif l['strata'] == 'Clay':
            item['Cu (kPa)'] = l.get('Cu', '')
        elif l['strata'] == 'Rock':
            item['Rock Type'] = l.get('rock_type', '')
            item['UCS (MPa)'] = l.get('ucs_mpa', '')

        cleaned_layer_inputs.append(item)

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame([general_inputs]).to_excel(writer, sheet_name='Sheet1_GeneralInputs', index=False)
        pd.DataFrame(cleaned_layer_inputs).to_excel(writer, sheet_name='Sheet1_LayerInputs', index=False)
        if not soil_df.empty:
            soil_df.to_excel(writer, sheet_name='Sheet2_SoilResults', index=False)
        if not rock_df.empty:
            rock_df.to_excel(writer, sheet_name='Sheet3_RockAnalysis', index=False)

    return output.getvalue()


def create_plots(soil_df: pd.DataFrame):
    """Generates Plotly graphs for soil performance profile."""
    if soil_df.empty:
        empty_fig = go.Figure()
        return empty_fig, empty_fig, empty_fig

    def apply_chart_borders(fig, title, x_label):
        fig.update_layout(
            title=dict(
                text=f"<b>{title}</b>",
                x=0.5,
                xanchor='center',
                y=0.01,
                yanchor='bottom',
                font=dict(size=14, color="#1e3c72")
            ),
            yaxis_title='Depth in Soil (m)',
            yaxis_autorange='reversed',
            plot_bgcolor='white',
            margin=dict(l=50, r=40, t=50, b=65)
        )
        fig.update_xaxes(
            title=dict(text=x_label, font=dict(size=12)),
            side='top',
            showline=True,
            linewidth=1.5,
            linecolor='black',
            mirror=True,
            gridcolor='#f0f0f0'
        )
        fig.update_yaxes(
            showline=True,
            linewidth=1.5,
            linecolor='black',
            mirror=True,
            gridcolor='#f0f0f0'
        )

    # Plot 1: Unit Skin Friction vs Depth
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=soil_df['Unit Skin Friction (kPa)'],
        y=soil_df['Depth (m)'],
        mode='lines+markers',
        name='Unit Skin Friction',
        line=dict(color='#1e3c72', width=2)
    ))
    apply_chart_borders(fig1, 'Unit Skin Friction vs Depth', 'Unit Skin Friction (kPa)')

    # Plot 2: Ultimate End Bearing Resistance vs Depth
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=soil_df['End Bearing Resistance Qb (kN)'],
        y=soil_df['Depth (m)'],
        mode='lines+markers',
        name='End Bearing (Qb)',
        line=dict(color='#ff7f0e', width=2)
    ))
    apply_chart_borders(fig2, 'Ultimate End Bearing Resistance vs Depth', 'Qb (kN)')

    # Plot 3: Ultimate Pile Capacity vs Depth
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=soil_df['Ultimate Bearing Resistance Qu (MN)'],
        y=soil_df['Depth (m)'],
        mode='lines+markers',
        name='Compression (Qu)',
        line=dict(color='#2ca02c', width=2)
    ))
    fig3.add_trace(go.Scatter(
        x=soil_df['Ultimate Capacity Qu Tens (MN)'],
        y=soil_df['Depth (m)'],
        mode='lines+markers',
        name='Tension (Qu)',
        line=dict(color='#d62728', width=2, dash='dash')
    ))
    apply_chart_borders(fig3, 'Ultimate Soil Pile Capacity vs Depth', 'Capacity (MN)')

    return fig1, fig2, fig3
