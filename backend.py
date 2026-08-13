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
    Performs layer-by-layer pile capacity calculations per IS 2911 Part 1 Sec 2.
    """
    D = general_inputs['pile_diameter']
    A_p = math.pi * (D ** 2) / 4.0
    gamma_conc = general_inputs['gamma_concrete']
    fos = general_inputs['fos']

    K_i = 1.0
    N_c_default = 9.0

    cumulative_Qs = 0.0
    cumulative_weight = 0.0

    output_rows = []
    rock_inputs_list = []

    # Identify all rock strata for multi-layer socket calculations
    rock_layers = [l for l in layers if l['strata'] == 'Rock']

    for idx, layer in enumerate(layers):
        depth_from = layer['from']
        depth_to = layer['to']
        thickness = abs(depth_to - depth_from)
        strata = layer['strata']

        # Effective Overburden Pressure (PDi)
        gamma_sub = layer.get('submerged_unit_weight', 0.0)
        PDi = gamma_sub * thickness

        # --- SAND STRATA ---
        if strata == 'Sand':
            phi = layer.get('phi', 0.0)
            if phi < 30:
                H_cr = 15.0 * D
            elif phi > 40:
                H_cr = 20.0 * D
            else:
                H_cr = 17.5 * D

            PD_lim = gamma_sub * H_cr
            PD = min(PDi, PD_lim)

            N_gamma = get_n_gamma(phi)
            N_q = 0.178 * math.exp(0.1609 * phi)
            delta = math.radians(phi)
            A_s = math.pi * D * thickness

            unit_end_bearing = (0.5 * D * gamma_sub * N_gamma) + (PD * N_q)
            Qb_layer = A_p * unit_end_bearing

            unit_skin_friction = K_i * PD * math.tan(delta)
            layer_Qs = unit_skin_friction * A_s
            cumulative_Qs += layer_Qs

        # --- CLAY STRATA ---
        elif strata == 'Clay':
            Cu = layer.get('Cu', 0.0)

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
            cumulative_Qs += layer_Qs

        # --- ROCK STRATA ---
        else:
            rock_type = layer.get('rock_type', 1)
            ucs_mpa = layer.get('ucs_mpa', 0.0)

            # Max socket length based on option
            if rock_type == 1:
                desired_ls = 2.0 * D
            elif rock_type == 2:
                desired_ls = 3.0 * D
            else:
                desired_ls = 4.0 * D

            ls = min(thickness, desired_ls)

            if rock_type == 1:
                qc_ton_m2 = ucs_mpa * 101.97
                spacing = layer.get('spacing_discontinuities', '>300')
                if spacing == '>300':
                    N_j = 0.4
                elif spacing == '100-300':
                    N_j = 0.25
                else:
                    N_j = 0.1

                N_d = 0.8 + 0.2 * (ls / D)
                alpha_r = 5.0 / math.sqrt(ucs_mpa) if ucs_mpa > 0 else 0

                ed = layer.get('Ed', None)
                ei = layer.get('Ei', None)
                rqd = layer.get('rqd', 80)

                if ed and ei and ei != 0:
                    j_val = ed / ei
                else:
                    if rqd < 50:
                        j_val = 0.2
                    elif 50 <= rqd <= 75:
                        j_val = 0.35
                    elif 75 < rqd <= 90:
                        j_val = 0.65
                    else:
                        j_val = 1.0

                beta_r = j_val ** 0.45
                Qu_rock_tons = (qc_ton_m2 * N_j * N_d * A_p) + (qc_ton_m2 * math.pi * D * ls * alpha_r * beta_r)
                Qu_rock_MN = Qu_rock_tons * 0.00980665

                Cu1_calc = ucs_mpa
                Cu2_calc = ucs_mpa

            else:  # Rock Option 2 & 3
                # Determine Cu1 (UCS at socket end) and Cu2 (Average UCS across socket length)
                socket_remaining = ls
                weighted_ucs_sum = 0.0
                Cu1_calc = ucs_mpa  # default fallback

                curr_layer_index = layers.index(layer)
                for r_idx in range(curr_layer_index, len(layers)):
                    if socket_remaining <= 0:
                        break
                    r_layer = layers[r_idx]
                    if r_layer['strata'] != 'Rock':
                        break

                    r_thick = abs(r_layer['to'] - r_layer['from'])
                    penetration = min(socket_remaining, r_thick)
                    r_ucs = r_layer.get('ucs_mpa', 0.0)

                    weighted_ucs_sum += r_ucs * penetration
                    socket_remaining -= penetration
                    Cu1_calc = r_ucs  # Last rock layer reached by socket end defines Cu1

                Cu2_calc = (weighted_ucs_sum / ls) if ls > 0 else ucs_mpa
                
                Nc = 9.0
                alpha_rock = 0.9
                
                # Formula: Qu = Cu1 * Nc * Ap + alpha * Cu2 * pi() * D * ls
                Qu_rock_MN = (Cu1_calc * Nc * (math.pi * D ** 2 / 4.0)) + (alpha_rock * Cu2_calc * math.pi * D * ls)

            Qa_rock_MN = Qu_rock_MN / fos

            rock_inputs_list.append({
                'Layer Index': idx + 1,
                'Rock Type Option': rock_type,
                'Cu1 - Base UCS (MPa)': Cu1_calc,
                'Cu2 - Avg UCS (MPa)': Cu2_calc,
                'Socket Length ls (m)': ls,
                'Ultimate Capacity Qu (MN)': Qu_rock_MN,
                'Allowable Capacity Qa (MN)': Qa_rock_MN
            })

            unit_end_bearing = Qu_rock_MN * 1000 / A_p if A_p else 0
            Qb_layer = Qu_rock_MN * 1000
            unit_skin_friction = 0

        # Layer weight calculation
        layer_weight = gamma_conc * A_p * thickness
        cumulative_weight += layer_weight

        # Ultimate & Allowable Capacities
        Qu_comp_kN = cumulative_Qs + Qb_layer
        Qu_comp_MN = Qu_comp_kN / 1000.0
        Qa_comp_MN = Qu_comp_MN / fos

        Qu_tens_kN = cumulative_weight + cumulative_Qs
        Qu_tens_MN = Qu_tens_kN / 1000.0
        Qa_tens_MN = Qu_tens_MN / fos

        output_rows.append({
            'Depth (m)': depth_to,
            'Strata': strata,
            'Unit Skin Friction (kPa)': unit_skin_friction,
            'Skin Friction Qs (kN)': cumulative_Qs,
            'Unit End Bearing (kPa)': unit_end_bearing,
            'End Bearing Resistance Qb (kN)': Qb_layer,
            'Ultimate Capacity Qu Comp (MN)': Qu_comp_MN,
            'Allowable Capacity Qa Comp (MN)': Qa_comp_MN,
            'Ultimate Capacity Qu Tens (MN)': Qu_tens_MN,
            'Allowable Capacity Qa Tens (MN)': Qa_tens_MN
        })

    results_df = pd.DataFrame(output_rows)
    rock_df = pd.DataFrame(rock_inputs_list) if rock_inputs_list else pd.DataFrame()

    return results_df, rock_df


def generate_excel_report(general_inputs: dict, layers: list, results_df: pd.DataFrame, rock_df: pd.DataFrame) -> bytes:
    """Generates multi-sheet Excel file in memory."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame([general_inputs]).to_excel(writer, sheet_name='General Inputs', index=False)
        pd.DataFrame(layers).to_excel(writer, sheet_name='Layer Inputs', index=False)
        results_df.to_excel(writer, sheet_name='Results', index=False)
        if not rock_df.empty:
            rock_df.to_excel(writer, sheet_name='Rock Analysis', index=False)

    return output.getvalue()


