"""Generate the updated academic project report and its exact experiment visuals."""

import math
import os
import re
import sys
from pathlib import Path

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


SRC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SRC_DIR.parent
REPORT_DIR = PROJECT_DIR / "report"
ASSET_DIR = REPORT_DIR / "assets_generated"
OUTPUT_PATH = REPORT_DIR / "proje_raporu_guncel.pdf"
sys.path.insert(0, str(SRC_DIR))

from astar import (  # noqa: E402
    CLASSIC_HEURISTICS,
    astar_search_dynamic,
    manhattan_distance,
    octile_distance,
)
from environment import (  # noqa: E402
    ACTIVE_THREAT,
    NO_FLY,
    PASSIVE_THREAT,
    STATIC_OBSTACLE,
    build_environment,
)
from neural_heuristic import MLP, NeuralHeuristic  # noqa: E402


SCENARIOS = [
    ("simple", "Basit Sizma", "01_basit"),
    ("urban", "Sehir Operasyonu", "02_sehir"),
    ("corridor", "Koridor Gecisi", "03_koridor"),
    ("dynamic", "Dinamik Tehdit", "04_dinamik"),
]
METHODS = ["Dijkstra (h=0)", "Manhattan", "Octile", "Neural (MLP)"]
PATH_COLORS = {
    "Dijkstra (h=0)": (245, 245, 245),
    "Manhattan": (255, 45, 141),
    "Octile": (24, 216, 152),
    "Neural (MLP)": (255, 210, 31),
}


def register_fonts():
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ]
    for normal, bold in candidates:
        if Path(normal).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("Report", normal))
            pdfmetrics.registerFont(TTFont("Report-Bold", bold))
            return "Report", "Report-Bold", normal
    return "Helvetica", "Helvetica-Bold", None


FONT, FONT_BOLD, PIL_FONT_PATH = register_fonts()


def pil_font(size, bold=False):
    if PIL_FONT_PATH:
        path = PIL_FONT_PATH
        if bold and "DejaVuSans.ttf" in path:
            path = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def run_experiments():
    model = MLP.load(str(PROJECT_DIR / "data" / "mlp_heuristic.pkl"))
    all_results = {}
    environments = {}
    missions = {}
    for scenario, _, _ in SCENARIOS:
        env, mission = build_environment(scenario, seed=42)
        neural = NeuralHeuristic(model, env, time=0)
        results = {
            "Dijkstra (h=0)": astar_search_dynamic(
                env, mission, CLASSIC_HEURISTICS["zero"], "Dijkstra (h=0)"
            ),
            "Manhattan": astar_search_dynamic(
                env, mission, manhattan_distance, "Manhattan"
            ),
            "Octile": astar_search_dynamic(
                env, mission, octile_distance, "Octile"
            ),
            "Neural (MLP)": astar_search_dynamic(
                env, mission, neural, "Neural (MLP)"
            ),
        }
        all_results[scenario] = results
        environments[scenario] = env
        missions[scenario] = mission
    return model, all_results, environments, missions


def map_xy(row, col, margin, cell):
    return margin + col * cell + cell / 2, margin + row * cell + cell / 2


def draw_route_map(env, mission, results, output_path):
    cell = 12
    margin = 35
    map_size = env.size * cell
    legend_w = 300
    image = PILImage.new("RGB", (map_size + 2 * margin + legend_w, map_size + 2 * margin), "#1e1e1e")
    overlay = PILImage.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    for r in range(env.size):
        for c in range(env.size):
            x0 = margin + c * cell
            y0 = margin + r * cell
            state = int(env.static_grid[r, c])
            if state == STATIC_OBSTACLE:
                draw.rectangle((x0, y0, x0 + cell, y0 + cell), fill=(92, 92, 92, 255))
            elif state == NO_FLY:
                draw.rectangle((x0, y0, x0 + cell, y0 + cell), fill=(127, 29, 29, 230))

    for threat in env.threats:
        x, y = map_xy(threat.center[0], threat.center[1], margin, cell)
        radius = threat.radius * cell
        active = env.is_threat_active(threat, time=0)
        fill = (255, 76, 76, 105) if active else (240, 165, 43, 70)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=(230, 230, 230, 190), width=2)

    for i in range(0, env.size + 1, 5):
        pos = margin + i * cell
        draw.line((margin, pos, margin + map_size, pos), fill=(60, 60, 60, 180), width=1)
        draw.line((pos, margin, pos, margin + map_size), fill=(60, 60, 60, 180), width=1)

    for name, result in results.items():
        points = [map_xy(r, c, margin, cell) for r, c in result.path]
        if len(points) > 1:
            draw.line(points, fill=PATH_COLORS[name] + (225,), width=4, joint="curve")

    sx, sy = map_xy(*mission.start, margin, cell)
    gx, gy = map_xy(*mission.goal, margin, cell)
    draw.ellipse((sx - 8, sy - 8, sx + 8, sy + 8), fill=(22, 224, 96, 255), outline=(0, 0, 0, 255), width=2)
    draw.rectangle((gx - 7, gy - 7, gx + 7, gy + 7), fill=(32, 184, 232, 255), outline=(0, 0, 0, 255), width=2)
    image = PILImage.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(image)
    title_font = pil_font(23, bold=True)
    text_font = pil_font(17)
    draw.text((margin, 4), localize_turkish(f"Rota Karsilastirmasi - {mission.name}"), font=title_font, fill="white")
    lx = margin + map_size + 25
    draw.text((lx, 60), localize_turkish("Yontemler"), font=title_font, fill="white")
    y = 105
    for name in METHODS:
        draw.line((lx, y + 9, lx + 50, y + 9), fill=PATH_COLORS[name], width=5)
        result = results[name]
        draw.text((lx + 62, y), f"{name}", font=text_font, fill="white")
        draw.text((lx + 62, y + 24), f"maliyet={result.cost:.2f}", font=pil_font(14), fill="#cfcfcf")
        y += 68
    draw.text((lx, y + 10), "Arka plan: t=0", font=pil_font(14), fill="#cfcfcf")
    draw.text((lx, y + 34), localize_turkish("Rotalar: zaman-genisletmeli"), font=pil_font(14), fill="#cfcfcf")
    image.save(output_path, quality=94)


