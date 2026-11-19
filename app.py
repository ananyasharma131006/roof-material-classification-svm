
import os
import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
import plotly.express as px

from streamlit_folium import st_folium

# --------------------------------------------------
# 1. PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="RoofInsight | Spatial Inspection",
    page_icon="🏘️",
    layout="wide"
)

ROOT = "/content/drive/MyDrive/RoofMaterialProject"

GRID_FILE = (
    f"{ROOT}/vulnerability_mapping/concern_levels/"
    "roof_concern_levels.geojson"
)

BUILDING_FILE = (
    f"{ROOT}/vulnerability_mapping/spatial_join/"
    "test_buildings_with_predictions.geojson"
)

CLASSES = [
    "healthy_metal",
    "irregular_metal",
    "incomplete",
    "concrete_cement"
]

CLASS_COLORS = {
    "healthy_metal": "#16A36A",
    "irregular_metal": "#E58B32",
    "incomplete": "#D84B42",
    "concrete_cement": "#64748B"
}

LEVEL_COLORS = {
    "Low": "#2CA25F",
    "Moderate": "#FEE08B",
    "High": "#FDAE61",
    "Very High": "#D7191C"
}

# --------------------------------------------------
# 2. LOAD DATA
# --------------------------------------------------

@st.cache_data
def load_data(grid_file, building_file):

    grid = gpd.read_file(grid_file)
    buildings = gpd.read_file(building_file)

    # Handle possible building ID naming difference
    if "building_id" not in buildings.columns:
        if "id" in buildings.columns:
            buildings = buildings.rename(
                columns={"id": "building_id"}
            )
        else:
            raise ValueError(
                "No building_id or id column found."
            )

    required_grid = [
        "grid_id",
        "region",
        "building_count",
        "roof_concern_proxy",
        "concern_level",
        "healthy_metal_pct",
        "irregular_metal_pct",
        "incomplete_pct",
        "concrete_cement_pct",
        "geometry"
    ]

    required_buildings = [
        "building_id",
        "region",
        "predicted",
        "geometry"
    ]

    missing_grid = [
        c for c in required_grid
        if c not in grid.columns
    ]

    missing_buildings = [
        c for c in required_buildings
        if c not in buildings.columns
    ]

    if missing_grid:
        raise ValueError(
            f"Missing grid columns: {missing_grid}"
        )

    if missing_buildings:
        raise ValueError(
            f"Missing building columns: {missing_buildings}"
        )

    if grid.crs is None or buildings.crs is None:
        raise ValueError("Missing CRS information.")

    grid["concern_level"] = (
        grid["concern_level"].astype(str)
    )

    # Use the same geographic CRS for display
    grid = grid.to_crs("EPSG:4326")
    buildings = buildings.to_crs("EPSG:4326")

    # Create representative points for building assignment
    buildings = buildings.reset_index(drop=True)

    points = buildings[
        ["building_id", "geometry"]
    ].copy()

    points["geometry"] = (
        points.geometry.representative_point()
    )

    points["_row_id"] = range(len(points))

    # Spatially associate each building with one hexagon
    joined = gpd.sjoin(
        points,
        grid[["grid_id", "geometry"]],
        how="left",
        predicate="within"
    )

    # Validate assignment
    if joined["grid_id"].isna().any():
        missing_count = joined["grid_id"].isna().sum()
        raise ValueError(
            f"{missing_count} buildings could not be "
            "assigned to a grid cell."
        )

    if joined["building_id"].duplicated().any():
        raise ValueError(
            "Some buildings were assigned to multiple cells."
        )

    if len(joined) != len(buildings):
        raise ValueError(
            "Building-to-grid assignment count mismatch."
        )

    # Attach grid IDs to original building polygons
    assignment = (
        joined[["_row_id", "grid_id"]]
        .set_index("_row_id")["grid_id"]
    )

    buildings["grid_id"] = (
        buildings.index.map(assignment)
    )

    return grid, buildings


# --------------------------------------------------
# 3. CHECK INPUT FILES
# --------------------------------------------------

st.title("🏘️ RoofInsight")
st.caption(
    "AI-Based Roof Material Classification "
    "and Spatial Inspection Dashboard"
)

if not os.path.exists(GRID_FILE):
    st.error(f"Grid file not found: {GRID_FILE}")
    st.stop()

