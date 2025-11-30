import time
from flask import Flask, render_template, request, session, make_response
from netmiko import (
    ConnectHandler,
    NetmikoTimeoutException,
    NetmikoAuthenticationException,
)
from datetime import datetime
import re

app = Flask(__name__)

# SOLO LAB – en algo real, usá una env var
app.secret_key = "cambia-esta-clave-para-tu-lab"

# VLANs legacy que no queremos ver ni tocar
IGNORE_VLANS = {"1002", "1003", "1004", "1005"}


def build_device(device_ip, username, password, port, protocol):
    """
    Arma el diccionario de conexión para Netmiko según el protocolo.
    protocol: "telnet" o "ssh"
    """
    if protocol == "ssh":
        device_type = "cisco_ios"
    else:
        device_type = "cisco_ios_telnet"

    return {
        "device_type": device_type,
        "host": device_ip,
        "username": username,
        "password": password,
        "secret": password,  # si el enable es otro, cambialo
        "port": port,
    }


def apply_config(vlans, hostname, device_ip, username, password, port, protocol):
    """
    Aplica configuración de VLANs y hostname en el dispositivo Cisco.
    """
    device = build_device(device_ip, username, password, port, protocol)

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

        conn.disconnect()
        return True, output

    except NetmikoAuthenticationException as e:
        return False, f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, f"Error inesperado: {e}"


def fetch_current_vlans(device_ip, username, password, port, protocol):
    """
    Ejecuta 'show vlan brief' y devuelve una lista de VLANs parseadas (sin 1002–1005).
    """
    device = build_device(device_ip, username, password, port, protocol)

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


def fetch_hostname(device_ip, username, password, port, protocol):
    """
    Lee el hostname actual del dispositivo (show run | i ^hostname).
    """
    device = build_device(device_ip, username, password, port, protocol)

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


def save_config_only(device_ip, username, password, port, protocol):
    """
    Solo ejecuta 'write memory' / 'copy run start' vía Netmiko (save_config()).
    """
    device = build_device(device_ip, username, password, port, protocol)

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        try:
            output = conn.save_config()
        except Exception:
            output = "No se pudo ejecutar save_config automáticamente (probá manualmente 'write memory')."

        conn.disconnect()
        return True, output

    except NetmikoAuthenticationException as e:
        return False, f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, f"Error inesperado: {e}"


def fetch_full_config(device_ip, username, password, port, protocol):
    """
    Obtiene la running-config completa (show running-config).
    """
    device = build_device(device_ip, username, password, port, protocol)

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        output = conn.send_command("show running-config")
        conn.disconnect()
        return True, output

    except NetmikoAuthenticationException as e:
        return False, f"Error de autenticación: {e}"
    except NetmikoTimeoutException as e:
        return False, f"Timeout conectando al dispositivo: {e}"
    except Exception as e:
        return False, f"Error inesperado: {e}"


