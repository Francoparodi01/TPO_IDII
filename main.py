from pymongo import MongoClient, UpdateOne 
from flask import Flask, request, jsonify, url_for, flash, jsonify, render_template, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity  # type: ignore
from datetime import datetime, timedelta
import redis  # type: ignore
from bson import ObjectId
from functools import wraps
import json


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
inventario= database.get_collection("inventario")
registro_inventario = database.get_collection("registroInventario")
facturas = database.get_collection("facturas")
historico = database.get_collection("historico")

# Registra un evento histórico en la colección "historico".
def log_event(event_type, description, data, user_id=None, session_id=None):

    try:
        log_entry = {
            "event_type": event_type,
            "description": description,
            "data": data,
            "user_id": str(user_id) if user_id else None,  # Convertir a string si existe
            "session_id": str(session_id) if session_id else None,  # Convertir a string si existe
            "timestamp": datetime.now()
        }
        historico.insert_one(log_entry)
    except Exception as e:
        print(f"Error en log_event: {e}")  # Log para depuración

def admin_required(func):
    @wraps(func)
    @jwt_required()
    def wrapper(*args, **kwargs):
        try:
            current_user_id = get_jwt_identity()
            user = users.find_one({"_id": ObjectId(current_user_id)}, {"rol": 1})  # Solo traemos "rol"

            if not user or user.get("rol") != "admin":
                return jsonify({"error": "Acceso denegado: Se requieren permisos de administrador"}), 403

            return func(*args, **kwargs)
        except Exception as e:
            return jsonify({"error": f"Error en verificación de administrador: {str(e)}"}), 500

    return wrapper


# ----------------------------------- Autenticación y sesiones -----------------------------------
@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()

        # Validar campos obligatorios
        required_fields = ["nombre", "email", "password", "pais", "direccion"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"El campo '{field}' es obligatorio"}), 400

        # Verificar si el email ya está registrado
        if users.find_one({"email": data["email"]}):
            return jsonify({"error": "El email ya está registrado"}), 400

        # Validar estructura de dirección
        if not isinstance(data["direccion"], list) or len(data["direccion"]) == 0:
            return jsonify({"error": "Debe proporcionar al menos una dirección válida"}), 400

        # Extraer dirección principal
        direccion = data["direccion"][0]
        required_address_fields = ["direccion", "altura", "codigo_postal", "telefono"]
        for field in required_address_fields:
            if field not in direccion or not direccion[field]:
                return jsonify({"error": f"La dirección debe contener '{field}' válido"}), 400

        # Hashear la contraseña
        hashed_password = generate_password_hash(data["password"])

        # Crear usuario con valores por defecto
        nuevo_usuario = {
            "nombre": data["nombre"],
            "email": data["email"],
            "password": hashed_password,
            "pais": data["pais"],
            "direccion": data["direccion"],
            "cantidad_facturas": 0,  # Valor por defecto
            "categoria": "Bronce",  # Valor por defecto
            "rol": "cliente",  # Valor por defecto
            "created_at": datetime.now()
        }

        # Insertar usuario
        user_id = users.insert_one(nuevo_usuario).inserted_id

        # Registrar evento en histórico
        log_event("signup", "Usuario registrado", {"email": data["email"]}, str(user_id))

        return jsonify({"message": "Usuario registrado exitosamente", "user_id": str(user_id)}), 201

    except Exception as e:
        return jsonify({"error": f"Error en el registro: {str(e)}"}), 500




# Obtiene un usuario de Redis si está en caché.
def get_user_from_cache(email):
    user_data = redis_client.get(f"cacheLogin:{email}")
    return json.loads(user_data) if user_data else None

# Guarda un usuario en Redis con expiración de 10 minutos.
def save_user_to_cache(email, user_data):
    redis_client.setex(f"cacheLogin:{email}", 600, json.dumps(user_data))


