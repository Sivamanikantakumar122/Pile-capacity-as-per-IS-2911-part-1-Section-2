import math
import datetime
import streamlit as st
import pandas as pd
from backend import calculate_pile_capacity, generate_excel_report, create_plots

# --------------------------
# PAGE CONFIG & STYLING
# --------------------------
st.set_page_config(
    page_title="Pile Capacity - IS 2911",
    page_icon="🏗️",
    layout="wide"
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .hero-banner {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        padding: 24px 30px;
        border-radius: 12px;
        color: white;
        margin-bottom: 25px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .hero-banner h1 { color: white !important; font-weight: 700; margin-bottom: 5px !important; }
    .hero-banner p { color: #d0e1fd; font-size: 1.05rem; margin-bottom: 12px; }
    .badge {
        background-color: rgba(255, 255, 255, 0.2);
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] { background-color: #f1f5f9; }
    div.stButton > button { border-radius: 8px; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --------------------------
# SIDEBAR METADATA & PARAMS
# --------------------------
with st.sidebar:
    st.markdown("### 🏗️ **Pile Capacity**")
    st.caption("Bored Cast-in-situ Concrete Piles (Part 1 Sec 2)")
    st.markdown("**Developed by:** Siva Manikanta kumar")
    st.markdown("---")

    st.subheader("📋 Project Info")
    project_name = st.text_input("Project Name", value="", placeholder="e.g. Metro")
    project_location = st.text_input("Project Location", value="", placeholder="e.g. Attili")
    designer_name = st.text_input("Designer Name", value="", placeholder="e.g. Siva")
    bh_number = st.text_input("Borehole ID", value="", placeholder="e.g. BH-02")

    st.markdown("---")
    st.subheader("⚙️ General Parameters")

    pile_diameter = st.number_input("Pile Diameter, D (m)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    pile_area = math.pi * (pile_diameter ** 2) / 4.0
    st.info(f"📐 **Pile Area (Ap):** `{pile_area:.4f} m²`", icon="ℹ️")

    gw_depth = st.number_input("Ground Water Depth (m)", min_value=0.0, value=2.0, step=0.5)
    gamma_concrete = st.number_input("Concrete Density (kN/m³)", min_value=15.0, value=24.0, step=0.5)
    fos = st.select_slider("Factor of Safety (FOS)", options=[1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], value=2.5)

# --------------------------
# HERO BANNER
# --------------------------
st.markdown("""
    <div class="hero-banner">
        <h1>Pile Capacity Engine</h1>
        <p>Comprehensive axial bearing & rock socket capacity analysis strictly adhering to IS 2911 Part 1 Sec 2.</p>
        <span class="badge">IS 2911:2010</span>
        <span class="badge">Soil & Rock Strata</span>
        <span class="badge">Interactive Curves</span>
    </div>
""", unsafe_allow_html=True)

# --------------------------
# SOIL PROFILE INPUTS
# --------------------------
st.markdown("### 🧱 Stratigraphy & Soil Layers")

if "layers" not in st.session_state:
    st.session_state["layers"] = []

layers_to_delete = []

for i, layer in enumerate(st.session_state["layers"]):
    if i > 0:
        layer['from'] = st.session_state["layers"][i-1]['to']

    icon = "🏖️" if layer['strata'] == "Sand" else ("🧱" if layer['strata'] == "Clay" else "🪨")

    with st.expander(f"{icon} Layer {i+1}: {layer['strata']} ({layer['from']}m to {layer['to']}m)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.number_input(f"From Depth (m)", value=float(layer['from']), disabled=True, key=f"from_{i}")
        with c2:
            layer['to'] = st.number_input(f"To Depth (m)", value=float(layer['to']), min_value=float(layer['from']) + 0.1, step=0.5, key=f"to_{i}")
        with c3:
            layer['strata'] = st.selectbox(f"Strata Type", ["Sand", "Clay", "Rock"], index=["Sand", "Clay", "Rock"].index(layer['strata']), key=f"strata_{i}")
        with c4:
            st.write("")
            st.write("")
            if st.button(f"❌ Remove", key=f"del_{i}"):
                layers_to_delete.append(i)

        if layer['strata'] == "Sand":
            sc1, sc2 = st.columns(2)
            with sc1:
                layer['submerged_unit_weight'] = st.number_input("Submerged Unit Weight γ' (kN/m³)", value=float(layer.get('submerged_unit_weight', 10.0)), key=f"gamma_{i}")
            with sc2:
                layer['phi'] = st.number_input("Internal Friction Angle ϕ (°)", value=float(layer.get('phi', 30.0)), key=f"phi_{i}")

        elif layer['strata'] == "Clay":
            cc1, cc2 = st.columns(2)
            with cc1:
                layer['submerged_unit_weight'] = st.number_input("Submerged Unit Weight γ' (kN/m³)", value=float(layer.get('submerged_unit_weight', 10.0)), key=f"gamma_c_{i}")
            with cc2:
                layer['Cu'] = st.number_input("Unconfined Shear Strength Cu (kPa)", value=float(layer.get('Cu', 50.0)), key=f"cu_{i}")

        elif layer['strata'] == "Rock":
            rc1, rc2 = st.columns(2)
            with rc1:
                rock_opts = [
                    "1. Sound relatively homogenous rock (Granite, Gneiss)",
                    "2. Moderately weathered, closely jointed (Schist, Slate)",
                    "3. Soft rock / Sedimentary (Shale, Sandstone, Mudstone)"
                ]
                selected_opt = st.selectbox("Rock Classification", rock_opts, key=f"rocktype_{i}")
                layer['rock_type'] = int(selected_opt[0])

            with rc2:
                layer['ucs_mpa'] = st.number_input("Uniaxial Compressive Strength UCS (MPa)", value=float(layer.get('ucs_mpa', 15.0)), key=f"ucs_{i}")

            if layer['rock_type'] == 1:
                st.caption("⚙️ Option 1 Optional Properties")
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

if layers_to_delete:
    for index in sorted(layers_to_delete, reverse=True):
        st.session_state["layers"].pop(index)
    st.rerun()

st.write("")

# Add & Clear Buttons
col_b1, col_b2, _ = st.columns([1.3, 1.5, 3])
with col_b1:
    if st.button("➕ Add Soil Layer", use_container_width=True):
        last_to = st.session_state["layers"][-1]['to'] if st.session_state["layers"] else 0.0
        st.session_state["layers"].append({
            "from": last_to, "to": last_to + 2.0, "strata": "Sand",
            "submerged_unit_weight": 10.0, "phi": 30.0, "Cu": 50.0,
            "rock_type": 1, "ucs_mpa": 10.0,
            "spacing_discontinuities": ">300", "rqd": 80, "Ed": None, "Ei": None
        })
        st.rerun()

with col_b2:
    if st.button("🗑️ Clear All Layers", use_container_width=True):
        st.session_state["layers"] = []
        st.rerun()

st.markdown("---")

# --------------------------
# EXECUTION & RESULTS TABS
# --------------------------
if st.button("⚡ Run Analysis", type="primary", use_container_width=True):
    if not st.session_state["layers"]:
        st.error("⚠️ Please add at least one soil/rock layer before running analysis.")
    else:
        gen_inputs = {
            'project_name': project_name if project_name else "N/A",
            'project_location': project_location if project_location else "N/A",
            'designer': designer_name if designer_name else "N/A",
            'bh_number': bh_number if bh_number else "N/A",
            'pile_diameter': pile_diameter,
            'pile_area': pile_area,
            'gw_depth': gw_depth,
            'gamma_concrete': gamma_concrete,
            'fos': fos
        }

        soil_df, rock_df = calculate_pile_capacity(gen_inputs, st.session_state["layers"])

        # SOIL CAPACITY VALUES
        total_soil_depth = soil_df['Depth (m)'].max() if not soil_df.empty else 0.0
        soil_qu_comp = soil_df['Ultimate Bearing Resistance Qu (MN)'].iloc[-1] if not soil_df.empty else 0.0
        soil_qa_comp = soil_df['Allowable Bearing Capacity Qa (MN)'].iloc[-1] if not soil_df.empty else 0.0
        soil_qa_tens = soil_df['Allowable Capacity Qa Tens (MN)'].iloc[-1] if not soil_df.empty else 0.0

        st.markdown("### 📊 Performance Summary")

        # 1. Soil Capacity Summary
        st.markdown("##### **1. Soil Capacity Summary**")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Depth in Soil", f"{total_soil_depth:.2f} m")
        s2.metric("Soil Ult. Compression (Qu)", f"{soil_qu_comp:.2f} MN")
        s3.metric("Soil Allow. Compression (Qa)", f"{soil_qa_comp:.2f} MN", delta=f"FOS = {fos}")
        s4.metric("Soil Allow. Tension (Qa)", f"{soil_qa_tens:.2f} MN")

        # 2. Rock Socket Summary (if rock exists)
        if not rock_df.empty:
            st.write("")
            st.markdown("##### **2. Rock Socket Capacity Summary**")
            r1, r2, r3 = st.columns(3)
            rock_ls = rock_df['Socket Length Taken ls (m)'].iloc[0]
            rock_qu = rock_df['Ultimate Rock Capacity Qu (MN)'].iloc[0]
            rock_qa = rock_df['Allowable Rock Capacity Qa (MN)'].iloc[0]

            r1.metric("Socketed Depth in Rock", f"{rock_ls:.2f} m")
            r2.metric("Rock Ult. Compression (Qu)", f"{rock_qu:.2f} MN")
            r3.metric("Rock Allow. Compression (Qa)", f"{rock_qa:.2f} MN", delta=f"FOS = {fos}")

        st.write("")

        # 4 TABS LAYOUT
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Capacity Results Table", 
            "📈 Depth vs Capacity Curves", 
            "🪨 Rock Socket Details", 
            "📄 Design Summary Report"
        ])

        # TAB 1: Soil Results Table Only
        with tab1:
            st.markdown("#### **Soil Layer-by-Layer Calculation Sheet**")
            if not soil_df.empty:
                display_cols = [
                    'Depth (m)', 
                    'Thickness (m)',
                    'Strata',
                    'Uncapped PD (kN/m²)',
                    'Critical Height Hcr (m)',
                    'Cumulative PD Lim (kN/m²)',
                    'Effective Overburden Pressure PD (kN/m²)',
                    'Skin Friction Qs (kN)',
                    'End Bearing Resistance Qb (kN)', 
                    'Ultimate Bearing Resistance Qu (MN)',
                    'Allowable Bearing Capacity Qa (MN)'
                ]
                st.dataframe(soil_df[display_cols], use_container_width=True)
            else:
                st.info("No soil strata defined in the inputs.", icon="ℹ️")

            excel_bytes = generate_excel_report(gen_inputs, st.session_state["layers"], soil_df, rock_df)
            st.download_button(
                label="📥 Download Detailed Excel Report",
                data=excel_bytes,
                file_name=f"Pile_Capacity_{bh_number if bh_number else 'Report'}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # TAB 2: Curves (Soil)
        with tab2:
            st.markdown("#### **Performance Profile Graphs (Soil)**")
            fig1, fig2, fig3 = create_plots(soil_df)
            
            g_col1, g_col2 = st.columns(2)
            with g_col1:
                st.plotly_chart(fig1, use_container_width=True)
                st.plotly_chart(fig2, use_container_width=True)
            with g_col2:
                st.plotly_chart(fig3, use_container_width=True)

        # TAB 3: Rock Socket Details Only
        with tab3:
            st.markdown("#### **Rock Socket Parameters & Capacity Summary**")
            if not rock_df.empty:
                st.dataframe(rock_df.style.format(precision=3), use_container_width=True)
            else:
                st.info("No rock strata identified in the inputs.", icon="ℹ️")

        # TAB 4: Design Summary Report
        with tab4:
            st.markdown("## 📄 Design Summary Report")
            st.markdown("---")

            # Project Information
            st.markdown("### **PROJECT INFORMATION**")
            st.markdown(f"* **Project:** {project_name if project_name else 'N/A'}")
            st.markdown(f"* **Location:** {project_location if project_location else 'N/A'}")
            st.markdown(f"* **Designer:** {designer_name if designer_name else 'N/A'}")
            st.markdown(f"* **Borehole ID / Site:** {bh_number if bh_number else 'N/A'}")
            st.markdown(f"* **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.markdown("* **Standard / Engine:** IS 2911 Part 1 Sec 2 Engine v1.0")

            st.markdown("---")

            # Pile Properties
            st.markdown("### **PILE PROPERTIES**")
            st.markdown(f"* **Diameter (D):** {pile_diameter:.3f} m")
            st.markdown(f"* **Cross-sectional Area (Ap):** {pile_area:.4f} m²")
            st.markdown(f"* **Soil Depth Analyzed:** {total_soil_depth:.2f} m")
            if not rock_df.empty:
                st.markdown(f"* **Rock Socket Length (ls):** {rock_df['Socket Length Taken ls (m)'].iloc[0]:.2f} m")
            st.markdown("* **Type:** Bored Cast-in-situ Concrete Pile")
            st.markdown(f"* **Concrete Unit Density:** {gamma_concrete:.1f} kN/m³")
            st.markdown(f"* **Factor of Safety (FOS):** {fos}")

            st.markdown("---")

            # Stratigraphy & Soil Profile
            st.markdown("### **STRATIGRAPHY PROFILE**")
            st.markdown(f"* **Ground Water Depth:** {gw_depth:.2f} m")
            st.markdown(f"* **Total Layers Input:** {len(st.session_state['layers'])}")
            st.markdown("**Subsurface Layer Details:**")

            for l_idx, l in enumerate(st.session_state["layers"]):
                strata_type = l['strata']
                st.markdown(f"**{l_idx+1}. Layer {l_idx+1} ({strata_type.lower()})**")
                st.markdown(f"  * **Depth:** {l['from']:.2f} - {l['to']:.2f} m")
                
                if strata_type in ['Sand', 'Clay']:
                    st.markdown(f"  * **Submerged Unit Weight γ':** {l.get('submerged_unit_weight', 0.0):.2f} kN/m³")
                if strata_type == 'Sand':
                    st.markdown(f"  * **Internal Friction Angle (ϕ):** {l.get('phi', 0.0):.1f}°")
                elif strata_type == 'Clay':
                    st.markdown(f"  * **Unconfined Shear Strength (Cu):** {l.get('Cu', 0.0):.1f} kPa")
                elif strata_type == 'Rock':
                    st.markdown(f"  * **Rock Option:** {l.get('rock_type', 1)}")
                    st.markdown(f"  * **UCS:** {l.get('ucs_mpa', 0.0):.2f} MPa")

            st.markdown("---")

            # Capacity Results Summary
            st.markdown("### **CAPACITY RESULTS SUMMARY**")
            
            c_res1, c_res2 = st.columns(2)
            with c_res1:
                st.markdown("#### **Soil Capacities**")
                st.markdown(f"* **Soil Ult. Compression Capacity (Qu):** {soil_qu_comp:.3f} MN ({soil_qu_comp*1000:.1f} kN)")
                st.markdown(f"* **Soil Allow. Compression Capacity (Qa):** {soil_qa_comp:.3f} MN ({soil_qa_comp*1000:.1f} kN)")
                st.markdown(f"* **Soil Allow. Tension Capacity (Qa):** {soil_qa_tens:.3f} MN ({soil_qa_tens*1000:.1f} kN)")

            with c_res2:
                if not rock_df.empty:
                    st.markdown("#### **Rock Socket Capacities**")
                    st.markdown(f"* **Socket Length (ls):** {rock_df['Socket Length Taken ls (m)'].iloc[0]:.2f} m")
                    st.markdown(f"* **Cu1 (Base UCS):** {rock_df['Cu1 - Base UCS (MPa)'].iloc[0]:.2f} MPa")
                    st.markdown(f"* **Cu2 (Avg UCS):** {rock_df['Cu2 - Avg UCS (MPa)'].iloc[0]:.2f} MPa")
                    st.markdown(f"* **Rock Ult. Capacity (Qu):** {rock_df['Ultimate Rock Capacity Qu (MN)'].iloc[0]:.3f} MN")
                    st.markdown(f"* **Rock Allow. Capacity (Qa):** {rock_df['Allowable Rock Capacity Qa (MN)'].iloc[0]:.3f} MN")
                else:
                    st.markdown("#### **Rock Socket Capacities**")
                    st.markdown("*No rock strata evaluated.*")
