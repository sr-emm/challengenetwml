"""
# Challenge Networking ML (Parte 1: Automatización de Switch)

Este repositorio contiene la solución para la Parte 1 del Challenge de Automatización de ML, enfocada en la interacción con un switch Cisco (simulado en GNS3) mediante una interfaz web desarrollada en Flask y Netmiko.

El diseño del Frontend fue evolucionado a un **Dashboard NOC** (Network Operations Center) con una vista dividida (50/50) que permite monitorizar el output exacto de la consola en tiempo real mientras se modifica la configuración.

## 💾 Instalación y Configuración (Requisito 9)

### 1. Ubicación de Archivos

Coloque `app.py` y la carpeta `templates/` (que contiene `index.html`) en la misma raíz del proyecto.

### 2. Python y Entorno Virtual (Requisito 9)

Es altamente recomendado usar un entorno virtual (`venv`) para aislar las dependencias:

```bash
# 1. Crear el entorno virtual
python3 -m venv venv

# 2. Activar el entorno
source venv/bin/activate
```

*(Su consola ahora mostrará `(venv)` al inicio).*

<img width="422" height="35" alt="image" src="https://github.com/user-attachments/assets/974eae03-895b-4818-8bf6-2f7ad50c2358" />


### 3. Instalación de Dependencias

Con el entorno virtual activado, instale las librerías necesarias:

```bash
pip install flask netmiko
```

### 4. Ejecución de la Aplicación

Ejecute el script principal. La aplicación se levantará en el puerto **5001** y será accesible desde cualquier IP (`0.0.0.0`) en la red:

```bash
python3 app.py
```

<img width="744" height="210" alt="image" src="https://github.com/user-attachments/assets/e8cec7d2-9bb9-4cf0-bf3a-743c51065ce2" />

Acceda a la aplicación en su navegador: `http://<IP_DEL_SERVIDOR>:5001`

<img width="1600" height="1165" alt="image" src="https://github.com/user-attachments/assets/1888193a-57bd-47c3-b4a3-b4a23b8a9fc6" />

## 🛡️ Hardening y Robustez (Garantía de Producción)

Se implementaron mejoras críticas en el backend (Netmiko/Flask) para asegurar la integridad de la configuración y la fiabilidad del script en entornos de laboratorio o producción:

* **Validación Estricta de Hostname:** El sistema rechaza cualquier hostname que contenga espacios o caracteres que no sean alfanuméricos, guiones medios (`-`) o guiones bajos (`_`) (Regex: `^[\w-]+$`). Esto previene fallos de sintaxis en Cisco IOS y garantiza nombres de archivo válidos para backups.
* **Gestión de Conexiones Seguras:** Se utiliza el patrón `with ConnectHandler(...) as conn:` (Context Managers) para garantizar que la sesión SSH/Telnet se cierre limpiamente después de cada transacción, evitando sesiones huérfanas en el switch.

<img width="1191" height="86" alt="image" src="https://github.com/user-attachments/assets/1a82eed0-ca44-477e-86ed-0edcf2657703" />

* **Interacciones Robustas:** Las operaciones interactivas críticas (`copy run tftp` y `write memory`) utilizan el método `send_command_timing()`. Esto elimina el uso de `time.sleep()` y permite que el script responda dinámicamente a los prompts del dispositivo (como la pregunta `Continue? [no]:` en vIOS/IOU), haciendo el script mucho más fiable.
* **Formato de Backup Unificado:** Se asegura que el formato del nombre de archivo (`AAAA-MM-DD-HHMM-HOSTNAME.txt`) sea consistente y a prueba de errores para las descargas directas (`download_config`) y las subidas a TFTP.

    <img width="538" height="43" alt="image" src="https://github.com/user-attachments/assets/44d5313a-5e29-47ad-83a0-89c16a0cc129" />

## 💻 Características y Flujo de Trabajo

### 1. Interfaz y Parámetros de Acceso (Requisito 2)

El frontend presenta una interfaz clara dividida en dos tarjetas principales y una terminal lateral (Split View):

* **Persistencia:** Todos los campos (IP, Usuario, Password, TFTP) mantienen los datos entre acciones (gracias al uso de la sesión de Flask).
* **Protocolo Inteligente:** Al seleccionar `SSH`, el puerto se ajusta automáticamente a `22`; al seleccionar `Telnet`, se ajusta a `23`.
* **Terminal Consolidada:** El output de todos los comandos (lectura, aplicación, backup) se muestra en la terminal de la derecha, incluyendo mensajes de *debug* sobre el protocolo de conexión usado.

<img width="2422" height="984" alt="image" src="https://github.com/user-attachments/assets/30d28e46-f2d8-450f-8aa8-c3891dabcd2c" />

### 2. Obtención y Edición de Datos (`Fetch All`)

Al presionar **"Leer Config"**, el script establece una única conexión para obtener los datos más recientes del switch:

* **Hostname:** Se lee el hostname actual del dispositivo (utilizando el prompt, que es rápido).
* **VLANs:** Se lee la salida de `show vlan brief`.
  * **Filtro:** Las VLANs de sistema (1002 a 1005) son automáticamente filtradas y omitidas de la interfaz.

<img width="2359" height="1242" alt="image" src="https://github.com/user-attachments/assets/dfc0eab1-935b-43d3-b0ee-461eced1a5fa" />

### 3. Configuración de Hostname y VLANs (Requisito 3 & 4)

Los cambios se aplican al presionar **"APLICAR CAMBIOS"**.

#### Hostname (Requisito 4)

* Se lee el valor del campo "Hostname del Switch" y se valida contra el regex de seguridad.
* Si es válido, se aplica el cambio (`hostname <nuevo_nombre>`).

#### VLANs (Requisito 3)

* **Creación/Modificación:** Se pueden agregar filas (`Agregar VLAN`) o editar IDs/Nombres.
* **Regla de Negocio:** Se impone un límite de **20 caracteres** en el nombre de la VLAN.
* **Comportamiento:** La herramienta sobrescribe la configuración de las VLANs existentes o crea las nuevas, manteniendo el flujo simple de "configuración deseada".

<img width="2394" height="1177" alt="image" src="https://github.com/user-attachments/assets/4a979012-ce33-4971-b41b-c25fb15b8426" />

### 4. Funcionalidades de Backup (Requisito 5 & 6)

#### Guardar Configuración (Requisito 5)

El botón **"Write Mem"** ejecuta el comando `write memory` (o `copy run start`), manejando cualquier prompt de confirmación.

<img width="2027" height="534" alt="image" src="https://github.com/user-attachments/assets/84828a49-3238-415b-bf5c-6f8c288379d3" />

#### Backup Descargable (Requisito 6)

El botón **"Descargar .txt"** genera un archivo `running-config` y lo envía directamente al navegador del usuario.

* **Formato de Nombre:** `AAAA-MM-DD-HHMM-HOSTNAME.txt`.

<img width="447" height="139" alt="image" src="https://github.com/user-attachments/assets/53bef03d-39b0-41a6-987e-d959276d8761" />

#### Subir a TFTP (Requisito 6 - Opcional)

El botón **"Subir a TFTP"** ejecuta el comando `copy running-config tftp:` hacia el servidor especificado, manejando el diálogo interactivo de la CLI.
<img width="2396" height="260" alt="image" src="https://github.com/user-attachments/assets/97910386-1aac-42fe-b91e-274817547794" />

### 5. Validación de Configuración (Requisito 7)

La herramienta utiliza dos métodos de validación:

1. **Validación Implícita (Netmiko Output):** Después de cada acción, la terminal muestra el output exacto del dispositivo (Netmiko).
2. **Validación de Seguridad (Backend Alerts):** Si el script no puede autenticarse, sufre un timeout, o el hostname es inválido, el frontend muestra una **alerta clara** en la parte superior con el mensaje de error del servidor o del dispositivo, cumpliendo con el requisito de alerta en caso de desviación.

## 6. Control de Versiones (Requisito 8)

El proyecto se gestiona mediante Git. El historial de commits refleja un uso amplio de la herramienta, aunque se debe mejorar el como y cuando se hacen para que sean más utiles. 

<img width="1831" height="1111" alt="image" src="https://github.com/user-attachments/assets/51904968-5e01-4ac2-a070-ddcf714c3e3d" />

"""
