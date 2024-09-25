import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
%matplotlib
# Задаем место (Новосибирск)
place_name = "Novosibirsk, Russia"

# Загружаем данные дорог (граф дорог)
G = ox.graph_from_place(place_name, network_type='all')
# Преобразуем граф дорог в GeoDataFrame
gdf_roads = ox.graph_to_gdfs(G, nodes=False)

# Загружаем данные зданий
gdf_buildings = ox.geometries_from_place(place_name, tags={'building': True})

# Функция для отрисовки карт
def plot_map(roads=True, buildings=True):
    fig, ax = plt.subplots(figsize=(12, 12))
    
    if roads:
        gdf_roads.plot(ax=ax, linewidth=1, edgecolor="black", alpha=0.7, label="Roads")
        
    if buildings:
        gdf_buildings.plot(ax=ax, facecolor="lightgray", edgecolor="gray", alpha=0.6, label="Buildings")
        
    plt.title("Map of Novosibirsk")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend()
    plt.show()

# Отрисовка карты с дорогами и зданиями
plot_map(roads=True, buildings=True)

# Отрисовка только дорог
plot_map(roads=True, buildings=False)

# Отрисовка только зданий
plot_map(roads=False, buildings=True)
