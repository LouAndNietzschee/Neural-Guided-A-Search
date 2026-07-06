"""
A* Search Algorithm with Pluggable Heuristics
----------------------------------------------
Bu modul A* arama algoritmasinin esnek bir implementasyonunu icerir.
Heuristic fonksiyonu (h) disardan verilir; klasik heuristic'ler ile
sinir agi tabanli heuristic'i karsilastirabilmek icin.

A* algoritmasi:
    f(n) = g(n) + h(n)
    g(n): Baslangictan n'ye kadar olan gercek maliyet
    h(n): n'den hedefe tahmini maliyet (heuristic)

Admissibility: h(n) <= h*(n) ise A* optimal sonucu garanti eder
(h*(n) = gercek en kisa mesafe).
"""

import heapq
import math
import time as time_lib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Set, Any

from environment import UAVEnvironment, Mission


# ============================================================
# HEURISTIC FONKSIYONLARI (Klasik)
# ============================================================

def manhattan_distance(node: Tuple[int, int], goal: Tuple[int, int],
                       time: Optional[int] = None) -> float:
    """Manhattan (L1) mesafesi.

    Sadece 4-yonlu hareket icin admissible; 8-yonlu hareket icin
    asiri tahmin yapabilir (overestimate). Yine de pratikte hizli ve
    cogu zaman iyi sonuc verir.
    """
    return abs(node[0] - goal[0]) + abs(node[1] - goal[1])


def euclidean_distance(node: Tuple[int, int], goal: Tuple[int, int],
                       time: Optional[int] = None) -> float:
    """Euclidean (L2) mesafesi.

    Her zaman admissible (8-yonlu hareket icin bile). Ancak biraz
    daha az bilgilendirici oldugu icin Manhattan'dan daha fazla
    dugum genisletir.
    """
    dr = node[0] - goal[0]
    dc = node[1] - goal[1]
    return math.sqrt(dr*dr + dc*dc)


def chebyshev_distance(node: Tuple[int, int], goal: Tuple[int, int],
                       time: Optional[int] = None) -> float:
    """Chebyshev (L∞) mesafesi.

    8-yonlu hareket icin tam admissible: capraz hareket maliyetinin
    1.0 oldugu varsayilirsa. Capraz maliyet √2 ise overestimate olabilir.
    """
    return max(abs(node[0] - goal[0]), abs(node[1] - goal[1]))


def octile_distance(node: Tuple[int, int], goal: Tuple[int, int],
                    time: Optional[int] = None) -> float:
    """Octile mesafesi - 8-yonlu hareket icin en iyi klasik heuristic.

    Capraz hareketin maliyeti √2 oldugunda admissible ve consistent.
    Formula: max(dr,dc) + (√2-1) * min(dr,dc)
    """
    dr = abs(node[0] - goal[0])
    dc = abs(node[1] - goal[1])
    return max(dr, dc) + (math.sqrt(2) - 1) * min(dr, dc)


# ============================================================
# A* DUGUM YAPISI
# ============================================================

@dataclass(order=True)
class AStarNode:
    """A* arama dugumu (priority queue icin order=True)."""
    f_score: float
    counter: int = field(compare=True)
    position: Tuple[int, int] = field(compare=False)
    g_score: float = field(compare=False, default=0.0)
    h_score: float = field(compare=False, default=0.0)
    parent: Optional["AStarNode"] = field(compare=False, default=None)


# ============================================================
# A* ALGORITMASI
# ============================================================

@dataclass
class AStarResult:
    """A* arama sonucu (analiz icin tum detaylar)."""
    path: List[Tuple[int, int]]
    cost: float
    nodes_expanded: int
    nodes_generated: int
    runtime_seconds: float
    success: bool
    heuristic_name: str
    explored_set: Set[Tuple[int, int]] = field(default_factory=set)
    h_values: Dict[Tuple[int, int], float] = field(default_factory=dict)
    g_values: Dict[Tuple[int, int], float] = field(default_factory=dict)
    # Dinamik A* icin her rota noktasinin zaman adimi. Statik A*'ta bos kalir.
    time_path: List[int] = field(default_factory=list)


