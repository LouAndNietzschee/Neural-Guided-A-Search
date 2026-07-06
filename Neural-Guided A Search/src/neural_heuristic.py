"""
Neural Network Heuristic for A* Search (NumPy Implementation)
--------------------------------------------------------------
Bu modul, A* aramasi icin ogrenilmis heuristic uretmek amaciyla
sifirdan implement edilmis bir MLP (Multi-Layer Perceptron) icerir.

Neden numpy ile? Saydamlik icin - PyTorch/TF kara kutu olur.
Burada her adim acik gozukur (forward, backward, optimizasyon).

Mimari (default):
    Input  (8 ozellik) -> Hidden (64) -> Hidden (32) -> Output (1)
    Activation: ReLU (gizli katmanlar), Linear (cikis)
    Loss: Mean Squared Error (MSE)
    Optimizer: Adam

Input ozellikleri (her dugum icin):
    1. Hedef'e Manhattan mesafesi (normalize)
    2. Hedef'e Euclidean mesafesi (normalize)
    3. Hedef'e Octile mesafesi (normalize)
    4. Yatay fark (dr/grid_size)
    5. Dikey fark (dc/grid_size)
    6. Cevredeki engel yogunlugu (5x5 pencere)
    7. Hedef yonunde engel yogunlugu
    8. Dugumun mevcut hucre durumu (tehdit/temiz)

Cikis: O dugumden hedefe tahmini mesafe (gercek mesafenin tahmini).
"""

import math
import os
import pickle
from typing import Callable, List, Tuple, Dict, Optional

import numpy as np

from environment import UAVEnvironment, EMPTY, PASSIVE_THREAT
from astar import true_distance


# ============================================================
# OZELLIK CIKARIMI (Feature Extraction)
# ============================================================

def extract_features(
    env: UAVEnvironment,
    node: Tuple[int, int],
    goal: Tuple[int, int],
    time: int = 0,
) -> np.ndarray:
    """Bir dugum + hedef cifti icin ozellik vektoru cikar.

    Donen vektor 8 boyutlu, [0, 1] aralıgına normalize.
    """
    nr, nc = node
    gr, gc = goal
    size = env.size

    # 1-3: Mesafe tabanli ozellikler (normalize, 0..1)
    manhattan = (abs(nr - gr) + abs(nc - gc)) / (2 * size)
    dr = nr - gr
    dc = nc - gc
    euclidean = math.sqrt(dr*dr + dc*dc) / (size * math.sqrt(2))
    octile_raw = max(abs(dr), abs(dc)) + (math.sqrt(2) - 1) * min(abs(dr), abs(dc))
    octile = octile_raw / (size * math.sqrt(2))

    # 4-5: Yon farklari (-1..1 -> 0..1)
    delta_r = (dr / size + 1) / 2
    delta_c = (dc / size + 1) / 2

    # 6: 5x5 pencerede engel yogunlugu
    obstacle_count = 0
    total_count = 0
    for ddr in range(-2, 3):
        for ddc in range(-2, 3):
            tr, tc = nr + ddr, nc + ddc
            if 0 <= tr < size and 0 <= tc < size:
                total_count += 1
                if not env.is_passable(tr, tc, time=time):
                    obstacle_count += 1
    local_density = obstacle_count / max(total_count, 1)

    # 7: Hedef yonundeki engel yogunlugu (node ile goal arasi dogruda)
    sample_count = 5
    obstacle_on_path = 0
    for k in range(1, sample_count + 1):
        t = k / (sample_count + 1)
        sr = int(nr + t * dr * -1) if dr != 0 else nr  # Hedefe dogru
        sc = int(nc + t * dc * -1) if dc != 0 else nc
        # Duzeltme: hedef yonu
        sr = int(nr + t * (gr - nr))
        sc = int(nc + t * (gc - nc))
        if 0 <= sr < size and 0 <= sc < size:
            if not env.is_passable(sr, sc, time=time):
                obstacle_on_path += 1
    path_obstacle_ratio = obstacle_on_path / sample_count

    # 8: Mevcut hucrenin durumu (0=bos, 0.5=pasif tehdit, 1=tehlikeli)
    state = env.get_cell_state(nr, nc, time=time)
    cell_risk = 0.0
    if state == PASSIVE_THREAT:
        cell_risk = 0.5
    elif state != EMPTY:
        cell_risk = 1.0

    return np.array([
        manhattan, euclidean, octile,
        delta_r, delta_c,
        local_density, path_obstacle_ratio, cell_risk,
    ], dtype=np.float32)


