"""
Visualization Module - UAV Mission Planning
--------------------------------------------
Bu modul, IHA gorev planlamasinin gorsellestirilmesi icin
fonksiyonlar saglar:

1. Operasyonel haritayi cizer (tehditler, engeller, yasak bolgeler)
2. A* tarafindan bulunan rotayi gosterir
3. Genisletilen dugumleri (search frontier) gorsellestirir
4. Heuristic degerlerinin heatmap'ini olusturur
5. Farkli heuristic'leri (klasik vs neural) yan yana karsilastirir
"""

import os
from typing import List, Optional, Tuple, Dict

import matplotlib
if not os.environ.get("MPLBACKEND"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import LinearSegmentedColormap, ListedColormap
import numpy as np

from environment import (
    UAVEnvironment, Mission,
    EMPTY, STATIC_OBSTACLE, ACTIVE_THREAT, PASSIVE_THREAT, NO_FLY,
)
from astar import AStarResult


# Renk paleti (operasyonel harita)
# 0: Bos (soluk yesil/temiz)
# 1: Statik engel (koyu gri)
# 2: Aktif tehdit (kirmizi)
# 3: Pasif tehdit (turuncu)
# 4: Yasak bolge (mor)
TERRAIN_COLORS = ListedColormap([
    "#e8f5e9",  # 0 EMPTY - acik yesil
    "#424242",  # 1 STATIC_OBSTACLE - koyu gri
    "#c62828",  # 2 ACTIVE_THREAT - kirmizi
    "#ff8f00",  # 3 PASSIVE_THREAT - turuncu
    "#6a1b9a",  # 4 NO_FLY - mor
])

MISSION_NAME_EN = {
    "Basit Sizma Gorevi": "Simple Infiltration Mission",
    "Sehir Operasyonu": "Urban Operation",
    "Koridor Gecisi": "Corridor Passage",
    "Dinamik Tehdit Ortami": "Dynamic Threat Environment",
}


def _mission_name_en(mission: Mission) -> str:
    return MISSION_NAME_EN.get(mission.name, mission.name)


def _draw_environment(ax, env: UAVEnvironment, time: int = 0):
    """Operasyonel haritayi ax uzerine cizer."""
    grid = np.zeros((env.size, env.size), dtype=int)
    for r in range(env.size):
        for c in range(env.size):
            grid[r, c] = env.get_cell_state(r, c, time=time)

    ax.imshow(grid, cmap=TERRAIN_COLORS, vmin=0, vmax=4, origin="upper")

    # Grid cizgileri
    ax.set_xticks(np.arange(-0.5, env.size, 5), minor=False)
    ax.set_yticks(np.arange(-0.5, env.size, 5), minor=False)
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.grid(True, color="gray", linewidth=0.3, alpha=0.5)
    ax.set_xlim(-0.5, env.size - 0.5)
    ax.set_ylim(env.size - 0.5, -0.5)

    # Tehdit merkezlerini isaretleyerek tipini yaz
    for threat in env.threats:
        is_active = env.is_threat_active(threat, time=time)
        symbol = threat.threat_type[0]  # S/R/E
        color = "white" if is_active else "yellow"
        center_r, center_c = threat.center_at(time)
        ax.text(
            center_c, center_r, symbol,
            ha="center", va="center",
            fontsize=10, fontweight="bold", color=color,
        )


def _draw_mission_endpoints(ax, mission: Mission):
    """Baslangic ve hedef noktalarini cizer."""
    sr, sc = mission.start
    gr, gc = mission.goal
    # Baslangic - mavi yildiz
    ax.plot(sc, sr, marker="*", markersize=22,
            markerfacecolor="#1976d2", markeredgecolor="white",
            markeredgewidth=2, zorder=5)
    ax.text(sc, sr - 1.5, "START", ha="center", fontsize=9,
            fontweight="bold", color="#0d47a1",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))
    # Hedef - yesil daire
    ax.plot(gc, gr, marker="o", markersize=18,
            markerfacecolor="#2e7d32", markeredgecolor="white",
            markeredgewidth=2, zorder=5)
    ax.text(gc, gr + 1.5, "GOAL", ha="center", fontsize=9,
            fontweight="bold", color="#1b5e20",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8))


