import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt

# Задаем место (Новосибирск)
place_name = "Novosibirsk, Russia"

# Загружаем данные дорог (граф дорог)
G = ox.graph_from_place(place_name, network_type='all')
# Преобразуем граф дорог в GeoDataFrame
gdf_roads = ox.graph_to_gdfs(G, nodes=False)

# Загружаем данные зданий
gdf_buildings = ox.geometries_from_place(place_name, tags={'building': True})

# Загрузка тепловой карты
heatmap_path = "../out/AllPoint/itog.phantom.512.AllPoint.png"

heatmap_img = plt.imread(heatmap_path)

# Координаты углов тепловой карты (широта и долгота)
min_lon, max_lon = 82.875552, 83.02694899462323  # Минимальная и максимальная долгота (X-координаты)
min_lat, max_lat = 55.0066866, 55.0498451  # Минимальная и максимальная широта (Y-координаты)

# Функция для отрисовки карты с тепловой картой
def plot_map(roads=True, buildings=True, heatmap=False):
    fig, ax = plt.subplots(figsize=(12, 12))
    
    # Отрисовка дорог
    if roads:
        gdf_roads.plot(ax=ax, linewidth=1, edgecolor="black", alpha=0.7, label="Roads")
    
    # Отрисовка зданий
    if buildings:
        gdf_buildings.plot(ax=ax, facecolor="lightgray", edgecolor="gray", alpha=0.6, label="Buildings")
    
    # Наложение тепловой карты
    if heatmap:
        # extent определяет [min_lon, max_lon, min_lat, max_lat]
        ax.imshow(heatmap_img, extent=[min_lon, max_lon, min_lat, max_lat], alpha=0.8, aspect='auto')

    plt.title("Map of Novosibirsk with Heatmap" if heatmap else "Map of Novosibirsk")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend()
    plt.show()

# Отрисовка карты с дорогами, зданиями и тепловой картой
plot_map(roads=True, buildings=False, heatmap=True)
