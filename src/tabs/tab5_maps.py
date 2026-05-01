"""
tab5_maps.py — Supply Chain Geography
Interactive Folium map showing critical mineral production sites,
key shipping chokepoints, shipping routes, and HHI choropleth overlay.
Historically framed — no live crisis dependency.
Display code only — all data access goes through loaders.py.
"""

import streamlit as st
import folium

from streamlit_folium import st_folium


# ── Key shipping chokepoints ──────────────────────────────────────────────────
CHOKEPOINTS = [
    {"name": "Strait of Hormuz",   "lat": 26.50,  "lon": 56.50,  "note": "~20% global oil · semiconductor feedstocks"},
    {"name": "Strait of Malacca",  "lat": 1.25,   "lon": 103.82, "note": "~40% global trade · Taiwan supply route"},
    {"name": "Suez Canal",         "lat": 30.42,  "lon": 32.35,  "note": "Red Sea route · Houthi disruption 2024"},
    {"name": "Taiwan Strait",      "lat": 24.50,  "lon": 119.50, "note": "TSMC · advanced semiconductor fab"},
    {"name": "South China Sea",    "lat": 12.00,  "lon": 113.00, "note": "Rare earth shipping · China territorial claims"},
]

# ── Critical mineral production sites ────────────────────────────────────────
MINERAL_SITES = [
    {"name": "Bayan Obo",         "lat": 41.78,  "lon": 109.97, "country": "China",    "mineral": "Rare Earths (HHI 0.71)"},
    {"name": "Atacama Desert",    "lat": -23.50, "lon": -68.20, "country": "Chile",    "mineral": "Lithium (world #1)"},
    {"name": "Kolwezi",           "lat": -10.70, "lon": 25.47,  "country": "DRC",      "mineral": "Cobalt (world #1)"},
    {"name": "Escondida",         "lat": -24.27, "lon": -69.07, "country": "Chile",    "mineral": "Copper"},
    {"name": "Grasberg",          "lat": -4.05,  "lon": 137.10, "country": "Indonesia","mineral": "Copper / Gold"},
    {"name": "Norilsk",           "lat": 69.33,  "lon": 88.22,  "country": "Russia",   "mineral": "Nickel / Palladium (sanctioned)"},
    {"name": "Lviv Region",       "lat": 49.84,  "lon": 24.02,  "country": "Ukraine",  "mineral": "Titanium / Neon (war-disrupted)"},
    {"name": "Jiangxi Province",  "lat": 27.61,  "lon": 115.92, "country": "China",    "mineral": "Germanium (HHI 0.76) / Gallium (HHI 0.77)"},
]

# ── Shipping routes (waypoints along key supply corridors) ─────────────────
SHIPPING_ROUTES = [
    {
        "name":  "Semiconductor supply route",
        "color": "#FF6B35",
        "note":  "Hormuz → Malacca → Taiwan Strait (chip feedstocks + finished semis)",
        "coords": [
            [26.50, 56.50],   # Hormuz
            [12.00, 66.00],   # Arabian Sea
            [1.25, 103.82],   # Malacca
            [10.00, 110.00],  # South China Sea
            [24.50, 119.50],  # Taiwan Strait
            [25.05, 121.55],  # Taiwan (TSMC)
        ],
    },
    {
        "name":  "Lithium supply route",
        "color": "#00FFB2",
        "note":  "Atacama → Pacific → Asian battery gigafactories",
        "coords": [
            [-23.50, -68.20],  # Atacama
            [-33.45, -70.66],  # Valparaíso port
            [-20.00, -100.00], # Pacific crossing
            [1.25, 103.82],    # Malacca
            [22.30, 114.18],   # Hong Kong / Guangzhou
            [30.68, 104.07],   # Chengdu (CATL)
        ],
    },
    {
        "name":  "Rare earth export route",
        "color": "#A78BFA",
        "note":  "Jiangxi → South China Sea → global",
        "coords": [
            [27.61, 115.92],   # Jiangxi
            [22.30, 114.18],   # Guangzhou port
            [12.00, 113.00],   # South China Sea
            [1.25, 103.82],    # Malacca
            [7.00, 79.86],     # Sri Lanka
            [12.97, 77.59],    # India (Bangalore tech cluster)
        ],
    },
    {
        "name":  "Nickel / palladium route (pre-sanctions)",
        "color": "#FACC15",
        "note":  "Norilsk → Northern Sea Route → European industry (now sanctioned)",
        "coords": [
            [69.33, 88.22],    # Norilsk
            [72.00, 52.00],    # Kara Sea
            [70.00, 20.00],    # Norwegian Sea
            [55.68, 12.57],    # Copenhagen
            [51.50, 0.13],     # London
        ],
    },
]

