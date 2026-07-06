"""
Main Application - Neural-Guided A* for UAV Mission Planning
-------------------------------------------------------------
Calistirma:
    python main.py --mode demo                  # Statik demo
    python main.py --mode demo --planner dynamic # Zaman genisletmeli dinamik demo
    python main.py --mode train                 # MLP'yi yeniden egit
"""

import argparse
import os
import sys
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

from environment import build_environment
from astar import (
    astar_search, astar_search_dynamic, CLASSIC_HEURISTICS,
    manhattan_distance, octile_distance,
)
from neural_heuristic import (
    MLP, NeuralHeuristic, generate_training_data, extract_features, FEATURE_DIM,
)

SCENARIO_TITLES_EN = {
    "simple": "Scenario 1: Simple Infiltration Mission",
    "urban": "Scenario 2: Urban Operation",
    "corridor": "Scenario 3: Corridor Passage",
    "dynamic": "Scenario 4: Dynamic Threat Environment",
}
# ============================================================
# MLP EGITIMI
# ============================================================

def train_model(
    model_path: str = str(PROJECT_DIR / "data" / "mlp_heuristic.pkl"),
    epochs: int = 150,
    verbose: bool = True,
) -> MLP:
    """MLP modelini egit ve kaydet."""
    print("\n" + "=" * 60)
    print(" MLP HEURISTIC EGITIMI")
    print("=" * 60)

    # 1. Egitim verisi uret
    X_train, y_train = generate_training_data(
        n_scenarios=4, samples_per_scenario=1000, seed=42,
    )
    # Dogrulama farkli harita seed'lerinden uretilir; ayni haritanin
    # dugumlerini rastgele bolmek genelleme basarisini oldugundan iyi gosterir.
    X_val, y_val = generate_training_data(
        n_scenarios=4, samples_per_scenario=200, seed=10_042,
    )

    print(f"\nEgitim seti: {X_train.shape[0]} ornek")
    print(f"Dogrulama seti: {X_val.shape[0]} ornek")

    # 2. Modeli olustur ve egit (daha derin)
    print("\nMLP olusturuluyor (mimari: 8 -> 64 -> 64 -> 32 -> 1)...")
    model = MLP(input_dim=FEATURE_DIM, hidden_dims=(64, 64, 32), output_dim=1, seed=42)

    print(f"\nEgitim basliyor ({epochs} epoch)...\n")
    model.fit(
        X_train, y_train, X_val, y_val,
        epochs=epochs, batch_size=64, lr=0.001, verbose=verbose,
    )

    # 3. Kaydet
    model.save(model_path)
    print(f"\nModel kaydedildi: {model_path}")

    # Egitim sonu metrikleri
    final_train = model.training_history["train_loss"][-1]
    final_val = model.training_history["val_loss"][-1]
    print(f"\nFinal egitim kaybi    : {final_train:.4f}")
    print(f"Final dogrulama kaybi : {final_val:.4f}")

    return model


# ============================================================
# TEK SENARYO DEMO
# ============================================================