def astar_search(
    env: UAVEnvironment,
    mission: Mission,
    heuristic_fn: Callable[[Tuple[int, int], Tuple[int, int]], float],
    heuristic_name: str = "unknown",
    time: int = 0,
    max_nodes: int = 100000,
    enforce_max_range: bool = True,
) -> AStarResult:
    """A* arama algoritmasi.

    Args:
        env: IHA ortami
        mission: Gorev tanimi (start, goal)
        heuristic_fn: Heuristic fonksiyon h(node, goal) -> float
        heuristic_name: Heuristic'in adi (raporlama icin)
        time: Hangi zaman adiminda arama yapildigi (dinamik tehditler icin)
        max_nodes: Maksimum genisletilebilecek dugum sayisi
        enforce_max_range: True ise mission.max_range asildiginda yol reddedilir

    Returns:
        AStarResult: Yol ve istatistikler
    """
    start = mission.start
    goal = mission.goal

    start_time = time_lib.time()

    # Baslangic kontrolleri
    if not env.is_passable(*start, time=time):
        return AStarResult(
            path=[], cost=float("inf"), nodes_expanded=0,
            nodes_generated=0, runtime_seconds=0,
            success=False, heuristic_name=heuristic_name,
        )
    if not env.is_passable(*goal, time=time):
        return AStarResult(
            path=[], cost=float("inf"), nodes_expanded=0,
            nodes_generated=0, runtime_seconds=0,
            success=False, heuristic_name=heuristic_name,
        )

    # Priority queue (open set)
    counter = 0
    h_start = heuristic_fn(start, goal, time)
    start_node = AStarNode(
        f_score=h_start, counter=counter, position=start,
        g_score=0.0, h_score=h_start, parent=None,
    )
    open_heap = [start_node]
    best_g: Dict[Tuple[int, int], float] = {start: 0.0}
    explored: Set[Tuple[int, int]] = set()
    h_values: Dict[Tuple[int, int], float] = {start: h_start}

    nodes_expanded = 0
    nodes_generated = 1

    while open_heap and nodes_expanded < max_nodes:
        current = heapq.heappop(open_heap)

        # Daha iyi bir yol bulunmussa atla
        if current.g_score > best_g.get(current.position, float("inf")):
            continue

        nodes_expanded += 1
        explored.add(current.position)

        # Hedef bulundu mu?
        if current.position == goal:
            # Yolu cikar
            path = []
            node = current
            while node is not None:
                path.append(node.position)
                node = node.parent
            path.reverse()
            runtime = time_lib.time() - start_time
            return AStarResult(
                path=path,
                cost=current.g_score,
                nodes_expanded=nodes_expanded,
                nodes_generated=nodes_generated,
                runtime_seconds=runtime,
                success=True,
                heuristic_name=heuristic_name,
                explored_set=explored,
                h_values=h_values,
                g_values=best_g,
            )

        # Limit kontrolu
        if nodes_expanded >= max_nodes:
            break

        # Komsulari genislet
        for (npos, move_cost) in env.get_neighbors(*current.position, time=time):
            tentative_g = current.g_score + move_cost
            if enforce_max_range and tentative_g > mission.max_range:
                continue
            if tentative_g < best_g.get(npos, float("inf")):
                best_g[npos] = tentative_g
                h_n = heuristic_fn(npos, goal, time)
                h_values[npos] = h_n
                f_n = tentative_g + h_n
                counter += 1
                heapq.heappush(open_heap, AStarNode(
                    f_score=f_n, counter=counter, position=npos,
                    g_score=tentative_g, h_score=h_n, parent=current,
                ))
                nodes_generated += 1

    # Yol bulunamadi
    runtime = time_lib.time() - start_time
    return AStarResult(
        path=[], cost=float("inf"),
        nodes_expanded=nodes_expanded,
        nodes_generated=nodes_generated,
        runtime_seconds=runtime,
        success=False,
        heuristic_name=heuristic_name,
        explored_set=explored,
        h_values=h_values,
        g_values=best_g,
    )


# ============================================================
# ZAMAN GENISLETMELI DINAMIK A* ALGORITMASI
# ============================================================

