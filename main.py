from pymongo import MongoClient
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity # type: ignore
from datetime import datetime, timedelta
import redis # type: ignore
import pytz  # Importar pytz para manejar las zonas horarias
from bson import ObjectId
from functools import wraps
from datetime import datetime
import uuid


# Configuración de la base de datos y servidor
uri = "mongodb+srv://rgarabano:0wJj7eJmF2cnMNwT@tpouade.yhucf.mongodb.net/"
app = Flask(__name__)

# Configuración de JWT
app.config['JWT_SECRET_KEY'] = 'mi_clave'  # Cambiar por una clave secreta más robusta
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)  # Duración del token

redis_host = 'redis-10400.c308.sa-east-1-1.ec2.redns.redis-cloud.com'
redis_port = 10400
redis_db = 0
redis_password = 'tNPV4XOHe0nwmhZMfI6sClC5DN406dJW'
# Configuración de Redis
redis_client = redis.StrictRedis(host=redis_host, port=redis_port, db=redis_db, password=redis_password)

redis_client.execute_command("AUTH", redis_password)

# Inicialización de JWT
jwt = JWTManager(app)

# Conexión a MongoDB
client = MongoClient(uri)
database = client.get_database("ecomerce")
users = database.get_collection("usuarios")
sessions = database.get_collection("sesiones")
pedidos = database.get_collection("pedidos")
inventario= database.get_collection("inventario")
registro_inventario = database.get_collection("registroInventario")
facturas = database.get_collection("facturas")

# Definir zona horaria de Argentina
argentina_tz = pytz.timezone('America/Argentina/Buenos_Aires')