def create_plots(results_df: pd.DataFrame):
    """Generates Plotly graphs with X-axis on top and full outer borders."""
    
    # Common layout options for top X-axis and full borders
    def apply_chart_borders(fig, title, x_label):
        fig.update_layout(
            title=dict(text=title, x=0.5, xanchor='center'),
            yaxis_title='Depth (m)',
            yaxis_autorange='reversed',
            plot_bgcolor='white',
            margin=dict(l=40, r=40, t=60, b=40)
        )
        fig.update_xaxes(
            title=x_label,
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
        x=results_df['Unit Skin Friction (kPa)'],
        y=results_df['Depth (m)'],
        mode='lines+markers',
        name='Unit Skin Friction',
        line=dict(color='#1e3c72', width=2)
    ))
    apply_chart_borders(fig1, 'Unit Skin Friction vs Depth', 'Unit Skin Friction (kPa)')

    # Plot 2: Ultimate End Bearing Resistance vs Depth
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=results_df['End Bearing Resistance Qb (kN)'],
        y=results_df['Depth (m)'],
        mode='lines+markers',
        name='End Bearing (Qb)',
        line=dict(color='#ff7f0e', width=2)
    ))
    apply_chart_borders(fig2, 'Ultimate End Bearing Resistance vs Depth', 'Qb (kN)')

    # Plot 3: Ultimate Pile Capacity vs Depth (Compression vs Tension)
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=results_df['Ultimate Capacity Qu Comp (MN)'],
        y=results_df['Depth (m)'],
        mode='lines+markers',
        name='Compression (Qu)',
        line=dict(color='#2ca02c', width=2)
    ))
    fig3.add_trace(go.Scatter(
        x=results_df['Ultimate Capacity Qu Tens (MN)'],
        y=results_df['Depth (m)'],
        mode='lines+markers',
        name='Tension (Qu)',
        line=dict(color='#d62728', width=2, dash='dash')
    ))
    apply_chart_borders(fig3, 'Ultimate Pile Capacity vs Depth', 'Capacity (MN)')

    return fig1, fig2, fig3