def run_scenario_demo(
    scenario_name: str,
    scenario_title: str,
    prefix: str,
    model: MLP,
    output_dir: str,
    time: int = 0,
    planner: str = "static",
    generate_visuals: bool = True,
):
    """Bir senaryo icin 3 heuristic karsilastirmasi yap."""
    print(f"\n{'=' * 60}")
    print(f"  {scenario_title}")
    print(f"{'=' * 60}")

    env, mission = build_environment(scenario_name, seed=42)
    visual_title = SCENARIO_TITLES_EN.get(scenario_name, scenario_title)
    print(f"Gorev: {mission.name}")
    print(f"Baslangic -> Hedef: {mission.start} -> {mission.goal}")
    print(f"Planlayici: {'Zaman genisletmeli dinamik A*' if planner == 'dynamic' else 'Statik A*'}")

    def run_planner(heuristic_fn, heuristic_name):
        if planner == "dynamic":
            return astar_search_dynamic(
                env, mission, heuristic_fn=heuristic_fn,
                heuristic_name=heuristic_name, start_time_step=time,
            )
        return astar_search(
            env, mission, heuristic_fn=heuristic_fn,
            heuristic_name=heuristic_name, time=time,
        )

    if generate_visuals:
        from visualization import visualize_environment
        visualize_environment(
            env, mission, time=time,
            save_path=os.path.join(output_dir, f"{prefix}_harita.png"),
            title=visual_title,
        )

    # 2. Heuristic'leri calistir
    print("\nHeuristic'ler karsilastiriliyor...")

    # 2a. Dijkstra baseline (h=0) - optimum kontrolu icin
    result_dijkstra = run_planner(CLASSIC_HEURISTICS["zero"], "Dijkstra (h=0)")
    print(f"  Dijkstra  : {result_dijkstra.nodes_expanded:>5d} dugum, "
          f"maliyet {result_dijkstra.cost:.2f}, "
          f"{result_dijkstra.runtime_seconds*1000:.1f}ms")

    # 2b. Manhattan
    result_manhattan = run_planner(manhattan_distance, "Manhattan")
    print(f"  Manhattan : {result_manhattan.nodes_expanded:>5d} dugum, "
          f"maliyet {result_manhattan.cost:.2f}, "
          f"{result_manhattan.runtime_seconds*1000:.1f}ms")

    # 2c. Octile (8-yonlu icin daha iyi)
    result_octile = run_planner(octile_distance, "Octile")
    print(f"  Octile    : {result_octile.nodes_expanded:>5d} dugum, "
          f"maliyet {result_octile.cost:.2f}, "
          f"{result_octile.runtime_seconds*1000:.1f}ms")

    # 2d. Neural
    neural_h = NeuralHeuristic(model, env, time=time, admissibility_factor=1.0)
    result_neural = run_planner(neural_h, "Neural (MLP)")
    print(f"  Neural    : {result_neural.nodes_expanded:>5d} dugum, "
          f"maliyet {result_neural.cost:.2f}, "
          f"{result_neural.runtime_seconds*1000:.1f}ms")

    results = {
        "Dijkstra (h=0)": result_dijkstra,
        "Manhattan": result_manhattan,
        "Octile": result_octile,
        "Neural (MLP)": result_neural,
    }

    if generate_visuals:
        from visualization import (
            visualize_astar_result,
            visualize_benchmark_dashboard,
            visualize_dynamic_snapshots,
            visualize_heuristic_heatmap,
            visualize_route_overlay_dark,
        )
        for name, result in results.items():
            safe_name = name.lower().replace(" ", "_").replace("(", "").replace(")", "")
            visualize_astar_result(
                env, mission, result, time=time,
                save_path=os.path.join(output_dir, f"{prefix}_sonuc_{safe_name}.png"),
                title=f"{visual_title} - {name}",
            )

        visualize_route_overlay_dark(
            env, mission, results, time=time,
            save_path=os.path.join(output_dir, f"{prefix}_karsilastirma_gorsel.png"),
            title=f"{visual_title} - Heuristic Comparison",
        )
        visualize_benchmark_dashboard(
            results,
            save_path=os.path.join(output_dir, f"{prefix}_benchmark.png"),
            title=f"{visual_title} - Performance Metrics",
        )
        visualize_heuristic_heatmap(
            env, mission, manhattan_distance, time=time,
            save_path=os.path.join(output_dir, f"{prefix}_heatmap_manhattan.png"),
            title=f"{visual_title} - Manhattan Heuristic Values",
        )
        visualize_heuristic_heatmap(
            env, mission, neural_h, time=time,
            save_path=os.path.join(output_dir, f"{prefix}_heatmap_neural.png"),
            title=f"{visual_title} - Neural Heuristic Values",
        )
        if planner == "dynamic":
            from visualization import visualize_dynamic_animation
            visualize_dynamic_snapshots(
                env, mission, result_neural, output_dir=output_dir,
                prefix=prefix, step_interval=5,
            )
            visualize_dynamic_animation(
                env, mission, result_neural,
                save_path=os.path.join(output_dir, f"{prefix}_dynamic_animation.gif"),
                title=f"{visual_title} - Dynamic Threat Animation",
            )

    return results


# ============================================================
# DEMO MODU - Tum senaryolari calistir
# ============================================================