def draw_benchmark(results, output_path):
    width, height = 1200, 430
    image = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = pil_font(24, bold=True)
    label_font = pil_font(17)
    small = pil_font(14)
    draw.text((40, 12), localize_turkish("Arama Verimliligi ve Rota Maliyeti"), font=title_font, fill="#111111")
    panels = [
        (40, 70, 550, 320, localize_turkish("Genisletilen Dugum"), [results[m].nodes_expanded for m in METHODS], False),
        (630, 70, 550, 320, "Rota Maliyeti", [results[m].cost for m in METHODS], True),
    ]
    colors_bar = ["#4169e1", "#dc143c", "#2e8b57", "#e5b900"]
    short_names = ["Dijkstra", "Manhattan", "Octile", "Neural"]
    for x, y, w, h, title, values, decimal in panels:
        draw.text((x, y), title, font=label_font, fill="#111111")
        chart_top = y + 40
        chart_h = h - 70
        max_val = max(values) * 1.12
        bar_w = 82
        gap = 45
        for i, (name, value, bar_color) in enumerate(zip(short_names, values, colors_bar)):
            bx = x + 25 + i * (bar_w + gap)
            bh = chart_h * value / max_val if max_val else 0
            by = chart_top + chart_h - bh
            draw.rectangle((bx, by, bx + bar_w, chart_top + chart_h), fill=bar_color)
            label = f"{value:.2f}" if decimal else f"{int(value):,}".replace(",", ".")
            bbox = draw.textbbox((0, 0), label, font=small)
            draw.text((bx + (bar_w - (bbox[2] - bbox[0])) / 2, by - 20), label, font=small, fill="#111111")
            draw.text((bx - 2, chart_top + chart_h + 8), name, font=small, fill="#111111")
        draw.line((x + 10, chart_top + chart_h, x + w - 10, chart_top + chart_h), fill="#333333", width=2)
    image.save(output_path, quality=94)


def heat_color(value, low, high):
    ratio = 0.0 if high <= low else max(0.0, min(1.0, (value - low) / (high - low)))
    # Yellow -> green -> blue, close to viridis_r semantics.
    if ratio < 0.5:
        t = ratio * 2
        return (int(245 - 165 * t), int(225 - 20 * t), int(60 + 80 * t))
    t = (ratio - 0.5) * 2
    return (int(80 - 30 * t), int(205 - 130 * t), int(140 + 80 * t))


def draw_heatmap(env, mission, heuristic, title, output_path):
    cell = 11
    margin = 48
    size = env.size * cell
    image = PILImage.new("RGB", (size + 2 * margin, size + 2 * margin + 36), "white")
    values = {}
    for r in range(env.size):
        for c in range(env.size):
            if env.is_passable(r, c, time=0):
                values[(r, c)] = float(heuristic((r, c), mission.goal, 0))
    low, high = min(values.values()), max(values.values())
    draw = ImageDraw.Draw(image)
    draw.text((margin, 8), localize_turkish(title), font=pil_font(21, bold=True), fill="#111111")
    for r in range(env.size):
        for c in range(env.size):
            x0 = margin + c * cell
            y0 = margin + 36 + r * cell
            if (r, c) in values:
                fill = heat_color(values[(r, c)], low, high)
            else:
                fill = (60, 60, 60)
            draw.rectangle((x0, y0, x0 + cell, y0 + cell), fill=fill)
    sx, sy = map_xy(*mission.start, margin, cell)
    gx, gy = map_xy(*mission.goal, margin, cell)
    sy += 36
    gy += 36
    draw.ellipse((sx - 6, sy - 6, sx + 6, sy + 6), fill="#16e060")
    draw.rectangle((gx - 5, gy - 5, gx + 5, gy + 5), fill="#20b8e8")
    image.save(output_path, quality=94)


def draw_training_curve(model, output_path):
    train = model.training_history.get("train_loss", [])
    val = model.training_history.get("val_loss", [])
    width, height = 1000, 430
    image = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 18), localize_turkish("MLP Egitim ve Dogrulama Kaybi"), font=pil_font(24, bold=True), fill="#111111")
    x0, y0, x1, y1 = 80, 75, 950, 360
    draw.line((x0, y0, x0, y1), fill="#222222", width=2)
    draw.line((x0, y1, x1, y1), fill="#222222", width=2)
    all_values = train + val
    low, high = min(all_values), max(all_values)
    def point(i, value, count):
        x = x0 + (x1 - x0) * i / max(count - 1, 1)
        y = y1 - (y1 - y0) * (value - low) / max(high - low, 1e-9)
        return x, y
    if train:
        draw.line([point(i, v, len(train)) for i, v in enumerate(train)], fill="#d73b3e", width=3)
    if val:
        draw.line([point(i, v, len(val)) for i, v in enumerate(val)], fill="#2b9b58", width=3)
    draw.line((700, 32, 750, 32), fill="#d73b3e", width=4)
    draw.text((760, 22), localize_turkish("Egitim"), font=pil_font(15), fill="#111111")
    draw.line((835, 32, 885, 32), fill="#2b9b58", width=4)
    draw.text((895, 22), localize_turkish("Dogrulama"), font=pil_font(15), fill="#111111")
    draw.text((450, 380), "Epoch", font=pil_font(16), fill="#111111")
    draw.text((12, 205), "MSE", font=pil_font(16), fill="#111111")
    image.save(output_path, quality=94)


