"""Build small but faithful stand-in PDFs for the two corpus documents so the
pipeline can be exercised end-to-end. Captions, table numbers and a data chart
mirror the originals (page numbers printed in the footer)."""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

MR4 = "ntrs-extractor/data/raw/mercury/mercury_redstone_4_results.pdf"
A14 = "ntrs-extractor/data/raw/apollo/Medical_Results_of_Apollo_14.pdf"
os.makedirs(os.path.dirname(MR4), exist_ok=True)
os.makedirs(os.path.dirname(A14), exist_ok=True)


def footer(c, printed):
    c.setFont("Times-Roman", 10)
    c.drawCentredString(letter[0] / 2, 0.5 * inch, str(printed))


def grid_table(c, x, y, data, col_w=0.9 * inch, row_h=0.24 * inch):
    """Draw a ruled table so lattice detection works."""
    rows = len(data)
    cols = len(data[0])
    w = cols * col_w
    h = rows * row_h
    c.setLineWidth(0.6)
    for i in range(rows + 1):
        c.line(x, y - i * row_h, x + w, y - i * row_h)
    for j in range(cols + 1):
        c.line(x + j * col_w, y, x + j * col_w, y - h)
    c.setFont("Times-Roman", 8)
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            c.drawString(x + j * col_w + 3, y - (i + 1) * row_h + 7, str(val))


# ---------------- MR-4 ----------------
c = canvas.Canvas(MR4, pagesize=letter)
# p1 title
c.setFont("Times-Bold", 16)
c.drawCentredString(letter[0]/2, 9*inch, "RESULTS OF THE SECOND")
c.drawCentredString(letter[0]/2, 8.6*inch, "U.S. MANNED SUBORBITAL SPACE FLIGHT")
footer(c, 1); c.showPage()

# p7 Table 2-I comparison of flight parameters
c.setFont("Times-Roman", 10)
c.drawString(1*inch, 9*inch, "A comparison of the flight parameters of MR-4 and MR-3 spacecraft.")
c.setFont("Times-Bold", 10)
c.drawCentredString(letter[0]/2, 8.4*inch, "TABLE 2-I.-Comparison of Flight Parameters for MR-3 and MR-4 Spacecraft")
grid_table(c, 1.2*inch, 8.0*inch, [
    ["Parameter", "MR-3", "MR-4"],
    ["Range, n. mi.", "263.1", "262.5"],
    ["Max altitude, n. mi.", "101.2", "102.8"],
    ["Max exit dyn press", "586.0", "605.5"],
    ["Max exit long load g", "6.3", "6.3"],
    ["Max reentry load g", "11.0", "11.1"],
    ["Period weightless", "5:04", "5:00"],
    ["Earth-fixed vel ft/s", "6414", "6618"],
    ["Space-fixed vel ft/s", "7388", "7580"],
], col_w=1.6*inch)
footer(c, 7); c.showPage()

# p11 Table 3-I Vital Signs
c.setFont("Times-Bold", 10)
c.drawCentredString(letter[0]/2, 9*inch, "TABLE 3-I.-Vital Signs")
grid_table(c, 1.0*inch, 8.6*inch, [
    ["Measure", "Preflight -7hr", "Post +30min", "Post +2hr"],
    ["Body weight lb", "150.5", "147.19", "147.5"],
    ["Temperature F", "97.8", "100.4", "98.4"],
    ["Pulse per min", "68", "160-104", "90"],
    ["Respiration", "12", "28", "14"],
    ["BP sitting", "128/75", "120/85", "125/85"],
    ["Vital capacity L", "5.0", "4.5", "4.8"],
], col_w=1.5*inch)
footer(c, 11); c.showPage()

# p16 Figure 4-1 telemetry (schematic-ish, should be catalogued as trace)
c.setFont("Times-Roman", 9)
c.drawCentredString(letter[0]/2, 1.2*inch,
                    "FIGURE 4-1. Blockhouse telemetry record obtained during countdown (5:43 a.m. e.s.t.).")
footer(c, 16); c.showPage()

# p21 Figure 4-7 Pulse and respiration rates during flight (LINE CHART with data)
import math
ax_x, ax_y, ax_w, ax_h = 1.2*inch, 2.0*inch, 5.5*inch, 5.0*inch
c.setLineWidth(1.2)
c.line(ax_x, ax_y, ax_x + ax_w, ax_y)          # x axis
c.line(ax_x, ax_y, ax_x, ax_y + ax_h)          # y axis
c.setFont("Times-Roman", 8)
# y ticks 50..180 bpm
for val in range(50, 190, 20):
    yy = ax_y + (val - 40) / (180 - 40) * ax_h
    c.line(ax_x - 3, yy, ax_x, yy)
    c.drawRightString(ax_x - 5, yy - 3, str(val))