def admin_required(func):
    @wraps(func)
    @jwt_required()
    def wrapper(*args, **kwargs):
        current_user_id = get_jwt_identity()

        # Buscar al usuario en la base de datos
        user = users.find_one({"_id": ObjectId(current_user_id)})

        # Verificar si el usuario existe y tiene el rol "admin"
        if not user or user.get("rol") != "admin":
            return jsonify({"error": "Acceso denegado, permisos insuficientes"}), 403
        
        return func(*args, **kwargs)
    
    return wrapper

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        nombre = data['nombre']
        email = data['email']
        pais = data['pais']
        password = data['password']
        
        # Obtener la dirección como un array
        direccion = [{
            "direccion": data['direccion'],
            "altura": data['altura'],
            "codigo_postal": data['codigo_postal'],
            "telefono": data['telefono']
        }]
        
        # Verificar si el usuario ya existe
        if users.find_one({"email": email}):
            return jsonify({"error": "El usuario ya existe"}), 400
        
        # Encriptar la contraseña
        hashed_password = generate_password_hash(password)
        
        # Guardar el usuario en la base de datos
        nuevo_usuario = users.insert_one({
            "nombre": nombre,
            "email": email,
            "password": hashed_password,
            "pais": pais,
            "direccion": direccion,
            "cantidad_facturas": 0,
            "categoria": "Bronce", # Inicialmente lo asignamos como 'Bronce'
            "rol": "cliente"
        })
        
        # Obtener el user_id del nuevo usuario
        user_id = nuevo_usuario.inserted_id
        
        # Calcular y actualizar la categoría del usuario
        categoria = calcular_categoria(user_id)
        
        # Actualizar la categoría en la base de datos
        users.update_one({"_id": user_id}, {"$set": {"categoria": categoria}})
        
        return jsonify({"message": "Usuario registrado exitosamente"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data['email']
        password = data['password']
        
        # Buscar al usuario en la base de datos
        user = users.find_one({"email": email})
        
        if not user or not check_password_hash(user['password'], password):
            return jsonify({"error": "Credenciales incorrectas"}), 401
        
        # Crear un token de acceso
        access_token = create_access_token(identity=str(user['_id']))

        # Guardar el token en Redis, con expiración de 1 hora
        redis_client.set(f"session:{email}", access_token, ex=3600)

        # Guardar sesión en la base de datos MongoDB
        sessions.insert_one({
            "user_id": user['_id'],
            "token": access_token,
            "fecha_inicio": datetime.now(argentina_tz),  # Usar hora en Argentina
            "actividad": []
        })
        
        return jsonify({"access_token": access_token}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/session', methods=['GET'])
def session():
    try:
        # Obtener el user_id de la solicitud
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "El user_id es requerido"}), 400

        # Convertir el user_id a ObjectId si es necesario
        if not ObjectId.is_valid(user_id):
            return jsonify({"error": "El user_id no es válido"}), 400

        # Buscar la sesión usando el user_id
        session_data = sessions.find_one({"user_id": ObjectId(user_id)})

        if not session_data:
            return jsonify({"error": "Sesión no encontrada"}), 404

        return jsonify({
            "token": session_data["token"],
            "fecha_inicio": session_data["fecha_inicio"],
            "actividad": session_data["actividad"]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        current_user_id = get_jwt_identity()
        print(f"Usuario identificado: {current_user_id}")  # 🔍 Verifica el ID extraído del token
        
        # Convertir el user_id a ObjectId si no lo es
        try:
            current_user_id = ObjectId(current_user_id)
        except:
            return jsonify({"error": "ID de usuario inválido"}), 400
        
        # Buscar la sesión en MongoDB
        session_data = sessions.find_one({"user_id": current_user_id})
        
        if session_data:
            sessions.delete_one({"user_id": current_user_id})
            redis_client.delete(f"session:{current_user_id}")
            return jsonify({"message": "Sesión cerrada exitosamente"}), 200
        else:
            return jsonify({"error": "Sesión no encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/action', methods=['POST'])
@jwt_required()
def record_activity():
    try:
        # Obtener el usuario de la sesión activa (obteniendo el user_id del token JWT)
        current_user_id = get_jwt_identity()
        
        # Buscar la sesión usando el user_id
        session_data = sessions.find_one({"user_id": ObjectId(current_user_id)})

        if session_data:
            # Registrar una nueva acción
            action = request.get_json().get('action')
            session_data['actividad'].append({
                "action": action,
                "timestamp": datetime.now(argentina_tz)  # Usar hora en Argentina
            })
            
            # Actualizar la sesión en MongoDB
            sessions.update_one(
                {"user_id": ObjectId(current_user_id)},
                {"$set": {"actividad": session_data['actividad']}}
            )
            
            return jsonify({"message": "Actividad registrada exitosamente"}), 200
        else:
            return jsonify({"error": "Sesión no encontrada"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/agregar_productos', methods=['POST'])
@admin_required
def agregar_producto():
    try:
        data = request.json
        required_fields = ["nombre", "categoria", "descripcion", "precio", "stock", "imagenes", "valoraciones", "etiquetas"]
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Falta el campo '{field}'"}), 400

        nuevo_producto = {
            "nombre": data["nombre"],
            "categoria": data["categoria"],
            "descripcion": data["descripcion"],
            "precio": data["precio"],
            "stock": data["stock"],
            "imagenes": data["imagenes"],
            "valoraciones": data["valoraciones"],
            "etiquetas": data["etiquetas"]
        }
        resultado = inventario.insert_one(nuevo_producto)

        return jsonify({"mensaje": "Producto agregado exitosamente", "id": str(resultado.inserted_id)}), 201
    except Exception as e:
        return jsonify({"error": "No tenes los permisos necesarios"}), 500

@app.route('/comprar', methods=['POST'])
@jwt_required()
def comprar():
    try:
        # Obtener el usuario de la sesión activa (obteniendo el user_id del token JWT)
        current_user_id = get_jwt_identity()

        #Obtener los detalles de la compra desde la solicitud
        compras = request.get_json().get('compras')

        # Validar que las compras tienen el formato esperado
        if not isinstance(compras, list) or any('producto_id' not in compra or 'cantidad' not in compra for compra in compras):
            return jsonify({"error": "Formato de compra inválido"}), 400

        for compra in compras:
            producto_id = compra['producto_id']
            cantidad = int(compra['cantidad'])

            # Verificar el stock del producto
            producto = inventario.find_one({"_id": ObjectId(producto_id)})
            if not producto:
                return jsonify({"error": f"Producto con id {producto_id} no encontrado"}), 404

            stock_actual = int(producto.get('stock', 0))
            if stock_actual < cantidad:
                return jsonify({"error": f"No hay suficiente stock para el producto {producto['nombre']}"}), 400

            # Registrar la compra en Redis
            compra_id = f"user:{current_user_id}:compra:{producto_id}"
            redis_client.hmset(compra_id, {'producto_id': producto_id, 'cantidad': cantidad})

            # Transferir la compra a MongoDB y reducir el stock en la colección inventario
            pedidos.insert_one({
                "user_id": ObjectId(current_user_id),
                "producto_id": ObjectId(producto_id),
                "cantidad": cantidad,
                "fecha_compra": datetime.now(argentina_tz)
            })

            inventario.update_one(
                {"_id": ObjectId(producto_id)},
                {"$inc": {"stock": -cantidad}}
            )

        return jsonify({"message": "Compras registradas exitosamente"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/productos', methods=['GET'])
def obtener_productos():
    try:
        productos = list(inventario.find())
        for producto in productos:
            producto['_id'] = str(producto['_id'])

        return jsonify(productos), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/modificar_inventario', methods=['POST'])
@admin_required
def modificar_inventario():
    try:
        # Obtener el usuario de la sesión activa (obteniendo el user_id del token JWT)
        current_user_id = get_jwt_identity()
        
        # Obtener los detalles de la modificación desde la solicitud
        modificaciones = request.get_json().get('modificaciones')

        # Validar que las modificaciones tienen el formato esperado
        if not isinstance(modificaciones, list) or any('producto_id' not in mod or 'campo' not in mod or 'nuevo_valor' not in mod for mod in modificaciones):
            return jsonify({"error": "Formato de modificación inválido"}), 400

        # Realizar las modificaciones en la colección inventario y registrar en registroInventario
        for mod in modificaciones:
            producto_id = mod['producto_id']
            campo = mod['campo']
            nuevo_valor = mod['nuevo_valor']

            # Obtener el valor actual del campo antes de actualizarlo
            producto = inventario.find_one({"_id": ObjectId(producto_id)})
            if not producto:
                return jsonify({"error": f"Producto con id {producto_id} no encontrado"}), 404

            valor_anterior = producto.get(campo, None)

            # Actualizar el inventario
            inventario.update_one({"_id": ObjectId(producto_id)}, {"$set": {campo: nuevo_valor}})
            
            # Registrar el cambio en registroInventario
            registro_inventario.insert_one({
                "user_id": ObjectId(current_user_id),
                "producto_id": ObjectId(producto_id),
                "campo": campo,
                "valor_anterior": valor_anterior,
                "nuevo_valor": nuevo_valor,
                "fecha_modificacion": datetime.now(argentina_tz)
            })
        
        return jsonify({"message": "Modificaciones registradas exitosamente"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def calcular_categoria(cantidad_facturas):
    try:
        # Definir la categoría según la cantidad de facturas
        if cantidad_facturas >= 9:
            return "Oro"
        elif cantidad_facturas >= 4:
            return "Plata"
        else:
            return "Bronce"
    except Exception as e:
        print(f"Error al calcular la categoría: {e}")
        return "Bronce"  # Si hay un error, se mantiene como Bronce por defecto

#@app.route('/generar_factura', methods=['POST'])
#@jwt_required()
#def generar_factura():
#    try:
#        # Obtener el usuario de la sesión activa (obteniendo el user_id del token JWT)
#        current_user_id = get_jwt_identity()
#        
#        # Obtener los detalles del usuario
#        user = users.find_one({"_id": ObjectId(current_user_id)})
#        if not user:
#            return jsonify({"error": "Usuario no encontrado"}), 404
#
#        # Obtener los detalles de los pedidos del usuario
#        pedidos_usuario = list(pedidos.find({"user_id": ObjectId(current_user_id)}))
#        if not pedidos_usuario:
#            return jsonify({"error": "No se encontraron pedidos para el usuario"}), 404
#
#        # Construir la dirección del usuario
#        direccion = user['direccion'][0]
#        ubicacion_usuario = f"{user['pais']}, {direccion['direccion']} {direccion['altura']}, CP: {direccion['codigo_postal']}"
#
#        # Construir la factura
#        factura = {
#            "fecha_compra": datetime.now(argentina_tz),
#            "nombre_usuario": user['nombre'],
#            "ubicacion_usuario": ubicacion_usuario,
#            "productos": [],
#            "total": 0,
#            "iva": 0,
#            "total_con_iva": 0,
#            "descuento_categoria": 0,
#            "total_final": 0
#        }
#
#        for pedido in pedidos_usuario:
#            producto_id = pedido['producto_id']
#            cantidad = int(pedido['cantidad'])
#            
#            # Obtener los detalles del producto
#            producto = inventario.find_one({"_id": ObjectId(producto_id)})
#            if not producto:
#                continue  # Si el producto no se encuentra, pasar al siguiente
#            
#            producto_factura = {
#                "nombre": producto['nombre'],
#                "descripcion": producto['descripcion'],
#                "cantidad": cantidad,
#                "precio_unitario": round(float(producto['precio']), 2),
#                "total": round(cantidad * float(producto['precio']), 2)
#            }
#
#            factura['productos'].append(producto_factura)
#            factura['total'] += producto_factura['total']
#
#        # Redondear el total a dos decimales
#        factura['total'] = round(factura['total'], 2)
#
#        # Calcular el IVA (24% del total)
#        factura['iva'] = round(factura['total'] * 0.24, 2)
#        factura['total_con_iva'] = round(factura['total'] + factura['iva'], 2)
#
#        # Calcular el descuento según la categoría del usuario
#        categoria = user.get('categoria', 'bronce').lower()  # Por defecto, 'bronce'
#        if categoria == 'plata':
#            factura['descuento_categoria'] = round(factura['total_con_iva'] * 0.05, 2)
#        elif categoria == 'oro':
#            factura['descuento_categoria'] = round(factura['total_con_iva'] * 0.10, 2)
#
#        # Calcular el total final con el descuento aplicado
#        factura['total_final'] = round(factura['total_con_iva'] - factura['descuento_categoria'], 2)
#
#        # Guardar la factura en la colección facturas
#        facturas.insert_one(factura)
#
#        # Actualizar la cantidad de facturas del usuario
#        users.update_one({"_id": ObjectId(current_user_id)}, {"$inc": {"cantidad_facturas": 1}})
#
#        # Obtener la nueva cantidad de facturas del usuario
#        user = users.find_one({"_id": ObjectId(current_user_id)})
#
#        # Calcular la nueva categoría del usuario
#        nueva_categoria = calcular_categoria(user["cantidad_facturas"])
#
#        # Actualizar la categoría del usuario en la base de datos
#        users.update_one({"_id": ObjectId(current_user_id)}, {"$set": {"categoria": nueva_categoria}})
#
#        # Convertir ObjectId a string para la respuesta
#        factura['_id'] = str(factura['_id']) if '_id' in factura else None
#
#        return jsonify(factura), 200
#    except Exception as e:
#        return jsonify({"error": str(e)}), 500
# 

# ----------------------------------- Carrito de compras -----------------------------------

@app.route('/carrito/agregar', methods=['POST'])
@jwt_required()
def agregar_al_carrito():
    try:
        current_user_id = get_jwt_identity()
        data = request.json
        producto_id = data.get("producto_id")
        cantidad = int(data.get("cantidad", 1))

        if not ObjectId.is_valid(producto_id):
            return jsonify({"error": "ID de producto inválido"}), 400
        
        # Obtener el stock del producto
        producto = inventario.find_one({"_id": ObjectId(producto_id)})
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
        
        # Guardar en Redis (como hash)
        carrito_key = f"carrito:{current_user_id}"
        redis_client.hincrby(carrito_key, producto_id, cantidad)

        return jsonify({"message": "Producto agregado al carrito"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# Ver carrito de compras
@app.route('/carrito', methods=['GET'])
@jwt_required()
def ver_carrito():
    try:
        current_user_id = get_jwt_identity()
        carrito_key = f"carrito:{current_user_id}"
        
        # Obtener carrito de Redis (las claves y valores están en bytes)
        carrito_bytes = redis_client.hgetall(carrito_key)
        
        if not carrito_bytes:
            return jsonify({"message": "Carrito vacío"}), 200

        productos_en_carrito = []
        total = 0

        for producto_id_bytes, cantidad_bytes in carrito_bytes.items():
            producto_id = producto_id_bytes.decode("utf-8")  # Decodificar el ID
            cantidad = int(cantidad_bytes.decode("utf-8"))  # Decodificar la cantidad
            
            producto = inventario.find_one({"_id": ObjectId(producto_id)})
            if not producto:
                continue
            
            total += producto["precio"] * cantidad
            productos_en_carrito.append({
                "producto_id": producto_id,
                "nombre": producto["nombre"],
                "precio_unitario": producto["precio"],
                "cantidad": cantidad,
                "total": producto["precio"] * cantidad
            })

        return jsonify({"productos": productos_en_carrito, "total": total}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Eliminar producto del carrito
@app.route('/carrito/eliminar', methods=['POST'])
@jwt_required()
def eliminar_del_carrito():
    try:
        current_user_id = get_jwt_identity()
        data = request.json
        producto_id = data.get("producto_id")

        carrito_key = f"carrito:{current_user_id}"

        if not redis_client.hexists(carrito_key, producto_id):
            return jsonify({"error": "Producto no está en el carrito"}), 400
        
        redis_client.hdel(carrito_key, producto_id)
        return jsonify({"message": "Producto eliminado del carrito"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Confirmar compra
@app.route('/carrito/comprar', methods=['POST'])
@jwt_required()
def confirmar_compra():
    try:
        current_user_id = get_jwt_identity()
        carrito_key = f"carrito:{current_user_id}"
        carrito_bytes = redis_client.hgetall(carrito_key)

        if not carrito_bytes:
            return jsonify({"error": "Carrito vacío"}), 400

        pedidos_guardados = []
        total_factura = 0

        # Guardar los pedidos y calcular el total de la factura
        for producto_id_bytes, cantidad_bytes in carrito_bytes.items():
            producto_id = producto_id_bytes.decode("utf-8")
            cantidad = int(cantidad_bytes.decode("utf-8"))

            producto = inventario.find_one({"_id": ObjectId(producto_id)})

            if not producto or producto["stock"] < cantidad:
                return jsonify({"error": f"Stock insuficiente para {producto['nombre']}"}), 400

            # Restar stock en MongoDB
            inventario.update_one(
                {"_id": ObjectId(producto_id)},
                {"$inc": {"stock": -cantidad}}
            )

            # Guardar pedido en MongoDB
            pedido = {
                "user_id": ObjectId(current_user_id),
                "producto_id": ObjectId(producto_id),
                "cantidad": cantidad,
                "precio_unitario": producto["precio"],
                "subtotal": producto["precio"] * cantidad,
                "fecha_compra": datetime.now()
            }
            pedidos.insert_one(pedido)

            # Acumular total de factura
            total_factura += pedido["subtotal"]

            # Convertir los ObjectId a string para la respuesta
            pedido["user_id"] = str(pedido["user_id"])
            pedido["producto_id"] = str(pedido["producto_id"])
            pedidos_guardados.append(pedido)

        # Generar la factura con los pedidos
        factura = generar_factura_from_data(current_user_id, pedidos_guardados)

        # Guardar la factura en la colección de facturas
        factura_insertada = facturas.insert_one(factura)

        # Obtener el _id de la factura insertada
        factura['_id'] = str(factura_insertada.inserted_id)

        # Vaciar carrito en Redis
        redis_client.delete(carrito_key)

        # Retornar la factura generada como parte de la respuesta
        return jsonify({
            "message": "Compra confirmada y factura generada",
            "factura": factura
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def generar_factura_from_data(current_user_id, pedidos_usuario):
    try:
        # Obtener el usuario de la sesión activa
        user = users.find_one({"_id": ObjectId(current_user_id)})
        if not user:
            raise Exception("Usuario no encontrado")

        # Construir la dirección del usuario
        direccion = user['direccion'][0]
        ubicacion_usuario = f"{user['pais']}, {direccion['direccion']} {direccion['altura']}, CP: {direccion['codigo_postal']}"

        # Construir la factura
        factura = {
            "fecha_compra": datetime.now(),
            "nombre_usuario": user['nombre'],
            "ubicacion_usuario": ubicacion_usuario,
            "productos": [],
            "total": 0,
            "iva": 0,
            "total_con_iva": 0,
            "descuento_categoria": 0,
            "total_final": 0
        }

        # Iterar sobre los pedidos y completar la factura
        for pedido in pedidos_usuario:
            producto_id = pedido['producto_id']
            cantidad = int(pedido['cantidad'])

            # Obtener los detalles del producto
            producto = inventario.find_one({"_id": ObjectId(producto_id)})
            if not producto:
                continue  # Si el producto no se encuentra, pasar al siguiente

            producto_factura = {
                "nombre": producto['nombre'],
                "descripcion": producto['descripcion'],
                "cantidad": cantidad,
                "precio_unitario": round(float(producto['precio']), 2),
                "total": round(cantidad * float(producto['precio']), 2)
            }

            factura['productos'].append(producto_factura)
            factura['total'] += producto_factura['total']

        # Redondear el total a dos decimales
        factura['total'] = round(factura['total'], 2)

        # Calcular el IVA (24% del total)
        factura['iva'] = round(factura['total'] * 0.24, 2)
        factura['total_con_iva'] = round(factura['total'] + factura['iva'], 2)

        # Calcular el descuento según la categoría del usuario
        categoria = user.get('categoria', 'bronce').lower()
        if categoria == 'plata':
            factura['descuento_categoria'] = round(factura['total_con_iva'] * 0.05, 2)
        elif categoria == 'oro':
            factura['descuento_categoria'] = round(factura['total_con_iva'] * 0.10, 2)

        # Calcular el total final con el descuento aplicado
        factura['total_final'] = round(factura['total_con_iva'] - factura['descuento_categoria'], 2)
        
        return factura

    except Exception as e:
        return {"error": str(e)}


if __name__ == '__main__':
    app.run(debug=True)