def build_assets(model, all_results, environments, missions):
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for scenario, _, prefix in SCENARIOS:
        draw_route_map(
            environments[scenario], missions[scenario], all_results[scenario],
            ASSET_DIR / f"{prefix}_routes.png",
        )
        draw_benchmark(all_results[scenario], ASSET_DIR / f"{prefix}_benchmark.png")
    urban_env = environments["urban"]
    urban_mission = missions["urban"]
    draw_heatmap(
        urban_env, urban_mission, manhattan_distance,
        "Sehir Senaryosu - Manhattan Heatmap", ASSET_DIR / "urban_manhattan_heatmap.png",
    )
    draw_heatmap(
        urban_env, urban_mission, NeuralHeuristic(model, urban_env),
        "Sehir Senaryosu - Neural Heatmap", ASSET_DIR / "urban_neural_heatmap.png",
    )
    draw_training_curve(model, ASSET_DIR / "training_curve.png")


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("TitleTR", parent=base["Title"], fontName=FONT_BOLD, fontSize=20, leading=25, alignment=TA_CENTER, textColor=colors.HexColor("#0b3b72")),
        "cover": ParagraphStyle("Cover", parent=base["Normal"], fontName=FONT_BOLD, fontSize=13, leading=18, alignment=TA_CENTER),
        "h1": ParagraphStyle("H1TR", parent=base["Heading1"], fontName=FONT_BOLD, fontSize=14, leading=18, textColor=colors.HexColor("#0b4a86"), spaceAfter=8),
        "h2": ParagraphStyle("H2TR", parent=base["Heading2"], fontName=FONT_BOLD, fontSize=11.5, leading=15, textColor=colors.HexColor("#174f7a"), spaceBefore=5, spaceAfter=5),
        "body": ParagraphStyle("BodyTR", parent=base["BodyText"], fontName=FONT, fontSize=9.1, leading=13.2, alignment=TA_JUSTIFY, spaceAfter=6),
        "bullet": ParagraphStyle("BulletTR", parent=base["BodyText"], fontName=FONT, fontSize=8.8, leading=12.5, leftIndent=12, bulletIndent=2, spaceAfter=3),
        "caption": ParagraphStyle("CaptionTR", parent=base["BodyText"], fontName=FONT, fontSize=7.8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceBefore=3, spaceAfter=6),
        "table": ParagraphStyle("TableTR", parent=base["BodyText"], fontName=FONT, fontSize=7.5, leading=9.5, alignment=TA_LEFT),
        "code": ParagraphStyle("CodeTR", parent=base["Code"], fontName="Courier", fontSize=8, leading=11, backColor=colors.HexColor("#f1f3f5"), borderPadding=6, spaceAfter=5),
    }


STYLES = make_styles()


