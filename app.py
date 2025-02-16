import redis # type: ignore
from pymongo import MongoClient

# Configurar la conexión a Redis
redis_host = 'redis-10400.c308.sa-east-1-1.ec2.redns.redis-cloud.com'
redis_port = 10400
redis_db = 0
redis_password = 'tNPV4XOHe0nwmhZMfI6sClC5DN406dJW'
r = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)

# Autenticarse en Redis
r.execute_command("AUTH", redis_password)

# Configurar la conexión a MongoDB utilizando una URL de conexión
mongo_url = 'mongodb+srv://rgarabano:0wJj7eJmF2cnMNwT@tpouade.yhucf.mongodb.net/'
client = MongoClient(mongo_url)
db = client.get_database("ecomerce")  # Utiliza la base de datos especificada en la URL
collection = db['usuarios']  # Utiliza la colección 'usuarios'

# Insertar un valor de prueba en Redis
clave = 'prueba_clave'
valor = 'prueba_valor'
r.set(clave, valor)

# Recuperar el valor desde Redis
valor_recuperado = r.get(clave)

if valor_recuperado:
    # Si el valor existe en Redis, insertamos los datos en MongoDB
    documento = {'clave': clave, 'valor': valor_recuperado.decode('utf-8')}
    collection.insert_one(documento)
    print('Datos insertados en MongoDB')
else:
    # Si no se encuentra la clave en Redis, muestra el mensaje de error
    print('Clave no encontrada en Redis')
