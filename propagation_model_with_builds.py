from PIL import Image
import os
import math
import numpy as np
import matplotlib.pyplot as plt
from functools import partial
import multiprocessing as mp
from enum import Enum
import geopandas as gpd
from shapely.geometry import Point, LineString, box
import rasterio
from rasterio.features import rasterize
import osmnx as ox
import pandas as pd
BUILDING_ATTENUATION = 4.0  # Доп. затухание через здания (дБ)


class PropagationModel(Enum):
    UMa = "Urban Macro (3GPP TR 38.901)"
    UMi = "Urban Micro (3GPP TR 38.901)"
    RMa = "Rural Macro (3GPP TR 38.901)"
    COST_HATA_URBAN = "COST-Hata Urban"
    COST_HATA_SUBURBAN = "COST-Hata Suburban"
    COST_HATA_RURAL = "COST-Hata Rural"
    INH_OFFICE = "Indoor Office (3GPP TR 38.901)"
    INF = "Industrial Factory (InF-SL/DL/SH/DH) (3GPP TR 38.901)"

# Параметры БС
FREQUENCY = 1800           # MHz
HT = 25                    # m
HR = 1.5                   # m
PTX = 40                   # dBm
ANTENNA_GAIN = 15          # dBi
CABLE_LOSS = 3             # dB
N_SUBCARRIERS = 1200       # для 20 MHz
PTX_SUB = PTX - 10 * np.log10(N_SUBCARRIERS)

# Параметры антенны 3GPP TR 38.901
WAVELENGTH = 3e8 / (FREQUENCY * 1e6)  # м
G_MAX = ANTENNA_GAIN

# Панели антенны
Mg = 1  # количество панелей по вертикали
Ng = 1  # количество панелей по горизонтали

# Элементы внутри одной панели
M = 8  # по вертикали
N = 4  # по горизонтали
P = 1  # поляризация 

# Расстояния между элементами
dH = 0.5 * WAVELENGTH  # по горизонтали
dV = 0.5 * WAVELENGTH  # по вертикали

# Порог чувствительности UE
RECEIVER_SENSITIVITY = -110  # dBm

ZOOM_LEVELS = range(12, 14)
OUTPUT_DIR = "coverage_tiles/"
ALPHA = 255  # непрозрачность


def get_affected_tiles(tx_lat, tx_lon, target_tile, zoom):
    """Получаем все тайлы, через которые проходит луч от БС до целевого тайла"""
    tx_tile = deg2num(tx_lat, tx_lon, zoom)
    x1, y1 = tx_tile
    x2, y2 = target_tile['x'], target_tile['y']
    
    # Алгоритм Брезенхема для рисования линии между тайлами
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    x, y = x1, y1
    sx = -1 if x1 > x2 else 1
    sy = -1 if y1 > y2 else 1
    
    affected_tiles = []
    
    if dx > dy:
        err = dx / 2.0
        while x != x2:
            affected_tiles.append({'z': zoom, 'x': x, 'y': y})
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y2:
            affected_tiles.append({'z': zoom, 'x': x, 'y': y})
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    
    affected_tiles.append(target_tile)
    return affected_tiles

def get_buildings_for_tile_path(tile, tx_lat, tx_lon, all_buildings):
    """Получаем здания для всех тайлов на пути сигнала"""
    affected_tiles = get_affected_tiles(tx_lat, tx_lon, tile, tile['z'])
    
    buildings_list = []
    for affected_tile in affected_tiles:
        min_lat, min_lon = num2deg(affected_tile['x'], affected_tile['y'] + 1, affected_tile['z'])
        max_lat, max_lon = num2deg(affected_tile['x'] + 1, affected_tile['y'], affected_tile['z'])
        tile_bbox = box(min_lon, min_lat, max_lon, max_lat)
        
        if all_buildings is not None:
            # Получаем здания, пересекающиеся с текущим тайлом
            tile_buildings = all_buildings[all_buildings.geometry.intersects(tile_bbox)].copy()
            if len(tile_buildings) > 0:
                # Обрезаем геометрию по границам тайла
                tile_buildings.geometry = tile_buildings.geometry.intersection(tile_bbox)
                buildings_list.append(tile_buildings)
    
    if buildings_list:
        return pd.concat(buildings_list).drop_duplicates()
    return None