# ── Country HHI data for choropleth (ISO3) ────────────────────────────────
HHI_DATA = {
    "CHN": {"label": "China",     "hhi": 0.74, "minerals": "Rare Earths · Germanium · Gallium"},
    "CHL": {"label": "Chile",     "hhi": 0.45, "minerals": "Lithium · Copper"},
    "COD": {"label": "DRC",       "hhi": 0.62, "minerals": "Cobalt"},
    "RUS": {"label": "Russia",    "hhi": 0.38, "minerals": "Nickel · Palladium (sanctioned)"},
    "IDN": {"label": "Indonesia", "hhi": 0.28, "minerals": "Nickel · Copper"},
    "AUS": {"label": "Australia", "hhi": 0.22, "minerals": "Lithium · Iron Ore"},
    "USA": {"label": "USA",       "hhi": 0.15, "minerals": "Molybdenum · Coal"},
}


def _hhi_to_color(hhi: float) -> str:
    """Map HHI value to a red-gradient hex color."""
    if hhi >= 0.65:
        return "#7F1D1D"   # very high concentration
    if hhi >= 0.50:
        return "#B91C1C"
    if hhi >= 0.35:
        return "#EF4444"
    if hhi >= 0.20:
        return "#FCA5A5"
    return "#FEE2E2"


def render(demo_mode: bool = True) -> None:
    """Render the Supply Chain Geography tab."""
    st.subheader("Supply Chain Geography")
    st.caption("Critical mineral sites · Shipping chokepoints · Supply routes · HHI concentration · 2010–2024")

    # ── Map legend toggles ────────────────────────────────────────────────────
    with st.expander("Map Legend", expanded=True):
        lcol1, lcol2, lcol3 = st.columns(3)
        with lcol1:
            st.markdown("🔴 **Red markers** — shipping chokepoints")
            st.markdown("🟢 **Green circles** — mineral production sites")
        with lcol2:
            st.markdown("🟠 **Orange line** — semiconductor supply route")
            st.markdown("🟢 **Teal line** — lithium supply route")
        with lcol3:
            st.markdown("🟣 **Purple line** — rare earth export route")
            st.markdown("🟡 **Yellow line** — Norilsk nickel (pre-sanctions)")

    col1, col2 = st.columns([2, 1])

    with col1:
        m = folium.Map(location=[20.0, 60.0], zoom_start=3, tiles="CartoDB dark_matter")

        # Shipping routes
        for route in SHIPPING_ROUTES:
            folium.PolyLine(
                locations=route["coords"],
                color=route["color"],
                weight=2.5,
                opacity=0.75,
                tooltip=f"<b>{route['name']}</b><br>{route['note']}",
                dash_array="6 4",
            ).add_to(m)
            # Arrow at midpoint for direction
            mid = len(route["coords"]) // 2
            folium.Marker(
                location=route["coords"][mid],
                icon=folium.DivIcon(
                    html=f"<div style='font-size:10px;color:{route['color']};font-weight:bold'>▶</div>",
                    icon_size=(12, 12),
                ),
            ).add_to(m)

        # HHI country shading (circle overlays — no external geojson needed)
        country_centers = {
            "CHN": [35.86, 104.20],
            "CHL": [-35.68, -71.54],
            "COD": [-4.04, 21.76],
            "RUS": [61.52, 105.32],
            "IDN": [-0.79, 113.92],
            "AUS": [-25.27, 133.78],
            "USA": [37.09, -95.71],
        }
        for iso, data in HHI_DATA.items():
            center = country_centers.get(iso)
            if not center:
                continue
            folium.Circle(
                location=center,
                radius=int(data["hhi"] * 800_000),  # radius proportional to HHI
                color=_hhi_to_color(data["hhi"]),
                fill=True,
                fill_opacity=0.3,
                popup=(
                    f"<b>{data['label']}</b><br>"
                    f"HHI: {data['hhi']}<br>"
                    f"Minerals: {data['minerals']}"
                ),
                tooltip=f"{data['label']} — HHI {data['hhi']}",
            ).add_to(m)

        # Shipping chokepoints
        for cp in CHOKEPOINTS:
            folium.Marker(
                location=[cp["lat"], cp["lon"]],
                popup=f"<b>{cp['name']}</b><br>{cp['note']}",
                icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon"),
                tooltip=cp["name"],
            ).add_to(m)

        # Mineral production sites
        for site in MINERAL_SITES:
            folium.CircleMarker(
                location=[site["lat"], site["lon"]],
                radius=8,
                color="#00FFB2",
                fill=True,
                fill_opacity=0.7,
                popup=f"<b>{site['name']}</b><br>{site['country']}<br>{site['mineral']}",
                tooltip=f"{site['name']} — {site['mineral']}",
            ).add_to(m)

        st_folium(m, width=720, height=540)

    with col2:
        st.markdown("### Chokepoints")
        for cp in CHOKEPOINTS:
            st.markdown(f"**{cp['name']}**  \n{cp['note']}")
            st.divider()

        st.markdown("### HHI Concentration")
        for iso, data in sorted(HHI_DATA.items(), key=lambda x: -x[1]["hhi"]):
            st.metric(data["label"], f"HHI {data['hhi']}", data["minerals"])

        st.divider()
        st.markdown("### Key Vaartha HHI Findings")
        st.metric("Gallium HHI", "0.77", "China dominant")
        st.metric("Germanium HHI", "0.76", "China dominant")
        st.metric("Rare Earths HHI", "0.71", "China dominant")
        st.caption("HHI > 0.25 = high concentration (DoJ threshold)")