# x ticks 0..15 min
for t in range(0, 16, 3):
    xx = ax_x + t / 15.0 * ax_w
    c.line(xx, ax_y - 3, xx, ax_y)
    c.drawCentredString(xx, ax_y - 12, str(t))
# pulse curve
c.setLineWidth(1.0)
pts = []
for i in range(0, 151):
    t = i / 10.0
    bpm = 150 + 20*math.sin(t/2.0) - (5 if t > 8 else 0)
    xx = ax_x + t / 15.0 * ax_w
    yy = ax_y + (bpm - 40) / (180 - 40) * ax_h
    pts.append((xx, yy))
c.lines([(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1]) for i in range(len(pts)-1)])
c.setFont("Times-Roman", 9)
c.drawCentredString(letter[0]/2, 1.2*inch,
                    "FIGURE 4-7. Pulse and respiration rates during flight.")
footer(c, 21); c.showPage()
c.save()
print("wrote", MR4)

# ---------------- Apollo 14 ----------------
c = canvas.Canvas(A14, pagesize=letter)
c.setFont("Times-Bold", 14)
c.drawCentredString(letter[0]/2, 8.5*inch, "MEDICAL RESULTS OF APOLLO 14")
footer(c, 1); c.showPage()

# printed p2 Table 1 Apollo 14 Mission
c.setFont("Times-Bold", 10)
c.drawCentredString(letter[0]/2, 9*inch, "Table 1")
c.drawCentredString(letter[0]/2, 8.75*inch, "Apollo 14 Mission")
grid_table(c, 1.2*inch, 8.4*inch, [
    ["Field", "Value"],
    ["Launch", "31 January 1971"],
    ["Recovery", "7 February 1971"],
    ["Total Mission Duration", "217:03 hours"],
    ["Time on Lunar Surface", "34:11"],
    ["First EVA", "4:49"],
    ["Second EVA", "4:20"],
], col_w=2.2*inch)
footer(c, 2); c.showPage()

# printed p3 Table 2 Radiation Exposure
c.setFont("Times-Bold", 10)
c.drawCentredString(letter[0]/2, 9*inch, "Table 2")
c.drawCentredString(letter[0]/2, 8.75*inch, "Radiation Exposure for Apollo 14")
grid_table(c, 1.0*inch, 8.4*inch, [
    ["Position", "CDR", "CMP", "LMP"],
    ["Chest", "0.996", "1.126", "1.078"],
    ["Thigh", "1.095", "1.145", "1.204"],
    ["Ankle", "1.073", "1.279", "1.248"],
], col_w=1.4*inch)
footer(c, 3); c.showPage()

# printed p10 Figure 1 heart-rate static stand test (LINE CHART, two curves)
ax_x, ax_y, ax_w, ax_h = 1.4*inch, 2.2*inch, 5.0*inch, 4.6*inch
c.setLineWidth(1.2)
c.line(ax_x, ax_y, ax_x + ax_w, ax_y)
c.line(ax_x, ax_y, ax_x, ax_y + ax_h)
c.setFont("Times-Roman", 8)
for val in range(50, 130, 10):
    yy = ax_y + (val - 50) / (120 - 50) * ax_h
    c.line(ax_x - 3, yy, ax_x, yy); c.drawRightString(ax_x - 5, yy - 3, str(val))
for t in range(2, 11, 2):
    xx = ax_x + (t - 1) / 9.0 * ax_w
    c.line(xx, ax_y - 3, xx, ax_y); c.drawCentredString(xx, ax_y - 12, str(t))
# postflight curve (rises to 115 while standing)
post = []
for i in range(1, 101):
    t = 1 + i * 9.0/100
    bpm = 82 if t < 5 else min(115, 82 + (t-5)*22)
    if t > 8: bpm = 115 - (t-8)*20
    xx = ax_x + (t-1)/9.0*ax_w; yy = ax_y + (bpm-50)/(120-50)*ax_h
    post.append((xx, yy))
c.setLineWidth(1.0)
c.lines([(post[i][0],post[i][1],post[i+1][0],post[i+1][1]) for i in range(len(post)-1)])
# preflight curve (flat ~60)
pre = []
for i in range(1, 101):
    t = 1 + i * 9.0/100
    bpm = 60 + (5 if t > 5 else 0)
    xx = ax_x + (t-1)/9.0*ax_w; yy = ax_y + (bpm-50)/(120-50)*ax_h
    pre.append((xx, yy))
c.lines([(pre[i][0],pre[i][1],pre[i+1][0],pre[i+1][1]) for i in range(len(pre)-1)])
c.setFont("Times-Roman", 9)
c.drawCentredString(letter[0]/2, 1.3*inch,
                    "Figure 1. Heart Rate Data of Apollo 14 Command Module Pilot in Static Stand Test")
footer(c, 10); c.showPage()
c.save()
print("wrote", A14)