def filter_buildings_for_tile(buildings, tile_bounds):
    """Фильтрация зданий, которые пересекаются с текущим тайлом"""
    if buildings is None or len(buildings) == 0:
        return None
    
    min_lon, max_lat, max_lon, min_lat = tile_bounds
    tile_bbox = box(min_lon, min_lat, max_lon, max_lat)
    
    # Фильтруем здания, которые пересекаются с тайлом
    filtered = buildings[buildings.geometry.intersects(tile_bbox)].copy()
    
    # Обрезаем геометрию зданий по границам тайла
    filtered.geometry = filtered.geometry.intersection(tile_bbox)
    
    return filtered if len(filtered) > 0 else None
def calculate_bbox(tx_lat, tx_lon, radius_km):
    """Вычисление bounding box для заданного радиуса"""
    earth_radius = 6371.0  # км
    delta_lat = radius_km / earth_radius * (180.0 / math.pi)
    delta_lon = delta_lat / math.cos(math.radians(tx_lat))
    
    return (
        tx_lat - delta_lat,  # min_lat
        tx_lon - delta_lon,  # min_lon
        tx_lat + delta_lat,  # max_lat
        tx_lon + delta_lon   # max_lon
    )

def download_osm_buildings(min_lat, min_lon, max_lat, max_lon):
    """Загрузка данных о зданиях из OpenStreetMap"""
    try:
        print("Загрузка данных OSM...")
        north, south, east, west = max_lat, min_lat, max_lon, min_lon
        tags = {'building': True}
        
        # Скачиваем данные
        gdf = ox.features_from_bbox(
            north, south, east, west,
            tags=tags
        )
        
        # Оставляем только геометрию
        gdf = gdf[['geometry']].reset_index(drop=True)
        gdf = gdf[gdf.geometry.notnull()]
        
        print(f"Загружено {len(gdf)} зданий")
        return gdf
    
    except Exception as e:
        print(f"Ошибка при загрузке OSM данных: {str(e)}")
        return None

def create_building_mask(tile_bounds, buildings, shape):
    """Создание бинарной маски зданий для тайла"""
    if buildings is None or len(buildings) == 0:
        return None
        
    min_lon, max_lat, max_lon, min_lat = tile_bounds
    transform = rasterio.transform.from_bounds(
        min_lon, min_lat, max_lon, max_lat, 
        shape[1], shape[0]
    )
    
    # Растеризация с учетом мультиполигонов
    shapes = ((geom, 1) for geom in buildings.geometry)
    mask = rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype=np.uint8
    )
    return mask

def calculate_obstruction_loss(tx_point, rx_point, buildings):
    """Расчет дополнительных потерь из-за зданий"""
    if buildings is None or len(buildings) == 0:
        return 0.0
    
    line = LineString([tx_point, rx_point])
    intersections = buildings[buildings.geometry.intersects(line)]
    return len(intersections) * BUILDING_ATTENUATION

def calculate_3d_distance(d_2d, h_tx, h_rx):
    # 3D-расстояние
    return math.sqrt(d_2d**2 + (h_tx - h_rx)**2)

def path_loss_rma(d_2d, frequency_mhz, ht, hr, scenario='NLOS'):
    f_ghz = frequency_mhz / 1000.0
    d_3d = calculate_3d_distance(d_2d, ht, hr)
    h = 5     # средняя высота зданий
    W = 20    # средняя ширина улицы
    h_bs = ht
    h_ut = hr

    if scenario == 'LOS':
        if not (10 <= d_2d <= 10000):
            raise ValueError("Для LOS: d_2d должен быть в пределах 10 м ≤ d ≤ 10 км")
        
        c = 3e8
        d_bp = (2 * math.pi * h_bs * h_ut * frequency_mhz * 1e6) / c

        pl_los_1 = (
            20 * math.log10(40 * math.pi * d_3d * f_ghz / 3)
            + min(0.03 * h**1.72, 10) * math.log10(d_3d)
            - min(0.044 * h**1.72, 14.77)
            + 0.002 * math.log10(h) * d_3d
        )

        if d_2d <= d_bp:
            return pl_los_1
        else:
            return pl_los_1 + 40 * math.log10(d_3d / d_bp)

    elif scenario == 'NLOS':
        if not (10 <= d_2d <= 10000):
            print(d_2d)
            raise ValueError("Для NLOS: d_2d должен быть в пределах 10 м ≤ d ≤ 10 км")
            
        return (
            161.04
            - 7.1 * math.log10(W)
            + 7.5 * math.log10(h)
            - (24.37 - 3.7 * ((h / h_bs) ** 2)) * math.log10(h_bs)
            + (43.42 - 3.1 * math.log10(h_bs)) * (math.log10(d_3d) - 3)
            + 20 * math.log10(f_ghz)
            - 3.2 * (math.log10(11.75 * h_ut)) ** 2
            - 4.97
        )

