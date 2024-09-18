import requests

def load_from_go(url):
    
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        return data
    else:
        print("Ошибка при отправке запроса. Код ответа:", response.status_code)

load_url = "http://78.24.222.170:8080/api/sockets/thermalmapdataall"

load_from_go(load_url)