FEATURE_DIM = 8


# ============================================================
# MLP MIMARISI (Sifirdan NumPy ile)
# ============================================================

class MLP:
    """Multi-Layer Perceptron - sifirdan numpy ile.

    Iki gizli katmanli yapay sinir agi. ReLU aktivasyonu, linear cikis.
    Adam optimizer kullanir.
    """

    def __init__(
        self,
        input_dim: int = FEATURE_DIM,
        hidden_dims: Tuple[int, ...] = (64, 32),
        output_dim: int = 1,
        seed: int = 42,
    ):
        self.input_dim = input_dim
        self.hidden_dims = hidden_dims
        self.output_dim = output_dim

        # Agirliklari Xavier/Glorot baslatma ile olustur
        rng = np.random.default_rng(seed)
        self.weights: List[np.ndarray] = []
        self.biases: List[np.ndarray] = []
        dims = [input_dim] + list(hidden_dims) + [output_dim]
        for i in range(len(dims) - 1):
            fan_in, fan_out = dims[i], dims[i + 1]
            limit = math.sqrt(6.0 / (fan_in + fan_out))
            w = rng.uniform(-limit, limit, size=(fan_in, fan_out)).astype(np.float32)
            b = np.zeros((fan_out,), dtype=np.float32)
            self.weights.append(w)
            self.biases.append(b)

        # Adam optimizer durumu
        self.m_w = [np.zeros_like(w) for w in self.weights]
        self.v_w = [np.zeros_like(w) for w in self.weights]
        self.m_b = [np.zeros_like(b) for b in self.biases]
        self.v_b = [np.zeros_like(b) for b in self.biases]
        self.adam_t = 0

        # Egitim gecmisi
        self.training_history: Dict[str, List[float]] = {
            "train_loss": [], "val_loss": [], "epoch": [],
        }

    # ----------- FORWARD PASS -----------

    def forward(self, X: np.ndarray, return_cache: bool = False):
        """Ileri yayma. X: (batch_size, input_dim)."""
        cache = {"a0": X}
        a = X
        n_layers = len(self.weights)
        for i in range(n_layers):
            z = a @ self.weights[i] + self.biases[i]
            cache[f"z{i+1}"] = z
            if i < n_layers - 1:
                a = np.maximum(z, 0.0)  # ReLU
            else:
                a = z  # Linear cikis (regresyon)
            cache[f"a{i+1}"] = a
        if return_cache:
            return a, cache
        return a

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Tahmin yap (numpy 2D array bekler)."""
        return self.forward(X).ravel()

    def predict_single(self, x: np.ndarray) -> float:
        """Tek bir ornek icin tahmin (1D vektor)."""
        return float(self.predict(x.reshape(1, -1))[0])

    # ----------- BACKPROPAGATION -----------

    def _backward(self, cache: dict, y_true: np.ndarray):
        """Geri yayma. MSE loss gradyanlarini hesaplar."""
        n_layers = len(self.weights)
        batch_size = y_true.shape[0]
        y_pred = cache[f"a{n_layers}"]
        # MSE turevi: 2 * (y_pred - y_true) / batch_size
        delta = (2.0 / batch_size) * (y_pred - y_true.reshape(-1, 1))

        grads_w = [None] * n_layers
        grads_b = [None] * n_layers

        for i in reversed(range(n_layers)):
            a_prev = cache[f"a{i}"]
            grads_w[i] = a_prev.T @ delta
            grads_b[i] = delta.sum(axis=0)
            if i > 0:
                # ReLU turevi
                relu_grad = (cache[f"z{i}"] > 0).astype(np.float32)
                delta = (delta @ self.weights[i].T) * relu_grad
        return grads_w, grads_b

    # ----------- ADAM OPTIMIZER -----------

    def _adam_step(
        self, grads_w, grads_b,
        lr: float = 0.001, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8,
    ):
        """Adam optimizer adimi."""
        self.adam_t += 1
        t = self.adam_t
        for i in range(len(self.weights)):
            # Momentum guncellemesi
            self.m_w[i] = beta1 * self.m_w[i] + (1 - beta1) * grads_w[i]
            self.v_w[i] = beta2 * self.v_w[i] + (1 - beta2) * (grads_w[i] ** 2)
            m_hat = self.m_w[i] / (1 - beta1 ** t)
            v_hat = self.v_w[i] / (1 - beta2 ** t)
            self.weights[i] -= lr * m_hat / (np.sqrt(v_hat) + eps)

            self.m_b[i] = beta1 * self.m_b[i] + (1 - beta1) * grads_b[i]
            self.v_b[i] = beta2 * self.v_b[i] + (1 - beta2) * (grads_b[i] ** 2)
            mb_hat = self.m_b[i] / (1 - beta1 ** t)
            vb_hat = self.v_b[i] / (1 - beta2 ** t)
            self.biases[i] -= lr * mb_hat / (np.sqrt(vb_hat) + eps)

    # ----------- EGITIM DONGUSU -----------

    def fit(
        self,
        X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
        epochs: int = 100, batch_size: int = 64, lr: float = 0.001,
        verbose: bool = True,
    ):
        """MLP'yi egit."""
        n_samples = X_train.shape[0]
        for epoch in range(epochs):
            # Karistir
            perm = np.random.permutation(n_samples)
            X_shuffled = X_train[perm]
            y_shuffled = y_train[perm]

            epoch_loss = 0.0
            n_batches = 0
            for i in range(0, n_samples, batch_size):
                X_batch = X_shuffled[i:i+batch_size]
                y_batch = y_shuffled[i:i+batch_size]

                y_pred, cache = self.forward(X_batch, return_cache=True)
                batch_loss = float(np.mean((y_pred.ravel() - y_batch) ** 2))
                epoch_loss += batch_loss
                n_batches += 1

                grads_w, grads_b = self._backward(cache, y_batch)
                self._adam_step(grads_w, grads_b, lr=lr)

            train_loss = epoch_loss / max(n_batches, 1)
            val_loss = None
            if X_val is not None and y_val is not None:
                y_val_pred = self.predict(X_val)
                val_loss = float(np.mean((y_val_pred - y_val) ** 2))

            self.training_history["epoch"].append(epoch + 1)
            self.training_history["train_loss"].append(train_loss)
            self.training_history["val_loss"].append(val_loss if val_loss else 0)

            if verbose and (epoch + 1) % 10 == 0:
                val_str = f", val_loss: {val_loss:.4f}" if val_loss is not None else ""
                print(f"  Epoch {epoch+1:3d}/{epochs} | train_loss: {train_loss:.4f}{val_str}")

    # ----------- KAYDET / YUKLE -----------

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "weights": self.weights,
                "biases": self.biases,
                "input_dim": self.input_dim,
                "hidden_dims": self.hidden_dims,
                "output_dim": self.output_dim,
                "training_history": self.training_history,
            }, f)

    @classmethod
    def load(cls, path: str) -> "MLP":
        with open(path, "rb") as f:
            data = pickle.load(f)
        model = cls(
            input_dim=data["input_dim"],
            hidden_dims=tuple(data["hidden_dims"]),
            output_dim=data["output_dim"],
        )
        model.weights = data["weights"]
        model.biases = data["biases"]
        model.training_history = data.get("training_history", {})
        return model


