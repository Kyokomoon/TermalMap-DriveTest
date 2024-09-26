import requests

def load_from_go():
    url = "http://78.24.222.170:8080/api/sockets/thermalmapdataall"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print("Ошибка при отправке запроса. Код ответа:", response.status_code)
        

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
    data=load_from_go()
   
    DATA={'ALL' : [] ,'Beeline' : [], 'Mts' : [], 'Yota' : [], 'Megafon' : []}
    for item in data:
        if float(item['latitude']) > 0 and float(item['longitude']) > 0:
            try:
                count = 0
                summ = 0
                for point in item['lte']:
                    if int(point["rsrp"]) <= -60 and int(point["rsrp"]) >= -125:
                        summ+=int(point["rsrp"])
                        count+=1
                rsrp = int(summ/count)
                if count>0:
                    DATA['ALL'].append([rsrp, float(item['latitude']), float(item['longitude'])])
                    DATA[item['operator']].append([rsrp, float(item['latitude']), float(item['longitude'])])
            except:
                print("пустое значение")
    max_LAT, max_LON, min_LAT, min_LON = max_min_latlon(DATA['ALL']) 
    return DATA, max_LAT, max_LON, min_LAT, min_LON