def serialize_user(user):
    """Convierte ObjectId en string para JSON."""
    user["_id"] = str(user["_id"])  # Convertir ObjectId a string
    return user

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        # Validar que email y contraseña sean proporcionados
        if not email or not password:
            return jsonify({"error": "Email y contraseña son requeridos"}), 400

        # Validar que el email tenga una estructura mínima (debe contener '@' y '.')
        if "@" not in email or "." not in email:
            return jsonify({"error": "Email no tiene formato válido"}), 400

        # Buscar usuario en MongoDB
        user = users.find_one({"email": email})
        if not user:
            return jsonify({"error": "Credenciales incorrectas"}), 401

        user["_id"] = str(user["_id"])  # Convertir ObjectId a string
        
        # Verificar contraseña
        if not check_password_hash(user["password"], password):
            return jsonify({"error": "Credenciales incorrectas"}), 401

        # Revisar si hay una sesión activa en Redis
        existing_session = redis_client.get(f"session:{email}")
        if existing_session:
            # Si ya existe una sesión activa, evitar que inicie sesión nuevamente
            return jsonify({"error": "Ya tienes una sesión activa. No puedes iniciar sesión nuevamente"}), 403
        
        # Crear nuevo token de acceso
        access_token = create_access_token(identity=user["_id"], expires_delta=timedelta(hours=1))

        # Guardar la nueva sesión en Redis
        redis_client.setex(f"session:{email}", 3600, json.dumps({"token": access_token, "user_id": user["_id"]}))

        # Guardar sesión en MongoDB
        session_id = sessions.insert_one({
            "user_id": user["_id"],  
            "email": email, 
            "token": access_token,
            "fecha_inicio": datetime.now(),
            "actividad": []
        }).inserted_id

        # Registrar evento en histórico
        log_event("login", "Usuario inició sesión", {"email": email}, user["_id"], str(session_id))

        return jsonify({"access_token": access_token}), 200

    except Exception as e:
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

    

def serialize_session(session):
    """Convierte ObjectId en string y prepara la respuesta JSON."""
    session["_id"] = str(session["_id"])
    session["user_id"] = str(session["user_id"])
    return session