def run_demo(output_dir: str = str(PROJECT_DIR / "visualizations"),
             model_path: str = str(PROJECT_DIR / "data" / "mlp_heuristic.pkl"),
             planner: str = "dynamic", generate_visuals: bool = True):
    """Tum senaryolari calistir."""
    os.makedirs(output_dir, exist_ok=True)

    # Modeli yukle (yoksa egit)
    if os.path.exists(model_path):
        print(f"Var olan model yukleniyor: {model_path}")
        model = MLP.load(model_path)
    else:
        print("Model bulunamadi, egitim baslatiliyor...")
        model = train_model(model_path=model_path)

    # Egitim grafigi
    if generate_visuals and model.training_history["epoch"]:
        from visualization import visualize_training_history
        visualize_training_history(
            model,
            save_path=os.path.join(output_dir, "00_egitim_kaybi.png"),
            title="MLP Training Process",
        )

    # Tum senaryolar
    all_results = {}
    scenarios = [
        ("simple",   "Scenario 1: Simple Infiltration Mission",  "01_basit"),
        ("urban",    "Scenario 2: Urban Operation",              "02_sehir"),
        ("corridor", "Scenario 3: Corridor Passage",             "03_koridor"),
        ("dynamic",  "Scenario 4: Dynamic Threat Environment",   "04_dinamik"),
    ]

    for scenario_name, scenario_title, prefix in scenarios:
        results = run_scenario_demo(
            scenario_name, scenario_title, prefix, model, output_dir,
            planner=planner, generate_visuals=generate_visuals,
        )
        all_results[scenario_name] = results

    # Genel ozet tablosu
    print(f"\n{'=' * 60}")
    print(" GENEL OZET")
    print(f"{'=' * 60}")
    print(f"{'Senaryo':<25}{'Dijkstra':<15}{'Manhattan':<15}{'Octile':<15}{'Neural':<15}")
    print("-" * 85)
    for sc_name, results in all_results.items():
        line = f"{sc_name:<25}"
        for h_name in ["Dijkstra (h=0)", "Manhattan", "Octile", "Neural (MLP)"]:
            r = results[h_name]
            line += f"{r.nodes_expanded:>10,d}    "
        print(line)

    # Ozeti dosyaya kaydet
    summary_path = os.path.join(output_dir, "ozet.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("Senaryo Bazinda Genisletilen Dugum Sayilari\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"{'Senaryo':<25}{'Dijkstra':>12}{'Manhattan':>12}{'Octile':>12}{'Neural':>12}\n")
        f.write("-" * 65 + "\n")
        for sc_name, results in all_results.items():
            f.write(f"{sc_name:<25}"
                    f"{results['Dijkstra (h=0)'].nodes_expanded:>12,}"
                    f"{results['Manhattan'].nodes_expanded:>12,}"
                    f"{results['Octile'].nodes_expanded:>12,}"
                    f"{results['Neural (MLP)'].nodes_expanded:>12,}\n")
        f.write("\nMaliyet Karsilastirmasi (rota uzunlugu):\n")
        f.write("-" * 65 + "\n")
        f.write(f"{'Senaryo':<25}{'Dijkstra':>12}{'Manhattan':>12}{'Octile':>12}{'Neural':>12}\n")
        for sc_name, results in all_results.items():
            f.write(f"{sc_name:<25}"
                    f"{results['Dijkstra (h=0)'].cost:>12.2f}"
                    f"{results['Manhattan'].cost:>12.2f}"
                    f"{results['Octile'].cost:>12.2f}"
                    f"{results['Neural (MLP)'].cost:>12.2f}\n")
    print(f"\nOzet kaydedildi: {summary_path}")

    return all_results


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Neural-Guided A* for UAV Mission Planning"
    )
    parser.add_argument(
        "--mode", choices=["demo", "train"], default="demo",
        help="demo: tum senaryolar, train: MLP yeniden egit",
    )
    parser.add_argument("--output", type=str, default=str(PROJECT_DIR / "visualizations"))
    parser.add_argument("--model", type=str, default=str(PROJECT_DIR / "data" / "mlp_heuristic.pkl"))
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument(
        "--planner", choices=["static", "dynamic"], default="dynamic",
        help="static: eski A*; dynamic: durum=(satir,sutun,zaman) A*",
    )
    parser.add_argument(
        "--skip-visuals", action="store_true",
        help="Matplotlib olmadan yalnizca algoritma ve ozet tablosunu calistir",
    )
    args = parser.parse_args()

    if args.mode == "train":
        train_model(model_path=args.model, epochs=args.epochs)
    else:
        run_demo(
            output_dir=args.output, model_path=args.model, planner=args.planner,
            generate_visuals=not args.skip_visuals,
        )
