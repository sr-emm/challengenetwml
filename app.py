from flask import Flask, render_template, request, session
from netmiko import (
    ConnectHandler,
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)
import re

app = Flask(__name__)

# SOLO LAB – en algo real, usá una env var
app.secret_key = "cambia-esta-clave-para-tu-lab"

# VLANs legacy que no queremos ver ni tocar
IGNORE_VLANS = {"1002", "1003", "1004", "1005"}


def apply_config(vlans, hostname, device_ip, username, password, port, device_type="cisco_ios_telnet"):
    """
    Aplica configuración de VLANs y hostname en el dispositivo Cisco.
    """
    device = {
        "device_type": device_type,  # "cisco_ios" si usás SSH
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,  # si el enable es otro, cambialo
        "port": port,
    }

    commands = []

    # Cambiar nombre del switch si se indicó
    if hostname:
        commands.append(f"hostname {hostname}")

    # Config de VLANs
    for vlan in vlans:
        vlan_id = vlan["id"]
        vlan_name = vlan["name"]
        commands.extend([
            f"vlan {vlan_id}",
            f"name {vlan_name}",
        ])

    if not commands:
        return False, "No hay cambios para aplicar (sin hostname ni VLANs)."

    try:
        conn = ConnectHandler(**device)

        # Intentar enable
        try:
            conn.enable()
        except Exception:
            pass

        output = conn.send_config_set(commands)

        # NO guardamos obligatoriamente acá; hay un botón dedicado
        conn.disconnect()
        return True, output

    except NetmikoAuthenticationException as e:
        return False, f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, f"Error inesperado: {e}"


def fetch_current_vlans(device_ip, username, password, port, device_type="cisco_ios_telnet"):
    """
    Ejecuta 'show vlan brief' y devuelve una lista de VLANs parseadas (sin 1002–1005).
    """
    device = {
        "device_type": device_type,
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,
        "port": port,
    }

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        output = conn.send_command("show vlan brief")
        conn.disconnect()

        vlans = parse_vlans_from_show(output)
        return True, vlans, output

    except NetmikoAuthenticationException as e:
        return False, [], f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, [], f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, [], f"Error inesperado: {e}"


def parse_vlans_from_show(output):
    """
    Parseo simple de 'show vlan brief'.
    Ignora las VLANs 1002–1005 (FDDI/TokenRing).
    """
    vlans = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line[0].isdigit():
            continue

        parts = re.split(r"\s+", line)
        if len(parts) < 2:
            continue

        vlan_id = parts[0]
        vlan_name = parts[1]

        if not vlan_id.isdigit():
            continue

        if vlan_id in IGNORE_VLANS:
            continue

        vlans.append({"id": vlan_id, "name": vlan_name})

    return vlans


def fetch_hostname(device_ip, username, password, port, device_type="cisco_ios_telnet"):
    """
    Lee el hostname actual del dispositivo (show run | i ^hostname).
    """
    device = {
        "device_type": device_type,
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,
        "port": port,
    }

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        output = conn.send_command("show running-config | include ^hostname")
        conn.disconnect()

        hostname = parse_hostname_from_output(output)
        return True, hostname, output

    except NetmikoAuthenticationException as e:
        return False, "", f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, "", f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, "", f"Error inesperado: {e}"


def parse_hostname_from_output(output):
    """
    Busca una línea 'hostname X' y devuelve X.
    """
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("hostname "):
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    return ""


def save_config_only(device_ip, username, password, port, device_type="cisco_ios_telnet"):
    """
    Solo ejecuta 'write memory' / 'copy run start' vía Netmiko (save_config()).
    """
    device = {
        "device_type": device_type,
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,
        "port": port,
    }

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        try:
            output = conn.save_config()
        except Exception:
            # Algunos IOS no soportan save_config directo
            output = "No se pudo ejecutar save_config automáticamente (probá manualmente 'write memory')."

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
    # Valores iniciales desde sesión
    device_ip = session.get("device_ip", "")
    username = session.get("username", "")
    stored_password = session.get("device_password", "")
    port = session.get("port", 23)
    hostname = session.get("hostname", "")

    vlans = []
    error_msg = None
    success_msg = None
    netmiko_output = None

    password = ""
    password_for_field = stored_password

    if request.method == "POST":
        action = request.form.get("action", "apply")  # apply, fetch_vlans, fetch_hostname, save_config

        # Datos de conexión
        form_ip = request.form.get("device_ip", "").strip()
        form_user = request.form.get("username", "").strip()
        form_pass = request.form.get("password", "")
        form_port = request.form.get("port", "").strip()
        form_hostname = request.form.get("hostname", "").strip()

        if form_ip:
            device_ip = form_ip
        if form_user:
            username = form_user
        if form_port:
            try:
                port = int(form_port)
            except ValueError:
                port = 23

        # hostname desde form (si escribió algo, pisa lo anterior)
        if form_hostname:
            hostname = form_hostname

        # Password: si la escribe, actualiza; si no, uso la guardada
        if form_pass:
            password = form_pass
        else:
            password = stored_password

        # Guardar en sesión
        session["device_ip"] = device_ip
        session["username"] = username
        session["port"] = port
        session["hostname"] = hostname
        if password:
            session["device_password"] = password

        password_for_field = password

        # VLANs desde formulario (para aplicar; para fetch_vlans se sobrescriben)
        vlan_ids = request.form.getlist("vlan_id")
        vlan_names = request.form.getlist("vlan_name")

        for vid, vname in zip(vlan_ids, vlan_names):
            vid = vid.strip()
            vname = vname.strip()

            if not vid:
                continue
            if vid in IGNORE_VLANS:
                continue
            if not vname:
                vname = f"VLAN_{vid}"

            vlans.append({"id": vid, "name": vname})

        if not device_ip or not username or not password:
            error_msg = "Faltan datos de conexión (IP, usuario o password)."
        else:
            if action == "fetch_vlans":
                ok, vlans_from_device, output = fetch_current_vlans(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    device_type="cisco_ios_telnet",  # "cisco_ios" si usás SSH
                )
                if ok:
                    vlans = vlans_from_device
                    success_msg = "VLANs leídas correctamente del dispositivo."
                    netmiko_output = output
                else:
                    error_msg = output

            elif action == "fetch_hostname":
                ok, hostname_from_device, output = fetch_hostname(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    device_type="cisco_ios_telnet",
                )
                if ok:
                    hostname = hostname_from_device or hostname
                    session["hostname"] = hostname
                    success_msg = "Nombre del switch leído correctamente."
                    netmiko_output = output
                else:
                    error_msg = output

            elif action == "save_config":
                ok, output = save_config_only(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    device_type="cisco_ios_telnet",
                )
                if ok:
                    success_msg = "Configuración guardada en el dispositivo."
                    netmiko_output = output
                else:
                    error_msg = output

            else:  # apply
                if len(vlans) == 0 and not hostname:
                    error_msg = "No hay cambios para aplicar (ni VLANs ni hostname)."
                else:
                    ok, output = apply_config(
                        vlans=vlans,
                        hostname=hostname,
                        device_ip=device_ip,
                        username=username,
                        password=password,
                        port=port,
                        device_type="cisco_ios_telnet",
                    )
                    if ok:
                        success_msg = "Configuración aplicada correctamente (VLANs/hostname)."
                        netmiko_output = output
                    else:
                        error_msg = output

    return render_template(
        "index.html",
        vlans=vlans,
        device_ip=device_ip,
        username=username,
        port=port,
        hostname=hostname,
        password_value=password_for_field,
        error_msg=error_msg,
        success_msg=success_msg,
        netmiko_output=netmiko_output,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