@dataclass(order=True)
class DynamicAStarNode:
    """Zaman genisletmeli A* dugumu.

    state = (satir, sutun, zaman). Rota donerken yalnizca (satir, sutun)
    listesi cikarilir; time_path alaninda zamanlar tutulur.
    """
    f_score: float
    counter: int = field(compare=True)
    position: Tuple[int, int] = field(compare=False)
    time_step: int = field(compare=False)
    g_score: float = field(compare=False, default=0.0)
    h_score: float = field(compare=False, default=0.0)
    parent: Optional["DynamicAStarNode"] = field(compare=False, default=None)


def astar_search_dynamic(
    env: UAVEnvironment,
    mission: Mission,
    heuristic_fn: Callable[[Tuple[int, int], Tuple[int, int]], float],
    heuristic_name: str = "unknown",
    start_time_step: int = 0,
    max_nodes: int = 200000,
    max_time_steps: Optional[int] = None,
    allow_wait: bool = True,
    wait_cost: float = 1.0,
    enforce_max_range: bool = True,
) -> AStarResult:
    """Zaman genisletmeli A* aramasi.

    Normal astar_search fonksiyonu tehditleri tek bir zaman aninda dondurur.
    Bu fonksiyon ise durumu (r, c, t) olarak tutar. Her hareketten sonra t bir
    artar ve komsu hucrenin gecilebilirligi varis zamaninda kontrol edilir.

    Args:
        env: IHA ortami
        mission: Gorev tanimi
        heuristic_fn: h((r, c), goal) -> float
        heuristic_name: Raporlama adi
        start_time_step: Baslangic zamani
        max_nodes: Maksimum genisletilecek zamanli dugum sayisi
        max_time_steps: Arama ufku. None ise max_range tabanli makul deger atanir.
        allow_wait: True ise IHA ayni hucrede 1 zaman adimi bekleyebilir
        wait_cost: Bekleme maliyeti
        enforce_max_range: True ise mission.max_range asildiginda yol reddedilir
    """
    start = mission.start
    goal = mission.goal
    start_clock = time_lib.time()

    if max_time_steps is None:
        # Bir adimda maliyet en az 1 oldugu icin menzil makul bir zaman ufkudur.
        # Menzil kullanilmazsa grid boyutunun 4 kati guvenli bir varsayimdir.
        if mission.max_range and math.isfinite(mission.max_range):
            max_time_steps = start_time_step + int(math.ceil(mission.max_range)) + 2
        else:
            max_time_steps = start_time_step + 4 * env.size

    # Tehdit durumlari periyodik oldugu icin ayni (konum, zaman fazi)
    # tekrar gorulurse daha yuksek maliyetli yol domine edilir. Bu, dinamik
    # Dijkstra'nin gereksiz sekilde sinirsiz zaman katmanlarina yayilmasini onler.
    threat_period = 1
    for threat in env.threats:
        if threat.active_pattern:
            threat_period = math.lcm(threat_period, len(threat.active_pattern))

    if not env.is_passable(*start, time=start_time_step):
        return AStarResult(
            path=[], cost=float("inf"), nodes_expanded=0, nodes_generated=0,
            runtime_seconds=0, success=False, heuristic_name=heuristic_name,
        )

    counter = 0
    h_start = heuristic_fn(start, goal, start_time_step)
    start_node = DynamicAStarNode(
        f_score=h_start, counter=counter, position=start,
        time_step=start_time_step, g_score=0.0, h_score=h_start, parent=None,
    )
    open_heap = [start_node]
    start_phase = start_time_step % threat_period
    best_g: Dict[Tuple[int, int, int], float] = {(start[0], start[1], start_phase): 0.0}
    explored_states: Set[Tuple[int, int, int]] = set()
    explored_positions: Set[Tuple[int, int]] = set()
    h_values: Dict[Tuple[int, int], float] = {start: h_start}
    best_g_by_position: Dict[Tuple[int, int], float] = {start: 0.0}

    nodes_expanded = 0
    nodes_generated = 1

    while open_heap and nodes_expanded < max_nodes:
        current = heapq.heappop(open_heap)
        phase = current.time_step % threat_period
        state = (current.position[0], current.position[1], phase)

        if current.g_score > best_g.get(state, float("inf")):
            continue

        nodes_expanded += 1
        explored_states.add(state)
        explored_positions.add(current.position)

        if current.position == goal:
            path: List[Tuple[int, int]] = []
            time_path: List[int] = []
            node: Optional[DynamicAStarNode] = current
            while node is not None:
                path.append(node.position)
                time_path.append(node.time_step)
                node = node.parent
            path.reverse()
            time_path.reverse()
            return AStarResult(
                path=path,
                cost=current.g_score,
                nodes_expanded=nodes_expanded,
                nodes_generated=nodes_generated,
                runtime_seconds=time_lib.time() - start_clock,
                success=True,
                heuristic_name=heuristic_name,
                explored_set=explored_positions,
                h_values=h_values,
                g_values=best_g_by_position,
                time_path=time_path,
            )

        if current.time_step >= max_time_steps:
            continue

        next_time = current.time_step + 1
        candidates = env.get_neighbors(*current.position, time=next_time)

        if allow_wait and env.is_passable(*current.position, time=next_time):
            cell_cost = env.get_movement_cost(*current.position, time=next_time)
            if math.isfinite(cell_cost):
                candidates.append((current.position, wait_cost * cell_cost))

        for (npos, move_cost) in candidates:
            tentative_g = current.g_score + move_cost
            if enforce_max_range and tentative_g > mission.max_range:
                continue

            next_phase = next_time % threat_period
            next_state = (npos[0], npos[1], next_phase)
            if tentative_g < best_g.get(next_state, float("inf")):
                best_g[next_state] = tentative_g
                if tentative_g < best_g_by_position.get(npos, float("inf")):
                    best_g_by_position[npos] = tentative_g
                h_n = heuristic_fn(npos, goal, next_time)
                h_values[npos] = h_n
                counter += 1
                heapq.heappush(open_heap, DynamicAStarNode(
                    f_score=tentative_g + h_n,
                    counter=counter,
                    position=npos,
                    time_step=next_time,
                    g_score=tentative_g,
                    h_score=h_n,
                    parent=current,
                ))
                nodes_generated += 1

    return AStarResult(
        path=[], cost=float("inf"), nodes_expanded=nodes_expanded,
        nodes_generated=nodes_generated, runtime_seconds=time_lib.time() - start_clock,
        success=False, heuristic_name=heuristic_name,
        explored_set=explored_positions,
        h_values=h_values,
        g_values=best_g_by_position,
    )