TR_WORDS = {
    "Agi": "Ağı", "Agi": "Ağı", "Arastirma": "Araştırma",
    "Baslangic": "Başlangıç", "baslangic": "başlangıç",
    "Calisma": "Çalışma", "Calismanin": "Çalışmanın", "Calistirma": "Çalıştırma",
    "calisma": "çalışma", "calismada": "çalışmada", "calismanin": "çalışmanın",
    "calistirilabilir": "çalıştırılabilir", "calistirilmistir": "çalıştırılmıştır",
    "Capraz": "Çapraz", "capraz": "çapraz", "ciktilari": "çıktıları", "cizilir": "çizilir",
    "Cikis": "Çıkış", "cikis": "çıkış", "cok": "çok", "Coklu": "Çoklu",
    "Dogrulama": "Doğrulama", "dogrulama": "doğrulama", "dogrulamayi": "doğrulamayı",
    "Dogru": "Doğru", "dogru": "doğru", "dogrudan": "doğrudan", "dogrultusu": "doğrultusu",
    "Donem": "Dönem", "dort": "dört", "Dort": "Dört", "dugum": "düğüm",
    "Dugum": "Düğüm", "dugumleri": "düğümleri", "dugumun": "düğümün",
    "Duzeltme": "Düzeltme", "Duzeltmeleri": "Düzeltmeleri", "duzeltmis": "düzeltmiş",
    "Egitim": "Eğitim", "egitim": "eğitim", "egitilmistir": "eğitilmiştir",
    "Farkli": "Farklı", "farkli": "farklı", "Gecisi": "Geçişi", "Gecti": "Geçti",
    "gecilebilir": "geçilebilir", "gecici": "geçici", "genisletilen": "genişletilen",
    "Genisletilen": "Genişletilen", "genisletme": "genişletme", "genisletmistir": "genişletmiştir",
    "genislettigi": "genişlettiği", "Gercek": "Gerçek", "gercek": "gerçek",
    "Giris": "Giriş", "giris": "giriş", "Gorev": "Görev", "gorev": "görev",
    "gosterir": "gösterir", "gostermektedir": "göstermektedir", "gostermistir": "göstermiştir",
    "guclu": "güçlü", "Guclu": "Güçlü", "guvenli": "güvenli", "guvenilir": "güvenilir",
    "Guncel": "Güncel", "guncel": "güncel", "Guncellenmis": "Güncellenmiş",
    "Hazirlayanlar": "Hazırlayanlar", "Hucre": "Hücre", "hucre": "hücre",
    "Icindekiler": "İçindekiler", "icin": "için", "IHA": "İHA", "iyilestirmeler": "iyileştirmeler",
    "karsilastirma": "karşılaştırma", "Karsilastirma": "Karşılaştırma",
    "karsilastirilmasi": "karşılaştırılması", "karsilastirilmistir": "karşılaştırılmıştır",
    "karsilik": "karşılık", "Katkilar": "Katkılar", "katkilari": "katkıları",
    "Klasor": "Klasör", "Klasor Yapisi": "Klasör Yapısı", "kosum": "koşum", "kosumundan": "koşumundan",
    "Kullanilir": "Kullanılır", "kullanilir": "kullanılır", "kullanilmasi": "kullanılması",
    "kullanilmistir": "kullanılmıştır", "kucuk": "küçük", "Mimari": "Mimari",
    "maliyeti": "maliyeti", "Maliyeti": "Maliyeti", "mevcut": "mevcut", "modeliyle": "modeliyle",
    "Ogretmen": "Öğretmen", "ogrenilen": "öğrenilen", "ogrenilmis": "öğrenilmiş",
    "Ogrenilmis": "Öğrenilmiş", "olcegi": "ölçeği", "olusturulur": "oluşturulur",
    "olusturulmustur": "oluşturulmuştur", "onceden": "önceden", "Onbellek": "Önbellek",
    "onbellek": "önbellek", "Ortamlarinda": "Ortamlarında", "ortamlarinda": "ortamlarında",
    "Ozellik": "Özellik", "Ozellikleri": "Özellikleri", "ozellik": "özellik", "ozellikleri": "özellikleri",
    "Ozeti": "Özeti", "Ozet": "Özet", "ozet": "özet", "Sinir": "Sinir", "Sinirliliklar": "Sınırlılıklar",
    "sinirlandirmalari": "sınırlandırmaları", "sinirlidir": "sınırlıdır", "Sinir": "Sinir",
    "Sizma": "Sızma", "Sehir": "Şehir", "sehir": "şehir", "sekiz": "sekiz",
    "Sekil": "Şekil", "Sirasi": "Sırası", "Sonuclari": "Sonuçları", "Sonuc": "Sonuç",
    "sonuc": "sonuç", "sonuclari": "sonuçları", "Sure": "Süre", "sure": "süre",
    "Tabanli": "Tabanlı", "tabanli": "tabanlı", "tasir": "taşır", "tasinir": "taşınır",
    "Tartisma": "Tartışma", "Tehdit": "Tehdit", "Uygulama": "Uygulama",
    "Ucus": "Uçuş", "ucus": "uçuş", "Uretim": "Üretim", "uretilir": "üretilir",
    "uretilmistir": "üretilmiştir", "Varis": "Varış", "varis": "varış", "yapisi": "yapısı",
    "Yapisi": "Yapısı", "yapilmasi": "yapılması", "yaklasim": "yaklaşım",
    "yaklasimi": "yaklaşımı", "yaklasimin": "yaklaşımın", "Yontem": "Yöntem",
    "Yontemler": "Yöntemler", "yontem": "yöntem", "yontemin": "yöntemin", "yontemleri": "yöntemleri",
    "Yonlu": "Yönlü", "yonlu": "yönlü", "yonu": "yönü", "Yuzey": "Yüzey",
    "yuzde": "yüzde", "zayif": "zayıf", "Zaman": "Zaman", "zamana": "zamana",
    "bagli": "bağlı", "bagimsiz": "bağımsız", "basari": "başarı", "basariyla": "başarıyla",
    "deger": "değer", "degeri": "değeri", "degerleri": "değerleri", "degerlendirilir": "değerlendirilir",
    "degildir": "değildir", "degisimi": "değişimi", "dagilimini": "dağılımını", "ayri": "ayrı",
    "acik": "açık", "acikca": "açıkça", "acisindan": "açısından", "azalmasi": "azalması",
    "ciftlerinde": "çiftlerinde", "cozum": "çözüm", "izlenir": "izlenir",
}


def localize_turkish(text):
    if not isinstance(text, str):
        return text
    for source in sorted(TR_WORDS, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(source)}\b", TR_WORDS[source], text)
    return text


def P(text, style="body"):
    visible_text = text if style == "code" else localize_turkish(text)
    return Paragraph(visible_text, STYLES[style])


def bullet(text):
    return Paragraph(localize_turkish(text), STYLES["bullet"], bulletText="•")


def styled_table(data, widths, header=True):
    converted = []
    for row in data:
        converted.append([cell if hasattr(cell, "wrap") else P(str(cell), "table") for cell in row])
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="CENTER")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#8996a3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b4a86")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ]
    table.setStyle(TableStyle(commands))
    return table


def report_image(path, width_cm, caption):
    with PILImage.open(path) as img:
        ratio = img.height / img.width
    image = Image(str(path), width=width_cm * cm, height=width_cm * ratio * cm)
    return [image, P(caption, "caption")]


def pct(base, value):
    return 100.0 * (value - base) / base


def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(colors.HexColor("#5d6670"))
    canvas.drawCentredString(A4[0] / 2, 0.75 * cm, f"Sayfa {doc.page}")
    if doc.page > 1:
        canvas.setStrokeColor(colors.HexColor("#b8c4cf"))
        canvas.line(2 * cm, 1.05 * cm, A4[0] - 2 * cm, 1.05 * cm)
    canvas.restoreState()


