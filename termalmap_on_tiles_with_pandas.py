from PIL import Image
import os
import math
import numpy
import json
import numpy as np
import matplotlib.pyplot as plt
import multiprocessing as mp  # Добавлено для параллельной обработки
from functools import partial
from src.getData import create_point_for_draw
import pandas as pd
DROW_ALL_POINT = True
DROW_OPERATORS = True
zoom=16
MAX_LAT = 55.150
MIN_LAT = 54.800
MAX_LON = 83.100
MIN_LON = 82.700
MAX_X = 256
MAX_Y = 256
output_dir = "out/"

with open("data/thermalmapdataall.json", 'r') as f:
    data = json.load(f)
    
def load_data(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    priced_points = []
    for item in data:
        try:
            if int(item['rsrp']) <= -60 and int(item['rsrp']) >= -120 and (float(item["latitude"]) >= MIN_LAT and float(item["latitude"]) <= MAX_LAT and float(item["longitude"]) >= MIN_LON and float(item["longitude"]) <= MAX_LON):
                priced_points.append([int(item['rsrp']), float(item["latitude"]), float(item["longitude"]),int(item['rsrq']), int(item['rssi'])])
        except:
            pass
    return priced_points
      
def point_per_operator(data, operator):
    sorted_poits = []
    for point in data:
        if point[-1] == operator:
            sorted_poits.append(point)
    return sorted_poits
            
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
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def pixel_to_ll(x, y, MIN_lon, MAX_lat, MAX_lon, MIN_lat):
    delta_lat = MAX_lat - MIN_lat
    delta_lon = MAX_lon - MIN_lon

    x_frac = float(x) / MAX_X
    y_frac = float(y) / MAX_Y

    lon = MIN_lon + x_frac * delta_lon
    lat = MAX_lat - y_frac * delta_lat

    return lat, lon


def haversine_distance(lat1, lon1, lat2, lon2, to_radians=True, earth_radius=6371, to_meters=True):
    """
    Вычисляет расстояние между двумя координатами, поддерживает векторные операции.
    
    Args:
        lat1, lon1: Скаляры или массивы (широта и долгота начальной точки).
        lat2, lon2: Скаляры или массивы (широта и долгота конечной точки).
        to_radians: Преобразовать градусы в радианы (по умолчанию True).
        earth_radius: Радиус Земли (по умолчанию 6371 км).
        to_meters: Возвратить расстояние в метрах (по умолчанию True).
        
    Returns:
        np.array: Расстояния в метрах или километрах между точками.
    """
    if to_radians:
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2 * np.arcsin(np.sqrt(a))

    distance = earth_radius * c
    return distance * 1000 if to_meters else distance


def get_gradient_color(value, vmin, vmax, cmap_name):
    if vmax > 0 and vmin <= 0:
        norm_value = (value - vmin) / (vmax - vmin)
        norm_value = np.clip(norm_value, 0, 1)

        cmap = plt.get_cmap(cmap_name)
        rgba_color = cmap(norm_value)
        rgb_color = (np.array(rgba_color) * 255).astype(int)  # Убираем альфа-канал и умножаем на 255
        tuple_color = tuple(rgb_color.tolist())
        
        return tuple_color
    
    else:
        if value:
            norm_value = (value - vmin) / (vmax - vmin)
            norm_value = np.clip(norm_value, 0, 1)
    
            cmap = plt.get_cmap(cmap_name)
            rgba_color = cmap(norm_value)
            rgb_color = (np.array(rgba_color) * 255).astype(int)  # Убираем альфа-канал и умножаем на 255
            tuple_color = tuple(rgb_color.tolist())
            
            return tuple_color
        else:
            return (0, 0, 0, 0)  # Черный цвет, если значение пустоее
      
def get_pci_color(value, field):
    if field == 'pci_mod_3':
        max_values = 3
    else:
        max_values = 6
    if value != None:
        norm_value = value / max_values
        cmap = plt.get_cmap('jet')
        rgba_color = cmap(norm_value)
        rgb_color = (np.array(rgba_color) * 255).astype(int)
        tuple_color = tuple(rgb_color.tolist())
        return tuple_color
    else:
        return (0, 0, 0, 0)
    

def calculate_price(points_df, lat, lon, radius=7):
    """
    Вычисляет средние значения для всех слоев в радиусе заданного расстояния (метры).

    Args:
        points_df (pd.DataFrame): DataFrame с колонками ['rsrp', 'lat', 'lon', 'rsrq', 'rssnr', 'pci', 'pci_mod_3', 'pci_mod_6'].
        lat (float): Широта центральной точки.
        lon (float): Долгота центральной точки.
        radius (float): Радиус поиска в метрах (по умолчанию 7 м).

    Returns:
        dict: Средние значения для всех полей, включая логарифмические параметры.
    """
    # Вычисление расстояния для всех точек и фильтрация по радиусу
    points_df['distance'] = haversine_distance(
        lat, lon,
        points_df['lat'].to_numpy(), 
        points_df['lon'].to_numpy()
    )
    points_in_radius = points_df[points_df['distance'] <= radius]

    # Если точек нет, возвращаем None для всех значений
    if points_in_radius.empty:
        return {
            'rsrp': None,
            'rsrq': None,
            'rssnr': None,
            'pci': None,
            'pci_mod_3': None,
            'pci_mod_6': None
        }

    # Функция для усреднения значений в логарифмическом масштабе
    def average_logarithmic(values):
        if values.empty:
            return None
        linear_values = 10 ** (values / 10)
        avg_linear = np.mean(linear_values)
        return 10 * np.log10(avg_linear)

    # Определение максимального RSRP для извлечения PCI и модификаций
    max_rsrp_idx = points_in_radius['rsrp'].idxmax()
    max_rsrp_row = points_in_radius.loc[max_rsrp_idx]

    # Формирование результата
    averages = {
        'rsrp': average_logarithmic(points_in_radius['rsrp']),
        'rsrq': average_logarithmic(points_in_radius['rsrq']),
        'rssnr': average_logarithmic(points_in_radius['rssnr']),
        'pci': max_rsrp_row['pci'] if not points_in_radius.empty else None,
        'pci_mod_3': max_rsrp_row['pci_mod_3'] if not points_in_radius.empty else None,
        'pci_mod_6': max_rsrp_row['pci_mod_6'] if not points_in_radius.empty else None
    }

    # Удаление временной колонки
    points_df.drop(columns=['distance'], inplace=True)

    return averages



def drow_map(tile, operator):
    points = tile["points"]
    delta = {'rsrp': [-120, -60], 'rsrq': [-21, -2], 'rssnr': [-20, 20], 'pci': [0, 502], 'pci_mod_3': [0, 2], 'pci_mod_6': [0, 5]}
    tile_cord_XX = tile["cords"][1]
    tile_cord_XY = tile["cords"][0]
    tile_cord_YX = tile["cords"][3]
    tile_cord_YY = tile["cords"][2]
    
    # Инициализация массивов для всех слоев
    priced = {field: np.zeros((MAX_X, MAX_Y)) for field in delta.keys()}
    
    # Заполнение массивов значениями из одного вызова `calculate_price`
    for x in range(MAX_X):
        for y in range(MAX_Y):
            lat, lon = pixel_to_ll(x, y, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY)
            averages = calculate_price(points, lat, lon)
            
            for field, value in averages.items():
                priced[field][x, y] = value

    # Цветовые карты для сохранения
    color_maps = ['jet']
    
    # Сохранение изображений для каждого слоя и цветовой карты
    for cmap_name in color_maps:
        for field in delta.keys():
            img = Image.new('RGBA', (MAX_X, MAX_Y))
            pixels = img.load()
            
            if field == 'pci_mod_3' or field == 'pci_mod_6':
                for x in range(MAX_X):
                    for y in range(MAX_Y):
                        pixels[x, y] = get_pci_color(priced[field][x, y],field)
            else:
                for x in range(MAX_X):
                    for y in range(MAX_Y):
                            pixels[x, y] = get_gradient_color(priced[field][x, y], delta[field][0], delta[field][1], cmap_name)
            
            # Создаем папку для каждой карты
            folder_path = os.path.join(output_dir, operator, field, cmap_name, str(tile["z"]), str(tile["x"]))
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, f"{tile['y']}.png")
            img.save(file_path, "PNG")

    


