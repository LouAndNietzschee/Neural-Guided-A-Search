"""
UAV (IHA/SIHA) Operational Environment
---------------------------------------
Bu modul, otonom IHA/SIHA gorev planlamasi icin 2D operasyon ortamini modelleyer.

Ortam ozellikleri:
- 50x50 grid harita (her hucre = 100m x 100m gercek alan)
- Statik tehditler: daglar, binalar (her zaman engel)
- Dinamik tehditler: radar/SAM bolgeleri (zamana gore acilir/kapanir)
- No-fly zones: hicbir zaman gecilmemeli
- Yakit/menzil sinirlamasi (toplam yol maliyeti)

Hucre durumlari:
- 0: Bos (gecilebilir)
- 1: Statik engel (dag/bina)
- 2: Aktif tehdit bolgesi (radar/SAM aktif)
- 3: Pasif tehdit (radar kapanmis, gecici olarak gecilebilir)
- 9: Hedef
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set
import random


GRID_SIZE = 50  # 50x50 grid (5km x 5km operasyonel alan)

# Hucre tipleri
EMPTY = 0
STATIC_OBSTACLE = 1     # Dag, yuksek bina
ACTIVE_THREAT = 2       # Aktif radar/SAM bolgesi
PASSIVE_THREAT = 3      # Kapanmis radar (gecici olarak guvenli)
NO_FLY = 4              # Yasak bolge (kesinlikle gecilemez)
START = 8
GOAL = 9


@dataclass
class Threat:
    """Dinamik tehdit bolgesi (radar/SAM)."""
    center: Tuple[int, int]
    radius: int           # Etki yaricapi
    active_pattern: List[int]  # Hangi zaman adimlarinda aktif (0/1 listesi)
    threat_type: str = "SAM"   # SAM, Radar, EW
    motion_pattern: Optional[List[Tuple[int, int]]] = None

    def center_at(self, time: int = 0) -> Tuple[int, int]:
        """Return the threat center at a time step."""
        if not self.motion_pattern:
            return self.center
        dr, dc = self.motion_pattern[time % len(self.motion_pattern)]
        return self.center[0] + dr, self.center[1] + dc


@dataclass
class Mission:
    """IHA gorev tanimi."""
    start: Tuple[int, int]
    goal: Tuple[int, int]
    max_range: float = 200.0    # Maksimum menzil (hucre cinsinden)
    name: str = "Gorev"


class UAVEnvironment:
    """IHA operasyonel ortami."""

    def __init__(self, size: int = GRID_SIZE, seed: Optional[int] = None):
        self.size = size
        self.static_grid = np.zeros((size, size), dtype=int)
        self.threats: List[Threat] = []
        self.current_time = 0
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

    # ============================================================
    # ORTAM OLUSTURMA
    # ============================================================

    def add_mountain_range(self, points: List[Tuple[int, int]], thickness: int = 1):
        """Dag silsilesi ekle (statik engel)."""
        for (r, c) in points:
            for dr in range(-thickness, thickness + 1):
                for dc in range(-thickness, thickness + 1):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.size and 0 <= nc < self.size:
                        self.static_grid[nr, nc] = STATIC_OBSTACLE

    def add_building_cluster(self, center: Tuple[int, int], size: int):
        """Bina kumesi ekle (sehir bolgesi)."""
        r, c = center
        for dr in range(-size, size + 1):
            for dc in range(-size, size + 1):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    # Bazi hucreler bos (sokaklar)
                    if random.random() < 0.7:
                        self.static_grid[nr, nc] = STATIC_OBSTACLE

    def add_no_fly_zone(self, center: Tuple[int, int], radius: int):
        """Yasak ucus bolgesi (askeri/sivil havalimani vb.)."""
        r, c = center
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dr*dr + dc*dc <= radius*radius:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.size and 0 <= nc < self.size:
                        self.static_grid[nr, nc] = NO_FLY

    def add_threat(
        self,
        center: Tuple[int, int],
        radius: int,
        active_pattern: List[int],
        threat_type: str = "SAM",
        motion_pattern: Optional[List[Tuple[int, int]]] = None,
    ):
        """Dinamik tehdit bolgesi ekle (radar/SAM)."""
        self.threats.append(Threat(
            center=center,
            radius=radius,
            active_pattern=active_pattern,
            threat_type=threat_type,
            motion_pattern=motion_pattern,
        ))

    # ============================================================
    # DURUM SORGULAMA
    # ============================================================

    def is_threat_active(self, threat: Threat, time: Optional[int] = None) -> bool:
        """Bir tehdidin belirli bir zamanda aktif olup olmadigi."""
        if time is None:
            time = self.current_time
        if not threat.active_pattern:
            return True
        return bool(threat.active_pattern[time % len(threat.active_pattern)])

    def get_cell_state(self, r: int, c: int, time: Optional[int] = None) -> int:
        """Bir hucrenin mevcut durumu (zamana gore)."""
        if not (0 <= r < self.size and 0 <= c < self.size):
            return STATIC_OBSTACLE
        if self.static_grid[r, c] != EMPTY:
            return int(self.static_grid[r, c])
        # Dinamik tehditleri kontrol et.
        # Birden fazla tehdit cakisirsa guvenlik onceliklidir:
        # herhangi biri aktifse hucre ACTIVE_THREAT kabul edilir.
        in_passive_threat = False
        for threat in self.threats:
            center_r, center_c = threat.center_at(time or 0)
            dr = r - center_r
            dc = c - center_c
            if dr*dr + dc*dc <= threat.radius * threat.radius:
                if self.is_threat_active(threat, time):
                    return ACTIVE_THREAT
                in_passive_threat = True
        if in_passive_threat:
            return PASSIVE_THREAT
        return EMPTY

    def is_passable(self, r: int, c: int, time: Optional[int] = None) -> bool:
        """Bir hucre gecilebilir mi? (yasak bolge + aktif tehdit ENGEL)."""
        state = self.get_cell_state(r, c, time)
        return state not in (STATIC_OBSTACLE, ACTIVE_THREAT, NO_FLY)

    def get_movement_cost(
        self, r: int, c: int, time: Optional[int] = None
    ) -> float:
        """Bir hucreye gecmenin maliyeti.

        Pasif tehdit bolgeleri biraz daha pahalidir (risk primi).
        Aktif tehdit/engel = sonsuz maliyet.
        """
        state = self.get_cell_state(r, c, time)
        if state in (STATIC_OBSTACLE, ACTIVE_THREAT, NO_FLY):
            return float("inf")
        if state == PASSIVE_THREAT:
            return 1.5  # Risk primi (radar tekrar aktiflesebilir)
        return 1.0

    # ============================================================
    # KOMSULUK FONKSIYONU (8-yonlu hareket)
    # ============================================================

    NEIGHBORS_8 = [
        (-1, -1, np.sqrt(2)), (-1, 0, 1.0), (-1, 1, np.sqrt(2)),
        (0, -1, 1.0),                       (0, 1, 1.0),
        (1, -1, np.sqrt(2)),  (1, 0, 1.0),  (1, 1, np.sqrt(2)),
    ]

    def get_neighbors(
        self,
        r: int,
        c: int,
        time: Optional[int] = None,
        prevent_corner_cutting: bool = True,
    ) -> List[Tuple[Tuple[int, int], float]]:
        """8-yonlu komsulari ve maliyetlerini dondurur.

        IHA 8 yonde hareket edebilir (capraz hareket daha maliyetli).
        Aktif tehditler ve engeller atlanir.

        prevent_corner_cutting=True iken capraz gecislerde iki yan
        hucrenin de gecilebilir olmasi gerekir. Boylece IHA iki engelin
        kosesinden fiziksel olmayan sekilde gecemez.
        """
        neighbors = []
        for dr, dc, move_cost in self.NEIGHBORS_8:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < self.size and 0 <= nc < self.size):
                continue

            # Capraz harekette kose kesmeyi engelle.
            if prevent_corner_cutting and dr != 0 and dc != 0:
                if (not self.is_passable(r + dr, c, time=time) or
                        not self.is_passable(r, c + dc, time=time)):
                    continue

            cell_cost = self.get_movement_cost(nr, nc, time)
            if cell_cost == float("inf"):
                continue
            total_cost = move_cost * cell_cost
            neighbors.append(((nr, nc), total_cost))
        return neighbors

    # ============================================================
    # HAZIR ORTAM SENARYOLARI
    # ============================================================

    def setup_scenario_1_simple(self):
        """Senaryo 1: Basit gorev - az engel, tek tehdit."""
        # Sehir bolgesi (sag alt kose)
        self.add_building_cluster(center=(38, 38), size=6)
        # Bir dag (orta)
        self.add_mountain_range(
            points=[(20, 25), (21, 25), (22, 26), (23, 26)], thickness=2
        )
        # Tek radar bolgesi
        self.add_threat(
            center=(25, 25), radius=5,
            active_pattern=[1, 1, 1, 0, 0],  # Cogu zaman aktif
            threat_type="Radar",
        )
        return Mission(
            start=(5, 5), goal=(45, 45),
            max_range=120.0, name="Basit Sizma Gorevi"
        )

    def setup_scenario_2_urban(self):
        """Senaryo 2: Sehir operasyonu - cok engel, cok tehdit."""
        # Buyuk sehir bolgesi
        self.add_building_cluster(center=(15, 25), size=5)
        self.add_building_cluster(center=(25, 30), size=4)
        self.add_building_cluster(center=(35, 20), size=5)
        # Yasak bolge (havalimani)
        self.add_no_fly_zone(center=(20, 10), radius=4)
        # Birden cok SAM bolgesi
        self.add_threat(
            center=(20, 35), radius=4,
            active_pattern=[1, 1, 0, 1, 1, 0],
            threat_type="SAM",
        )
        self.add_threat(
            center=(35, 35), radius=5,
            active_pattern=[1, 1, 1, 1, 0],
            threat_type="SAM",
        )
        self.add_threat(
            center=(10, 35), radius=3,
            active_pattern=[0, 1, 1, 0, 0],
            threat_type="EW",
        )
        return Mission(
            start=(2, 2), goal=(47, 47),
            max_range=200.0, name="Sehir Operasyonu"
        )

    def setup_scenario_3_corridor(self):
        """Senaryo 3: Daraltilmis koridor - sadece dar gecit."""
        # Iki paralel dag silsilesi (dar koridor olusturur)
        for c in range(10, 40):
            for r in range(15, 18):
                self.static_grid[r, c] = STATIC_OBSTACLE
            for r in range(32, 35):
                self.static_grid[r, c] = STATIC_OBSTACLE
        # Koridor icinde 2 dinamik tehdit (zaman zaman koridoru kapatir)
        self.add_threat(
            center=(25, 18), radius=3,
            active_pattern=[1, 1, 1, 1, 0, 0],
            threat_type="SAM",
        )
        self.add_threat(
            center=(25, 32), radius=3,
            active_pattern=[0, 0, 1, 1, 1, 1],
            threat_type="SAM",
        )
        return Mission(
            start=(25, 2), goal=(25, 47),
            max_range=80.0, name="Koridor Gecisi"
        )

    def setup_scenario_4_dynamic(self):
        """Senaryo 4: Yuksek dinamik - tehditler hizla degisir."""
        # Karisik harita
        self.add_building_cluster(center=(15, 15), size=4)
        self.add_building_cluster(center=(35, 35), size=4)
        self.add_mountain_range(
            points=[(25, 10), (25, 15), (25, 20), (25, 25)], thickness=1
        )
        # Hizla degisen tehditler
        self.add_threat(
            center=(15, 30), radius=4,
            active_pattern=[1, 0, 1, 0],
            threat_type="Radar",
            motion_pattern=[(0, -1), (0, 0), (0, 1), (0, 0)],
        )
        self.add_threat(
            center=(35, 15), radius=4,
            active_pattern=[0, 1, 0, 1],
            threat_type="Radar",
            motion_pattern=[(-1, 0), (0, 0), (1, 0), (0, 0)],
        )
        self.add_threat(
            center=(25, 40), radius=5,
            active_pattern=[1, 1, 0, 0],
            threat_type="SAM",
            motion_pattern=[(0, 0), (1, 0), (1, -1), (0, -1)],
        )
        return Mission(
            start=(5, 5), goal=(45, 45),
            max_range=180.0, name="Dinamik Tehdit Ortami"
        )

    def reset(self):
        """Ortami sifirla."""
        self.static_grid = np.zeros((self.size, self.size), dtype=int)
        self.threats = []
        self.current_time = 0


def build_environment(scenario: str = "simple", seed: int = 42) -> Tuple[UAVEnvironment, Mission]:
    """Hazir senaryolardan birini olustur."""
    env = UAVEnvironment(seed=seed)
    if scenario == "simple":
        mission = env.setup_scenario_1_simple()
    elif scenario == "urban":
        mission = env.setup_scenario_2_urban()
    elif scenario == "corridor":
        mission = env.setup_scenario_3_corridor()
    elif scenario == "dynamic":
        mission = env.setup_scenario_4_dynamic()
    else:
        raise ValueError(f"Bilinmeyen senaryo: {scenario}")
    return env, mission