#Esta función verifica si el usuario tiene una sesión activa, devuelve la actividad del usuario y el token de acceso. Primero consulta el token en redis y luego en mongo. 
@app.route('/session', methods=['GET'])
def session():
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "El user_id es requerido"}), 400

        # Buscar sesión en Redis primero
        session_data = redis_client.get(f"session:{user_id}")
        
        if session_data:
            session_data = json.loads(session_data)
        else:
            # Si no está en Redis, buscar en MongoDB
            session_data = sessions.find_one({"user_id": user_id}, {"_id": 0, "token": 1, "fecha_inicio": 1})
            if not session_data:
                return jsonify({"error": "Sesión no encontrada"}), 404

        # Obtener actividades desde MongoDB (historial)
        actividades = list(historico.find(
            {"user_id": user_id},
            {"_id": 0, "event_type": 1, "description": 1, "timestamp": 1}
        ))

        return jsonify({
            "token": session_data["token"],
            "fecha_inicio": session_data["fecha_inicio"],
            "actividad": actividades
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    
@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    try:
        # Obtener ID del usuario autenticado
        current_user_id = get_jwt_identity()
        
        if not ObjectId.is_valid(current_user_id):
            return jsonify({"error": "ID de usuario inválido"}), 400
        
        current_user_id = ObjectId(current_user_id)

        # Buscar sesión activa en MongoDB
        session_data = sessions.find_one({"user_id": str(current_user_id)})
        if not session_data:
            return jsonify({"error": "Sesión no encontrada"}), 404
        
        session_id = session_data["_id"]
        user_email = session_data.get("email")  # Obtener el email si está en la sesión

        # Buscar y eliminar la sesión en Redis
        redis_session_key = f"session:{user_email}" if user_email else f"session:{current_user_id}"
        redis_client.delete(redis_session_key)  # Primero eliminar en Redis

        # Eliminar sesión en MongoDB
        sessions.delete_one({"_id": session_id})

        # Registrar evento en histórico con session_id
        log_event("logout", "Usuario cerró sesión", {}, str(current_user_id), str(session_id))

        # Invalidar JWT (si se usa en cookies)
        response = jsonify({"message": "Sesión cerrada exitosamente"})
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500
#------------------------------------ Conexión con front ------------------------------------

# ----------------------------------- Usuarios y productos -----------------------------------

@app.route('/usuarios', methods=['GET'])
def obtener_usuarios():
    try:
        usuarios = list(users.find({}, {"password": 0}))  # Excluir el campo 'password'

        # Convertir ObjectId a string antes de enviar la respuesta
        for usuario in usuarios:
            usuario["_id"] = str(usuario["_id"])

        return jsonify(usuarios), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/usuario/<string:id>', methods=['GET'])
def obtener_usuario(id):
    try:
        if not ObjectId.is_valid(id):
            return jsonify({"error": "ID de usuario no válido"}), 400

        usuario = users.find_one({"_id": ObjectId(id)}, {"password": 0})  # Excluir el campo 'password'

        if not usuario:
            return jsonify({"error": "Usuario no encontrado"}), 404

        usuario["_id"] = str(usuario["_id"])  # Convertir ObjectId a string
        return jsonify(usuario), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/productos', methods=['GET'])
def obtener_productos():
    try:
        # Optimizar la consulta para traer solo los campos necesarios
        productos = list(inventario.find({}, {"_id": 1, "nombre": 1, "precio": 1, "stock": 1}))  
        
        # Convertir _id a string para evitar problemas de serialización
        for producto in productos:
            producto['_id'] = str(producto['_id'])

        return jsonify(productos), 200
    
    except Exception as e:
        print(f"Error obteniendo productos: {e}")  # Log para debug
        return jsonify({"error": "Error interno del servidor"}), 500
    

@app.route('/producto/<string:id>', methods=['GET'])
def obtener_detalle_producto(id):
    try:
        # Validar si el ID es un ObjectId válido
        try:
            obj_id = ObjectId(id)
        except:
            return jsonify({"error": "ID de producto no válido"}), 400

        # Buscar el producto con proyección para traer solo campos necesarios
        producto = inventario.find_one({"_id": obj_id}, {"_id": 1, "nombre": 1, "precio": 1, "stock": 1, "descripcion": 1, "valoraciones": 1,"etiquetas": 1})
        
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404
        
        # Convertir el _id a string
        producto['_id'] = str(producto['_id'])

        return jsonify(producto), 200

    except Exception as e:
        print(f"Error en obtener_detalle_producto: {e}")  # Log para depuración
        return jsonify({"error": "Error interno del servidor"}), 500
    

@app.route('/agregar_productos', methods=['POST'])
@admin_required  # Asegura que solo administradores puedan agregar productos
def agregar_productos():
    try:
        data = request.json
        
        # Si los datos recibidos son un array, procesarlos como múltiples productos
        if isinstance(data, list):
            productos = data
        # Si los datos son un objeto, procesarlos como un solo producto
        elif isinstance(data, dict):
            productos = [data]
        else:
            return jsonify({"error": "El cuerpo de la solicitud debe ser un objeto o un array de productos"}), 400
        
        for producto_data in productos:
            required_fields = ["nombre", "categoria", "descripcion", "precio", "stock"]

            # Verificar que los campos obligatorios existan y no estén vacíos
            for field in required_fields:
                if field not in producto_data or not producto_data[field]:
                    return jsonify({"error": f"Falta el campo obligatorio '{field}' para un producto"}), 400

            # Validar que precio y stock sean números
            if not isinstance(producto_data["precio"], (int, float)) or producto_data["precio"] < 0:
                return jsonify({"error": "El precio debe ser un número positivo"}), 400
            if not isinstance(producto_data["stock"], int) or producto_data["stock"] < 0:
                return jsonify({"error": "El stock debe ser un número entero positivo"}), 400

            # Asignar valores por defecto si faltan campos opcionales
            nuevo_producto = {
                "nombre": producto_data["nombre"],
                "categoria": producto_data["categoria"],
                "descripcion": producto_data["descripcion"],
                "precio": producto_data["precio"],
                "stock": producto_data["stock"],
                "imagenes": producto_data.get("imagenes", []),  # Lista vacía si no se proporcionan imágenes
                "valoraciones": producto_data.get("valoraciones", []),  # Lista vacía para valoraciones
                "etiquetas": producto_data.get("etiquetas", []),  # Lista vacía para etiquetas
                "fecha_agregado": datetime.now()  # Timestamp de creación
            }

            # Insertar producto en la base de datos
            resultado = inventario.insert_one(nuevo_producto)
            producto_id = str(resultado.inserted_id)

            # Registrar en el historial con información completa del producto
            log_event("add_product", "Producto agregado al catálogo", {
                "producto_id": producto_id,
                "nombre": producto_data["nombre"],
                "precio": producto_data["precio"],
                "stock": producto_data["stock"]
            }, get_jwt_identity())

        return jsonify({"mensaje": "Productos agregados exitosamente"}), 201

    except PermissionError:  # Manejo de errores por falta de permisos
        return jsonify({"error": "No tienes los permisos necesarios"}), 403
    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500



@app.route('/eliminar_producto/<string:id>', methods=['DELETE'])
@admin_required  # Asegura que solo administradores puedan eliminar productos
def eliminar_producto(id):
    try:
        current_user_id = get_jwt_identity()  # Obtener ID del usuario que elimina el producto

        # Validar si el ID es un ObjectId válido
        try:
            obj_id = ObjectId(id)
        except:
            return jsonify({"error": "ID de producto no válido"}), 400

        # Buscar el producto antes de eliminarlo
        producto = inventario.find_one({"_id": obj_id})
        if not producto:
            return jsonify({"error": "Producto no encontrado"}), 404

        # Guardar detalles del producto antes de eliminarlo para el histórico
        producto_eliminado = {
            "producto_id": str(producto["_id"]),
            "nombre": producto.get("nombre", "Desconocido"),
            "categoria": producto.get("categoria", "Desconocida"),
            "precio": producto.get("precio", "Desconocido"),
            "stock": producto.get("stock", "Desconocido")
        }

        # Eliminar el producto de la base de datos
        resultado = inventario.delete_one({"_id": obj_id})
        if resultado.deleted_count == 0:
            return jsonify({"error": "Error al eliminar el producto"}), 500

        # Registrar evento en `historico`
        log_event(
            "delete_product",
            f"Producto eliminado: {producto_eliminado['nombre']}",
            producto_eliminado,
            current_user_id
        )

        return jsonify({"mensaje": "Producto eliminado exitosamente"}), 200

    except PermissionError:  # Manejo de errores por falta de permisos
        return jsonify({"error": "No tienes los permisos necesarios"}), 403
    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

    
    
@app.route('/modificar_inventario', methods=['POST'])
@admin_required
def modificar_inventario():
    try:
        current_user_id = get_jwt_identity()
        modificaciones = request.get_json().get('modificaciones')

        if not isinstance(modificaciones, list) or not modificaciones:
            return jsonify({"error": "Debe enviar una lista de modificaciones válidas"}), 400

        cambios_realizados = []

        for mod in modificaciones:
            if not all(key in mod for key in ['producto_id', 'campo', 'nuevo_valor']):
                return jsonify({"error": "Cada modificación debe contener 'producto_id', 'campo' y 'nuevo_valor'"}), 400
            
            producto_id = mod['producto_id']
            campo = mod['campo']
            nuevo_valor = mod['nuevo_valor']

            # Validar si el ID del producto es válido
            try:
                obj_producto_id = ObjectId(producto_id)
            except:
                return jsonify({"error": f"ID de producto no válido: {producto_id}"}), 400

            # Buscar el producto en la base de datos
            producto = inventario.find_one({"_id": obj_producto_id}, {"nombre": 1, campo: 1})
            if not producto:
                return jsonify({"error": f"Producto con id {producto_id} no encontrado"}), 404

            nombre_producto = producto.get("nombre", "Desconocido")
            valor_anterior = producto.get(campo, "Campo no existía")

            # Modificar el campo en el inventario
            inventario.update_one({"_id": obj_producto_id}, {"$set": {campo: nuevo_valor}})

            # Registrar la modificación en la colección `registro_inventario`
            registro_inventario.insert_one({
                "user_id": ObjectId(current_user_id),
                "producto_id": obj_producto_id,
                "campo": campo,
                "valor_anterior": valor_anterior if valor_anterior is not None else "Campo no existía",
                "nuevo_valor": nuevo_valor,
                "fecha_modificacion": datetime.now()
            })

            # Registrar en `historico` con el nombre del producto
            log_event(
                "inventory_modification",
                f"Modificado el campo '{campo}' del producto '{nombre_producto}'",
                {"producto_id": producto_id, "campo": campo, "valor_anterior": valor_anterior, "nuevo_valor": nuevo_valor},
                current_user_id
            )

            cambios_realizados.append({
                "producto_id": producto_id,
                "nombre": nombre_producto,
                "campo": campo,
                "valor_anterior": valor_anterior,
                "nuevo_valor": nuevo_valor
            })

        return jsonify({"message": "Modificaciones registradas exitosamente", "cambios": cambios_realizados}), 200

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500




# ----------------------------------- Carrito de compras -----------------------------------
@app.route('/carrito', methods=['POST', 'DELETE'])
@jwt_required()
def manejar_carrito():
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()

        # Validar acción
        accion = data.get('accion')
        if accion not in ['agregar', 'eliminar']:
            return jsonify({"error": "Acción inválida. Usa 'agregar' o 'eliminar'"}), 400

        # Validar producto_id como ObjectId válido
        producto_id = data.get('producto_id')
        if not producto_id or not ObjectId.is_valid(producto_id):
            return jsonify({"error": "ID de producto no válido"}), 400

        # Clave del carrito en Redis
        carrito_id = f"carrito:{current_user_id}"

        if accion == 'agregar':
            # Validar cantidad
            try:
                cantidad = int(data.get('cantidad', 0))
                if cantidad <= 0:
                    return jsonify({"error": "La cantidad debe ser mayor a 0"}), 400
            except ValueError:
                return jsonify({"error": "Cantidad inválida"}), 400

            # Agregar producto al carrito
            redis_client.hincrby(carrito_id, producto_id, cantidad)

            # Restablecer el TTL a 1 hora cada vez que se modifique el carrito
            redis_client.expire(carrito_id, 3600)  # Seteamos el ttl en 1 hora en segundos

            log_event("cart_update", f"Producto {producto_id} agregado al carrito", {"cantidad": cantidad}, current_user_id)
            return jsonify({"message": f"{cantidad} unidades del producto agregadas al carrito"}), 200

        elif accion == 'eliminar':
            # Verificar existencia del producto en el carrito
            cantidad_actual = redis_client.hget(carrito_id, producto_id)
            if cantidad_actual is None:
                return jsonify({"error": "El producto no está en el carrito"}), 400

            # Convertir cantidad actual a entero
            cantidad_actual = int(cantidad_actual)
            try:
                cantidad_a_eliminar = int(data.get('cantidad', 0))
                if cantidad_a_eliminar <= 0:
                    return jsonify({"error": "La cantidad a eliminar debe ser mayor a 0"}), 400
            except ValueError:
                return jsonify({"error": "Cantidad inválida"}), 400

            if cantidad_a_eliminar >= cantidad_actual:
                # Eliminar completamente el producto si la cantidad a eliminar es mayor o igual
                redis_client.hdel(carrito_id, producto_id)
                log_event("cart_update", f"Producto {producto_id} eliminado completamente del carrito", {}, current_user_id)
                return jsonify({"message": "Producto eliminado completamente del carrito"}), 200
            else:
                # Reducir la cantidad en el carrito
                redis_client.hincrby(carrito_id, producto_id, -cantidad_a_eliminar)
                log_event("cart_update", f"Se eliminaron {cantidad_a_eliminar} unidades del producto {producto_id}", {}, current_user_id)
                return jsonify({"message": f"Se eliminaron {cantidad_a_eliminar} unidades del producto del carrito"}), 200

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500


@app.route('/ver_carrito', methods=['GET'])
@jwt_required()
def ver_carrito():
    try:
        current_user_id = get_jwt_identity()
        carrito_id = f"carrito:{current_user_id}"

        # Obtener los productos en el carrito desde Redis
        carrito = redis_client.hgetall(carrito_id)

        if not carrito:
            return jsonify({"message": "El carrito está vacío", "recomendaciones": []}), 200

        # Convertir datos de Redis a un diccionario con valores enteros
        carrito = {
            producto_id.decode('utf-8'): int(cantidad)
            for producto_id, cantidad in carrito.items()
        }

        # Validar que los IDs sean ObjectId válidos antes de la consulta a MongoDB
        producto_ids = [ObjectId(pid) for pid in carrito.keys() if ObjectId.is_valid(pid)]

        if not producto_ids:
            return jsonify({"error": "Error al obtener los productos"}), 400

        # Obtener detalles de los productos en el carrito
        productos_carrito = list(inventario.find(
            {"_id": {"$in": producto_ids}},
            {"nombre": 1, "precio": 1, "etiquetas": 1}  # Obtener etiquetas también
        ))

        # Construir la respuesta del carrito
        carrito_detalles = [
            {
                "producto_id": str(producto["_id"]),
                "nombre": producto.get("nombre", "Producto sin nombre"),
                "precio": producto.get("precio", 0),
                "cantidad": carrito.get(str(producto["_id"]), 0)
            }
            for producto in productos_carrito
        ]

        # Obtener todas las etiquetas de los productos en el carrito
        etiquetas_carrito = set()
        for producto in productos_carrito:
            etiquetas_carrito.update(producto.get("etiquetas", []))  # Extraer etiquetas

        # Buscar productos con etiquetas similares (excluyendo los que ya están en el carrito)
        recomendaciones = list(inventario.find(
            {
                "etiquetas": {"$in": list(etiquetas_carrito)},  # Coincidencia con etiquetas
                "_id": {"$nin": producto_ids}  # No incluir productos del carrito
            },
            {"nombre": 1, "precio": 1}  # Solo traer los datos necesarios
        ).limit(5))  # Limitar a 5 recomendaciones

        # Formatear las recomendaciones
        recomendaciones_formateadas = [
            {
                "producto_id": str(producto["_id"]),
                "nombre": producto.get("nombre", "Producto sin nombre"),
                "precio": producto.get("precio", 0)
            }
            for producto in recomendaciones
        ]

        return jsonify({"carrito": carrito_detalles, "recomendaciones": recomendaciones_formateadas}), 200

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500


# funciones para el manejo de pagos y facturas
def registrar_pago(user_id, factura_id, monto, forma_pago):
    try:
        # Validar que los IDs sean válidos
        factura_object_id = ObjectId(factura_id) if ObjectId.is_valid(factura_id) else None
        user_object_id = ObjectId(user_id) if ObjectId.is_valid(user_id) else None
        if not factura_object_id or not user_object_id:
            raise ValueError("Factura ID o Usuario ID inválidos")

        # Crear objeto de pago
        pago = {
            "user_id": user_object_id,
            "factura_id": factura_object_id,
            "monto": round(monto, 2),
            "forma_pago": forma_pago,
            "fecha_pago": datetime.now(),
            "estado": "completado"
        }

        pagos = database.get_collection("pagos")
        pagos.insert_one(pago)

        # Registrar en el histórico
        log_event("payment", f"Pago realizado por {user_id} con {forma_pago}", 
                  {"monto": monto, "factura_id": factura_id}, str(user_id))

    except Exception as e:
        print(f"Error al registrar el pago: {e}")  # Agregamos log en consola

        
@app.route('/carrito/comprar', methods=['POST'])
@jwt_required()
def confirmar_compra():
    try:
        current_user_id = get_jwt_identity()
        carrito_key = f"carrito:{current_user_id}"
        carrito_bytes = redis_client.hgetall(carrito_key)

        if not carrito_bytes:
            return jsonify({"error": "Carrito vacío"}), 400

        forma_pago = request.json.get('forma_pago')
        if not forma_pago:
            return jsonify({"error": "Debe seleccionar una forma de pago"}), 400

        total_factura = 0
        operaciones_stock = []
        productos_factura = []

        for producto_id_bytes, cantidad_bytes in carrito_bytes.items():
            producto_id = producto_id_bytes.decode("utf-8")
            cantidad = int(cantidad_bytes.decode("utf-8"))

            producto = inventario.find_one({"_id": ObjectId(producto_id)}, {"nombre": 1, "precio": 1, "stock": 1})
            if not producto:
                return jsonify({"error": f"Producto {producto_id} no encontrado"}), 400

            if producto["stock"] < cantidad:
                return jsonify({"error": f"Stock insuficiente para {producto['nombre']}"}), 400

            operaciones_stock.append(UpdateOne({"_id": ObjectId(producto_id)}, {"$inc": {"stock": -cantidad}}))

            productos_factura.append({
                "producto_id": str(producto["_id"]),
                "nombre": producto["nombre"],
                "cantidad": cantidad,
                "precio_unitario": producto["precio"],
                "subtotal": producto["precio"] * cantidad
            })
            total_factura += producto["precio"] * cantidad

        if operaciones_stock:
            inventario.bulk_write(operaciones_stock)

        user = users.find_one({"_id": ObjectId(current_user_id)})
        cantidad_facturas = user.get("cantidad_facturas", 0)

        descuento = 0
        if cantidad_facturas >= 10:
            descuento = total_factura * 0.20
        elif cantidad_facturas >= 5:
            descuento = total_factura * 0.10
        total_factura -= descuento

        categoria_usuario = calcular_categoria(cantidad_facturas)
        factura = generar_factura_from_data(current_user_id, productos_factura, descuento)
        factura["forma_pago"] = forma_pago

        factura_insertada = facturas.insert_one(factura)
        factura["_id"] = str(factura_insertada.inserted_id)

        registrar_pago(current_user_id, factura["_id"], factura["total_final"], forma_pago)
        redis_client.delete(carrito_key)
        log_event("purchase", "Compra confirmada y factura generada", {"factura_id": factura["_id"], "total": factura["total_final"], "forma_pago": forma_pago}, current_user_id)

        factura["productos"] = productos_factura

        users.update_one({"_id": ObjectId(current_user_id)}, {"$set": {"categoria": categoria_usuario}})
        users.update_one({"_id": ObjectId(current_user_id)}, {"$inc": {"cantidad_facturas": 1}})

        return jsonify({"message": "Compra confirmada y factura generada", "factura": factura}), 200
    except Exception as e:
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

@app.route('/carrito/eliminar', methods=['DELETE'])
@jwt_required()
def eliminar_carrito():
    try:
        # Obtener el ID del usuario actual desde el JWT
        current_user_id = get_jwt_identity()

        # Clave del carrito en Redis
        carrito_id = f"carrito:{current_user_id}"

        # Verificar si el carrito existe en Redis
        if not redis_client.exists(carrito_id):
            return jsonify({"error": "El carrito está vacío o no existe"}), 404

        # Obtener el carrito antes de eliminarlo
        carrito = redis_client.hgetall(carrito_id)

        # Almacenar el carrito en caché por 10 minutos antes de eliminarlo
        if carrito:
            redis_client.setex(f"carrito_eliminado:{current_user_id}", 600, str(carrito))  # 600 segundos = 10 minutos

        # Eliminar el carrito completo de Redis
        redis_client.delete(carrito_id)

        # Registrar el evento de eliminación
        log_event("cart_update", "Carrito eliminado completamente", {}, current_user_id)

        return jsonify({"message": "Carrito eliminado exitosamente y guardado en caché por 10 minutos"}), 200

    except Exception as e:
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@app.route('/restaurar_carrito', methods=['POST'])
@jwt_required()
def restaurar_carrito():
    try:
        current_user_id = get_jwt_identity()

        # Verificar si el carrito eliminado está en caché (en Redis)
        carrito_cache = redis_client.get(f"carrito_eliminado:{current_user_id}")

        if not carrito_cache:
            return jsonify({"error": "No se encuentra un carrito eliminado para este usuario en caché"}), 404

        # Restaurar el carrito desde Redis
        carrito = eval(carrito_cache)  # Convertir el string almacenado en un diccionario

        # Reinsertar el carrito en Redis
        redis_client.hmset(f"carrito:{current_user_id}", carrito)

        # Eliminar el carrito de Redis ya que se restauró
        redis_client.delete(f"carrito_eliminado:{current_user_id}")

        return jsonify({"mensaje": "Carrito restaurado con éxito"}), 200

    except Exception as e:
        return jsonify({"error": f"Error al restaurar el carrito: {str(e)}"}), 500



def generar_factura_from_data(current_user_id, productos_factura, descuento=0):
    try:
        user = users.find_one({"_id": ObjectId(current_user_id)}, {"nombre": 1, "pais": 1, "direccion": 1, "categoria": 1})
        if not user:
            raise Exception("Usuario no encontrado")

        direccion = user.get("direccion", [{}])[0]
        ubicacion_usuario = f"{user.get('pais', 'Desconocido')}, {direccion.get('direccion', 'Desconocida')} {direccion.get('altura', 'S/N')}, CP: {direccion.get('codigo_postal', '0000')}"

        factura = {
            "fecha_compra": datetime.now(),
            "user_id": str(ObjectId(current_user_id)),
            "nombre_usuario": user["nombre"],
            "ubicacion_usuario": ubicacion_usuario,
            "productos": productos_factura,
            "total": sum(p["subtotal"] for p in productos_factura),
            "iva": 0,
            "total_con_iva": 0,
            "descuento_categoria": 0,
            "total_final": 0
        }

        factura["iva"] = round(factura["total"] * 0.24, 2)
        factura["total_con_iva"] = round(factura["total"] + factura["iva"], 2)

        descuentos = {"plata": 0.05, "oro": 0.10, "bronce": 0.00}
        categoria_usuario = user.get("categoria", "bronce").lower()
        factura["descuento_categoria"] = round(factura["total_con_iva"] * descuentos.get(categoria_usuario, 0), 2)

        factura["total_final"] = round(factura["total_con_iva"] - descuento, 2)
        return factura
    except Exception as e:
        return {"error": f"Error en generación de factura: {str(e)}"}


@app.route('/facturas', methods=['GET'])
@jwt_required()
def obtener_facturas():
    try:
        # Buscar todas las facturas sin filtro por user_id
        facturas_lista = facturas.find().sort("fecha_compra", -1)

        # Verificar si se encontraron facturas
        facturas_lista = list(facturas_lista)
        if not facturas_lista:
            return jsonify({"message": "No se encontraron facturas"}), 404

        # Formatear los datos de las facturas
        facturas_lista = [
            {
                "_id": str(factura["_id"]),
                "fecha_compra": factura["fecha_compra"].isoformat(),
                "nombre_usuario": factura["nombre_usuario"],
                "ubicacion_usuario": factura["ubicacion_usuario"],
                "total": factura["total"],
                "iva": factura["iva"],
                "total_con_iva": factura["total_con_iva"],
                "descuento_categoria": factura["descuento_categoria"],
                "total_final": factura["total_final"],
                "productos": factura.get("productos", []),
                "forma_pago": factura.get("forma_pago")
            }
            for factura in facturas_lista
        ]

        return jsonify(facturas_lista), 200

    except Exception as e:
        return jsonify({"error": f"Error interno: {str(e)}"}), 500

@app.route('/facturas/<string:user_id>', methods=['GET'])
def obtener_facturas_por_usuario(user_id):
    try:
        # Verificar si el user_id es un ObjectId válido, pero si es un string válido no lo convierte
        if not ObjectId.is_valid(user_id):
            # En caso de que no sea un ObjectId válido, considerarlo como un string
            user_id = str(user_id)

        # Buscar las facturas del usuario en MongoDB
        facturas_usuario = list(facturas.find({"user_id": user_id}))  # Buscar usando el string de user_id

        if not facturas_usuario:
            return jsonify({"mensaje": "No se encontraron facturas para este usuario"}), 404

        # Convertir ObjectId a string en cada factura para que sea serializable en JSON
        for factura in facturas_usuario:
            factura["_id"] = str(factura["_id"])
            factura["user_id"] = str(factura["user_id"])  # Asegurarse de que user_id se convierte en string
            if "fecha_compra" in factura:
                factura["fecha_compra"] = factura["fecha_compra"].isoformat()  # Convertir fecha

        return jsonify(facturas_usuario), 200

    except Exception as e:
        return jsonify({"error": f"Error al obtener las facturas del usuario: {str(e)}"}), 500



def calcular_categoria(cantidad_facturas):
    try:
        if cantidad_facturas >=9:
            return "Oro"
        elif cantidad_facturas >= 4:
            return "Plata"
        else:
            return "Bronce"
    except Exception as e:
        print(f"Error al calcular la categoría: {e}")
        return "Bronce"


if __name__ == '__main__':
    app.run(debug=True)
