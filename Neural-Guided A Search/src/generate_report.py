"""
PDF Report Generator - Neural-Guided A* Project
------------------------------------------------
Rapor metni ve tabloları, mümkün olduğunca visualizations/ozet.txt dosyasından
okunan güncel demo çıktılarıyla üretilir. Böylece kod çıktısı ile rapor arasındaki
hardcoded sonuç tutarsızlığı azaltılır.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Image, Table, TableStyle,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

SCENARIO_LABELS = {
    "simple": "Basit (Senaryo 1)",
    "urban": "Şehir (Senaryo 2)",
    "corridor": "Koridor (Senaryo 3)",
    "dynamic": "Dinamik (Senaryo 4)",
}

HEURISTIC_LABELS = ["Dijkstra", "Manhattan", "Octile", "Neural"]


def register_turkish_fonts() -> str:
    """Türkçe karakter destekli fontları kaydet. Font yoksa Helvetica'a düş."""
    font_dir = Path("/usr/share/fonts/truetype/dejavu")
    normal = font_dir / "DejaVuSans.ttf"
    bold = font_dir / "DejaVuSans-Bold.ttf"
    mono = font_dir / "DejaVuSansMono.ttf"

    if normal.exists() and bold.exists() and mono.exists():
        pdfmetrics.registerFont(TTFont("DejaVu", str(normal)))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(bold)))
        pdfmetrics.registerFont(TTFont("DejaVu-Mono", str(mono)))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            "DejaVu",
            normal="DejaVu", bold="DejaVu-Bold",
            italic="DejaVu", boldItalic="DejaVu-Bold",
        )
        return "DejaVu"
    print("Uyarı: DejaVu fontları bulunamadı; Helvetica kullanılacak.")
    return "Helvetica"


def build_styles(base_font: str):
    bold_font = "DejaVu-Bold" if base_font == "DejaVu" else "Helvetica-Bold"
    mono_font = "DejaVu-Mono" if base_font == "DejaVu" else "Courier"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverTitle", fontName=bold_font,
        fontSize=22, leading=28, alignment=TA_CENTER,
        textColor=colors.HexColor("#0d47a1"), spaceAfter=20,
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle", fontName=base_font,
        fontSize=13, leading=17, alignment=TA_CENTER,
        textColor=colors.HexColor("#37474f"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeading", fontName=bold_font,
        fontSize=15, leading=19,
        textColor=colors.HexColor("#0d47a1"),
        spaceBefore=16, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="SubHeading", fontName=bold_font,
        fontSize=12, leading=15,
        textColor=colors.HexColor("#263238"),
        spaceBefore=10, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="BodyTR", fontName=base_font,
        fontSize=10, leading=15, alignment=TA_JUSTIFY,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="BulletTR", fontName=base_font,
        fontSize=10, leading=14, alignment=TA_JUSTIFY,
        leftIndent=14, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Caption", fontName=base_font,
        fontSize=9, leading=11, alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="CodeBlock", fontName=mono_font,
        fontSize=8.5, leading=11, leftIndent=12, rightIndent=12,
        backColor=colors.HexColor("#f4f4f4"),
        borderColor=colors.HexColor("#cccccc"),
        borderWidth=0.5, borderPadding=6, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="TableCell", fontName=base_font,
        fontSize=8.5, leading=11, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="TableCellCenter", fontName=base_font,
        fontSize=8.5, leading=11, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableHeader", fontName=bold_font,
        fontSize=8.5, leading=11, alignment=TA_CENTER,
        textColor=colors.white,
    ))
    return styles


def add_image(story, image_path, width_cm=15, caption=None, styles=None):
    """Resmi oranını koruyarak ekle. Bulunamazsa uyarı basar."""
    image_path = Path(image_path)
    if not image_path.exists():
        print(f"Uyarı: görsel bulunamadı: {image_path}")
        return
    try:
        from PIL import Image as PILImage
        with PILImage.open(image_path) as pil_img:
            real_w, real_h = pil_img.size
        aspect = real_h / real_w
    except Exception:
        aspect = 0.6

    target_w = width_cm * cm
    target_h = target_w * aspect
    max_h = 18.5 * cm
    if target_h > max_h:
        target_h = max_h
        target_w = target_h / aspect

    story.append(Image(str(image_path), width=target_w, height=target_h))
    if caption and styles:
        story.append(Paragraph(caption, styles["Caption"]))
    story.append(Spacer(1, 0.2 * cm))


