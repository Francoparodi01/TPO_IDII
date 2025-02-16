from pymongo import MongoClient
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity # type: ignore
from datetime import datetime, timedelta
import redis # type: ignore
import pytz  # Importar pytz para manejar las zonas horarias
from bson import ObjectId

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


def calcular_categoria(user_id):
    try:
        # Contar la cantidad de pedidos del usuario en la base de datos
        cantidad_pedidos = pedidos.count_documents({"user_id": ObjectId(user_id)})

        # Definir la categoría según la cantidad de pedidos
        if cantidad_pedidos >= 9:
            return "Oro"
        elif cantidad_pedidos >= 4:
            return "Plata"
        else:
            return "Bronce"
    except Exception as e:
        print(f"Error al calcular la categoría: {e}")
        return "Bronce"  # Si hay un error, se mantiene como Bronce por defecto



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
            "categoria": "Bronce"  # Inicialmente lo asignamos como 'Bronce'
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
def agregar_producto():
    try:
        data = request.json  # Recibe los datos en formato JSON

        # Verifica que los datos requeridos están presentes
        required_fields = ["nombre", "categoria", "descripcion", "precio", "stock", "imagenes", "valoraciones", "etiquetas"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Falta el campo '{field}'"}), 400

        # Inserta el producto en la base de datos
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
        return jsonify({"error": str(e)}), 500

@app.route('/comprar', methods=['POST'])
@jwt_required()
def comprar():
    try:
        # Obtener el usuario autenticado desde el token JWT
        current_user_id = get_jwt_identity()
        
        # Obtener los detalles de la compra desde la solicitud
        compras = request.get_json().get('compras')

        # Validar que las compras tienen el formato esperado
        if not isinstance(compras, list) or any('producto_id' not in compra or 'cantidad' not in compra for compra in compras):
            return jsonify({"error": "Formato de compra inválido"}), 400

        # Guardar cada compra en MongoDB
        for compra in compras:
            pedidos.insert_one({
                "user_id": ObjectId(current_user_id),
                "producto_id": ObjectId(compra['producto_id']),
                "cantidad": compra['cantidad'],
                "fecha_compra": datetime.now(argentina_tz)
            })
        
        # Calcular la nueva categoría del usuario después de la compra
        nueva_categoria = calcular_categoria(current_user_id)

        # Actualizar la categoría en la base de datos
        users.update_one({"_id": ObjectId(current_user_id)}, {"$set": {"categoria": nueva_categoria}})

        return jsonify({"message": "Compras registradas y categoría actualizada"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/modificar_inventario', methods=['POST'])
@jwt_required()
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


@app.route('/generar_factura', methods=['POST'])
@jwt_required()
def generar_factura():
    try:
        # Obtener el usuario de la sesión activa (obteniendo el user_id del token JWT)
        current_user_id = get_jwt_identity()
        
        # Obtener los detalles del usuario
        user = users.find_one({"_id": ObjectId(current_user_id)})
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404

        # Obtener los detalles de los pedidos del usuario
        pedidos_usuario = list(pedidos.find({"user_id": ObjectId(current_user_id)}))
        if not pedidos_usuario:
            return jsonify({"error": "No se encontraron pedidos para el usuario"}), 404

        # Construir la factura
        factura = {
            "fecha_compra": datetime.now(argentina_tz),
            "nombre_usuario": user['nombre'],
            "ubicacion_usuario": user['pais'],
            "productos": [],
            "total": 0
        }

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
                "precio_unitario": float(producto['precio']),
                "total": cantidad * float(producto['precio'])
            }

            factura['productos'].append(producto_factura)
            factura['total'] += producto_factura['total']

        # Convertir ObjectId a string
        factura['_id'] = str(factura['_id']) if '_id' in factura else None

        for producto in factura['productos']:
            producto['producto_id'] = str(producto['producto_id']) if 'producto_id' in producto else None

        # Guardar la factura en la colección facturas
        facturas.insert_one(factura)

        return jsonify(factura), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
