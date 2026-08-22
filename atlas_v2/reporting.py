"""Phase 5D communication exports built from current V2 project state."""

from datetime import datetime, timezone
from html import escape
from io import BytesIO
import json
import re

from PIL import Image as PillowImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from .decision import compare_scenario


DISCLAIMER = (
    "Este resultado baseia-se nos dados e pressupostos atualmente disponíveis. "
    "Não substitui levantamento topográfico, projeto de arquitetura ou engenharia, "
    "parecer técnico, licenciamento nem confirmação junto das entidades competentes."
)

OBJECT_LABELS = {
    "building": "Edifício", "platform": "Plataforma", "access": "Acesso",
    "zone": "Zona de análise", "crop_area": "Área agrícola", "pond": "Charca",
}
ENGINE_LABELS = {
    "earthwork": "Movimentação de terras", "cultivable_area": "Área cultivável",
    "solar_potential": "Potencial solar", "water_context": "Contexto hídrico",
    "site_constraints": "Condicionantes conhecidas",
}
OBJECT_COLORS = {
    "building": "#b85f35", "platform": "#d19b45", "access": "#435f4d",
    "zone": "#3d7792", "crop_area": "#6e9348", "pond": "#397aa6",
    "base_parcel": "#764d35",
}
SIGNAL_COLORS = {
    "green": colors.HexColor("#397957"), "yellow": colors.HexColor("#a36f21"),
    "red": colors.HexColor("#a3483e"), "gray": colors.HexColor("#68736e"),
}


def _font(size=18, bold=False):
    names = ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _now_label():
    return datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")


def _paths(geometry):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return coordinates
    if geometry_type == "MultiPolygon":
        return [ring for polygon in coordinates for ring in polygon]
    if geometry_type == "LineString":
        return [coordinates]
    if geometry_type == "MultiLineString":
        return coordinates
    return []


def _all_points(project, scenario):
    geometries = [project["base_parcel"]["geometry"]] + [item["geometry"] for item in scenario["objects"]]
    return [point for geometry in geometries for path in _paths(geometry) for point in path]


def _draw_header(draw, title, subtitle, width):
    draw.rectangle((0, 0, width, 116), fill="#163f35")
    draw.text((58, 28), "ATLAS", font=_font(30, True), fill="#ffffff")
    draw.text((205, 29), title, font=_font(25, True), fill="#ffffff")
    draw.text((205, 68), subtitle, font=_font(16), fill="#dbe9e2")


def _draw_footer(draw, width, height, source_text):
    draw.line((54, height - 66, width - 54, height - 66), fill="#cfd8d3", width=1)
    draw.text((58, height - 49), source_text, font=_font(13), fill="#596761")
    date_text = f"Gerado em {_now_label()}"
    right = draw.textbbox((0, 0), date_text, font=_font(13))[2]
    draw.text((width - 58 - right, height - 49), date_text, font=_font(13), fill="#596761")


def _legend(draw, objects, x, y):
    present = list(dict.fromkeys(item["type"] for item in objects))
    draw.rounded_rectangle((x, y, x + 280, y + 36 + 28 * len(present)), radius=12, fill="#ffffff", outline="#d4ddd8")
    draw.text((x + 16, y + 10), "Legenda", font=_font(15, True), fill="#263a32")
    for index, object_type in enumerate(present):
        yy = y + 40 + index * 28
        draw.rectangle((x + 16, yy, x + 31, yy + 15), fill=OBJECT_COLORS.get(object_type, "#596761"))
        draw.text((x + 42, yy - 2), OBJECT_LABELS.get(object_type, object_type), font=_font(14), fill="#394b43")