def _add_legend(ax):
    """Lejand ekle."""
    legend_elements = [
        patches.Patch(facecolor="#e8f5e9", edgecolor="gray", label="Free cell"),
        patches.Patch(facecolor="#424242", label="Static obstacle"),
        patches.Patch(facecolor="#c62828", label="Active threat"),
        patches.Patch(facecolor="#ff8f00", label="Passive threat"),
        patches.Patch(facecolor="#6a1b9a", label="No-fly zone"),
    ]
    ax.legend(
        handles=legend_elements, loc="upper left",
        bbox_to_anchor=(1.02, 1.0), fontsize=9,
        framealpha=0.95, edgecolor="gray",
    )


# ============================================================
# 1. SADECE HARITA
# ============================================================

def visualize_environment(
    env: UAVEnvironment, mission: Mission,
    save_path: Optional[str] = None,
    title: str = "UAV Operational Map",
    time: int = 0,
):
    """Operasyonel haritayi ve gorev noktalarini gosterir."""
    fig, ax = plt.subplots(figsize=(11, 9))
    _draw_environment(ax, env, time=time)
    _draw_mission_endpoints(ax, mission)
    _add_legend(ax)

    ax.set_title(
        f"{title}\n"
        f"Mission: {_mission_name_en(mission)} | t={time} | "
        f"Manhattan distance: {abs(mission.goal[0]-mission.start[0]) + abs(mission.goal[1]-mission.start[1])} cells",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Map saved: {save_path}")
    plt.close()


# ============================================================
# 2. ROTA + GENISLETILEN DUGUMLER
# ============================================================

def visualize_astar_result(
    env: UAVEnvironment, mission: Mission, result: AStarResult,
    save_path: Optional[str] = None,
    title: Optional[str] = None,
    time: int = 0,
    show_explored: bool = True,
):
    """A* arama sonucunu gorsellestir.

    Gosterilen:
    - Harita
    - Genisletilen dugumler (gri/yarisaydam)
    - Bulunan rota (cizgi)
    - Baslangic ve hedef noktalari
    """
    fig, ax = plt.subplots(figsize=(11, 9))
    _draw_environment(ax, env, time=time)

    # Genisletilen dugumler (acik mavi noktalar)
    if show_explored and result.explored_set:
        exp_r = [p[0] for p in result.explored_set]
        exp_c = [p[1] for p in result.explored_set]
        ax.scatter(exp_c, exp_r, c="#64b5f6", s=20, alpha=0.4,
                   label=f"Expanded nodes ({len(result.explored_set)})",
                   zorder=2, edgecolors="none")

    # Rota
    if result.success and result.path:
        path_r = [p[0] for p in result.path]
        path_c = [p[1] for p in result.path]
        ax.plot(path_c, path_r, color="#fdd835", linewidth=3.5,
                alpha=0.95, zorder=4, label=f"Path ({len(result.path)} steps)")
        # Rota noktalari
        ax.scatter(path_c, path_r, c="#fbc02d", s=15, zorder=4, edgecolors="black", linewidths=0.5)

    _draw_mission_endpoints(ax, mission)
    _add_legend(ax)

    # Ust bilgi (basliktan ayri)
    if title is None:
        title = f"A* Search Result - Heuristic: {result.heuristic_name}"

    status = "SUCCESS" if result.success else "FAILED"
    info = (
        f"Status: {status} | "
        f"Expanded: {result.nodes_expanded:,} | "
        f"Cost: {result.cost:.2f}" if result.success else
        f"Status: {status} | Expanded: {result.nodes_expanded:,}"
    )
    ax.set_title(f"{title}\n{info}", fontsize=12, fontweight="bold")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Result visual saved: {save_path}")
    plt.close()


# ============================================================
# 3. HEURISTIC HEATMAP
# ============================================================

def visualize_heuristic_heatmap(
    env: UAVEnvironment, mission: Mission,
    heuristic_fn,
    save_path: Optional[str] = None,
    title: str = "Heuristic Values",
    time: int = 0,
):
    """Heuristic fonksiyonun her hucredeki tahminini heatmap olarak gosterir."""
    fig, ax = plt.subplots(figsize=(11, 9))

    # Her hucre icin h degerini hesapla
    h_grid = np.full((env.size, env.size), np.nan)
    for r in range(env.size):
        for c in range(env.size):
            if env.is_passable(r, c, time=time):
                h_grid[r, c] = heuristic_fn((r, c), mission.goal)

    # Heatmap (mask: gecilemez hucreler beyaz)
    masked = np.ma.array(h_grid, mask=np.isnan(h_grid))
    cmap = matplotlib.colormaps.get_cmap("viridis_r").copy()
    cmap.set_bad("lightgray")
    im = ax.imshow(masked, cmap=cmap, origin="upper", alpha=0.85)

    # Engelleri uzerine ciz (siyah)
    for r in range(env.size):
        for c in range(env.size):
            state = env.get_cell_state(r, c, time=time)
            if state in (STATIC_OBSTACLE, ACTIVE_THREAT, NO_FLY):
                ax.add_patch(patches.Rectangle(
                    (c - 0.5, r - 0.5), 1, 1,
                    facecolor={
                        STATIC_OBSTACLE: "#424242",
                        ACTIVE_THREAT: "#c62828",
                        NO_FLY: "#6a1b9a",
                    }[state],
                    edgecolor="none",
                ))

    _draw_mission_endpoints(ax, mission)

    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Estimated Distance to Goal (h)", fontweight="bold")

    ax.set_xticks(np.arange(-0.5, env.size, 5))
    ax.set_yticks(np.arange(-0.5, env.size, 5))
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.grid(True, color="gray", linewidth=0.3, alpha=0.5)
    ax.set_xlim(-0.5, env.size - 0.5)
    ax.set_ylim(env.size - 0.5, -0.5)

    ax.set_title(title, fontsize=13, fontweight="bold")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Heatmap saved: {save_path}")
    plt.close()


# ============================================================
# 4. KARSILASTIRMA (Yan yana)
# ============================================================

def compare_heuristics_visual(
    env: UAVEnvironment, mission: Mission,
    results: Dict[str, AStarResult],
    save_path: Optional[str] = None,
    title: str = "Heuristic Comparison",
    time: int = 0,
):
    """Birden cok heuristic sonucunu yan yana gosterir."""
    n = len(results)
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 7))
    if n == 1:
        axes = [axes]

    for ax, (name, result) in zip(axes, results.items()):
        _draw_environment(ax, env, time=time)

        # Genisletilen dugumler
        if result.explored_set:
            exp_r = [p[0] for p in result.explored_set]
            exp_c = [p[1] for p in result.explored_set]
            ax.scatter(exp_c, exp_r, c="#64b5f6", s=15, alpha=0.4, zorder=2, edgecolors="none")

        # Rota
        if result.success and result.path:
            path_r = [p[0] for p in result.path]
            path_c = [p[1] for p in result.path]
            ax.plot(path_c, path_r, color="#fdd835", linewidth=3, alpha=0.95, zorder=4)

        _draw_mission_endpoints(ax, mission)

        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlim(-0.5, env.size - 0.5)
        ax.set_ylim(env.size - 0.5, -0.5)

        status = "✓" if result.success else "✗"
        ax.set_title(
            f"{name}\n"
            f"{status} Expanded: {result.nodes_expanded:,} | "
            f"Cost: {result.cost:.1f}",
            fontsize=11, fontweight="bold",
        )

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Comparison saved: {save_path}")
    plt.close()