def process_tile(tile, operator):
    drow_map(tile, operator)

def get_neighbors(tile):
    """Возвращает список соседних тайлов для данного тайла."""
    x, y, z = tile['x'], tile['y'], tile['z']
    neighbors = [
        (x + 1, y), (x + 1, y + 1), (x, y + 1), (x - 1, y + 1),
        (x - 1, y), (x - 1, y - 1), (x, y - 1), (x + 1, y - 1)
    ]
    return [(nx, ny, z) for nx, ny in neighbors]

def get_tiles(priced_points):
    tiles_dict = {}
    for point in priced_points:
        xtile, ytile = deg2num(point[1], point[2], zoom)
        min_lon, max_lat = num2deg(xtile, ytile, zoom)
        max_lon, min_lat = num2deg(xtile + 1, ytile + 1, zoom)
        tile_cords = [min_lon, max_lat, max_lon, min_lat]

        tile_key = (xtile, ytile, zoom)
        if tile_key not in tiles_dict:
            tiles_dict[tile_key] = {
                'z': zoom,
                'x': xtile,
                'y': ytile,
                'cords': tile_cords,
                'points': []  # Временное хранилище списка точек
            }
        tiles_dict[tile_key]['points'].append(point)

    if zoom > 15:
        # Объединение точек только для соседних тайлов, предотвращая накопление
        processed_neighbors = set()  # Множество для хранения уже обработанных соседей
        for tile_key, tile_data in tiles_dict.items():
            neighbors = get_neighbors(tile_data)
            for neighbor in neighbors:
                if neighbor in tiles_dict and (tile_key, neighbor) not in processed_neighbors:
                    # Добавляем точки из соседнего тайла и помечаем, что эта пара обработана
                    tile_data['points'].extend(tiles_dict[neighbor]['points'])
                    processed_neighbors.add((neighbor, tile_key))  # Добавляем в обе стороны

    # Преобразование точек в pandas.DataFrame
    tiles = []
    for tile_key, tile_data in tiles_dict.items():
        # Преобразуем список точек в DataFrame
        tile_data['points'] = pd.DataFrame(
            tile_data['points'],
            columns=['rsrp', 'lat', 'lon', 'rsrq', 'rssnr', 'pci', 'pci_mod_3', 'pci_mod_6', 'operator']
        )
        tiles.append(tile_data)

    return tiles





