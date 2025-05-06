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
    if to_radians:
        lat1, lon1, lat2, lon2 = np.radians([lat1, lon1, lat2, lon2])

    a = np.sin((lat2 - lat1) / 2.0) ** 2 + \
        np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    if to_meters:
        return 1000 * earth_radius * 2 * np.arcsin(np.sqrt(a))
    else:
        return earth_radius * 2 * np.arcsin(np.sqrt(a))

import numpy as np
def get_gradient_color(value, vmin, vmax, cmap_name):
    if value:
        norm_value = (value - vmin) / (vmax - vmin)
        norm_value = np.clip(norm_value, 0, 1)

        cmap = plt.get_cmap(cmap_name)
        rgba_color = cmap(norm_value)
        rgb_color = (np.array(rgba_color) * 255).astype(int)  # Убираем альфа-канал и умножаем на 255
        tuple_color = tuple(rgb_color.tolist())
        
        return tuple_color
    else:
        return (0, 0, 0, 1)  # Черный цвет, если значение пустое
with open("magma_pci.txt", "w") as file:
    for i in range(0, 503):
        output = f"magma pci = {i}: "
        x = get_gradient_color(i, -21, -2, 'magma')
        output2 = f"{x}"
        print(output)
        print(output2)
        file.write(output + "\n" + output2 + "\n")  # Записываем в файл, добавляя перевод строки
    
def calculate_price(points, lat, lon,tile_cord_XX, tile_cord_XY,tile_cord_YX,tile_cord_YY, field_name):
    values = []
    for point in points:
        d = haversine_distance(lat, lon, point[1], point[2])
        if d <= 15:
            if field_name == "rsrp" :
                values.append(point[0])
            elif field_name == "rsrq" :
                values.append(point[3])
            elif field_name == "rssnr":
                values.append(point[4])
            elif field_name == "pci":
                values.append(point[5])
            elif field_name == "pci_mod_3":
                values.append(point[6])
            else:
                values.append(point[7])
            
            
    if values:
        average = np.mean(values)
        if field_name == "rsrp":
            return average if average <= -5 else None
        elif field_name == "rsrq":
            return average if average <= 0 else None
        elif field_name == "rssnr":
            return average if average <= 20 else None
        else:
            return average
    return 0

    
def drow_map(tile, operator):
    points = tile["points"]
    delta = {'rsrp' : [-120,-60], 'rsrq' : [-21, -2], 'rssnr' : [-20,20], 'pci' : [0,502], 'pci_mod_3' : [0,2], 'pci_mod_6' : [0,5]}
    tile_cord_XX = tile["cords"][1]
    tile_cord_XY = tile["cords"][0]
    tile_cord_YX = tile["cords"][3]
    tile_cord_YY = tile["cords"][2]
    fields = ["rsrp", "rsrq", "rssnr", "pci", "pci_mod_3", "pci_mod_6"]
    prices = np.zeros((MAX_X, MAX_Y))  # Используем массив NumPy для хранения цен
    prices_q = np.zeros((MAX_X, MAX_Y))
    prices_snr = np.zeros((MAX_X, MAX_Y))  # Используем массив NumPy для хранения цен
    prices_pci = np.zeros((MAX_X, MAX_Y))  # Используем массив NumPy для хранения цен
    prices_pci3 = np.zeros((MAX_X, MAX_Y))  # Используем массив NumPy для хранения цен
    prices_pci6 = np.zeros((MAX_X, MAX_Y))  # Используем массив NumPy для хранения цен
    
    for x in range(MAX_X):
        for y in range(MAX_Y):
            lat, lon = pixel_to_ll(x, y, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY)
            prices[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[0])
            prices_q[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[1])
            prices_snr[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[2])
            prices_pci[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[3])
            prices_pci3[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[4])
            prices_pci6[x, y] = calculate_price(points, lat, lon, tile_cord_XX, tile_cord_XY, tile_cord_YX, tile_cord_YY, fields[5])
    priced = {'rsrp' : prices, 'rsrq' : prices_q, 'rssnr' : prices_snr, 'pci' : prices_pci, 'pci_mod_3' : prices_pci3, 'pci_mod_6' : prices_pci6}
    # Цветовые карты для сохранения
    color_maps = ['magma', 'jet']
    
    for cmap_name in color_maps:
        for field in fields:
            img = Image.new('RGBA', (MAX_X, MAX_Y))
            pixels = img.load()
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
                'z': zoom, 'x': xtile, 'y': ytile, 'cords': tile_cords, 'points': set()
            }
        tiles_dict[tile_key]['points'].add(tuple(point))

    if zoom > 15:
        # Объединение точек только для соседних тайлов, предотвращая накопление
        processed_neighbors = set()  # Множество для хранения уже обработанных соседей
        for tile_key, tile_data in tiles_dict.items():
            neighbors = get_neighbors(tile_data)
            for neighbor in neighbors:
                if neighbor in tiles_dict and (tile_key, neighbor) not in processed_neighbors:
                    # Добавляем точки из соседнего тайла и помечаем, что эта пара обработана
                    tile_data['points'].update(tiles_dict[neighbor]['points'])
                    processed_neighbors.add((neighbor, tile_key))  # Добавляем в обе стороны

    # Преобразование точек обратно в списки для финального списка тайлов
    tiles = []
    for tile_key, tile_data in tiles_dict.items():
        tile_data['points'] = list(tile_data['points'])
        tiles.append(tile_data)

    return tiles




if __name__ == "__main__":
    operators = ['MTS', 'Beeline', 'YOTA', 'Megafon']
    #priced_points = load_data('data/thermalmapdataall.json')
    #=create_test_data(priced_points)
    print("Импорт точек из БД")
    priced_points = create_point_for_draw()
    print("Успешно\n Отрисовываются все точки: ", len(priced_points))
    if DROW_ALL_POINT == True:
        for i in range(12,19):
            zoom = i
            tiles = get_tiles(priced_points)
            print("Отрисовываются ", len(tiles), "тайлов для zoom >> ", zoom)
            process_with_operator = partial(process_tile, operator="ALL")
            # Параллельная обработка тайлов с использованием пула процессов
            with mp.Pool(mp.cpu_count()) as pool:
                pool.map(process_with_operator, tiles)
    if DROW_OPERATORS == True:
        print("\nОтрисовываются точки по операторам")
        for operator in operators:
            print("\nОтрисовывается >> ", operator)   
            priced_points = point_per_operator(priced_points, operator)
            if len(priced_points) > 0:
                for i in range(12,19):
                    zoom = i
                    tiles = get_tiles(priced_points)
                    print("Отрисовываются ", len(tiles), "тайлов для zoom= ", zoom)
                    process_with_operator = partial(process_tile, operator=operator)
                    # Параллельная обработка тайлов с использованием пула процессов
                    with mp.Pool(mp.cpu_count()) as pool:
                        pool.map(process_with_operator, tiles)