if not os.path.exists(BUILDING_FILE):
    st.error(f"Building file not found: {BUILDING_FILE}")
    st.stop()

try:
    grid, buildings = load_data(
        GRID_FILE,
        BUILDING_FILE
    )
except Exception as e:
    st.error(f"Data loading error: {e}")
    st.stop()

# --------------------------------------------------
# 4. SIDEBAR FILTERS
# --------------------------------------------------

st.sidebar.title("Inspection Filters")

regions = sorted(grid["region"].unique().tolist())

selected_region = st.sidebar.selectbox(
    "Select study region",
    regions
)

level_order = [
    "Low",
    "Moderate",
    "High",
    "Very High"
]

selected_levels = st.sidebar.multiselect(
    "Filter concern levels",
    level_order,
    default=level_order
)

selected_materials = st.sidebar.multiselect(
    "Filter by roof material",
    CLASSES,
    default=CLASSES,
    format_func=lambda x: x.replace("_", " ").title()
)

region_grid = grid[
    (grid["region"] == selected_region)
    & (grid["concern_level"].isin(selected_levels))
].copy()

# Apply material filter to map cells:
# show cells containing at least one selected material.
if selected_materials:
    region_grid = region_grid[
        region_grid[selected_materials].sum(axis=1) > 0
    ]
else:
    region_grid = region_grid.iloc[0:0]

region_buildings = buildings[
    buildings["region"] == selected_region
].copy()

# --------------------------------------------------
# 5. REGIONAL OVERVIEW
# --------------------------------------------------

st.header(
    selected_region.replace("_", " ").title()
)

total_buildings = len(region_buildings)
occupied_cells = len(
    grid[grid["region"] == selected_region]
)

high_very_high = grid[
    (grid["region"] == selected_region)
    & (grid["concern_level"].isin(["High", "Very High"]))
]

high_buildings = int(
    high_very_high["building_count"].sum()
)

high_pct = (
    high_buildings / total_buildings * 100
    if total_buildings else 0
)

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Buildings analyzed",
    f"{total_buildings:,}"
)

c2.metric(
    "Occupied grid cells",
    f"{occupied_cells:,}"
)

c3.metric(
    "Buildings in High / Very High cells",
    f"{high_buildings:,}"
)

c4.metric(
    "High / Very High building share",
    f"{high_pct:.2f}%"
)

st.divider()

# --------------------------------------------------
# 6. REGIONAL ROOF MATERIAL COMPOSITION
# --------------------------------------------------

st.subheader("Regional Roof Material Composition")

regional_counts = (
    grid[grid["region"] == selected_region][CLASSES]
    .sum()
)

regional_total = regional_counts.sum()

regional_material_data = pd.DataFrame({
    "Roof material": [
        c.replace("_", " ").title()
        for c in CLASSES
    ],
    "Buildings": [
        int(regional_counts[c])
        for c in CLASSES
    ],
    "Percentage": [
        regional_counts[c] / regional_total * 100
        if regional_total else 0
        for c in CLASSES
    ]
})

left, right = st.columns([1.2, 1])