def render_scenario_2d(project, scenario, clean=False, bounds=None, width=1600, height=1000):
    """Render a dependable, basemap-free 2D communication image."""
    background = "#ffffff" if clean else "#edf1eb"
    image = PillowImage.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    title = "Proposta limpa" if clean else "Vista 2D da proposta"
    _draw_header(draw, project["name"], f"{scenario['name']} · {title}", width)

    points = _all_points(project, scenario)
    if not points:
        draw.text((80, 200), "Não existem geometrias para representar.", font=_font(24), fill="#596761")
        return image
    if bounds:
        min_x, min_y, max_x, max_y = bounds
    else:
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    dx, dy = max(max_x - min_x, 1e-9), max(max_y - min_y, 1e-9)
    plot = (75, 155, width - 365, height - 95)
    scale = min((plot[2] - plot[0]) / dx, (plot[3] - plot[1]) / dy)

    def to_pixel(point):
        content_w, content_h = dx * scale, dy * scale
        ox = plot[0] + ((plot[2] - plot[0]) - content_w) / 2
        oy = plot[1] + ((plot[3] - plot[1]) - content_h) / 2
        return (ox + (point[0] - min_x) * scale, oy + (max_y - point[1]) * scale)

    if not clean:
        for step in range(1, 10):
            gx = plot[0] + step * (plot[2] - plot[0]) / 10
            gy = plot[1] + step * (plot[3] - plot[1]) / 10
            draw.line((gx, plot[1], gx, plot[3]), fill="#dfe5e1", width=1)
            draw.line((plot[0], gy, plot[2], gy), fill="#dfe5e1", width=1)

    parcel_paths = _paths(project["base_parcel"]["geometry"])
    for path in parcel_paths:
        pixel_path = [to_pixel(point) for point in path]
        if len(pixel_path) >= 3:
            draw.polygon(pixel_path, fill="#dfeadd" if clean else "#d8e6d4", outline=OBJECT_COLORS["base_parcel"], width=5)
    for item in scenario["objects"]:
        color = OBJECT_COLORS.get(item["type"], "#596761")
        for path in _paths(item["geometry"]):
            pixel_path = [to_pixel(point) for point in path]
            if len(pixel_path) >= 3 and item["geometry"]["type"] in ("Polygon", "MultiPolygon"):
                draw.polygon(pixel_path, fill=color, outline="#ffffff", width=3)
            elif len(pixel_path) >= 2:
                draw.line(pixel_path, fill=color, width=9)
        if _paths(item["geometry"]):
            first_path = _paths(item["geometry"])[0]
            if first_path:
                anchor = to_pixel(first_path[0])
                draw.text((anchor[0] + 7, anchor[1] + 7), item["name"], font=_font(14, True), fill="#1f2f28", stroke_width=2, stroke_fill="#ffffff")

    _legend(draw, scenario["objects"], width - 330, 165)
    draw.text((width - 315, 500), "N", font=_font(24, True), fill="#263a32")
    draw.polygon([(width - 300, 545), (width - 315, 585), (width - 285, 585)], fill="#263a32")
    source = "GeoJSON da alternativa · EPSG:4326 na comunicação; referência de terreno TM06 / EPSG:3763"
    _draw_footer(draw, width, height, source)
    return image


def render_scenario_3d(project, scenario, terrain_context, width=1600, height=1000):
    """Render a stable isometric terrain image for export and reporting."""
    image = PillowImage.new("RGB", (width, height), "#d9e1df")
    draw = ImageDraw.Draw(image)
    _draw_header(draw, project["name"], f"{scenario['name']} · Vista 3D indicativa", width)
    geometries = [project["base_parcel"]["geometry"]] + [item["geometry"] for item in scenario["objects"]]
    mesh = terrain_context.mesh_for_geometries(geometries, max_dimension=70, padding_pixels=5)
    clip = mesh.pop("_clip")
    elevations = mesh["elevacoes"]
    rows, cols = mesh["n_linhas"], mesh["n_cols"]
    emin, emax = mesh["elevacao_min"], mesh["elevacao_max"]
    elevation_span = max(emax - emin, 1)
    sx = min((width - 210) / max(rows + cols, 1), (height - 370) * 2.05 / max(rows + cols, 1))
    sy, zscale = sx * 0.43, min(8.0, max(2.0, 190 / elevation_span))
    center_x, top_y = width / 2, 170

    def project(row, col, elevation):
        return center_x + (col - row) * sx, top_y + (col + row) * sy - (elevation - emin) * zscale

    for row in range(rows - 1):
        for col in range(cols - 1):
            values = [elevations[row][col], elevations[row][col + 1], elevations[row + 1][col + 1], elevations[row + 1][col]]
            average = sum(values) / 4
            ratio = (average - emin) / elevation_span
            color = (int(78 + 85 * ratio), int(119 + 70 * ratio), int(78 + 40 * ratio))
            polygon = [project(row, col, values[0]), project(row, col + 1, values[1]), project(row + 1, col + 1, values[2]), project(row + 1, col, values[3])]
            draw.polygon(polygon, fill=color)

    for item in scenario["objects"]:
        projected = terrain_context.project_geojson(item["geometry"], clip)
        color = OBJECT_COLORS.get(item["type"], "#ffffff")
        for path in projected["paths"]:
            screen = []
            for point in path:
                if point["elevation"] is None:
                    continue
                row, col = point["z"] / mesh["pixel_m"], point["x"] / mesh["pixel_m"]
                x, y = project(row, col, point["elevation"] + 1.5)
                screen.append((x, y))
            if len(screen) >= 2:
                draw.line(screen, fill="#ffffff", width=9, joint="curve")
                draw.line(screen, fill=color, width=5, joint="curve")

    stats = f"Cotas MDT: {emin:.1f} m a {emax:.1f} m · resolução apresentada: {mesh['pixel_m']:.1f} m"
    draw.rounded_rectangle((75, height - 160, width - 75, height - 88), radius=12, fill="#ffffff", outline="#c9d3ce")
    draw.text((98, height - 142), stats, font=_font(17, True), fill="#31453c")
    draw.text((98, height - 113), "Modelo de comunicação preliminar; não representa projeto de execução nem levantamento topográfico.", font=_font(14), fill="#596761")
    _draw_footer(draw, width, height, "MDT LiDAR 2 m · modelo isométrico gerado pelo Atlas")
    return image