def path_loss_uma(d_2d, frequency_mhz, ht, hr, scenario='NLOS'):
    d = calculate_3d_distance(d_2d, ht, hr)
    f_ghz = frequency_mhz / 1000.0
    pl_los = 28.0 + 22.0 * math.log10(d) + 20.0 * math.log10(f_ghz)
    if scenario == 'LOS':
        return pl_los
    pl_nlos = 13.54 + 39.08 * math.log10(d) + 20.0 * math.log10(f_ghz) - 0.6 * (hr - 1.5)
    return max(pl_los, pl_nlos)

def path_loss_umi(d_2d, frequency_mhz, ht, hr, scenario='NLOS'):
    d = calculate_3d_distance(d_2d, ht, hr)
    f_ghz = frequency_mhz / 1000.0
    pl_los = 32.4 + 21.0 * math.log10(d) + 20.0 * math.log10(f_ghz)
    if scenario == 'LOS':
        return pl_los
    pl_nlos = 35.3 * math.log10(d) + 22.4 + 21.3 * math.log10(f_ghz) - 0.3 * (hr - 1.5)
    return max(pl_los, pl_nlos)

def path_loss_inh_office(d_2d, frequency_mhz, ht, hr, scenario='NLOS'):
    d = calculate_3d_distance(d_2d, ht, hr)
    f_ghz = frequency_mhz / 1000.0
    pl_los = 32.4 + 17.3 * math.log10(d) + 20.0 * math.log10(f_ghz)
    if scenario == 'LOS':
        return pl_los
    pl_nlos = 17.3 + 38.3 * math.log10(d) + 24.9 * math.log10(f_ghz)
    return max(pl_los, pl_nlos)

def path_loss_inf(d_2d, frequency_mhz, ht, hr, scenario='NLOS', inf_nlos_type=None):
    d = calculate_3d_distance(d_2d, ht, hr)
    f_ghz = frequency_mhz / 1000.0
    # LOS
    pl_los = 31.84 + 21.50 * math.log10(d) + 19.00 * math.log10(f_ghz)
    if scenario == 'LOS':
        return pl_los
    # NLOS
    if inf_nlos_type is None:
        raise ValueError("Для InF NLOS укажите inf_nlos_type: 'InF-SL', 'InF-DL', 'InF-SH' или 'InF-DH'")
    if inf_nlos_type == 'InF-SL':
        pl_nlos = 33.0 + 25.5 * math.log10(d) + 20.0 * math.log10(f_ghz)
    elif inf_nlos_type == 'InF-DL':
        pl_nlos = 18.6 + 35.7 * math.log10(d) + 20.0 * math.log10(f_ghz)
    elif inf_nlos_type == 'InF-SH':
        pl_nlos = 32.4 + 23.0 * math.log10(d) + 20.0 * math.log10(f_ghz)
    elif inf_nlos_type == 'InF-DH':
        pl_nlos = 33.63 + 21.9 * math.log10(d) + 20.0 * math.log10(f_ghz)
    else:
        raise ValueError(f"Неизвестный тип InF NLOS: {inf_nlos_type}")
    return max(pl_los, pl_nlos)

def cost_hata(d_2d, frequency_mhz, ht, hr, area_type='urban', city_size='large'):
    if d_2d < 1:
        d_2d = 1

    if area_type == 'urban':
        if city_size == 'large' and frequency_mhz >= 300:
            a_hr = 3.2 * (np.log10(11.75 * hr))**2 - 4.97
        else:
            a_hr = (1.1 * np.log10(frequency_mhz) - 0.7) * hr - (1.56 * np.log10(frequency_mhz) - 0.8)
        C_M = 3 if city_size == 'large' else 0
        path_loss = (46.3 + 33.9 * np.log10(frequency_mhz) - 13.82 * np.log10(ht) - a_hr +
                     (44.9 - 6.55 * np.log10(ht)) * np.log10(d_2d / 1000) + C_M)
    elif area_type == 'suburban':
        path_loss = cost_hata(d_2d, frequency_mhz, ht, hr, 'urban', city_size) - 2 * (np.log10(frequency_mhz / 28))**2 - 5.4
    elif area_type == 'rural':
        path_loss = cost_hata(d_2d, frequency_mhz, ht, hr, 'urban', city_size) - 4.78 * (np.log10(frequency_mhz))**2 + 18.33 * np.log10(frequency_mhz) - 40.94
    else:
        raise ValueError("Invalid area type.")
    return path_loss