def upload_config_tftp(device_ip, username, password, port, protocol, tftp_ip, hostname):
    """
    Ejecuta 'copy running-config tftp:' usando solo la IP TFTP.
    El nombre del archivo se genera como:
    Año-Mes-Dia-horaMinuto-Hostname.txt
    """
    tftp_ip = tftp_ip.strip()

    # Validación muy básica de IP
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", tftp_ip):
        return False, "IP de TFTP inválida. Ejemplo: 192.168.1.100"

    hn = hostname if hostname else "device"
    now = datetime.now()
    tftp_filename = f"{now.year:04d}-{now.month:02d}-{now.day:02d}-{now.hour:02d}{now.minute:02d}-{hn}.txt"

    device = build_device(device_ip, username, password, port, protocol)

    try:
        conn = ConnectHandler(**device)

        try:
            conn.enable()
        except Exception:
            pass

        output = ""

        # 1) Lanzamos el copy
        conn.write_channel("copy running-config tftp:\n")
        time.sleep(1)
        out = conn.read_channel()
        output += out

        # 2) Enviamos IP del servidor TFTP
        conn.write_channel(tftp_ip + "\n")
        time.sleep(1)
        out = conn.read_channel()
        output += out

        # 3) Enviamos nombre de archivo destino
        conn.write_channel(tftp_filename + "\n")
        time.sleep(1)
        out = conn.read_channel()
        output += out

        # 4) Si pide confirmación [confirm], mandamos ENTER
        if "[confirm]" in out.lower() or "confirm" in out.lower():
            conn.write_channel("\n")
            time.sleep(1)
            out = conn.read_channel()
            output += out

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
    protocol = session.get("protocol", "telnet")  # telnet / ssh
    tftp_server = session.get("tftp_server", "")

    vlans = []
    error_msg = None
    success_msg = None
    netmiko_output = None

    password = ""
    password_for_field = stored_password

    if request.method == "POST":
        action = request.form.get(
            "action", "apply"
        )  # apply, fetch_all, save_config, download_config, tftp_upload

        # Datos de conexión
        form_ip = request.form.get("device_ip", "").strip()
        form_user = request.form.get("username", "").strip()
        form_pass = request.form.get("password", "")
        form_port = request.form.get("port", "").strip()
        form_hostname = request.form.get("hostname", "").strip()
        form_protocol = request.form.get("protocol", "").strip().lower()
        form_tftp_server = request.form.get("tftp_server", "").strip()

        if form_ip:
            device_ip = form_ip
        if form_user:
            username = form_user

        if form_protocol in ("telnet", "ssh"):
            protocol = form_protocol

        # puerto: si no se indica, por defecto 23 para telnet, 22 para ssh
        if form_port:
            try:
                port = int(form_port)
            except ValueError:
                port = 23 if protocol == "telnet" else 22
        else:
            port = 23 if protocol == "telnet" else 22

        if form_hostname:
            hostname = form_hostname

        if form_pass:
            password = form_pass
        else:
            password = stored_password

        if form_tftp_server:
            tftp_server = form_tftp_server

        # Guardar en sesión
        session["device_ip"] = device_ip
        session["username"] = username
        session["port"] = port
        session["hostname"] = hostname
        session["protocol"] = protocol
        session["tftp_server"] = tftp_server
        if password:
            session["device_password"] = password

        password_for_field = password

        # VLANs desde el formulario (para aplicar)
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
            if action == "fetch_all":
                ok_vlans, vlans_from_device, out_vlans = fetch_current_vlans(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    protocol=protocol,
                )
                ok_host, hostname_from_device, out_host = fetch_hostname(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    protocol=protocol,
                )

                msgs_ok = []
                msgs_err = []

                if ok_vlans:
                    vlans = vlans_from_device
                    msgs_ok.append("VLANs leídas correctamente.")
                else:
                    msgs_err.append(f"Error leyendo VLANs: {vlans_from_device}")

                if ok_host:
                    if hostname_from_device:
                        hostname = hostname_from_device
                        session["hostname"] = hostname
                    msgs_ok.append("Hostname leído correctamente.")
                else:
                    msgs_err.append(f"Error leyendo hostname: {hostname_from_device}")

                if msgs_ok:
                    success_msg = " ".join(msgs_ok)
                if msgs_err:
                    error_msg = " ".join(msgs_err)

                netmiko_output = ""
                if out_vlans:
                    netmiko_output += "=== show vlan brief ===\n" + out_vlans
                if out_host:
                    netmiko_output += "\n\n=== hostname ===\n" + out_host

            elif action == "save_config":
                ok, output = save_config_only(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    protocol=protocol,
                )
                if ok:
                    success_msg = "Configuración guardada en el dispositivo."
                    netmiko_output = output
                else:
                    error_msg = output

            elif action == "download_config":
                ok, cfg_output = fetch_full_config(
                    device_ip=device_ip,
                    username=username,
                    password=password,
                    port=port,
                    protocol=protocol,
                )
                if not ok:
                    error_msg = cfg_output
                else:
                    hn = hostname or parse_hostname_from_output(cfg_output) or "device"
                    now = datetime.now()
                    filename = f"{now.year:04d}-{now.month:02d}-{now.day:02d}-{now.hour:02d}{now.minute:02d}-{hn}.txt"

                    response = make_response(cfg_output)
                    response.headers["Content-Type"] = "text/plain"
                    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
                    return response

            elif action == "tftp_upload":
                if not tftp_server:
                    error_msg = "Debes especificar la IP del servidor TFTP (ej: 192.168.1.100)."
                else:
                    # Si no tenemos hostname, intentamos leerlo antes de generar el nombre del archivo
                    if not hostname:
                        ok_host, hostname_from_device, _ = fetch_hostname(
                            device_ip=device_ip,
                            username=username,
                            password=password,
                            port=port,
                            protocol=protocol,
                        )
                        if ok_host and hostname_from_device:
                            hostname = hostname_from_device
                            session["hostname"] = hostname

                    ok, output = upload_config_tftp(
                        device_ip=device_ip,
                        username=username,
                        password=password,
                        port=port,
                        protocol=protocol,
                        tftp_ip=tftp_server,
                        hostname=hostname,
                    )
                    if ok:
                        success_msg = f"Configuración enviada al servidor TFTP {tftp_server}."
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
                        protocol=protocol,
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
        protocol=protocol,
        tftp_server=tftp_server,
        password_value=password_for_field,
        error_msg=error_msg,
        success_msg=success_msg,
        netmiko_output=netmiko_output,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