# ============================================================
# 5. BENCHMARK BAR CHART (Performans)
# ============================================================

def visualize_benchmark_bars(
    results: Dict[str, AStarResult],
    save_path: Optional[str] = None,
    title: str = "Heuristic Performance Comparison",
):
    """Heuristic'leri 3 metrik uzerinden bar chart ile karsilastirir.

    Metrikler:
    1. Genisletilen dugum sayisi (az = iyi)
    2. Calisma suresi
    3. Bulunan rota maliyeti (az = iyi)
    """
    names = list(results.keys())
    nodes_expanded = [r.nodes_expanded for r in results.values()]
    runtimes = [r.runtime_seconds * 1000 for r in results.values()]  # ms
    costs = [r.cost if r.success else 0 for r in results.values()]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Renkler - en iyi yesil, digerleri mavi/kirmizi
    def make_colors(values, lower_is_better=True):
        if lower_is_better:
            best_idx = values.index(min(values))
            worst_idx = values.index(max(values))
        else:
            best_idx = values.index(max(values))
            worst_idx = values.index(min(values))
        colors = []
        for i in range(len(values)):
            if i == best_idx:
                colors.append("#2ecc71")
            elif i == worst_idx:
                colors.append("#e74c3c")
            else:
                colors.append("#3498db")
        return colors

    # 1. Genisletilen dugumler
    ax = axes[0]
    colors = make_colors(nodes_expanded)
    bars = ax.bar(names, nodes_expanded, color=colors, edgecolor="black", linewidth=1.2)
    for bar, val in zip(bars, nodes_expanded):
        ax.text(bar.get_x() + bar.get_width() / 2, val,
                f"{val:,}", ha="center", va="bottom",
                fontweight="bold", fontsize=10)
    ax.set_ylabel("Expanded Node Count", fontweight="bold")
    ax.set_title("Search Efficiency (lower is better)", fontweight="bold")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(axis="y", alpha=0.3)

    # 2. Calisma suresi
    ax = axes[1]
    colors = make_colors(runtimes)
    bars = ax.bar(names, runtimes, color=colors, edgecolor="black", linewidth=1.2)
    for bar, val in zip(bars, runtimes):
        ax.text(bar.get_x() + bar.get_width() / 2, val,
                f"{val:.1f}ms", ha="center", va="bottom",
                fontweight="bold", fontsize=10)
    ax.set_ylabel("Runtime (ms)", fontweight="bold")
    ax.set_title("Speed (lower is better)", fontweight="bold")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(axis="y", alpha=0.3)

    # 3. Rota maliyeti
    ax = axes[2]
    colors = make_colors(costs)
    bars = ax.bar(names, costs, color=colors, edgecolor="black", linewidth=1.2)
    for bar, val in zip(bars, costs):
        ax.text(bar.get_x() + bar.get_width() / 2, val,
                f"{val:.1f}", ha="center", va="bottom",
                fontweight="bold", fontsize=10)
    ax.set_ylabel("Path Cost", fontweight="bold")
    ax.set_title("Path Quality (lower is closer to optimal)", fontweight="bold")
    ax.tick_params(axis="x", rotation=15)
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle(title, fontsize=14, fontweight="bold")
    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Benchmark saved: {save_path}")
    plt.close()


