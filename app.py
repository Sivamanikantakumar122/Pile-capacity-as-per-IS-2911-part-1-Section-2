import math
import streamlit as st
import pandas as pd
from backend import calculate_pile_capacity, generate_excel_report, create_plots

st.set_page_config(
    page_title="Pile Capacity Calculator - IS 2911",
    layout="wide"
)

# --------------------------
# SIDEBAR / HIGHLIGHTED LEFT
# --------------------------
st.sidebar.title("Pile Capacity Calculation")
st.sidebar.subheader("As per IS 2911 Part 1 Sec 2")
st.sidebar.markdown("**Developed by:** Siva Manikanta kumar")

st.sidebar.markdown("---")

# User inputs left blank with placeholders
project_name = st.sidebar.text_input("Project Name", value="", placeholder="Enter project name...")
designer_name = st.sidebar.text_input("Designer", value="", placeholder="Enter designer name...")

st.sidebar.markdown("---")
st.sidebar.header("General Parameters")

pile_diameter = st.sidebar.number_input("Pile Diameter, D (m)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
pile_area = math.pi * (pile_diameter ** 2) / 4.0
st.sidebar.text(f"Area of Pile (m²): {pile_area:.4f}")

gw_depth = st.sidebar.number_input("Ground Water Depth (m)", min_value=0.0, value=2.0, step=0.5)
gamma_concrete = st.sidebar.number_input("Density of Concrete (kN/m³)", min_value=15.0, value=24.0, step=0.5)
fos = st.sidebar.select_slider("Factor of Safety (FOS)", options=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], value=2.5)

# --------------------------
# MAIN PAGE CONTENT
# --------------------------
st.title("Geotechnical Pile Capacity Analysis")
st.markdown("### Soil & Rock Layer Input")

if "layers" not in st.session_state:
    st.session_state["layers"] = []

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    if st.button("➕ Add Layer"):
        st.session_state["layers"].append({
            "from": 0.0, "to": 2.0, "strata": "Sand",
            "submerged_unit_weight": 10.0, "phi": 30.0, "Cu": 50.0,
            "rock_type": 1, "ucs_mpa": 10.0, "Cu1": 10.0, "Cu2": 10.0,
            "spacing_discontinuities": ">300", "rqd": 80, "Ed": None, "Ei": None
        })

with col_btn2:
    if st.button("🗑️ Clear All Layers"):
        st.session_state["layers"] = []

layers_to_delete = []