def parse_summary(summary_path: Path) -> Optional[Dict[str, Dict[str, Dict[str, float]]]]:
    """visualizations/ozet.txt dosyasını okur.

    Beklenen iki bölüm:
    - Senaryo Bazinda Genisletilen Dugum Sayilari
    - Maliyet Karsilastirmasi
    """
    if not summary_path.exists():
        print(f"Uyarı: özet dosyası bulunamadı: {summary_path}")
        return None

    result: Dict[str, Dict[str, Dict[str, float]]] = {"nodes": {}, "costs": {}}
    section = None
    for raw in summary_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or set(line) <= {"=", "-"}:
            continue
        if "Dugum" in line or "Düğüm" in line or "Genisletilen" in line:
            section = "nodes"
            continue
        if "Maliyet" in line:
            section = "costs"
            continue
        if line.startswith("Senaryo"):
            continue
        if section not in result:
            continue

        parts = re.split(r"\s+", line)
        if len(parts) < 5:
            continue
        scenario = parts[0]
        values = parts[1:5]
        parsed_values = []
        for val in values:
            val = val.replace(",", "")
            try:
                parsed_values.append(float(val))
            except ValueError:
                parsed_values.append(float("nan"))
        result[section][scenario] = dict(zip(HEURISTIC_LABELS, parsed_values))

    if not result["nodes"] or not result["costs"]:
        print(f"Uyarı: özet dosyası eksik/uyumsuz görünüyor: {summary_path}")
        return None
    return result


def fmt_int(value: float) -> str:
    return f"{int(value):,}".replace(",", ".")


def fmt_cost(value: float) -> str:
    return f"{value:.2f}"


def pct_vs(base: float, value: float) -> str:
    if base == 0:
        return "-"
    pct = (value - base) / base * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def gap_text(opt_cost: float, cost: float) -> str:
    if abs(cost - opt_cost) <= 1e-6:
        return "optimal"
    gap = (cost - opt_cost) / opt_cost * 100 if opt_cost else 0
    return f"%{gap:.2f} sapma"


def make_node_table(summary, styles):
    data = [[
        Paragraph("Senaryo", styles["TableHeader"]),
        Paragraph("Dijkstra<br/>(h=0)", styles["TableHeader"]),
        Paragraph("Manhattan", styles["TableHeader"]),
        Paragraph("Octile", styles["TableHeader"]),
        Paragraph("Neural", styles["TableHeader"]),
        Paragraph("Neural<br/>vs Octile", styles["TableHeader"]),
    ]]
    for scenario in ["simple", "urban", "corridor", "dynamic"]:
        vals = summary["nodes"].get(scenario, {})
        octile = vals.get("Octile", 0)
        neural = vals.get("Neural", 0)
        data.append([
            Paragraph(SCENARIO_LABELS.get(scenario, scenario), styles["TableCell"]),
            Paragraph(fmt_int(vals.get("Dijkstra", 0)), styles["TableCellCenter"]),
            Paragraph(fmt_int(vals.get("Manhattan", 0)) + "*", styles["TableCellCenter"]),
            Paragraph(fmt_int(octile), styles["TableCellCenter"]),
            Paragraph(fmt_int(neural), styles["TableCellCenter"]),
            Paragraph(pct_vs(octile, neural), styles["TableCellCenter"]),
        ])
    table = Table(data, colWidths=[3.0 * cm, 2.4 * cm, 2.4 * cm, 2.2 * cm, 2.2 * cm, 2.6 * cm])
    table.setStyle(default_table_style())
    return table


def make_cost_table(summary, styles):
    data = [[
        Paragraph("Senaryo", styles["TableHeader"]),
        Paragraph("Dijkstra", styles["TableHeader"]),
        Paragraph("Manhattan", styles["TableHeader"]),
        Paragraph("Octile", styles["TableHeader"]),
        Paragraph("Neural", styles["TableHeader"]),
        Paragraph("Neural durumu", styles["TableHeader"]),
    ]]
    for scenario in ["simple", "urban", "corridor", "dynamic"]:
        vals = summary["costs"].get(scenario, {})
        opt = vals.get("Dijkstra", vals.get("Octile", 0))
        data.append([
            Paragraph(SCENARIO_LABELS.get(scenario, scenario), styles["TableCell"]),
            Paragraph(fmt_cost(vals.get("Dijkstra", 0)), styles["TableCellCenter"]),
            Paragraph(fmt_cost(vals.get("Manhattan", 0)), styles["TableCellCenter"]),
            Paragraph(fmt_cost(vals.get("Octile", 0)), styles["TableCellCenter"]),
            Paragraph(fmt_cost(vals.get("Neural", 0)), styles["TableCellCenter"]),
            Paragraph(gap_text(opt, vals.get("Neural", 0)), styles["TableCellCenter"]),
        ])
    table = Table(data, colWidths=[3.0 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 3.0 * cm])
    table.setStyle(default_table_style())
    return table


