Notas de secuencia de como utilizar postman para probar todas las cosas del script

Paso 1: Configurar Postman
- Abre Postman.
- Crea una nueva colección para organizar tus pruebas. Puedes llamarla, por ejemplo, "Pruebas API e-commerce".


Paso 2: Registro de Usuario
a. Crear una nueva solicitud:
 	- Método: POST

	- URL: http://localhost:5000/register

	- Pestaña "Body": Selecciona "raw" y elige "JSON" en el menú desplegable.

	- Cuerpo de la solicitud (ejemplo):
		{
		    "nombre": "Juan Pérez",
		    "email": "juan.perez@email.com",
		    "password": "Segura123!",
		    "pais": "Argentina",
		    "direccion": [
		        {
		            "direccion": "Av. Siempre Viva",
		            "altura": "742",
		            "codigo_postal": "1414",
		            "telefono": "1122334455"
 		       }
		    ]
		}


b. Enviar la solicitud y verifica que recibas una respuesta con el mensaje "Usuario registrado exitosamente". El mismo debe Replicar en MongoDB en la colección de "usuarios"



Paso 3: Iniciar Sesión
a. Crear una nueva solicitud:

	- Método: POST

	- URL: http://localhost:5000/login

	- Pestaña "Body": Selecciona "raw" y elige "JSON" en el menú desplegable.

	- Cuerpo de la solicitud (ejemplo):
		{
		  "email": "diego.ramirez@example.com",
		  "password": "mi_contraseña_segura"
		}

b. Enviar la solicitud y verifica que recibas un token de acceso (access_token).

c. Guardar el token de la respuesta para usarlo en la siguiente solicitud.

Es importante que el mail y contraseña del usuario sean de un usuario que se haya registrado anteriormente. Esta logeo se registrara en Redis y se mantiene un registro de inicio de sesión en histórico de MongoDB


Paso 4: Agregar/quitar productos del carrito
a. Crear una nueva solicitud:

	- Método: POST

	- URL: http://localhost:5000/carrito

	- Pestaña "Headers": Añade un nuevo encabezado con el nombre Authorization y el valor Bearer {access_token} (reemplaza {access_token} con el token obtenido en el paso anterior).

	- Pestaña "Body": Selecciona "raw" y elige "JSON" en el menú desplegable.

	- Cuerpo de la solicitud (ejemplo):
		{
		    "accion": "agregar",
		    "producto_id": "67b0e1a5173fcdd6b420ae3c",
		    "cantidad": 2
		}

	- O si se quiere eliminar un producto o una cantidad de productos agregados al carrito:
		{
		    "accion": "eliminar",
		    "producto_id": "67b0e1a5173fcdd6b420ae3c",
		    "cantidad": 2
		}


b. Enviar la solicitud y verifica que recibas un mensaje confirmando que los producto se agregados fueron registradas exitosamente. Esto replicara en Redis, almacenando el carrito mismo y replicara la acción de movimientos en históricos dentro de mongoDB


Paso 5: Ver contenido en carrito y recomendaciones
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://localhost:5000/ver_carrito

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body:
		- vacío

b. Enviar la solicitud y verificar que recibas en el mensaje el estado de tu carrito, si se tiene productos agregados recomendara productos que tengan las mis etiquetas


Paso 6: Ver listado de productos
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://localhost:5000/productos

	- Authorization:
		
		- no es necesario

	- Body (ejemplo):
		- vacío

b- Enviar la solicitud y verificar que recibas en el mensaje todo el listado de productos al igual que figura en MongoDB.

 
Paso 7: Consultar por producto especifico
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://127.0.0.1:5000/producto/67b0e1a5173fcdd6b420ae41  (lo ultimo es el ID del producto a consultar)

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):

b. Enviar la solicitud y verificar que recibas en el mensaje la descripción del producto consultado. 


Paso 8: Borrar carrito entero
a. Crear una nueva solicitud:
	- Método: DELETE

	- URL: http://localhost:5000/carrito/eliminar

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):
		- Vacío

b. Enviar la solicitud y verificar que recibas en el mensaje de carrito eliminado. Redis borra el carrito, pero guarda un registro para recuperar el mismo si es necesario


Paso 9: Recuperar carrito
a. Crear una nueva solicitud:
	- Método: POST

	- URL: http://localhost:5000/restaurar_carrito

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):
		- Vacío

b. Enviar la solicitud y verificar que recibas en el mensaje de recuperado el carrito con éxito. Esto es posible ya que se almacena por una cantidad de tiempo el carrito borrado para poder recuperarlo.


