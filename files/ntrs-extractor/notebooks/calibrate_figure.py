# ---
# Figure calibration worksheet
# Open in Jupyter (jupytext will pair this .py with a notebook) or run as a script.
# Purpose: turn a Pass-3 pixel trace into calibrated (x, y) data for one figure.
# ---

# %% [markdown]
# # Figure calibration — one chart at a time
# Steps: (1) auto-trace to find the plot rectangle, (2) read four tick references
# off the axes, (3) re-digitise with a CalibrationSpec, (4) save CSV + overlay,
# (5) eyeball the overlay.

# %%
from ntrs_extractor import figures, catalogue_io

# --- pick the figure from its catalogue row -------------------------------
DOC_CATALOGUE = "catalogues/apollo/A14_catalogue.xlsx"
CATALOGUE_ID = "A14-F-001"
PDF = "data/raw/apollo/Medical_Results_of_Apollo_14.pdf"

rows = {r["catalogue_id"]: r for r in catalogue_io.read_catalogue(DOC_CATALOGUE, "B_graphical")}
row = rows[CATALOGUE_ID]
PAGE = int(row["pdf_page_number"])
print(row["item_number"], "-", row["description"], "| pdf page", PAGE)

# %% [markdown]
# ## 1) Auto-trace to locate the plot rectangle (pixels)

# %%
r = figures.digitise_figure(PDF, PAGE)
x0, y0, x1, y1 = r.plot_bbox_px
print("plot rect (px):", r.plot_bbox_px, "| traced points:", r.n_points)

# %% [markdown]
# ## 2) Read tick labels off the axes and calibrate
# Provide TWO x ticks and TWO y ticks. Image y grows downward, so the bottom
# tick (y1) is the smaller data value. Set x_log/y_log True for log axes.

# %%
cal = figures.CalibrationSpec(
    x_px=(x0, x1), x_val=(1, 10),      # <-- EDIT: minutes at left / right
    y_px=(y1, y0), y_val=(50, 120),    # <-- EDIT: bpm at bottom / top
    x_log=False, y_log=False,
)

# %% [markdown]
# ## 3) Re-digitise with calibration and 4) save outputs

# %%
r2 = figures.digitise_figure(PDF, PAGE, calibration=cal)
out_csv = f"data/outputs/apollo/figures/{CATALOGUE_ID}.csv"
overlay = f"qc/apollo/overlays/{CATALOGUE_ID}.png"
figures.save_figure(r2, out_csv, overlay_png=overlay)
for name, arr in r2.series.items():
    print(f"{name}: n={len(arr)} x[{arr[:,0].min():.1f}..{arr[:,0].max():.1f}] "
          f"y[{arr[:,1].min():.0f}..{arr[:,1].max():.0f}]")
print("saved:", out_csv, "|", overlay)

# %% [markdown]
# ## 5) Eyeball the overlay (dots should sit on the plotted lines)

# %%
try:
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    plt.figure(figsize=(6, 8)); plt.imshow(mpimg.imread(overlay)); plt.axis("off"); plt.show()
except Exception as e:
    print("open the PNG directly:", overlay, "(matplotlib not available:", e, ")")