def image_bytes(project, scenario, terrain_context, view, bounds=None):
    if view == "proposal":
        rendered = render_scenario_2d(project, scenario, clean=True)
    elif view == "2d":
        rendered = render_scenario_2d(project, scenario, bounds=bounds)
    elif view == "3d":
        rendered = render_scenario_3d(project, scenario, terrain_context)
    else:
        raise ValueError("Vista de exportação não suportada.")
    output = BytesIO()
    rendered.save(output, "PNG", optimize=True)
    return output.getvalue()


def _safe(value):
    text = str(value).replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    return escape(text)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))


def _sources(assessment, results):
    found = []
    for dimension in assessment["dimensions"].values():
        found.extend(dimension.get("sources", []))
    for result in results:
        found.extend((result.get("metrics") or {}).get("sources", []))
    return list(dict.fromkeys(item for item in found if item))


def _limitations(assessment, results):
    found = []
    for dimension in assessment["dimensions"].values():
        found.extend(dimension.get("limitations", []))
    for result in results:
        found.extend(result.get("limitations", []))
    found.append(DISCLAIMER)
    return list(dict.fromkeys(item for item in found if item))


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AtlasTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=colors.HexColor("#163f35"), spaceAfter=7 * mm))
    styles.add(ParagraphStyle(name="AtlasH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#214c40"), spaceBefore=5 * mm, spaceAfter=3 * mm))
    styles.add(ParagraphStyle(name="AtlasBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13, textColor=colors.HexColor("#293b34")))
    styles.add(ParagraphStyle(name="AtlasSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#56635e")))
    styles.add(ParagraphStyle(name="AtlasDisclaimer", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8.5, leading=12, textColor=colors.HexColor("#70452d"), backColor=colors.HexColor("#f7eee7"), borderPadding=8))
    styles.add(ParagraphStyle(name="AtlasCode", parent=styles["BodyText"], fontName="Courier", fontSize=6.8, leading=9, textColor=colors.HexColor("#384740"), wordWrap="CJK"))
    styles.add(ParagraphStyle(name="AtlasCenter", parent=styles["AtlasSmall"], alignment=TA_CENTER))
    return styles


def _paragraph(text, style):
    return Paragraph(_safe(text), style)


def _bullet_list(items, styles):
    if not items:
        return [_paragraph("Sem elementos registados.", styles["AtlasSmall"])]
    return [Paragraph(f"• {_safe(item)}", styles["AtlasBody"]) for item in items]


def _page_number(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d4ddd8"))
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#65716c"))
    canvas.drawString(20 * mm, 10 * mm, "Atlas · indicação para estudo preliminar")
    canvas.drawRightString(190 * mm, 10 * mm, f"Página {document.page}")
    canvas.restoreState()


def _summary_story(project, scenario, results, assessment, terrain_context, styles):
    image_2d = image_bytes(project, scenario, terrain_context, "2d")
    image_3d = image_bytes(project, scenario, terrain_context, "3d")
    identification = Table([
        [_paragraph("Projeto", styles["AtlasSmall"]), _paragraph(project["name"], styles["AtlasBody"]), _paragraph("Alternativa", styles["AtlasSmall"]), _paragraph(scenario["name"], styles["AtlasBody"])],
        [_paragraph("Gerado", styles["AtlasSmall"]), _paragraph(_now_label(), styles["AtlasBody"]), _paragraph("Objetivo", styles["AtlasSmall"]), _paragraph("Estudo preliminar de implantação", styles["AtlasBody"])],
    ], colWidths=[22 * mm, 55 * mm, 25 * mm, 68 * mm])
    identification.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f5f2")), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d7dfda")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story = [
        _paragraph("Relatório simples da proposta", styles["AtlasTitle"]),
        identification, Spacer(1, 5 * mm), _paragraph(DISCLAIMER, styles["AtlasDisclaimer"]),
        _paragraph("Leitura visual", styles["AtlasH2"]),
        Table([[Image(BytesIO(image_2d), width=82 * mm, height=51.25 * mm), Image(BytesIO(image_3d), width=82 * mm, height=51.25 * mm)]], colWidths=[85 * mm, 85 * mm], style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")])),
        Table([[_paragraph("Vista 2D da alternativa", styles["AtlasCenter"]), _paragraph("Vista 3D indicativa do MDT", styles["AtlasCenter"])]], colWidths=[85 * mm, 85 * mm]),
        _paragraph("Objetos principais", styles["AtlasH2"]),
    ]
    object_rows = [[_paragraph("Tipo", styles["AtlasSmall"]), _paragraph("Nome", styles["AtlasSmall"]), _paragraph("Parâmetros principais", styles["AtlasSmall"])]]
    for item in scenario["objects"]:
        parameters = ", ".join(f"{key}: {value}" for key, value in list(item.get("parameters", {}).items())[:5]) or "Sem parâmetros adicionais"
        object_rows.append([_paragraph(OBJECT_LABELS.get(item["type"], item["type"]), styles["AtlasBody"]), _paragraph(item["name"], styles["AtlasBody"]), _paragraph(parameters, styles["AtlasSmall"])])
    objects_table = Table(object_rows, colWidths=[35 * mm, 48 * mm, 87 * mm], repeatRows=1)
    objects_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5eee8")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#d1dad5")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([objects_table, _paragraph("Semáforos explicados", styles["AtlasH2"])])
    signal_rows = [[_paragraph("Dimensão", styles["AtlasSmall"]), _paragraph("Estado", styles["AtlasSmall"]), _paragraph("Razão", styles["AtlasSmall"])]]
    dimension_names = {"objective": "Objetivo", "earthwork": "Terraplanagem", "terrain": "Relevo", "constraints": "Condicionantes"}
    for key, dimension in assessment["dimensions"].items():
        signal_rows.append([_paragraph(dimension_names[key], styles["AtlasBody"]), _paragraph(dimension["label"], styles["AtlasSmall"]), _paragraph(dimension["reason"], styles["AtlasSmall"])])
    signals = Table(signal_rows, colWidths=[30 * mm, 47 * mm, 93 * mm], repeatRows=1)
    style_commands = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5eee8")), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#d1dad5")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    for index, dimension in enumerate(assessment["dimensions"].values(), start=1):
        style_commands.append(("TEXTCOLOR", (1, index), (1, index), SIGNAL_COLORS[dimension["status"]]))
    signals.setStyle(TableStyle(style_commands))
    story.extend([signals, _paragraph("Métricas resumidas", styles["AtlasH2"])])
    metrics = []
    for dimension in assessment["dimensions"].values():
        for item in dimension.get("data", []):
            if not isinstance(item.get("value"), (list, dict)):
                metrics.append(f"{item['label']}: {item.get('value', 'n/d')} {item.get('unit', '')}".strip())
    story.extend(_bullet_list(metrics[:12], styles))
    story.append(_paragraph("Fontes de dados", styles["AtlasH2"]))
    story.extend(_bullet_list(_sources(assessment, results), styles))
    story.append(_paragraph("Limitações e validações recomendadas", styles["AtlasH2"]))
    story.extend(_bullet_list(_limitations(assessment, results)[:12], styles))
    story.extend(_bullet_list([
        "Confirmar limites e cotas por levantamento topográfico adequado.",
        "Validar arquitetura, engenharia, geotecnia, acessos e drenagem com profissionais habilitados.",
        "Confirmar regras, servidões e licenciamento junto das entidades competentes.",
    ], styles))
    return story


