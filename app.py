from flask import Flask, render_template, request
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

app = Flask(__name__)


def apply_vlan_config(vlans, device_ip, username, password, port, device_type="cisco_ios_telnet"):
    """
    Se conecta al dispositivo Cisco y configura las VLANs.
    Por defecto usa Telnet (cisco_ios_telnet). Si usás SSH, cambiá device_type a "cisco_ios".
    """
    device = {
        "device_type": device_type,
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,   # si el enable es distinto, cambialo
        "port": port,
    }

    commands = []
    for vlan in vlans:
        vlan_id = vlan["id"]
        vlan_name = vlan["name"]

        commands.extend([
            f"vlan {vlan_id}",
            f"name {vlan_name}"
        ])

    try:
        conn = ConnectHandler(**device)

        # Intentar entrar en modo enable (si aplica)
        try:
            conn.enable()
        except Exception:
            # Si no hay enable o no hace falta, lo ignoramos
            pass

        output = conn.send_config_set(commands)

        # Guardar configuración (no todos los IOS lo soportan igual)
        try:
            output += "\n" + conn.save_config()
        except Exception:
            output += "\n(No se pudo ejecutar save_config automáticamente)"

        conn.disconnect()
        return True, output

    except NetmikoAuthenticationException as e:
        return False, f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, f"Error inesperado: {e}"


@app.route("/", methods=["GET", "POST"])
def index():
    vlans = []
    device_ip = ""
    username = ""
    port = 23
    error_msg = None
    success_msg = None
    netmiko_output = None

    if request.method == "POST":
        # Datos de conexión
        device_ip = request.form.get("device_ip", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        port_raw = request.form.get("port", "").strip()
        if port_raw:
            try:
                port = int(port_raw)
            except ValueError:
                port = 23
        else:
            port = 23

        # VLANs
        vlan_ids = request.form.getlist("vlan_id")
        vlan_names = request.form.getlist("vlan_name")

        for vid, vname in zip(vlan_ids, vlan_names):
            vid = vid.strip()
            vname = vname.strip()

            if not vid:
                continue

            if not vname:
                vname = f"VLAN_{vid}"

            vlans.append({"id": vid, "name": vname})

        if not device_ip or not username or not password:
            error_msg = "Faltan datos de conexión (IP, usuario o password)."
        elif len(vlans) == 0:
            error_msg = "No se cargó ninguna VLAN válida."
        else:
            ok, output = apply_vlan_config(
                vlans=vlans,
                device_ip=device_ip,
                username=username,
                password=password,
                port=port,
                device_type="cisco_ios_telnet",  # Cambiá a "cisco_ios" si usás SSH
            )
            if ok:
                success_msg = "Configuración aplicada correctamente en el switch/router."
                netmiko_output = output
            else:
                error_msg = output

    return render_template(
        "index.html",
        vlans=vlans,
        device_ip=device_ip,
        username=username,
        port=port,
        error_msg=error_msg,
        success_msg=success_msg,
        netmiko_output=netmiko_output,
    )


if __name__ == "__main__":
    # Para desarrollo
    app.run(host="0.0.0.0", port=5000, debug=True)