Paso 10: Comprar carrito
a. Crear una nueva solicitud:
	- Método: POST
	
	- URL: http://localhost:5000/carrito/comprar

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):
		{
		    "forma_pago": "tarjeta"
		}


b. Enviar la solicitud y verifica que recibas un mensaje confirmando que la compra se haya realizado exitosamente. Esto replicara en Redis, borrando el almacenamiento del carrito y replicara en mongo, generado una factura del producto en "facturas" y archivando como pago realizado dentro de "pagos"




--------------------------------------------------------FUNCIONES QUE PUEDE REALIZAR UN ADMIN---------------------------------------------------------------------------------

Credenciales de  ejemplo de ADMIN:

	- "email": "dios@admin.com"
	- "password": "claveDios"



Paso 11: Agregar producto al inventario
a. Crear una nueva solicitud:
	- Método: POST

	- URL: http://localhost:5000/agregar_productos

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):
		{
		  "nombre": "Smartphone Pro",
		  "categoria": "Tecnología",
		  "descripcion": "Teléfono con pantalla AMOLED de 6.5' y 128GB de almacenamiento",
		  "precio": 899.99,
		  "stock": 50,
		  "imagenes": [
		    "https://example.com/imagen1.jpg",
		    "https://example.com/imagen2.jpg"
		  ],
		  "valoraciones": [
		    {
		      "usuario": "juan123",
		      "puntuacion": 5,
		      "comentario": "Excelente producto!"
		    },
		    {
		      "usuario": "maria456",
		      "puntuacion": 4,
		      "comentario": "Buena calidad, pero la batería podría ser mejor."
		    }
		  ],
		  "etiquetas": ["smartphone", "tecnología", "oferta"]
		}

b. Enviar la solicitud y verificar que recibas en el mensaje de agregado de los productos exitoso. Esto replicaría en MongoDB en la colección de "inventario" y la acción en "histórico"2



Paso 12: Modificar Inventario
a. Crear una nueva solicitud:

	- Método: POST

	- URL: http://localhost:5000/modificar_inventario

	- Headers:

		- Authorization: Bearer {access_token}

	- Body (ejemplo):
		{
		  "modificaciones": [
		    {"producto_id": "67b0e0bc173fcdd6b420ae16", "campo": "stock", "nuevo_valor": 25},
		    {"producto_id": "67b0e0bc173fcdd6b420ae15", "campo": "precio", "nuevo_valor": 950.00}
		  ]
		}

b. Enviar la solicitud y verificar que recibas en el mensaje de producto modificado con éxito. Se puede ver el producto modificado en "inventario" y la acción en "registroInventario" dentro de MongoDB 


Paso 13: Eliminar producto
a. Crear una nueva solicitud:
	- Método: DELETE

	- URL: http://127.0.0.1:5000/eliminar_producto/67b0e1a5173fcdd6b420ae39  (El ID final es el ID del producto a eliminar)

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body (ejemplo):

b. Enviar la solicitud y verificar que recibas en el mensaje de confirmación de borrado del producto en inventario. El mismo replicara en MongoDB.




------------------------------------------------------FUNCIONES EXTRAS--------------------------------------------------------------------------------------------------------

Paso 14: Ver usuarios registrados
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://127.0.0.1:5000/usuarios

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body:
		- Vacío

b. Enviar la solicitud y verificar que recibas en el mensaje con todo los usuarios registrados, al igual que se puede visualizar en MongoDB en "usuarios"


Paso 15: Ver actividad del usuario
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://127.0.0.1:5000/producto/67b0e1a5173fcdd6b420ae41  (el ID debe ser de un usuario en especifico)

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body:
		- Vacío

b. Enviar la solicitud y verificar que recibas en el mensaje todo el histórico del usuario para ver todas sus actividades.


Paso 16: Ver facturas de un cliente
a. Crear una nueva solicitud:
	- Método: GET

	- URL: http://127.0.0.1:5000/facturas/67b3ef2c1c829438730d8ba1  (ID del usuario)

	- Authorization:
		
		- Bearer Token: {acccess_token}

	- Body:
		- Vacío

b. Enviar la solicitud y verificar que recibas en el mensaje con las facturas realizadas por el usuario





---------------------------------------------------------PASO FINAL-----------------------------------------------------------------------------------------------------------



Paso para Desloguearte en Postman
a. Crear una nueva solicitud:

	- Método: POST

	- URL: http://localhost:5000/logout

	- Pestaña "Headers": Añade un nuevo encabezado con el nombre Authorization y el valor Bearer {access_token} (reemplaza {access_token} con el token obtenido durante el login).

b. Enviar la solicitud y verifica que recibas una respuesta con el mensaje "Sesión cerrada exitosamente".