def get_path_loss(d_2d, frequency_mhz, ht, hr, model, scenario='NLOS', inf_nlos_type=None):
    if model == PropagationModel.UMa:
        return path_loss_uma(d_2d, frequency_mhz, ht, hr, scenario)
    elif model == PropagationModel.UMi:
        return path_loss_umi(d_2d, frequency_mhz, ht, hr, scenario)
    elif model == PropagationModel.RMa:
        return path_loss_rma(d_2d, frequency_mhz, ht, hr, scenario)
    elif model == PropagationModel.INH_OFFICE:
        return path_loss_inh_office(d_2d, frequency_mhz, ht, hr, scenario)
    elif model == PropagationModel.INF:
        return path_loss_inf(d_2d, frequency_mhz, ht, hr, scenario, inf_nlos_type)
    elif model == PropagationModel.COST_HATA_URBAN:
        return cost_hata(d_2d, frequency_mhz, ht, hr, 'urban')
    elif model == PropagationModel.COST_HATA_SUBURBAN:
        return cost_hata(d_2d, frequency_mhz, ht, hr, 'suburban')
    elif model == PropagationModel.COST_HATA_RURAL:
        return cost_hata(d_2d, frequency_mhz, ht, hr, 'rural')
    else:
        raise ValueError(f"Неизвестная модель: {model}")

def calculate_max_distance(frequency_mhz, ht, hr, link_budget_dbm,
                           model=PropagationModel.UMa, max_search_distance=50000.0,
                           scenario='NLOS', inf_nlos_type=None):
    max_pl = PTX_SUB + ANTENNA_GAIN - CABLE_LOSS - link_budget_dbm
    low, high = 1.0, max_search_distance
    if model in (PropagationModel.INH_OFFICE, PropagationModel.INF):
        high = min(high, 500.0)
    if model in (PropagationModel.RMa, PropagationModel.RMa):
        high = min(high, 9000)
    while high - low > 1.0:
        mid = (low + high) / 2.0
        pl = get_path_loss(mid, frequency_mhz, ht, hr, model, scenario, inf_nlos_type)
        if pl < max_pl:
            low = mid
        else:
            high = mid
    return low / 1000.0  # км

# --- Antenna pattern (3GPP TR 38.901) ---
def element_pattern(theta_deg, phi_deg):
    A_m = 30
    theta_3dB = 65
    phi_3dB = 65
    A_theta = -min(12 * (theta_deg / theta_3dB)**2, A_m)
    A_phi = -min(12 * (phi_deg / phi_3dB)**2, A_m)
    attenuation = min(-(A_theta + A_phi), A_m)
    return G_MAX + attenuation  # в dBi

def array_factor(theta_rad, phi_rad):
    k = 2 * math.pi / WAVELENGTH
    af_real, af_imag = 0.0, 0.0

    for p in range(P):
        phase_offset_p = p * math.pi / 2  # 90° сдвиг между поляризациями

        for m in range(M):
            for n in range(N):
                phase_shift = k * (
                    m * dV * math.cos(theta_rad) +
                    n * dH * math.sin(theta_rad) * math.cos(phi_rad)
                ) + phase_offset_p

                af_real += math.cos(phase_shift)
                af_imag += math.sin(phase_shift)

    af_real /= P  # усреднение по поляризациям
    af_imag /= P

    af_magnitude = math.sqrt(af_real**2 + af_imag**2)
    af_gain_dB = 20 * math.log10(af_magnitude + 1e-9)
    return af_gain_dB

def antenna_gain(theta_deg, phi_deg):
    theta_rad = math.radians(theta_deg)
    phi_rad = math.radians(phi_deg)

    g_elem = element_pattern(theta_deg, phi_deg)
    g_array = array_factor(theta_rad, phi_rad)

    total_gain = g_elem + g_array
    return total_gain

