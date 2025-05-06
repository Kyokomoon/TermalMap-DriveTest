import redis
from io import BytesIO
from PIL import Image
import os
output_dir = "out/"



def upload_tiles_to_redis(redis_host, redis_port, redis_password, output_dir):
    """Загружает все тайлы из папки в Redis."""
    # Подключение к Redis
    r = redis.StrictRedis(host=redis_host, port=redis_port, password=redis_password, decode_responses=False)
    try:
        # Подключение к Redis
        r = redis.StrictRedis(host=redis_host, port=redis_port, password=redis_password, decode_responses=False)
        if not r.ping():
            raise ConnectionError("Не удалось подключиться к Redis.")
        print("Соединение с Redis успешно установлено.")
    except Exception as e:
        print(f"Ошибка подключения к Redis: {e}")
        return
    i = 0
    m = []
    # Проход по всем файлам в папке `output_dir`
    for root, _, files in os.walk(output_dir):
        for file_name in files:
            if file_name.endswith(".png"):
                # Генерация пути и извлечение ключа
                file_path = os.path.join(root, file_name)
                parts = root.replace(output_dir, "").strip(os.sep).split(os.sep)
                if len(parts) < 4:
                    continue  # Пропускаем некорректные папки
                
                operator, technology, style, zoom, x = parts[:5]
                y = file_name.replace(".png", "")
                
                # Генерация ключа для Redis
                redis_key = f"{operator.lower()}.{technology}.{style}.{zoom}.{x}.{y}.png"
                
                # Чтение файла и конвертация в байты
                with open(file_path, "rb") as img_file:
                    img_bytes = img_file.read()
                try:
                    # Конвертация изображения в массив байт
                    with Image.open(file_path) as img:
                        byte_stream = BytesIO()
                        img.save(byte_stream, format="PNG")
                        image_bytes = byte_stream.getvalue()
                except Exception as e:
                    print(f"Ошибка обработки файла {file_path}: {e}")
                # Сохранение в Redis
                #r.set(redis_key, img_bytes)
             
                m.append(img_bytes)
                if img_bytes == image_bytes:
                    print("esss")
                i +=1
                print(f"\nЗагружен тайл: {redis_key}, sum = {i}")
                r.set(redis_key, img_bytes)


if __name__ == "__main__":
    redis_host = "109.172.114.128"
    redis_port = 6379
    redis_password = "PsFAZRPspatsD3PGbeL9Z4ejchqqyvkXlyYKRdEbf94="  # Укажите пароль, если требуется
    
    print("Загрузка тайлов в Redis...")
    upload_tiles_to_redis(redis_host, redis_port, redis_password, output_dir)
    print("Все тайлы успешно загружены!")