for i, layer in enumerate(st.session_state["layers"]):
    with st.expander(f"Layer {i+1} Details", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            layer['from'] = st.number_input(f"From Depth (m)", value=float(layer['from']), key=f"from_{i}")
        with c2:
            layer['to'] = st.number_input(f"To Depth (m)", value=float(layer['to']), key=f"to_{i}")
        with c3:
            layer['strata'] = st.selectbox(f"Strata Type", ["Sand", "Clay", "Rock"], index=["Sand", "Clay", "Rock"].index(layer['strata']), key=f"strata_{i}")
        with c4:
            if st.button(f"Remove Layer {i+1}", key=f"del_{i}"):
                layers_to_delete.append(i)

        if layer['strata'] == "Sand":
            sc1, sc2 = st.columns(2)
            with sc1:
                layer['submerged_unit_weight'] = st.number_input("Submerged Unit Weight γ' (kN/m³)", value=float(layer.get('submerged_unit_weight', 10.0)), key=f"gamma_{i}")
            with sc2:
                layer['phi'] = st.number_input("Angle of Internal Friction ϕ (°)", value=float(layer.get('phi', 30.0)), key=f"phi_{i}")

        elif layer['strata'] == "Clay":
            cc1, cc2 = st.columns(2)
            with cc1:
                layer['submerged_unit_weight'] = st.number_input("Submerged Unit Weight γ' (kN/m³)", value=float(layer.get('submerged_unit_weight', 10.0)), key=f"gamma_c_{i}")
            with cc2:
                layer['Cu'] = st.number_input("Unconfined Shear Strength Cu (kN/m²)", value=float(layer.get('Cu', 50.0)), key=f"cu_{i}")

        elif layer['strata'] == "Rock":
            rc1, rc2 = st.columns(2)
            with rc1:
                rock_opts = [
                    "1. Sound relatively homogenous rock (Granite, Gneiss)",
                    "2. Moderately weathered, closely jointed (Schist, Slate)",
                    "3. Soft rock / Sedimentary (Shale, Sandstone, Mudstone)"
                ]
                selected_opt = st.selectbox("Rock Type Category", rock_opts, key=f"rocktype_{i}")
                layer['rock_type'] = int(selected_opt[0])

            if layer['rock_type'] == 1:
                with rc2:
                    layer['ucs_mpa'] = st.number_input("Uniaxial Compressive Strength (MPa)", value=float(layer.get('ucs_mpa', 15.0)), key=f"ucs_{i}")
                
                st.markdown("*Option 1 Parameters (Optional/Advanced)*")
                rc3, rc4, rc5, rc6 = st.columns(4)
                with rc3:
                    layer['spacing_discontinuities'] = st.selectbox("Discontinuity Spacing (mm)", [">300", "100-300", "30-100"], key=f"spacing_{i}")
                with rc4:
                    layer['rqd'] = st.number_input("RQD (%)", value=80, min_value=0, max_value=100, key=f"rqd_{i}")
                with rc5:
                    ed_val = st.number_input("In-situ Modulus Ed (MPa)", value=0.0, key=f"ed_{i}")
                    layer['Ed'] = ed_val if ed_val > 0 else None
                with rc6:
                    ei_val = st.number_input("Intact Modulus Ei (MPa)", value=0.0, key=f"ei_{i}")
                    layer['Ei'] = ei_val if ei_val > 0 else None

            else:  # Rock Options 2 & 3
                with rc2:
                    rc_col1, rc_col2 = st.columns(2)
                    with rc_col1:
                        layer['Cu1'] = st.number_input("UCS at Socket Base / End, Cu1 (MPa)", value=float(layer.get('Cu1', 10.0)), key=f"cu1_{i}")
                    with rc_col2:
                        layer['Cu2'] = st.number_input("Avg UCS over Socket Length, Cu2 (MPa)", value=float(layer.get('Cu2', 10.0)), key=f"cu2_{i}")

if layers_to_delete:
    for index in sorted(layers_to_delete, reverse=True):
        st.session_state["layers"].pop(index)
    st.rerun()

st.markdown("---")

if st.button("🚀 Run Analysis", type="primary"):
    if not st.session_state["layers"]:
        st.error("Please add at least one layer to perform the calculation.")
    else:
        gen_inputs = {
            'project_name': project_name if project_name else "N/A",
            'designer': designer_name if designer_name else "N/A",
            'pile_diameter': pile_diameter,
            'pile_area': pile_area,
            'gw_depth': gw_depth,
            'gamma_concrete': gamma_concrete,
            'fos': fos
        }

        results_df, rock_df = calculate_pile_capacity(gen_inputs, st.session_state["layers"])

        st.subheader("Results Summary")
        st.dataframe(results_df.style.format(precision=3), use_container_width=True)

        if not rock_df.empty:
            st.subheader("Rock Socket Analysis")
            st.dataframe(rock_df.style.format(precision=3), use_container_width=True)

        excel_bytes = generate_excel_report(gen_inputs, st.session_state["layers"], results_df, rock_df)
        st.download_button(
            label="📥 Download Excel Report",
            data=excel_bytes,
            file_name="Pile_Capacity_IS2911_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.markdown("---")
        st.subheader("Performance Curves")

        fig1, fig2, fig3 = create_plots(results_df)
        g_col1, g_col2 = st.columns(2)
        with g_col1:
            st.plotly_chart(fig1, use_container_width=True)
            st.plotly_chart(fig2, use_container_width=True)
        with g_col2:
            st.plotly_chart(fig3, use_container_width=True)
