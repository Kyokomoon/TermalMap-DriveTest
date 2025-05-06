import requests
import psycopg2
MAX_LAT = 55.150
MIN_LAT = 54.800
MAX_LON = 83.100
MIN_LON = 82.700
MAX_X = 256
MAX_Y = 256
def load_from_go():
    url = "http://78.24.222.170:8080/api/sockets/thermalmapdataall"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print("Ошибка при отправке запроса. Код ответа:", response.status_code)
        

def load_from_postgress():
    # Параметры подключения к базе данных
    db_config = {
        "dbname": "thermal_map_data_legacy",           # Имя базы данных
        "user": "postgres",             # Имя пользователя
        "password": "aqDAzZgBybD5AS/PxEBNFia4Xvx0wWxDeLr0pwGIihY=",  # Пароль
        "host": "109.172.114.128",      # IP адрес
        "port": "5432"                  # Порт
    }
    try:
        # Подключение к базе данных
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()
        query = """
        SELECT type, registered, mcc, mnc,ci, pci,earfcn,rsrp,rssi,rsrq,rssnr,cqi, time, latitude, longitude, operator
        FROM lte_data 
        JOIN message2 ON message2.id = lte_data.request_id
        WHERE registered = true;
        """
        cursor.execute(query)
        # Выполнение SQL-запроса
        cursor.execute(query)  # Замените на фактическое имя таблицы
    
        # Получение данных
        rows = cursor.fetchall()
        return rows
    
    except Exception as e:
        print(f"Ошибка при подключении к базе данных: {e}")
    
    finally:
        # Закрытие курсора и подключения
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    return 0


def max_min_latlon(data):
    max_LAT = 0.0
    max_LON = 0.0
    min_LAT = 999999.0
    min_LON = 999999.0
    for item in data:
        lat = float(item[1])
        lon = float(item[2])
        if lat > max_LAT:
            max_LAT = lat
        if lat < min_LAT:
            min_LAT = lat
        if lon > max_LON:
            max_LON = lon
        if lon < min_LON:
            min_LON = lon
    return max_LAT, max_LON, min_LAT, min_LON 

def create_point_for_draw():
    points = []
    data = load_from_postgress()
    for item in data:
        try:
            if int(item[7]) <= -60 and int(item[7]) >= -120 and (float(item[13]) >= MIN_LAT and float(item[13]) <= MAX_LAT and float(item[14]) >= MIN_LON and float(item[14]) <= MAX_LON):
                points.append([int(item[7]), float(item[13]), float(item[14]),int(item[9]), int(item[10]), int(item[5]), int(item[5]) % 3, int(item[5]) % 6,item[-1]])
        except:
            pass
    return points