# ============================================================
# YARDIMCI FONKSIYONLAR
# ============================================================

def true_distance(env: UAVEnvironment, start: Tuple[int, int],
                  time: int = 0) -> Dict[Tuple[int, int], float]:
    """Her hucreden ``start`` hedefine optimal statik maliyeti hesaplar.

    Hareket maliyeti girilen hucreye bagli oldugu icin kenarlar yonludur.
    Bu nedenle Dijkstra hedeften calisirken ters kenarin ileri maliyeti,
    yani mevcut hucreye giris maliyeti kullanilir.
    """
    counter = 0
    distances: Dict[Tuple[int, int], float] = {start: 0.0}
    open_heap = [AStarNode(
        f_score=0.0, counter=counter, position=start, g_score=0.0,
    )]

    while open_heap:
        current = heapq.heappop(open_heap)
        if current.g_score > distances.get(current.position, float("inf")):
            continue
        for (npos, _) in env.get_neighbors(*current.position, time=time):
            dr = abs(npos[0] - current.position[0])
            dc = abs(npos[1] - current.position[1])
            base_cost = math.sqrt(2) if dr and dc else 1.0
            reverse_edge_cost = base_cost * env.get_movement_cost(
                *current.position, time=time
            )
            tentative_g = current.g_score + reverse_edge_cost
            if tentative_g < distances.get(npos, float("inf")):
                distances[npos] = tentative_g
                counter += 1
                heapq.heappush(open_heap, AStarNode(
                    f_score=tentative_g, counter=counter, position=npos,
                    g_score=tentative_g,
                ))
    return distances


# Heuristic fonksiyonlarini isim->fonksiyon esleyen sozluk
CLASSIC_HEURISTICS = {
    "manhattan": manhattan_distance,
    "euclidean": euclidean_distance,
    "chebyshev": chebyshev_distance,
    "octile": octile_distance,
    "zero": lambda n, g, time=None: 0.0,  # Dijkstra
}