with left:
    fig = px.bar(
        regional_material_data,
        x="Roof material",
        y="Percentage",
        color="Roof material",
        text=regional_material_data[
            "Percentage"
        ].map(lambda x: f"{x:.2f}%"),
        title="Roof Material Distribution",
        color_discrete_sequence=[
            CLASS_COLORS[c] for c in CLASSES
        ]
    )

    fig.update_layout(
        showlegend=False,
        yaxis_title="Buildings (%)",
        xaxis_title=""
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

with right:
    st.dataframe(
        regional_material_data,
        hide_index=True,
        use_container_width=True
    )

st.divider()

# --------------------------------------------------
# 7. INTERACTIVE GRID MAP
# --------------------------------------------------

st.subheader("Interactive Spatial Concern Map")

st.caption(
    "Click a hexagon to view its popup. "
    "Use the grid selector below to load its "
    "individual building polygons and full details."
)

if region_grid.empty:
    st.warning(
        "No grid cells match the selected filters."
    )
    st.stop()

minx, miny, maxx, maxy = (
    region_grid.total_bounds
)

center = [
    (miny + maxy) / 2,
    (minx + maxx) / 2
]

m = folium.Map(
    location=center,
    zoom_start=14,
    tiles="CartoDB positron"
)

def grid_style(feature):
    level = feature["properties"]["concern_level"]

    return {
        "fillColor": LEVEL_COLORS.get(
            level, "#808080"
        ),
        "color": "#333333",
        "weight": 1.2,
        "fillOpacity": 0.72
    }

folium.GeoJson(
    region_grid,
    name="Concern grid cells",
    style_function=grid_style,
    tooltip=folium.GeoJsonTooltip(
        fields=[
            "grid_id",
            "concern_level",
            "building_count",
            "roof_concern_proxy"
        ],
        aliases=[
            "Grid ID:",
            "Concern level:",
            "Buildings:",
            "Concern proxy:"
        ],
        localize=True
    ),
    popup=folium.GeoJsonPopup(
        fields=[
            "grid_id",
            "concern_level",
            "building_count",
            "roof_concern_proxy",
            "healthy_metal_pct",
            "irregular_metal_pct",
            "incomplete_pct",
            "concrete_cement_pct"
        ],
        aliases=[
            "Grid ID:",
            "Concern level:",
            "Building count:",
            "Concern proxy:",
            "Healthy metal (%):",
            "Irregular metal (%):",
            "Incomplete (%):",
            "Concrete/cement (%):"
        ],
        localize=True
    )
).add_to(m)

# --------------------------------------------------
# 8. GRID CELL SELECTION
# --------------------------------------------------

grid_options = region_grid.sort_values(
    "roof_concern_proxy",
    ascending=False
)["grid_id"].tolist()

default_grid = grid_options[0]

if (
    "selected_grid" not in st.session_state
    or st.session_state["selected_grid"] not in grid_options
):
    st.session_state["selected_grid"] = default_grid

selected_grid = st.selectbox(
    "Select a grid cell for detailed inspection",
    grid_options,
    key="selected_grid"
)

selected_row = grid[
    grid["grid_id"] == selected_grid
].iloc[0]

selected_buildings = region_buildings[
    region_buildings["grid_id"] == selected_grid
].copy()

# Highlight selected hexagon
selected_polygon = grid[
    grid["grid_id"] == selected_grid
]

folium.GeoJson(
    selected_polygon,
    name="Selected grid cell",
    style_function=lambda feature: {
        "fillColor": "#00BFFF",
        "color": "#003366",
        "weight": 4,
        "fillOpacity": 0.12
    }
).add_to(m)

# --------------------------------------------------
# 9. INDIVIDUAL BUILDING POLYGONS
# --------------------------------------------------

if not selected_buildings.empty:

    building_layer = folium.FeatureGroup(
        name="Individual buildings",
        show=True
    )

    for _, building in selected_buildings.iterrows():

        roof_class = building["predicted"]

        color = CLASS_COLORS.get(
            roof_class, "#808080"
        )

        building_gdf = gpd.GeoDataFrame(
            [building],
            geometry="geometry",
            crs=selected_buildings.crs
        )

        folium.GeoJson(
            building_gdf,
            style_function=lambda feature, c=color: {
                "fillColor": c,
                "color": "#222222",
                "weight": 1,
                "fillOpacity": 0.8
            },
            tooltip=folium.Tooltip(
                f"Building ID: {building['building_id']}<br>"
                f"Roof material: "
                f"{str(roof_class).replace('_', ' ').title()}"
            )
        ).add_to(building_layer)

    building_layer.add_to(m)

folium.LayerControl(
    collapsed=False
).add_to(m)

m.fit_bounds(
    [[miny, minx], [maxy, maxx]]
)

st_folium(
    m,
    use_container_width=True,
    height=620,
    returned_objects=[]
)

st.divider()

# --------------------------------------------------
# 10. SELECTED GRID CELL DETAILS
# --------------------------------------------------

st.subheader("Selected Grid Cell Inspection")

d1, d2, d3 = st.columns(3)

d1.metric(
    "Building count",
    int(selected_row["building_count"])
)

d2.metric(
    "Roof concern proxy",
    f"{selected_row['roof_concern_proxy']:.2f}/100"
)

d3.metric(
    "Concern level",
    selected_row["concern_level"]
)

if int(selected_row["building_count"]) < 10:
    st.warning(
        "Low sample support: this cell contains fewer "
        "than 10 buildings. Interpret its percentages "
        "with caution."
    )
else:
    st.info(
        "This cell has at least 10 buildings. "
        "This is a preliminary sample-support flag, "
        "not a statistical reliability guarantee."
    )

# --------------------------------------------------
# 11. ALL FOUR ROOF MATERIALS IN SELECTED CELL
# --------------------------------------------------

st.markdown("### Roof Material Breakdown")

material_rows = []

for cls in CLASSES:

    count = int(selected_row[cls])

    percentage = float(
        selected_row[f"{cls}_pct"]
    )

    material_rows.append({
        "Roof material": cls.replace(
            "_", " "
        ).title(),
        "Buildings": count,
        "Percentage": round(percentage, 2)
    })

material_df = pd.DataFrame(material_rows)

left, right = st.columns([1, 1])

with left:
    fig = px.bar(
        material_df,
        x="Roof material",
        y="Percentage",
        color="Roof material",
        text=material_df[
            "Percentage"
        ].map(lambda x: f"{x:.2f}%"),
        color_discrete_sequence=[
            CLASS_COLORS[c] for c in CLASSES
        ],
        title="Selected Cell: Roof Composition"
    )

    fig.update_layout(
        showlegend=False,
        yaxis_title="Buildings (%)",
        xaxis_title=""
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

with right:
    st.dataframe(
        material_df,
        hide_index=True,
        use_container_width=True
    )

# --------------------------------------------------
# 12. BUILDING-LEVEL INSPECTION TABLE
# --------------------------------------------------

st.markdown("### Individual Buildings in Selected Cell")

if selected_buildings.empty:

    st.warning(
        "No building polygons were assigned to this cell."
    )

else:

    building_table = selected_buildings[
        ["building_id", "predicted"]
    ].copy()

    building_table["predicted"] = (
        building_table["predicted"]
        .str.replace("_", " ")
        .str.title()
    )

    st.write(
        f"Showing {len(building_table)} buildings "
        f"inside {selected_grid}."
    )

    st.dataframe(
        building_table,
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "Download selected cell building records",
        data=building_table.to_csv(index=False),
        file_name=f"{selected_grid}_buildings.csv",
        mime="text/csv"
    )

st.divider()

# --------------------------------------------------
# 13. REGIONAL CONCERN DISTRIBUTION
# --------------------------------------------------

st.subheader("Concern-Level Distribution")

level_counts = (
    grid[grid["region"] == selected_region]
    .groupby("concern_level")
    .agg(
        occupied_cells=("grid_id", "count"),
        buildings=("building_count", "sum")
    )
    .reindex(level_order, fill_value=0)
    .reset_index()
)

fig = px.bar(
    level_counts,
    x="concern_level",
    y="buildings",
    color="concern_level",
    text="buildings",
    color_discrete_map=LEVEL_COLORS,
    title="Buildings by Concern Level"
)

fig.update_layout(
    showlegend=False,
    xaxis_title="Concern level",
    yaxis_title="Number of buildings"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.dataframe(
    level_counts,
    hide_index=True,
    use_container_width=True
)

# --------------------------------------------------
# 14. DOWNLOAD FILTERED GRID DATA
# --------------------------------------------------

st.subheader("Export Inspection Data")

export_grid = region_grid.drop(
    columns="geometry"
).copy()

st.download_button(
    "Download filtered grid records",
    data=export_grid.to_csv(index=False),
    file_name=f"{selected_region}_grid_inspection.csv",
    mime="text/csv"
)

priority_export = region_grid[
    region_grid["concern_level"].isin(
        ["High", "Very High"]
    )
].drop(columns="geometry")

st.download_button(
    "Download High / Very High cells",
    data=priority_export.to_csv(index=False),
    file_name=f"{selected_region}_priority_cells.csv",
    mime="text/csv"
)

# --------------------------------------------------
# 15. FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "RoofInsight | Roof Material Classification "
    "and Spatial Concern Screening"
)

st.caption(
    "Concern proxy = irregular metal percentage "
    "+ incomplete roof percentage. "
    "Concern levels are relative, data-derived "
    "screening categories, not validated engineering "
    "or disaster-risk ratings. All roof classes are "
    "model predictions and should be field-verified."
)