def calculate_max_distance_with_antenna_sectors(frequency_mhz, ht, hr, link_budget_dbm,
                                                 model=PropagationModel.UMa,
                                                 max_search_distance=50000.0,
                                                 scenario='NLOS',
                                                 inf_nlos_type=None,
                                                 sector_degrees=10):
    """
    Расчет максимального расстояния с учетом диаграммы направленности антенны
    в разных азимутальных направлениях.
    """
    def get_rx_power(d_2d, azimuth_deg):
        # Расчет вертикального угла (без tilt)
        height_diff = ht - hr
        vertical_angle = math.degrees(math.atan2(height_diff, d_2d))

        # Усиление антенны для данного направления
        gain = antenna_gain(azimuth_deg, vertical_angle)

        # Потери на распространение
        pl = get_path_loss(d_2d, frequency_mhz, ht, hr, model, scenario, inf_nlos_type)

        # Мощность на приемнике
        return PTX_SUB + gain - CABLE_LOSS - pl

    max_radius_km = 0.0

    # Проверяем каждый сектор
    for azimuth_deg in range(0, 360, sector_degrees):
        low, high = 1.0, max_search_distance

        if get_rx_power(low, azimuth_deg) < link_budget_dbm:
            continue  # Нет покрытия даже вблизи

        while high - low > 1.0:
            mid = (low + high) / 2.0
            if get_rx_power(mid, azimuth_deg) >= link_budget_dbm:
                low = mid
            else:
                high = mid

        max_radius_km = max(max_radius_km, low / 1000.0)  # км

    return max_radius_km
# --- Гео-функции ---
def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 1 << zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile

def num2deg(xtile, ytile, zoom):
    n = 1 << zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    return math.degrees(lat_rad), lon_deg

def haversine_distance(lat1, lon1, lat2, lon2, to_radians=True, earth_radius=6371):
    if to_radians:
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2.0)**2
    return 2 * earth_radius * 1000 * np.arcsin(np.sqrt(a))

def pixel_to_ll(x, y, tile_bounds):
    min_lon, max_lat, max_lon, min_lat = tile_bounds
    lon = min_lon + (x / 256) * (max_lon - min_lon)
    lat = max_lat - (y / 256) * (max_lat - min_lat)
    return lat, lon

# --- Цвета ---
def get_gradient_color(value, distance, max_radius, vmin=-120, vmax=-60, cmap_name='jet'):
    if distance > max_radius * 1000:
        return (0, 0, 0, 0)
    norm_value = np.clip((value - vmin) / (vmax - vmin), 0, 1)
    cmap = plt.get_cmap(cmap_name)
    rgba = cmap(norm_value)
    return tuple((np.array(rgba[:3]) * 255).astype(int).tolist()) + (ALPHA,)

# --- Отрисовка тайла с учётом направленности ---
def render_tile(tile, tx_lat, tx_lon, max_radius_km, model, scenario, inf_nlos_type, azimuth_deg=0, tilt_deg=0, all_buildings=None):
    z, x, y = tile['z'], tile['x'], tile['y']
    min_lat, min_lon = num2deg(x, y + 1, z)
    max_lat, max_lon = num2deg(x + 1, y, z)
    tile_bounds = (min_lon, max_lat, max_lon, min_lat)
    
    # Получаем ВСЕ здания на пути сигнала от БС до этого тайла
    path_buildings = get_buildings_for_tile_path(tile, tx_lat, tx_lon, all_buildings)
    
    # Создаем маску зданий только для текущего тайла (для определения внутренних зданий)
    tile_buildings = filter_buildings_for_tile(all_buildings, tile_bounds)
    building_mask = create_building_mask(tile_bounds, tile_buildings, (256, 256)) if tile_buildings is not None else None
    
    img = Image.new('RGBA', (256, 256))
    pixels = img.load()
    tx_point = Point(tx_lon, tx_lat)

    for px in range(256):
        for py in range(256):
            lat, lon = pixel_to_ll(px, py, tile_bounds)
            d2d = haversine_distance(tx_lat, tx_lon, lat, lon)

            # --- Расчет углов и усиления антенны ---
            d_lon = lon - tx_lon
            d_lat = lat - tx_lat
            angle_to_pixel = (math.degrees(math.atan2(d_lon, d_lat)) + 360) % 360
            relative_theta = (angle_to_pixel - azimuth_deg + 360) % 360
            if relative_theta > 180:
                relative_theta = 360 - relative_theta
            
            height_diff = HT - HR
            vertical_angle = math.degrees(math.atan2(height_diff, d2d))
            gain = antenna_gain(relative_theta, vertical_angle)
            
            # --- Потери и мощность ---
            path_loss = get_path_loss(d2d, FREQUENCY, HT, HR, model, scenario, inf_nlos_type)
            
            # Дополнительные потери из-за ВСЕХ зданий на пути сигнала
            if path_buildings is not None:
                rx_point = Point(lon, lat)
                path_loss += calculate_obstruction_loss(tx_point, rx_point, path_buildings)
            
            # Доп. потери если пиксель внутри здания (только для зданий в текущем тайле)
            if building_mask is not None and building_mask[py, px]:
                path_loss += BUILDING_ATTENUATION
            
            rx_power = PTX_SUB + gain - CABLE_LOSS - path_loss
            
            if rx_power >= RECEIVER_SENSITIVITY:
                pixels[px, py] = get_gradient_color(rx_power, d2d, max_radius_km)
            else:
                pixels[px, py] = (0, 0, 0, 0)

    return img, z, x, y