def default_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d47a1")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.gray),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ])


def get_summary_sentence(summary) -> str:
    if not summary:
        return "Sonuçlar, rapor üretim anındaki ozet.txt dosyasından okunamadığı için bu bölümde yalnızca nitel değerlendirme verilmiştir."
    nodes = summary["nodes"]
    costs = summary["costs"]
    pieces = []
    for sc in ["urban", "corridor", "dynamic"]:
        n = nodes.get(sc, {})
        c = costs.get(sc, {})
        if not n or not c:
            continue
        saving = -((n["Neural"] - n["Octile"]) / n["Octile"] * 100) if n["Octile"] else 0
        gap = ((c["Neural"] - c["Dijkstra"]) / c["Dijkstra"] * 100) if c["Dijkstra"] else 0
        pieces.append(f"{SCENARIO_LABELS[sc].split()[0]} senaryosunda %{saving:.1f} daha az düğüm, maliyet sapması %{gap:.2f}")
    return "; ".join(pieces) + "."


def build_report(
    visualizations_dir: str = str(PROJECT_DIR / "visualizations"),
    output_path: str = str(PROJECT_DIR / "report" / "proje_raporu.pdf"),
):
    visualizations_dir = Path(visualizations_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base_font = register_turkish_fonts()
    styles = build_styles(base_font)
    summary = parse_summary(visualizations_dir / "ozet.txt")

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2.0 * cm, rightMargin=2.0 * cm,
        title="Neural-Guided A* Search for Dynamic Route Optimization",
    )
    story = []

    # Kapak
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Neural-Guided A* Search<br/>for Dynamic Route Optimization", styles["CoverTitle"]))
    story.append(Paragraph("Dinamik Rota Optimizasyonu için<br/>Sinir Ağı Destekli A* Araması", styles["CoverSubtitle"]))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("<b>Uygulama Alanı:</b> İHA/SİHA Otonom Görev Planlaması", styles["CoverSubtitle"]))
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("Yapay Zeka Dersi Dönem Projesi", styles["CoverSubtitle"]))
    story.append(Paragraph("Mayıs 2026", styles["CoverSubtitle"]))
    story.append(PageBreak())

    # Özet
    story.append(Paragraph("Özet", styles["SectionHeading"]))
    story.append(Paragraph(
        """Bu projede, İnsansız Hava Aracı (İHA) ve Silahlı İnsansız Hava Aracı (SİHA)
        gibi otonom hava platformları için dinamik tehdit ortamlarında rota planlama
        problemi ele alınmıştır. Sistem, klasik A* arama algoritmasını Manhattan, Octile
        ve sıfır heuristic'li Dijkstra baseline ile karşılaştırır; ayrıca ortamdan çıkarılan
        özniteliklerle eğitilen NumPy tabanlı bir MLP heuristic kullanır. Düzeltilmiş
        sürümde dinamik tehditler yalnızca başlangıç anındaki statik harita olarak değil,
        zaman-genişletmeli A* yapısı içinde (satır, sütun, zaman) durumu ile ele alınmıştır.
        Neural heuristic bazı engel yoğun senaryolarda Octile'a göre daha az düğüm
        genişletir; ancak admissibility garantisi olmadığı için her durumda optimal maliyet
        garantisi vermez. Bu nedenle sonuçlar, hız/arama verimliliği ile rota kalitesi
        arasındaki takas olarak değerlendirilmiştir.""",
        styles["BodyTR"],
    ))
    story.append(Paragraph("<b>Anahtar Kelimeler:</b> A* Araması, Dijkstra, Octile Heuristic, Sinir Ağı, MLP, İHA/SİHA, Dinamik Tehdit, Rota Optimizasyonu.", styles["BodyTR"]))

    # Sistem tasarımı
    story.append(Paragraph("1. Giriş ve Proje Hedefi", styles["SectionHeading"]))
    story.append(Paragraph(
        """Modern İHA görevlerinde rota planlama algoritması, statik engellerin yanında
        zamanla aktif/pasif olabilen radar veya SAM bölgelerini de hesaba katmalıdır.
        Klasik A* algoritması uygun bir heuristic ile verimli çalışır; ancak heuristic
        admissible değilse optimalite garantisi kaybolur. Bu projede hedef, klasik
        heuristic'ler ile öğrenilmiş bir heuristic'i aynı operasyonel senaryolarda
        karşılaştırmak ve dinamik tehditler için zaman boyutunu aramaya dahil etmektir.""",
        styles["BodyTR"],
    ))
    goals = [
        "50x50 grid tabanlı İHA operasyon ortamı oluşturmak.",
        "Statik A* ve zaman-genişletmeli dinamik A* planlayıcılarını çalıştırmak.",
        "Dijkstra (h=0), Manhattan, Octile ve Neural (MLP) heuristic'lerini karşılaştırmak.",
        "Bulunan yolları düğüm genişletme, çalışma süresi ve rota maliyeti açısından analiz etmek.",
    ]
    for g in goals:
        story.append(Paragraph(f"• {g}", styles["BulletTR"]))

    story.append(Paragraph("2. Sistem Tasarımı", styles["SectionHeading"]))
    story.append(Paragraph("2.1 Operasyon Ortamı", styles["SubHeading"]))
    env_data = [
        [Paragraph("Hücre tipi", styles["TableHeader"]), Paragraph("Açıklama", styles["TableHeader"]), Paragraph("Geçilebilirlik", styles["TableHeader"])],
        [Paragraph("Boş saha", styles["TableCell"]), Paragraph("Açık hava sahası", styles["TableCell"]), Paragraph("Evet, maliyet 1.0", styles["TableCellCenter"])],
        [Paragraph("Statik engel", styles["TableCell"]), Paragraph("Dağ/bina", styles["TableCell"]), Paragraph("Hayır", styles["TableCellCenter"])],
        [Paragraph("Aktif tehdit", styles["TableCell"]), Paragraph("Aktif radar/SAM", styles["TableCell"]), Paragraph("Hayır", styles["TableCellCenter"])],
        [Paragraph("Pasif tehdit", styles["TableCell"]), Paragraph("Geçici güvenli tehdit alanı", styles["TableCell"]), Paragraph("Evet, risk maliyeti", styles["TableCellCenter"])],
        [Paragraph("Yasak bölge", styles["TableCell"]), Paragraph("Havalimanı/kritik tesis", styles["TableCell"]), Paragraph("Hayır", styles["TableCellCenter"])]
    ]
    table = Table(env_data, colWidths=[3.2*cm, 6.5*cm, 4.0*cm])
    table.setStyle(default_table_style())
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        """Düzeltilmiş kodda çapraz hareketlerde corner-cutting kontrolü yapılır;
        yani iki engelin köşesinden fiziksel olarak mümkün olmayan geçişlere izin
        verilmez. Ayrıca bir hücre birden fazla tehdit bölgesinin içinde kalıyorsa,
        bu tehditlerden herhangi biri aktif olduğunda hücre aktif tehdit kabul edilir.""",
        styles["BodyTR"],
    ))

    story.append(Paragraph("2.2 A* ve Dinamik A*", styles["SubHeading"]))
    story.append(Paragraph(
        """Klasik A*, f(n) = g(n) + h(n) değerini kullanır. Statik planlayıcıda durum
        yalnızca (satır, sütun) konumudur. Dinamik planlayıcıda ise durum (satır, sütun,
        zaman) olarak tutulur; her hareketten sonra zaman bir adım ilerler ve komşu hücrenin
        geçilebilirliği varış zamanında kontrol edilir. Bu sayede periyodik olarak açılıp
        kapanan tehditler rota boyunca hesaba katılır.""",
        styles["BodyTR"],
    ))
    story.append(Paragraph(
        """function DynamicAStar(start, goal):<br/>
        &nbsp;&nbsp;open.push((start_row, start_col, start_time))<br/>
        &nbsp;&nbsp;while open is not empty:<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;current = pop_lowest_f()<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;if current.position == goal: return path<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;next_time = current.time + 1<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;for neighbor in passable_neighbors_at(next_time):<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;relax neighbor with g + movement_cost""",
        styles["CodeBlock"],
    ))

    story.append(Paragraph("2.3 Karşılaştırılan Heuristic Fonksiyonlar", styles["SubHeading"]))
    heuristic_data = [
        [Paragraph("Heuristic", styles["TableHeader"]), Paragraph("Kullanım", styles["TableHeader"]), Paragraph("Not", styles["TableHeader"])],
        [Paragraph("Dijkstra (h=0)", styles["TableCell"]), Paragraph("Optimum kontrolü", styles["TableCell"]), Paragraph("En çok düğüm genişletir", styles["TableCell"])],
        [Paragraph("Manhattan", styles["TableCell"]), Paragraph("|dr| + |dc|", styles["TableCell"]), Paragraph("8-yönlü harekette inadmissible", styles["TableCell"])],
        [Paragraph("Octile", styles["TableCell"]), Paragraph("8-yönlü hareket için klasik heuristic", styles["TableCell"]), Paragraph("Admissible ve güçlü baseline", styles["TableCell"])],
        [Paragraph("Neural (MLP)", styles["TableCell"]), Paragraph("8 öznitelikten tahmin", styles["TableCell"]), Paragraph("Daha yönlendirici olabilir, optimal garanti yok", styles["TableCell"])],
    ]
    table = Table(heuristic_data, colWidths=[3.5*cm, 5.5*cm, 5.0*cm])
    table.setStyle(default_table_style())
    story.append(table)

    # Sinir ağı
    story.append(Paragraph("3. Sinir Ağı Tasarımı", styles["SectionHeading"]))
    story.append(Paragraph(
        """Neural heuristic, NumPy ile sıfırdan yazılmış çok katmanlı algılayıcıdır.
        Model mimarisi 8 giriş özniteliği, 64-64-32 gizli nöron ve tek lineer regresyon
        çıkışından oluşur. Giriş öznitelikleri Manhattan/Euclidean/Octile uzaklıklarını,
        hedef yönünü, lokal engel yoğunluğunu, hedef yönündeki engel oranını ve hücre riskini
        içerir. Eğitim hedefi, Dijkstra ile hesaplanan gerçek mesafe değerlerine yaklaşmaktır.""",
        styles["BodyTR"],
    ))
    add_image(story, visualizations_dir / "00_egitim_kaybi.png", width_cm=12,
              caption="Şekil 1: MLP eğitim kaybı grafiği.", styles=styles)

    # Deneyler ve görseller
    story.append(PageBreak())
    story.append(Paragraph("4. Deneysel Sonuçlar", styles["SectionHeading"]))
    story.append(Paragraph(
        """Dört senaryoda Dijkstra, Manhattan, Octile ve Neural heuristic çalıştırılmıştır.
        Görsellerde mavi noktalar genişletilen düğümleri, sarı çizgi bulunan rotayı gösterir.
        Bu rapordaki tablolar, demo çalıştırması sonucu üretilen visualizations/ozet.txt
        dosyasından okunmuştur.""",
        styles["BodyTR"],
    ))

    scenario_figs = [
        ("01_basit", "4.1 Senaryo 1: Basit Sızma Görevi", "Az engelli ortam, tek radar bölgesi ve şehir/dağ engelleri."),
        ("02_sehir", "4.2 Senaryo 2: Şehir Operasyonu", "Yoğun bina kümeleri, çoklu SAM/EW tehdidi ve yasak bölge."),
        ("03_koridor", "4.3 Senaryo 3: Koridor Geçişi", "İki engel hattı arasında dar koridor ve dinamik tehditler."),
        ("04_dinamik", "4.4 Senaryo 4: Dinamik Tehdit Ortamı", "Aktivasyon paterni değişen çoklu radar/SAM bölgeleri."),
    ]
    for prefix, heading, desc in scenario_figs:
        story.append(Paragraph(heading, styles["SubHeading"]))
        story.append(Paragraph(desc, styles["BodyTR"]))
        add_image(story, visualizations_dir / f"{prefix}_karsilastirma_gorsel.png", width_cm=16,
                  caption=f"{heading} - heuristic karşılaştırması.", styles=styles)

    story.append(Paragraph("4.5 Heuristic Heatmap Karşılaştırması", styles["SubHeading"]))
    story.append(Paragraph(
        """Heatmap görselleri, seçilen senaryoda Manhattan ve Neural heuristic'in hedefe
        kalan maliyet tahminlerini karşılaştırır. Manhattan yalnızca geometrik uzaklığı
        bilir; Neural ise eğitim verisinden öğrendiği engel/risk örüntülerini tahmine
        yansıtabilir.""",
        styles["BodyTR"],
    ))
    add_image(story, visualizations_dir / "02_sehir_heatmap_manhattan.png", width_cm=12,
              caption="Şekil: Şehir senaryosu Manhattan heuristic heatmap.", styles=styles)
    add_image(story, visualizations_dir / "02_sehir_heatmap_neural.png", width_cm=12,
              caption="Şekil: Şehir senaryosu Neural heuristic heatmap.", styles=styles)

    # Genel karşılaştırma
    story.append(PageBreak())
    story.append(Paragraph("5. Genel Karşılaştırma ve Analiz", styles["SectionHeading"]))
    if summary:
        story.append(Paragraph("5.1 Genişletilen Düğüm Sayıları", styles["SubHeading"]))
        story.append(make_node_table(summary, styles))
        story.append(Paragraph("Tablo 1: Dijkstra optimum kontrolü, Manhattan, Octile ve Neural için genişletilen düğüm sayıları. * Manhattan 8-yönlü harekette inadmissible olduğu için az düğüm açması tek başına başarı ölçütü değildir.", styles["Caption"]))

        story.append(Paragraph("5.2 Rota Maliyetleri", styles["SubHeading"]))
        story.append(make_cost_table(summary, styles))
        story.append(Paragraph("Tablo 2: Rota maliyetleri. Dijkstra (h=0) referans optimum olarak kullanılmıştır.", styles["Caption"]))

        story.append(Paragraph("5.3 Yorum", styles["SubHeading"]))
        story.append(Paragraph(
            f"""Güncel demo çıktısına göre Neural heuristic'in Octile'a göre düğüm genişletme
            kazancı senaryoya bağlıdır: {get_summary_sentence(summary)} Bu sonuç,
            Neural heuristic'in bazı karmaşık ortamlarda aramayı daha doğrudan yönlendirebildiğini,
            ancak admissibility garantisi olmadığı için maliyet sapması üretebildiğini gösterir.""",
            styles["BodyTR"],
        ))
    else:
        story.append(Paragraph("Özet dosyası bulunamadığı için tablolar üretilemedi. Önce python src/main.py --mode demo --planner dynamic komutunu çalıştırın.", styles["BodyTR"]))

    story.append(Paragraph("5.4 Manhattan'ın Yanıltıcı Performansı", styles["SubHeading"]))
    story.append(Paragraph(
        """Manhattan heuristic, 4-yönlü gridlerde admissible olsa da bu projede kullanılan
        8-yönlü harekette çapraz hareket maliyetini olduğundan yüksek tahmin edebilir.
        Bu durum A*'ı daha greedy hale getirir; düğüm sayısı azalabilir ama optimal rota
        garantisi kaybolur. Bu nedenle Manhattan sonuçları, hız göstergesi olarak değil,
        inadmissible heuristic örneği olarak yorumlanmalıdır.""",
        styles["BodyTR"],
    ))

    # Tartışma
    story.append(PageBreak())
    story.append(Paragraph("6. Tartışma ve Sınırlılıklar", styles["SectionHeading"]))
    benefits = [
        "Zaman-genişletmeli A* sayesinde tehdit durumu rota boyunca varış zamanına göre kontrol edilir.",
        "Dijkstra baseline eklenerek optimum maliyet referansı daha açık hale getirilmiştir.",
        "Menzil sınırı, corner-cutting kontrolü ve çakışan tehdit güvenliği kodda ele alınmıştır.",
        "Neural heuristic, ortam farkındalığı sağlayarak bazı senaryolarda daha az düğüm genişletebilir.",
    ]
    story.append(Paragraph("6.1 Güçlü Yönler", styles["SubHeading"]))
    for b in benefits:
        story.append(Paragraph(f"• {b}", styles["BulletTR"]))

    limitations = [
        "Neural heuristic admissible değildir; bu yüzden optimal maliyet garantisi yoktur.",
        "MLP forward pass maliyeti küçük gridlerde çalışma süresini artırabilir.",
        "Eğitim ve test senaryoları aynı senaryo ailesinden geldiği için genelleme iddiası sınırlıdır.",
        "Tehdit paternleri önceden bilinen periyodik yapıdadır; gerçek zamanlı algılayıcı entegrasyonu yoktur.",
        "Planlama 2D grid üzerindedir; gerçek İHA görevlerinde irtifa ve aerodinamik kısıtlar da gerekir.",
    ]
    story.append(Paragraph("6.2 Sınırlılıklar", styles["SubHeading"]))
    for l in limitations:
        story.append(Paragraph(f"• {l}", styles["BulletTR"]))

    future_work = [
        "Farklı harita seed'leriyle ortalama ve standart sapma raporlamak.",
        "Neural heuristic'i h = min(neural, octile) gibi admissible sınırlarla denemek.",
        "GNN veya CNN tabanlı harita-farkındalıklı heuristic modelleriyle karşılaştırmak.",
        "3D rota planlama, yakıt tüketimi ve çok-İHA koordinasyonu eklemek.",
    ]
    story.append(Paragraph("6.3 Gelecek Çalışmalar", styles["SubHeading"]))
    for fw in future_work:
        story.append(Paragraph(f"• {fw}", styles["BulletTR"]))

    # Sonuç
    story.append(Paragraph("7. Sonuç", styles["SectionHeading"]))
    story.append(Paragraph(
        """Bu proje, klasik A* aramasını öğrenilmiş heuristic yaklaşımıyla birleştirerek
        İHA/SİHA görev planlaması için deneysel bir rota optimizasyon sistemi sunmaktadır.
        Düzeltilmiş sürümde dinamik tehditler zaman-genişletmeli A* ile daha doğru
        modellenmiş; Dijkstra baseline, menzil kontrolü, corner-cutting engeli ve tehdit
        çakışması güvenliği eklenmiştir. Sonuçlar Neural heuristic'in bazı engel yoğun
        durumlarda düğüm sayısını azaltabildiğini, fakat optimalite garantisi olmadığı için
        rota maliyetinin mutlaka Dijkstra/Octile ile kontrol edilmesi gerektiğini göstermiştir.""",
        styles["BodyTR"],
    ))

    # Kaynaklar
    story.append(Paragraph("Kaynaklar", styles["SectionHeading"]))
    refs = [
        "Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A formal basis for the heuristic determination of minimum cost paths. IEEE Transactions on Systems Science and Cybernetics.",
        "Russell, S., & Norvig, P. (2020). Artificial Intelligence: A Modern Approach, 4th ed. Pearson.",
        "Kingma, D. P., & Ba, J. (2015). Adam: A method for stochastic optimization. ICLR.",
        "Yonetani, R., Taniai, T., Barekatain, M., Nishimura, M., & Kanezaki, A. (2021). Path Planning using Neural A* Search. ICML.",
        "LaValle, S. M. (2006). Planning Algorithms. Cambridge University Press.",
    ]
    for i, ref in enumerate(refs, 1):
        story.append(Paragraph(f"[{i}] {ref}", styles["BodyTR"]))

    # Ek
    story.append(PageBreak())
    story.append(Paragraph("Ek A: Proje Klasör Yapısı", styles["SectionHeading"]))
    structure = """neural_astar_uav_fixed_v2/
├── src/
│   ├── environment.py
│   ├── astar.py
│   ├── neural_heuristic.py
│   ├── visualization.py
│   ├── main.py
│   └── generate_report.py
├── data/
│   └── mlp_heuristic.pkl
├── visualizations/
├── report/
│   └── proje_raporu.pdf
├── requirements.txt
└── README.md"""
    story.append(Paragraph(structure.replace("\n", "<br/>").replace(" ", "&nbsp;"), styles["CodeBlock"]))

    story.append(Paragraph("Ek B: Çalıştırma Talimatları", styles["SectionHeading"]))
    story.append(Paragraph("Proje kök dizininden çalıştırma:", styles["BodyTR"]))
    story.append(Paragraph(
        "python&nbsp;src/main.py&nbsp;--mode&nbsp;demo&nbsp;--planner&nbsp;dynamic<br/>"
        "python&nbsp;src/generate_report.py",
        styles["CodeBlock"],
    ))
    story.append(Paragraph("Statik karşılaştırma ayrıca istenirse:", styles["BodyTR"]))
    story.append(Paragraph(
        "python&nbsp;src/main.py&nbsp;--mode&nbsp;demo&nbsp;--planner&nbsp;static&nbsp;--output&nbsp;visualizations_static",
        styles["CodeBlock"],
    ))

    doc.build(story)
    print(f"\n  -> Rapor olusturuldu: {output_path}")
    return str(output_path)


if __name__ == "__main__":
    build_report()