# ============================================================
# 6. EGITIM KAYIP GRAFIGI
# ============================================================

def visualize_training_history(
    model,
    save_path: Optional[str] = None,
    title: str = "MLP Training Process",
):
    """MLP egitimi sirasinda train/val loss grafigi."""
    history = model.training_history
    epochs = history["epoch"]
    train_loss = history["train_loss"]
    val_loss = history["val_loss"]

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(epochs, train_loss, label="Training Loss", color="#e74c3c",
            linewidth=2, marker="o", markersize=3)
    if any(v > 0 for v in val_loss):
        ax.plot(epochs, val_loss, label="Validation Loss", color="#2ecc71",
                linewidth=2, marker="s", markersize=3)

    ax.set_xlabel("Epoch", fontweight="bold", fontsize=12)
    ax.set_ylabel("MSE Loss", fontweight="bold", fontsize=12)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(alpha=0.3)
    ax.set_yscale("log")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=120, bbox_inches="tight")
        print(f"  -> Training chart saved: {save_path}")
    plt.close()


# ============================================================
# 7. KOYU TEMA ROTA KARSILASTIRMASI VE DINAMIK SNAPSHOT'LAR
# ============================================================

DARK_COLORS = {
    "background": "#1e1e1e",
    "grid": "#343434",
    "static": "#5c5c5c",
    "active": "#ff4c4c",
    "passive": "#f0a52b",
    "no_fly": "#7f1d1d",
    "start": "#16e060",
    "goal": "#20b8e8",
}

PATH_COLORS = {
    "Dijkstra (h=0)": "#f5f5f5",
    "Manhattan": "#ff2d8d",
    "Octile": "#18d898",
    "Neural (MLP)": "#ffd21f",
}