def _technical_story(project, scenario, results, assessment, terrain_context, styles):
    story = [
        _paragraph("Relatório técnico da proposta", styles["AtlasTitle"]),
        _paragraph("Gerado a pedido do utilizador. Informação técnica para revisão e rastreabilidade; não constitui certificação.", styles["AtlasDisclaimer"]),
        _paragraph("Identificação e referência geográfica", styles["AtlasH2"]),
        Paragraph(
            f"Projeto: {_safe(project['name'])}<br/>Alternativa: {_safe(scenario['name'])}<br/>"
            f"CRS persistido da BaseParcel: {_safe(project['base_parcel']['crs'])}<br/>"
            f"Bounding box: {_safe(_json(project['base_parcel']['bounding_box']))}",
            styles["AtlasBody"],
        ),
        _paragraph("Geometrias e parâmetros", styles["AtlasH2"]),
    ]
    for item in scenario["objects"]:
        details = (
            f"<b>{_safe(item['name'])}</b> · {_safe(OBJECT_LABELS.get(item['type'], item['type']))}<br/>"
            f"Identidade: {_safe(item['id'])}<br/>Snapshot version: {_safe(item.get('snapshot_version', 'n/d'))}<br/>"
            f"Snapshot atualizado: {_safe(item.get('snapshot_updated_at', 'n/d'))}<br/>"
            f"Proveniência original_object_id: {_safe(item.get('original_object_id') or 'sem referência')}<br/>"
            f"Geometria GeoJSON: {_safe(_json(item['geometry']))}<br/>Parâmetros: {_safe(_json(item.get('parameters', {})))}"
        )
        story.append(KeepTogether([Paragraph(details, styles["AtlasCode"]), Spacer(1, 3 * mm)]))
    story.extend([PageBreak(), _paragraph("Resultados por motor", styles["AtlasH2"])])
    if not results:
        story.append(_paragraph("Não existem resultados persistidos para esta alternativa.", styles["AtlasBody"]))
    for result in results:
        stale = "SIM - não usar silenciosamente como atual" if result.get("is_stale") else "não"
        block = (
            f"<b>{_safe(ENGINE_LABELS.get(result['engine_type'], result['engine_type']))}</b><br/>"
            f"Estado: {_safe(result['status'])} · desatualizado: {_safe(stale)} · calculado em: {_safe(result['computed_at'])}<br/>"
            f"scenario_object_id: {_safe(result['scenario_object_id'])}<br/>"
            f"parameters_used: {_safe(_json(result.get('parameters_used', {})))}<br/>"
            f"Métricas: {_safe(_json(result.get('metrics', {})))}<br/>"
            f"Geometrias derivadas: {_safe(_json(result.get('derived_geometries', [])))}<br/>"
            f"Warnings: {_safe(_json(result.get('warnings', [])))}<br/>Erros: {_safe(_json(result.get('errors', [])))}<br/>"
            f"Limitações: {_safe(_json(result.get('limitations', [])))}"
        )
        story.append(KeepTogether([Paragraph(block, styles["AtlasCode"]), Spacer(1, 4 * mm)]))
    story.append(_paragraph("Proveniência, resolução e cobertura", styles["AtlasH2"]))
    geometries = [project["base_parcel"]["geometry"]] + [item["geometry"] for item in scenario["objects"]]
    mesh = terrain_context.mesh_for_geometries(geometries, max_dimension=80, padding_pixels=5)
    mesh.pop("_clip")
    provenance = {
        "terrain_source": mesh.get("source"), "bbox_3763": mesh.get("bbox_3763"),
        "coverage_complete": mesh.get("coverage_complete"), "sample_reduction": mesh.get("sample_reduction"),
        "display_grid": [mesh.get("n_linhas"), mesh.get("n_cols")],
    }
    story.append(Paragraph(_safe(_json(provenance)), styles["AtlasCode"]))
    story.append(_paragraph("Avaliação explicável atual", styles["AtlasH2"]))
    for key, dimension in assessment["dimensions"].items():
        story.append(_paragraph(f"{key}: {dimension['label']} - {dimension['reason']}", styles["AtlasBody"]))
        story.extend(_bullet_list(dimension.get("limitations", []), styles))
    story.append(_paragraph("Limitações técnicas detalhadas", styles["AtlasH2"]))
    story.extend([
        _paragraph("As limitações específicas estão registadas junto de cada motor e dimensão acima; resultados desatualizados são identificados e não são usados silenciosamente como atuais.", styles["AtlasSmall"]),
        _paragraph(DISCLAIMER, styles["AtlasSmall"]),
    ])
    return story


def report_bytes(project, scenario, results, terrain_context, level="simple"):
    if level not in ("simple", "technical"):
        raise ValueError("Nível de relatório não suportado.")
    assessment = compare_scenario(scenario, results, terrain_context)
    styles = _styles()
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=22 * mm,
        title=f"Atlas - {project['name']} - {scenario['name']}",
        author="Atlas",
    )
    story = _summary_story(project, scenario, results, assessment, terrain_context, styles)
    if level == "technical":
        story.extend([PageBreak(), *_technical_story(project, scenario, results, assessment, terrain_context, styles)])
    document.build(story, onFirstPage=_page_number, onLaterPages=_page_number)
    return output.getvalue()


def safe_filename(value):
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return normalized or "atlas"