# ============================================================
# EGITIM VERISI URETIMI
# ============================================================

def generate_training_data(
    n_scenarios: int = 4,
    samples_per_scenario: int = 1000,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Egitim verisi uret.

    Yontem: Her senaryoda rastgele hedef noktalari sec, o noktaya
    olan gercek (Dijkstra) mesafeleri hesapla. Her dugum-hedef cifti
    bir egitim ornegidir.
    """
    from environment import build_environment

    scenarios = ["simple", "urban", "corridor", "dynamic"]
    rng = np.random.default_rng(seed)

    X_list = []
    y_list = []

    print("Egitim verisi uretiliyor...")
    for sc_idx, scenario in enumerate(scenarios[:n_scenarios]):
        env, _ = build_environment(scenario, seed=seed + sc_idx)

        # Birkac farkli zaman adiminda veri topla
        for time_step in [0, 1, 2, 3, 4]:
            # Birkac rastgele hedef sec
            for _ in range(samples_per_scenario // 5):
                # Rastgele bir hedef nokta sec (gecilebilir)
                attempts = 0
                while attempts < 50:
                    gr = int(rng.integers(0, env.size))
                    gc = int(rng.integers(0, env.size))
                    if env.is_passable(gr, gc, time=time_step):
                        break
                    attempts += 1
                else:
                    continue
                goal = (gr, gc)

                # Bu hedefe olan tum gercek mesafeler
                distances = true_distance(env, goal, time=time_step)

                # Daha cok dugum ornekle (daha cesitli mesafeler)
                positions = list(distances.keys())
                if len(positions) < 30:
                    continue
                sampled_positions = rng.choice(
                    len(positions), size=min(40, len(positions)), replace=False
                )

                for idx in sampled_positions:
                    pos = positions[idx]
                    dist = distances[pos]
                    if dist == float("inf") or pos == goal:
                        continue
                    features = extract_features(env, pos, goal, time=time_step)
                    X_list.append(features)
                    y_list.append(dist)

        print(f"  Senaryo {scenario}: {len(X_list)} toplam ornek")

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.float32)
    print(f"Toplam egitim verisi: {X.shape[0]} ornek, {X.shape[1]} ozellik")
    return X, y


# ============================================================
# NEURAL HEURISTIC FONKSIYONU (A* icin)
# ============================================================

class NeuralHeuristic:
    """A* algoritmasi icin neural network tabanli heuristic.

    Bu sinif, A*'in heuristic_fn parametresi olarak kullanilabilir.
    Bir ortam ve zaman adimi icin onceden olusturulmus olmalidir.
    """

    def __init__(self, model: MLP, env: UAVEnvironment, time: int = 0,
                 admissibility_factor: float = 1.0):
        """
        Args:
            model: Egitilmis MLP modeli
            env: IHA ortami
            time: Hangi zaman adimi
            admissibility_factor: 1.0 (saf model) - 0.95 (hafifce dusurulmus).
                Modelin overestimate yapmasini engellemek icin <1.0
                degerleri kullanilabilir.
        """
        self.model = model
        self.env = env
        self.time = time
        self.admissibility_factor = admissibility_factor
        # Cache - ayni nokta icin tekrar hesaplama yapma
        self.cache: Dict[Tuple[Tuple[int, int], Tuple[int, int], int], float] = {}

    def __call__(self, node: Tuple[int, int], goal: Tuple[int, int],
                 time: Optional[int] = None) -> float:
        feature_time = self.time if time is None else time
        key = (node, goal, feature_time)
        if key in self.cache:
            return self.cache[key]
        features = extract_features(self.env, node, goal, time=feature_time)
        prediction = self.model.predict_single(features)
        # Negatif tahminleri engelle, admissibility_factor uygula
        h = max(0.0, prediction) * self.admissibility_factor
        self.cache[key] = h
        return h

    def reset_cache(self):
        self.cache.clear()