def build_report(model, results):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH), pagesize=A4,
        rightMargin=1.65 * cm, leftMargin=1.65 * cm,
        topMargin=1.45 * cm, bottomMargin=1.35 * cm,
        title="Neural-Guided A* Search - Guncel Proje Raporu",
        author="Kaan Arslan ve Rukiye Narsu Oymak",
    )
    story = []

    # Page 1 - Cover
    logo = REPORT_DIR / "biruni_logo.png"
    if logo.exists():
        story += [Spacer(1, 0.5 * cm), Image(str(logo), width=3.1 * cm, height=2.6 * cm)]
    story += [
        Spacer(1, 0.7 * cm),
        P("Neural-Guided A* Search", "title"),
        Spacer(1, 0.25 * cm),
        P("Dinamik Tehdit Ortamlarinda IHA Rota Planlamasi icin<br/>Sinir Agi Destekli A* Arama", "cover"),
        Spacer(1, 1.3 * cm),
        P("Yapay Zeka Dersi Donem Projesi<br/>Guncellenmis Proje Raporu", "cover"),
        Spacer(1, 1.5 * cm),
        P("HAZIRLAYANLAR", "cover"),
        P("Kaan Arslan (230404045)<br/>Rukiye Narsu Oymak (230404001)", "cover"),
        Spacer(1, 0.7 * cm),
        P("DANISMAN OGRETMEN", "cover"),
        P("Mahyar Teymournezhad", "cover"),
        Spacer(1, 1.2 * cm),
        P("Haziran 2026", "cover"),
        PageBreak(),
    ]

    # Page 2 - Abstract and contents
    story += [P("Proje Ozeti", "h1")]
    story += [P(
        "Bu calismada, statik engeller ve zamana bagli tehditler iceren 50x50 grid ortamlarda IHA rota "
        "planlamasi icin MLP tabanli ogrenilmis bir heuristic ile zaman-genisletmeli A* birlestirilmistir. "
        "Dijkstra, Manhattan, Octile ve Neural heuristic dort senaryoda dugum genisletme ve rota maliyeti "
        "acisindan karsilastirilmistir. Guncel uygulamada Neural heuristic her dugumun gercek varis zamanini "
        "kullanir; egitim etiketleri yonlu hucre maliyetlerine uygun ters Dijkstra ile uretilir ve dogrulama "
        "haritalari egitimden farkli seed degerleriyle olusturulur. Sonuclar Neural yaklasimin Basit Sizma ve "
        "Sehir Operasyonu senaryolarinda Octile'dan daha az dugum genislettigini; Koridor ve Dinamik Tehdit "
        "senaryolarinda ise Octile'in daha verimli kaldigini gostermistir. Neural heuristic admissible olmadigi "
        "icin maliyet sapmalari ayrica raporlanmistir."
    )]
    story += [P("Anahtar Kelimeler: A* aramasi, Dijkstra, MLP, ogrenilmis heuristic, IHA rota planlama, dinamik tehdit, zaman-genisletmeli arama.", "body")]
    story += [P("Icindekiler", "h1")]
    for item in [
        "1. Giris ve Katkilar", "2. Sistem Tasarimi", "3. Sinir Agi Tabanli Heuristic",
        "4. Uygulama Duzeltmeleri", "5. Deneysel Kurulum", "6. Deneysel Sonuclar",
        "7. Senaryo Analizleri", "8. Heatmap Analizi", "9. Tartisma ve Sinirliliklar",
        "10. Calistirma Talimatlari ve Sonuc", "Kaynakca", "Ek A. Proje Yapisi ve Testler",
    ]:
        story.append(bullet(item))
    story.append(PageBreak())

    # Page 3 - Introduction
    story += [P("1. Giris", "h1"), P(
        "Otonom IHA sistemlerinde guvenli rota planlama, yalnizca geometrik olarak kisa bir yol bulma "
        "problemi degildir. Radar, SAM ve elektronik harp bolgelerinin zamanla aktif veya pasif hale gelmesi, "
        "planlayicinin her hucreyi IHA'nin varis zamaninda degerlendirmesini gerektirir. A* algoritmasi uygun "
        "bir heuristic ile arama alanini daraltabilir; ancak ogrenilmis heuristic gercek maliyeti asarsa optimal "
        "cozum garantisi kaybolur. Bu proje, bu performans-kalite takasini deneysel olarak incelemektedir."
    ), P("1.1 Calismanin Katkilari", "h2")]
    for item in [
        "Zaman-genisletmeli durum uzayi (satir, sutun, zaman) ile periyodik tehditlerin rota boyunca kontrol edilmesi.",
        "Dijkstra, Manhattan, Octile ve MLP heuristiclerinin ayni deney duzeninde karsilastirilmasi.",
        "Neural heuristic ozelliklerinin her dugumun gercek varis zamaniyla hesaplanmasi.",
        "Yonlu hareket maliyetleri icin dogru ters-Dijkstra ground-truth uretimi.",
        "Egitim ve dogrulama haritalarinin farkli seed gruplarindan uretilmesi.",
        "Koyu temali rota karsilastirmasi, benchmark panelleri ve zaman uyumlu snapshot ciktilari.",
    ]:
        story.append(bullet(item))
    story += [P("1.2 Kapsam", "h2"), P(
        "Calisma iki boyutlu, ayrik zamanli ve periyodik tehdit bilgisi onceden bilinen bir simulasyonla "
        "sinirlidir. Ucus dinamigi, irtifa, ruzgar ve gercek zamanli algilama proje kapsami disindadir."
    ), PageBreak()]

    # Page 4 - System design
    story += [P("2. Sistem Tasarimi", "h1"), P("2.1 Operasyon Ortami", "h2"), P(
        "Ortam 50x50 hucreli bir grid olarak modellenmistir. IHA sekiz yonde hareket edebilir. Duz hareket "
        "maliyeti 1.0, capraz hareket maliyeti sqrt(2)'dir. Pasif tehdit bolgesine giris 1.5 risk carpaniyla "
        "maliyetlendirilir."
    )]
    story.append(styled_table([
        ["Hucre Tipi", "Aciklama", "Gecilebilirlik / Maliyet"],
        ["Bos saha", "Acik hava sahasi", "Evet, 1.0"],
        ["Statik engel", "Dag veya bina", "Hayir"],
        ["Aktif tehdit", "Aktif radar / SAM", "Hayir"],
        ["Pasif tehdit", "Gecici olarak kapali tehdit", "Evet, 1.5 risk carpani"],
        ["Yasak bolge", "Kritik tesis veya hava sahasi", "Hayir"],
    ], [3.0 * cm, 7.2 * cm, 6.1 * cm]))
    story += [P("2.2 Dinamik Durum Uzayi", "h2"), P(
        "Dinamik A* durumu (r, c, t) olarak tutar. Her hareket veya bekleme eylemi zamani bir adim ilerletir. "
        "Ayni konumun farkli tehdit fazlarindaki halleri farkli durumlar olarak ele alinir. Tehdit periyotlarinin "
        "EKOK'u kullanilarak durum uzayi sonlu tutulur."
    ), P("2.3 Klasik Heuristicler", "h2")]
    story.append(styled_table([
        ["Yontem", "Heuristic", "Optimalite"],
        ["Dijkstra", "h(n)=0", "Optimal referans"],
        ["Manhattan", "|dr|+|dc|", "8-yonlu harekette garanti yok"],
        ["Octile", "max+(sqrt(2)-1)min", "Admissible ve consistent"],
        ["Neural", "MLP(x(n,g,t))", "Admissibility garantisi yok"],
    ], [3.2 * cm, 7.0 * cm, 6.1 * cm]))
    story.append(PageBreak())

    # Page 5 - Model
    story += [P("3. Sinir Agi Tabanli Heuristic", "h1"), P("3.1 Model Mimarisi", "h2"), P(
        "NumPy ile sifirdan uygulanan MLP, sekiz ozellikten hedefe kalan maliyeti tahmin eden bir regresyon "
        "modelidir. ReLU gizli katmanlari, lineer cikis, MSE kaybi ve Adam optimizer kullanilir."
    )]
    story.append(styled_table([
        ["Katman", "Boyut", "Aktivasyon"],
        ["Giris", "8", "-"], ["Gizli 1", "64", "ReLU"],
        ["Gizli 2", "64", "ReLU"], ["Gizli 3", "32", "ReLU"],
        ["Cikis", "1", "Lineer"],
    ], [5.2 * cm, 5.2 * cm, 5.2 * cm]))
    story += [P("3.2 Giris Ozellikleri", "h2")]
    story.append(styled_table([
        ["No", "Ozellik", "Amac"],
        ["1", "Manhattan mesafesi", "Normalize geometrik uzaklik"],
        ["2", "Euclidean mesafesi", "Kus ucusu uzaklik"],
        ["3", "Octile mesafesi", "8-yonlu teorik alt sinir"],
        ["4-5", "Satir ve sutun farki", "Hedef yonu"],
        ["6", "5x5 lokal engel yogunlugu", "Yerel cevre bilgisi"],
        ["7", "Hedef dogrultusu engel orani", "Rota uzerindeki yapisal zorluk"],
        ["8", "Hucre riski", "Aktif/pasif tehdit bilgisi"],
    ], [1.2 * cm, 7.0 * cm, 7.4 * cm]))
    story.append(PageBreak())

    # Page 6 - Training and fixes
    story += [P("3.3 Egitim ve Dogrulama", "h1"), P(
        "Son model 157.693 egitim ve 31.668 dogrulama ornegiyle 80 epoch egitilmistir. Egitim haritalari "
        "42 tabanli seed grubundan, dogrulama haritalari 10042 tabanli ayri seed grubundan uretilmistir. "
        "Son egitim MSE degeri 15,5985; dogrulama MSE degeri 11,9248'dir. Nokta bazinda ayni haritayi "
        "rastgele bolmek yerine farkli haritalar kullanilmasi veri sizintisi riskini azaltir."
    )]
    story += report_image(ASSET_DIR / "training_curve.png", 16.0, "Sekil 1. MLP egitim ve dogrulama kaybinin epoch boyunca degisimi.")
    story += [P("4. Uygulama Duzeltmeleri", "h1")]
    story.append(styled_table([
        ["Duzeltme", "Guncel Uygulama"],
        ["Zaman farkindaligi", "Neural ozellikler her dugumun varis zamaniyla hesaplanir."],
        ["Ground-truth yonu", "Girilen hucreye bagli maliyet icin ters kenar maliyeti kullanilir."],
        ["Dogrulama ayrimi", "Egitim ve validation farkli harita seed'lerinden gelir."],
        ["Arama siniri", "max_nodes limiti gercek genisletme sayisina uygulanir."],
        ["Sunum", "Koyu tema, benchmark ve time_path tabanli snapshot eklenmistir."],
    ], [4.8 * cm, 11.0 * cm]))
    story.append(PageBreak())

    # Page 7 - Experimental setup and aggregate results
    story += [P("5. Deneysel Kurulum", "h1"), P(
        "Dort senaryo ayni seed=42 haritalarinda ve baslangic-hedef ciftlerinde calistirilmistir. Dijkstra "
        "optimal referans, Octile guclu admissible baseline, Manhattan ise 8-yonlu modelde inadmissible "
        "karsilastirma olarak kullanilmistir. Ana metrikler genisletilen dugum ve rota maliyetidir."
    ), P("6. Toplu Deney Sonuclari", "h1")]
    node_rows = [["Senaryo", "Dijkstra", "Manhattan", "Octile", "Neural", "Neural vs Octile"]]
    cost_rows = [["Senaryo", "Dijkstra", "Manhattan", "Octile", "Neural", "Neural Sapma"]]
    for scenario, title, _ in SCENARIOS:
        rs = results[scenario]
        node_rows.append([
            title, f"{rs[METHODS[0]].nodes_expanded:,}".replace(",", "."),
            f"{rs[METHODS[1]].nodes_expanded:,}".replace(",", "."),
            f"{rs[METHODS[2]].nodes_expanded:,}".replace(",", "."),
            f"{rs[METHODS[3]].nodes_expanded:,}".replace(",", "."),
            f"{pct(rs[METHODS[2]].nodes_expanded, rs[METHODS[3]].nodes_expanded):+.1f}%",
        ])
        cost_rows.append([
            title, f"{rs[METHODS[0]].cost:.2f}", f"{rs[METHODS[1]].cost:.2f}",
            f"{rs[METHODS[2]].cost:.2f}", f"{rs[METHODS[3]].cost:.2f}",
            f"{pct(rs[METHODS[0]].cost, rs[METHODS[3]].cost):+.2f}%",
        ])
    story.append(styled_table(node_rows, [3.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 3.0 * cm]))
    story.append(P("Tablo 7. Genisletilen dugum sayilari. Negatif yuzde Neural'in daha az dugum actigini gosterir.", "caption"))
    story.append(styled_table(cost_rows, [3.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 3.0 * cm]))
    story.append(P("Tablo 8. Rota maliyetleri ve Dijkstra optimumuna gore Neural sapmasi.", "caption"))
    story += [P(
        "Neural, Basit Sizma'da Octile'a gore %8,4 ve Sehir Operasyonu'nda %19,6 daha az dugum "
        "genisletmistir. Buna karsilik Koridor'da %105,5, Dinamik Tehdit'te %15,0 daha fazla dugum "
        "genisletmistir. Sonuc, ogrenilmis heuristicin kazancinin senaryo yapisina bagli oldugunu gosterir."
    ), PageBreak()]

    # Pages 8-11 - Scenario pages
    scenario_notes = {
        "simple": "Neural, Octile'dan daha az dugum genisletmis; rota maliyeti Dijkstra optimumundan yaklasik %0,91 sapmistir.",
        "urban": "Neural, Octile'a gore %19,6 daha az dugum genisletmistir. Maliyet sapmasi yaklasik %2,03'tur.",
        "corridor": "Dar gecit yapisinda Octile en verimli guvenli baseline olmustur. Neural daha fazla dugum acmis ve maliyette yaklasik %5,36 sapmistir.",
        "dynamic": "Dinamik tehdit senaryosunda Octile daha az dugum acmistir. Neural maliyet sapmasi yaklasik %0,92'dir.",
    }
    for index, (scenario, title, prefix) in enumerate(SCENARIOS, start=1):
        story += [P(f"7.{index} {title} Senaryosu", "h1"), P(scenario_notes[scenario])]
        story += report_image(ASSET_DIR / f"{prefix}_routes.png", 16.4, f"Sekil {index * 2}. {title} icin zaman-genisletmeli rota karsilastirmasi.")
        story += report_image(ASSET_DIR / f"{prefix}_benchmark.png", 16.4, f"Sekil {index * 2 + 1}. {title} icin dugum ve rota maliyeti paneli.")
        story.append(PageBreak())

    # Page 12 - Heatmaps
    story += [P("8. Heuristic Heatmap Analizi", "h1"), P(
        "Heatmap'ler ayni Sehir Operasyonu haritasinda Manhattan ve Neural heuristic degerlerinin uzamsal "
        "dagilimini gosterir. Manhattan yalnizca geometrik uzakliga baglidir. Neural yuzey ise mesafe "
        "ozelliklerine ek olarak lokal engel yogunlugu, hedef dogrultusu ve t=0 anindaki hucre riskini kullanir. "
        "Renkler her panel icinde normalize edildigi icin mutlak renk degil, uzamsal desen karsilastirilmalidir."
    )]
    heat_table = Table([
        [Image(str(ASSET_DIR / "urban_manhattan_heatmap.png"), width=8.0 * cm, height=8.0 * cm),
         Image(str(ASSET_DIR / "urban_neural_heatmap.png"), width=8.0 * cm, height=8.0 * cm)]
    ], colWidths=[8.2 * cm, 8.2 * cm])
    story.append(heat_table)
    story.append(P("Sekil 10-11. Sehir senaryosunda Manhattan (sol) ve Neural (sag) heuristic yuzeyleri.", "caption"))
    story += [P("8.1 Zaman Uyumlu Snapshot'lar", "h2"), P(
        "Demo modu Neural rota icin her bes adimda bir snapshot uretir. Her karede tehditlerin aktif/pasif "
        "durumu result.time_path alanindaki gercek varis zamaniyla cizilir. Boylece tek bir t=0 haritasi "
        "uzerinden dinamik rota yorumu yapma hatasi onlenir."
    ), PageBreak()]

    # Page 13 - Discussion
    story += [P("9. Tartisma ve Sinirliliklar", "h1"), P("9.1 Bulgularin Yorumu", "h2"), P(
        "Sonuclar Neural heuristicin her ortamda klasik Octile'i gecmedigini acikca gostermektedir. Sehir "
        "ve basit haritalarda ogrenilen cevre ozellikleri aramayi daha dogrudan yonlendirirken, dar koridor "
        "yapisinda modelin tahmin hatasi hem dugum sayisini hem rota maliyetini artirmistir. Bu nedenle "
        "Neural yontem tek basina ustun bir algoritma olarak degil, senaryoya bagli bir performans-kalite "
        "takasi olarak yorumlanmalidir."
    ), P("9.2 Manhattan Sonuclarinin Yorumu", "h2"), P(
        "Manhattan cok az dugum acsa da 8-yonlu ve sqrt(2) capraz maliyetli modelde admissible degildir. "
        "Bu nedenle dugum sayisi tek basina basari kaniti sayilamaz."
    ), P("9.3 Sinirliliklar", "h2")]
    for item in [
        "Neural heuristic admissible degildir ve optimalite garantisi vermez.",
        "Egitim etiketleri belirli bir zaman fazindaki statik maliyet yuzeyinden uretilir; tam dinamik cost-to-go etiketi degildir.",
        "Ana deney tablosu tek seed kosumudur; istatistiksel sonuc icin coklu seed, ortalama ve standart sapma gerekir.",
        "MLP inference maliyeti, dugum azalmasi olsa bile calisma suresini artirabilir.",
        "Simulasyon 2D grid, bilinen periyodik tehditler ve basit risk maliyetiyle sinirlidir.",
    ]:
        story.append(bullet(item))
    story += [P("9.4 Gelecek Calismalar", "h2")]
    for item in [
        "Farkli seed'lerle coklu tekrar ve guven araligi raporlamak.",
        "Tam zaman-genisletmeli cost-to-go etiketleriyle egitim yapmak.",
        "h=min(MLP, Octile) gibi admissible sinirlandirmalari deneysel olarak karsilastirmak.",
        "3D rota, yakit, ruzgar ve coklu IHA koordinasyonu eklemek.",
    ]:
        story.append(bullet(item))
    story.append(PageBreak())

    # Page 14 - Instructions, conclusion, references
    story += [P("10. Calistirma Talimatlari", "h1"), P("Windows PowerShell:", "h2")]
    story += [P(
        ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt<br/>"
        ".\\.venv\\Scripts\\python.exe src\\main.py --mode demo --planner dynamic<br/>"
        ".\\.venv\\Scripts\\python.exe src\\generate_final_report.py",
        "code",
    )]
    story += [P("Test komutu:", "h2"), P("python -m unittest discover -s tests -v", "code")]
    story += [P("11. Sonuc", "h1"), P(
        "Proje, klasik A* ile ogrenilmis heuristic yaklasimini dinamik IHA rota planlama problemi uzerinde "
        "bir araya getirmistir. Duzeltilmis uygulama zaman bilgisini Neural ozelliklere tasimis, yonlu "
        "ground-truth maliyetini duzeltmis ve dogrulamayi ayri harita seed'leriyle yapmistir. Neural heuristic "
        "iki senaryoda Octile'a gore daha az, iki senaryoda daha fazla dugum genisletmistir. Bu dengeli sonuc, "
        "ogrenilmis heuristiclerin faydasinin ortam yapisina ve tahmin kalitesine bagli oldugunu gostermektedir."
    ), P("Kaynakca", "h1")]
    refs = [
        "Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. IEEE TSSC, 4(2), 100-107.",
        "Russell, S., & Norvig, P. (2020). Artificial Intelligence: A Modern Approach (4th ed.). Pearson.",
        "Kingma, D. P., & Ba, J. (2015). Adam: A method for stochastic optimization. ICLR.",
        "Yonetani, R. et al. (2021). Path Planning using Neural A* Search. ICML.",
        "LaValle, S. M. (2006). Planning Algorithms. Cambridge University Press.",
    ]
    for i, ref in enumerate(refs, 1):
        story.append(P(f"{i}. {ref}", "bullet"))
    story.append(PageBreak())

    # Page 15 - Appendix
    story += [P("Ek A. Proje Klasor Yapisi", "h1"), P(
        "neural_astar_uav_birlesik/<br/>"
        "|-- src/<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- environment.py<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- astar.py<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- neural_heuristic.py<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- visualization.py<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- main.py<br/>"
        "|&nbsp;&nbsp;&nbsp;|-- generate_final_report.py<br/>"
        "|-- data/mlp_heuristic.pkl<br/>"
        "|-- tests/test_core.py<br/>"
        "|-- visualizations/<br/>"
        "|-- report/<br/>"
        "|-- MODEL_CARD.md<br/>"
        "|-- README.md<br/>"
        "`-- requirements.txt", "code"
    ), P("Ek B. Dogrulama Testleri", "h1")]
    test_rows = [
        ["Test", "Beklenen Davranis", "Sonuc"],
        ["Ground-truth", "Ters etiket ileri Dijkstra maliyetiyle esit", "Gecti"],
        ["Dinamik zaman", "Heuristic birden fazla varis zamani alir", "Gecti"],
        ["Rota guvenligi", "Her konum kendi varis zamaninda gecilebilir", "Gecti"],
        ["Corner-cutting", "Iki engel arasindan capraz gecis yok", "Gecti"],
        ["Neural cache", "Onbellek zaman adimini anahtara dahil eder", "Gecti"],
    ]
    story.append(styled_table(test_rows, [4.2 * cm, 9.5 * cm, 2.2 * cm]))
    story += [Spacer(1, 0.4 * cm), P(
        "Bes testin tamami basariyla gecmistir. Dinamik ve statik demo modlari egitilmis modelle uctan uca "
        "calistirilmistir. Rapor tablolari bu guncel model ve seed=42 deney kosumundan uretilmistir."
    )]

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def main():
    model, results, environments, missions = run_experiments()
    build_assets(model, results, environments, missions)
    build_report(model, results)
    print(f"Guncel rapor olusturuldu: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