# --- Сохранение ---
def save_tile(img, z, x, y):
    dir_path = os.path.join(OUTPUT_DIR, str(z), str(x))
    os.makedirs(dir_path, exist_ok=True)
    img.save(os.path.join(dir_path, f"{y}.png"), "PNG")

# --- Параллельная обработка ---
def process_tile(tile, tx_lat, tx_lon, max_radius_km, model, scenario, inf_nlos_type, azimuth_deg, all_buildings):
    """Обработка одного тайла с учетом зданий"""
    img, z, x, y = render_tile(tile, tx_lat, tx_lon, max_radius_km, model, scenario, inf_nlos_type, azimuth_deg, 0, all_buildings)
    save_tile(img, z, x, y)

def generate_tiles(tx_lat, tx_lon, radius_km, model, scenario, inf_nlos_type, azimuth_deg=0):
    earth_radius = 6371
    delta_lat = radius_km / earth_radius * (180 / math.pi)
    delta_lon = delta_lat / math.cos(math.radians(tx_lat))

    min_lat, max_lat = tx_lat - delta_lat, tx_lat + delta_lat
    min_lon, max_lon = tx_lon - delta_lon, tx_lon + delta_lon

    # Загружаем данные о зданиях для всей области покрытия
    print("Загрузка данных OSM...")
    try:
        north, south, east, west = max_lat, min_lat, max_lon, min_lon
        tags = {'building': True}
        all_buildings = ox.features_from_bbox(north, south, east, west, tags=tags)
        all_buildings = all_buildings[['geometry']].reset_index(drop=True)
        all_buildings = all_buildings[all_buildings.geometry.notnull()]
        print(f"Загружено {len(all_buildings)} зданий")
    except Exception as e:
        print(f"Ошибка при загрузке OSM данных: {str(e)}")
        all_buildings = None

    tiles = []
    for z in ZOOM_LEVELS:
        x_min, y_min = deg2num(max_lat, min_lon, z)
        x_max, y_max = deg2num(min_lat, max_lon, z)
        for x in range(x_min, x_max+1):
            for y in range(y_min, y_max+1):
                tiles.append({'z': z, 'x': x, 'y': y})

    # Создаем partial функцию с фиксированными параметрами
    process_func = partial(process_tile,
                         tx_lat=tx_lat,
                         tx_lon=tx_lon,
                         max_radius_km=radius_km,
                         model=model,
                         scenario=scenario,
                         inf_nlos_type=inf_nlos_type,
                         azimuth_deg=azimuth_deg,
                         all_buildings=all_buildings)

    with mp.Pool(mp.cpu_count()) as pool:
        pool.map(process_func, tiles)
        print(f"Сгенерировано {len(tiles)} тайлов")

if __name__ == "__main__":
    TX_LAT = 55.015970
    TX_LON = 82.942783
    AZIMUTH = 130  # градусов

    MODEL = PropagationModel.COST_HATA_URBAN
    SCENARIO = 'NLOS'
    INF_TYPE = None

    LINK_BUDGET = -118  # dBm

    max_radius_km = calculate_max_distance_with_antenna_sectors(
        FREQUENCY, HT, HR, LINK_BUDGET,
        model=MODEL,
        scenario=SCENARIO,
        inf_nlos_type=INF_TYPE,
        sector_degrees=10  # размер сектора в градусах
    )
    print(f"Максимальный радиус: {max_radius_km:.2f} км")

    generate_tiles(TX_LAT, TX_LON, max_radius_km, MODEL, SCENARIO, INF_TYPE, AZIMUTH)
    print("Готово!")