def _draw_environment_dark(ax, env: UAVEnvironment, time: int = 0):
    """Dinamik ortami koyu temada, tehdit alanlarini dairelerle cizer."""
    ax.set_facecolor(DARK_COLORS["background"])
    for r in range(env.size):
        for c in range(env.size):
            state = int(env.static_grid[r, c])
            if state == STATIC_OBSTACLE:
                ax.add_patch(patches.Rectangle(
                    (c - 0.5, r - 0.5), 1, 1,
                    facecolor=DARK_COLORS["static"], edgecolor="none",
                ))
            elif state == NO_FLY:
                ax.add_patch(patches.Rectangle(
                    (c - 0.5, r - 0.5), 1, 1,
                    facecolor=DARK_COLORS["no_fly"], edgecolor="#d97777",
                    linewidth=0.4, hatch="//",
                ))

    for threat in env.threats:
        active = env.is_threat_active(threat, time=time)
        color = DARK_COLORS["active"] if active else DARK_COLORS["passive"]
        center_r, center_c = threat.center_at(time)
        ax.add_patch(patches.Circle(
            (center_c, center_r), threat.radius,
            facecolor=color, edgecolor="#e5e5e5",
            alpha=0.52 if active else 0.28, linewidth=0.8,
        ))

    ax.set_xlim(-0.5, env.size - 0.5)
    ax.set_ylim(env.size - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.set_xticks(np.arange(-0.5, env.size, 5))
    ax.set_yticks(np.arange(-0.5, env.size, 5))
    ax.set_xticklabels([])
    ax.set_yticklabels([])
    ax.grid(True, color=DARK_COLORS["grid"], linewidth=0.45)


def _draw_dark_endpoints(ax, mission: Mission):
    sr, sc = mission.start
    gr, gc = mission.goal
    ax.plot(sc, sr, marker="*", markersize=18,
            color=DARK_COLORS["start"], markeredgecolor="black", zorder=8)
    ax.plot(gc, gr, marker="X", markersize=12,
            color=DARK_COLORS["goal"], markeredgecolor="black", zorder=8)


def visualize_route_overlay_dark(
    env: UAVEnvironment,
    mission: Mission,
    results: Dict[str, AStarResult],
    save_path: str,
    title: str,
    time: int = 0,
):
    """Tum heuristic rotalarini yeni surumdeki koyu temada ust uste cizer."""
    fig, ax = plt.subplots(figsize=(11.5, 9), facecolor=DARK_COLORS["background"])
    _draw_environment_dark(ax, env, time=time)
    _draw_dark_endpoints(ax, mission)

    for name, result in results.items():
        if not result.success or not result.path:
            continue
        path_r = [p[0] for p in result.path]
        path_c = [p[1] for p in result.path]
        color = PATH_COLORS.get(name, "white")
        ax.plot(
            path_c, path_r, color=color, linewidth=2.8, alpha=0.82,
            label=f"{name} | cost={result.cost:.2f}", zorder=6,
        )

    handles, labels = ax.get_legend_handles_labels()
    endpoint_handles = [
        plt.Line2D([], [], marker="*", linestyle="None", markersize=13,
                   color=DARK_COLORS["start"], label="Start"),
        plt.Line2D([], [], marker="X", linestyle="None", markersize=9,
                   color=DARK_COLORS["goal"], label="Goal"),
    ]
    legend = ax.legend(
        endpoint_handles + handles,
        [h.get_label() for h in endpoint_handles] + labels,
        loc="upper left", bbox_to_anchor=(1.01, 1), frameon=True,
        facecolor="#292929", edgecolor="#555555", fontsize=9,
    )
    for text_item in legend.get_texts():
        text_item.set_color("white")
    ax.set_title(
        f"{title}\nBackground at t={time}; routes are generated by time-expanded planning",
        color="white", fontsize=13, fontweight="bold", pad=12,
    )
    fig.tight_layout()
    fig.savefig(save_path, dpi=180, facecolor=fig.get_facecolor(), bbox_inches="tight")
    print(f"  -> Dark route comparison saved: {save_path}")
    plt.close(fig)


def visualize_benchmark_dashboard(
    results: Dict[str, AStarResult], save_path: str, title: str,
):
    """Dugum, sure ve rota maliyetini tek okunabilir panelde karsilastirir."""
    names = list(results.keys())
    short_names = ["Dijkstra", "Manhattan", "Octile", "Neural"]
    colors = [PATH_COLORS.get(name, "#4b7bec") for name in names]
    metrics = [
        ("Expanded Nodes", [r.nodes_expanded for r in results.values()], "{:,.0f}"),
        ("Runtime (ms)", [r.runtime_seconds * 1000 for r in results.values()], "{:.1f}"),
        ("Path Cost", [r.cost for r in results.values()], "{:.2f}"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), facecolor="white")
    for ax, (metric_title, values, value_format) in zip(axes, metrics):
        bars = ax.bar(short_names, values, color=colors, edgecolor="#222222", linewidth=0.8)
        ax.set_title(metric_title, fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.22)
        ax.tick_params(axis="x", rotation=12)
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height(),
                value_format.format(value), ha="center", va="bottom", fontsize=9,
            )
    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path, dpi=180, bbox_inches="tight")
    print(f"  -> Benchmark dashboard saved: {save_path}")
    plt.close(fig)