if __name__ == "__main__":
    operators = ['MTS', 'Beeline', 'YOTA', 'Megafon']
    #priced_points = load_data('data/thermalmapdataall.json')
    #=create_test_data(priced_points)
    print("Импорт точек из БД")
    priced_points = create_point_for_draw()
    print("Успешно\nОтрисовываются все точки: ", len(priced_points))
    if DROW_ALL_POINT == True:
        for i in range(12,13):
            zoom = i
            tiles = get_tiles(priced_points)
            print("Отрисовываются ", len(tiles), "тайлов для zoom >> ", zoom)
            
            #process_with_operator = partial(process_tile, operator="ALL")
            # Параллельная обработка тайлов с использованием пула процессов
            #with mp.Pool(mp.cpu_count()) as pool:
            #    pool.map(process_with_operator, tiles)
        '''
    if DROW_OPERATORS == True:
        print("\nОтрисовываются точки по операторам")
        for operator in operators:
            print("\nОтрисовывается >> ", operator)   
            priced_points_per_operator = point_per_operator(priced_points, operator)
            print("Количество точек: ", len(priced_points_per_operator))
            if len(priced_points_per_operator) > 0:
                for i in range(12,19):
                    zoom = i
                    tiles = get_tiles(priced_points_per_operator)
                    print("Отрисовываются ", len(tiles), "тайлов для zoom= ", zoom)
                    process_with_operator = partial(process_tile, operator=operator)
                    # Параллельная обработка тайлов с использованием пула процессов
                    with mp.Pool(mp.cpu_count()) as pool:
                        pool.map(process_with_operator, tiles)
    print("done")
        '''