def visualize_dynamic_snapshots(
    env: UAVEnvironment,
    mission: Mission,
    result: AStarResult,
    output_dir: str,
    prefix: str,
    step_interval: int = 5,
):
    """Rota boyunca tehditlerin gercek zaman adimlarindaki halini kaydeder."""
    if not result.success or not result.path:
        return
    times = result.time_path or list(range(len(result.path)))
    if len(times) != len(result.path):
        raise ValueError("Rota ve zaman yolu uzunluklari uyusmuyor")

    snapshot_dir = os.path.join(output_dir, f"{prefix}_snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)
    indices = list(range(0, len(result.path), step_interval))
    if indices[-1] != len(result.path) - 1:
        indices.append(len(result.path) - 1)

    for idx in indices:
        fig, ax = plt.subplots(figsize=(8, 8), facecolor=DARK_COLORS["background"])
        _draw_environment_dark(ax, env, time=times[idx])
        _draw_dark_endpoints(ax, mission)
        path = result.path[:idx + 1]
        ax.plot(
            [p[1] for p in path], [p[0] for p in path],
            color="#48d7ff", linewidth=2.2, linestyle="--", zorder=6,
        )
        current = result.path[idx]
        ax.plot(current[1], current[0], marker="^", markersize=12,
                color="#ffe13b", markeredgecolor="black", zorder=9)
        ax.set_title(
            f"{_mission_name_en(mission)} | step={idx} | time={times[idx]}",
            color="white", fontsize=12, fontweight="bold",
        )
        fig.tight_layout()
        path_out = os.path.join(snapshot_dir, f"step_{idx:03d}.png")
        fig.savefig(path_out, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)
    print(f"  -> Dynamic snapshots saved: {snapshot_dir}")


def visualize_dynamic_animation(
    env: UAVEnvironment,
    mission: Mission,
    result: AStarResult,
    save_path: str,
    title: str = "Dynamic Threat Animation",
    fps: int = 3,
):
    """Save a GIF showing the UAV path and time-varying dynamic threats."""
    if not result.success or not result.path:
        return

    times = result.time_path or list(range(len(result.path)))
    if len(times) != len(result.path):
        raise ValueError("Path and time_path lengths do not match")

    fig, ax = plt.subplots(figsize=(8, 8), facecolor=DARK_COLORS["background"])

    def draw_frame(frame_idx: int):
        ax.clear()
        t = times[frame_idx]
        _draw_environment_dark(ax, env, time=t)
        _draw_dark_endpoints(ax, mission)

        path = result.path[:frame_idx + 1]
        ax.plot(
            [p[1] for p in path],
            [p[0] for p in path],
            color="#48d7ff",
            linewidth=2.4,
            linestyle="--",
            zorder=6,
        )
        current = result.path[frame_idx]
        ax.plot(
            current[1],
            current[0],
            marker="^",
            markersize=13,
            color="#ffe13b",
            markeredgecolor="black",
            zorder=9,
        )

        active_count = sum(
            1 for threat in env.threats
            if env.is_threat_active(threat, time=t)
        )
        ax.set_title(
            f"{title}\n{_mission_name_en(mission)} | step={frame_idx} | "
            f"time={t} | active threats={active_count}",
            color="white",
            fontsize=12,
            fontweight="bold",
        )
        legend_elements = [
            patches.Patch(facecolor=DARK_COLORS["static"], label="Static obstacle"),
            patches.Patch(facecolor=DARK_COLORS["active"], alpha=0.52, label="Active threat"),
            patches.Patch(facecolor=DARK_COLORS["passive"], alpha=0.28, label="Passive threat"),
            patches.Patch(facecolor=DARK_COLORS["no_fly"], label="No-fly zone"),
            plt.Line2D([], [], color="#48d7ff", linestyle="--", label="Traversed path"),
            plt.Line2D([], [], marker="^", color="#ffe13b", linestyle="None", label="UAV"),
            plt.Line2D([], [], marker="*", color=DARK_COLORS["start"], linestyle="None", label="Start"),
            plt.Line2D([], [], marker="X", color=DARK_COLORS["goal"], linestyle="None", label="Goal"),
        ]
        legend = ax.legend(
            handles=legend_elements,
            loc="upper left",
            bbox_to_anchor=(1.01, 1),
            frameon=True,
            facecolor="#292929",
            edgecolor="#555555",
            fontsize=8,
        )
        for text_item in legend.get_texts():
            text_item.set_color("white")

    anim = FuncAnimation(fig, draw_frame, frames=len(result.path), interval=1000 / fps)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    anim.save(save_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    print(f"  -> Dynamic animation saved: {save_path}")
