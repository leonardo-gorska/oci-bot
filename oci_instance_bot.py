#!/usr/bin/env python3
"""
============================================================
  OCI A1.Flex Instance Creator Bot
  Tenta criar automaticamente uma instancia ARM
  VM.Standard.A1.Flex (Always Free) na Oracle Cloud
============================================================

Uso: python3 oci_instance_bot.py [--config config.json]
"""

import oci
import json
import sys
import os
import time
import logging
import argparse
import io
from datetime import datetime

# --------------------------------------------------
# Logging (UTF-8 safe for Windows and Linux)
# --------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("oci-bot")
logger.setLevel(logging.INFO)

# Console handler - force UTF-8 to avoid cp1252 issues on Windows
try:
    console_stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except AttributeError:
    console_stream = sys.stdout

console_handler = logging.StreamHandler(console_stream)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler("oci_bot.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
logger.addHandler(file_handler)


def load_config(config_path: str) -> dict:
    """Carrega o arquivo de configuracao JSON."""
    if not os.path.exists(config_path):
        logger.error(f"[ERRO] Arquivo de configuracao nao encontrado: {config_path}")
        logger.error("Copie o config.example.json para config.json e preencha os dados.")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Validacao de campos obrigatorios
    required_oci = ["tenancy_ocid", "user_ocid", "fingerprint", "key_file", "region"]
    required_instance = [
        "compartment_id", "availability_domain", "subnet_id",
        "image_id", "ssh_public_key"
    ]

    for field in required_oci:
        if not config.get("oci_credentials", {}).get(field):
            logger.error(f"[ERRO] Campo obrigatorio ausente em oci_credentials: {field}")
            sys.exit(1)

    for field in required_instance:
        if not config.get("instance", {}).get(field):
            logger.error(f"[ERRO] Campo obrigatorio ausente em instance: {field}")
            sys.exit(1)

    return config


def send_whatsapp(config: dict, message: str):
    """Envia notificacao via WhatsApp usando CallMeBot (gratuito)."""
    wa = config.get("whatsapp", {})
    phone = wa.get("phone", "")
    apikey = wa.get("apikey", "")

    if not phone or not apikey:
        return

    try:
        import requests
        from urllib.parse import quote
        # Remove markdown formatting que nao funciona no CallMeBot
        clean_msg = message.replace("*", "").replace("`", "")
        encoded_msg = quote(clean_msg)
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            logger.info("[OK] Notificacao WhatsApp enviada com sucesso!")
        else:
            logger.warning(f"[AVISO] Erro ao enviar WhatsApp: {resp.status_code} - {resp.text}")
    except ImportError:
        logger.warning("[AVISO] Modulo 'requests' nao instalado. WhatsApp desabilitado.")
    except Exception as e:
        logger.warning(f"[AVISO] Falha ao enviar notificacao WhatsApp: {e}")


def send_telegram(config: dict, message: str):
    """Envia notificacao via Telegram (opcional)."""
    tg = config.get("telegram", {})
    bot_token = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")

    if not bot_token or not chat_id:
        return

    try:
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("[OK] Notificacao Telegram enviada com sucesso!")
        else:
            logger.warning(f"[AVISO] Erro ao enviar Telegram: {resp.status_code} - {resp.text}")
    except ImportError:
        logger.warning("[AVISO] Modulo 'requests' nao instalado. Telegram desabilitado.")
    except Exception as e:
        logger.warning(f"[AVISO] Falha ao enviar notificacao Telegram: {e}")


def send_notification(config: dict, message: str):
    """Envia notificacao por todos os canais configurados (WhatsApp e/ou Telegram)."""
    send_whatsapp(config, message)
    send_telegram(config, message)


def create_oci_config(config: dict) -> dict:
    """Cria o dict de configuracao para o OCI SDK."""
    creds = config["oci_credentials"]

    # Expande ~ no caminho da chave
    key_file = os.path.expanduser(creds["key_file"])

    oci_config = {
        "user": creds["user_ocid"],
        "key_file": key_file,
        "fingerprint": creds["fingerprint"],
        "tenancy": creds["tenancy_ocid"],
        "region": creds["region"],
    }

    # Passphrase opcional
    passphrase = creds.get("key_passphrase")
    if passphrase:
        oci_config["pass_phrase"] = passphrase

    # Valida a config
    oci.config.validate_config(oci_config)

    return oci_config


def build_launch_details(config: dict) -> oci.core.models.LaunchInstanceDetails:
    """Constroi o objeto LaunchInstanceDetails com os parametros da config."""
    inst = config["instance"]

    shape = inst.get("shape", "VM.Standard.A1.Flex")
    ocpus = inst.get("ocpus", 4)
    memory_gb = inst.get("memory_gb", 24)
    display_name = inst.get("display_name", "gorvax-server")
    boot_volume_gb = inst.get("boot_volume_size_gb", 50)

    # Shape config (OCPUs e memoria)
    shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=float(ocpus),
        memory_in_gbs=float(memory_gb)
    )

    # Source details (imagem + tamanho do boot volume)
    source_details = oci.core.models.InstanceSourceViaImageDetails(
        image_id=inst["image_id"],
        boot_volume_size_in_gbs=boot_volume_gb
    )

    # Metadata (SSH key)
    metadata = {
        "ssh_authorized_keys": inst["ssh_public_key"]
    }

    # VNIC Details (rede)
    vnic_details = oci.core.models.CreateVnicDetails(
        subnet_id=inst["subnet_id"],
        assign_public_ip=True
    )

    # Monta o LaunchInstanceDetails
    launch_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=inst["compartment_id"],
        availability_domain=inst["availability_domain"],
        shape=shape,
        shape_config=shape_config,
        display_name=display_name,
        source_details=source_details,
        create_vnic_details=vnic_details,
        metadata=metadata,
        is_pv_encryption_in_transit_enabled=True
    )

    return launch_details


def get_instance_ip(compute_client, network_client, instance_id, compartment_id):
    """Tenta obter o IP publico da instancia criada."""
    try:
        # Lista os VNICs da instancia
        vnic_attachments = oci.pagination.list_call_get_all_results(
            compute_client.list_vnic_attachments,
            compartment_id=compartment_id,
            instance_id=instance_id
        ).data

        for vnic_att in vnic_attachments:
            if vnic_att.lifecycle_state == "ATTACHED":
                vnic = network_client.get_vnic(vnic_att.vnic_id).data
                if vnic.public_ip:
                    return vnic.public_ip

    except Exception as e:
        logger.warning(f"Nao foi possivel obter o IP publico: {e}")

    return None


def run_bot(config: dict):
    """Loop principal do bot."""
    bot_config = config.get("bot", {})
    retry_interval = bot_config.get("retry_interval_seconds", 60)
    max_attempts = bot_config.get("max_attempts", 0)  # 0 = infinito

    inst = config["instance"]
    shape = inst.get("shape", "VM.Standard.A1.Flex")
    ocpus = inst.get("ocpus", 4)
    memory_gb = inst.get("memory_gb", 24)

    logger.info("=" * 60)
    logger.info("[BOT] OCI A1.Flex Instance Creator Bot")
    logger.info("=" * 60)
    logger.info(f"Shape:    {shape}")
    logger.info(f"OCPUs:    {ocpus}")
    logger.info(f"RAM:      {memory_gb} GB")
    logger.info(f"Regiao:   {config['oci_credentials']['region']}")
    logger.info(f"AD:       {inst['availability_domain']}")
    logger.info(f"Nome:     {inst.get('display_name', 'gorvax-server')}")
    logger.info(f"Intervalo entre tentativas: {retry_interval}s")
    logger.info(f"Maximo de tentativas: {'INFINITO' if max_attempts == 0 else max_attempts}")
    logger.info("=" * 60)

    # Cria os clients OCI
    oci_config = create_oci_config(config)
    compute_client = oci.core.ComputeClient(oci_config)
    network_client = oci.core.VirtualNetworkClient(oci_config)

    # Testa a autenticacao
    logger.info("[AUTH] Testando autenticacao...")
    try:
        compute_client.list_instances(
            compartment_id=inst["compartment_id"],
            limit=1
        )
        logger.info("[OK] Autenticacao OK!")
    except oci.exceptions.ServiceError as e:
        logger.error(f"[FALHA] Falha na autenticacao: {e.message}")
        logger.error("Verifique suas credenciais no config.json")
        sys.exit(1)

    # Build launch details
    launch_details = build_launch_details(config)

    attempt = 0
    start_time = datetime.now()

    logger.info("")
    logger.info("[START] Iniciando tentativas de criacao da instancia...")
    logger.info("")

    while True:
        attempt += 1

        if max_attempts > 0 and attempt > max_attempts:
            logger.warning(f"[STOP] Atingiu o limite de {max_attempts} tentativas. Parando.")
            send_notification(config, f"*OCI Bot* parou apos {max_attempts} tentativas sem sucesso.")
            break

        elapsed = datetime.now() - start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        elapsed_str = f"{hours}h{minutes:02d}m{seconds:02d}s"

        logger.info(f"[TRY] Tentativa #{attempt} (rodando ha {elapsed_str})...")

        try:
            response = compute_client.launch_instance(launch_details)
            instance = response.data

            logger.info("=" * 60)
            logger.info("*** INSTANCIA CRIADA COM SUCESSO! ***")
            logger.info("=" * 60)
            logger.info(f"Instance OCID: {instance.id}")
            logger.info(f"Display Name:  {instance.display_name}")
            logger.info(f"Shape:         {instance.shape}")
            logger.info(f"State:         {instance.lifecycle_state}")
            logger.info(f"Tentativas:    {attempt}")
            logger.info(f"Tempo total:   {elapsed_str}")

            # Espera um pouco e tenta pegar o IP
            logger.info("[WAIT] Aguardando instancia inicializar para obter IP...")
            time.sleep(30)

            public_ip = get_instance_ip(
                compute_client, network_client,
                instance.id, inst["compartment_id"]
            )

            if public_ip:
                logger.info(f"[IP] IP Publico: {public_ip}")
            else:
                logger.info("[IP] IP publico ainda nao disponivel. Verifique no OCI Console.")

            # Notificacao Telegram
            msg = (
                f"*Instancia OCI criada com sucesso!*\n\n"
                f"- Nome: `{instance.display_name}`\n"
                f"- Shape: `{instance.shape}`\n"
                f"- OCPUs: `{ocpus}`\n"
                f"- RAM: `{memory_gb} GB`\n"
                f"- OCID: `{instance.id}`\n"
                f"- IP: `{public_ip or 'Verificar no console'}`\n"
                f"- Tentativas: `{attempt}`\n"
                f"- Tempo: `{elapsed_str}`"
            )
            send_notification(config, msg)

            logger.info("")
            logger.info("[OK] Bot finalizado. Sua instancia esta provisionando!")
            logger.info("     Acesse o OCI Console para acompanhar o status.")
            break

        except oci.exceptions.ServiceError as e:
            error_code = e.code if hasattr(e, 'code') else 'Unknown'
            error_status = e.status if hasattr(e, 'status') else 0
            error_msg = e.message if hasattr(e, 'message') else str(e)

            # Erros de capacidade -- continua tentando
            capacity_errors = [
                "InternalError",
                "OutOfCapacity",
                "Out of host capacity",
                "LimitExceeded",
                "TooManyRequests",
            ]

            is_capacity_error = any(
                err.lower() in error_msg.lower() or err.lower() in str(error_code).lower()
                for err in capacity_errors
            )

            # HTTP 500 geralmente eh "out of capacity"
            if error_status == 500:
                is_capacity_error = True

            # HTTP 429 = rate limit
            if error_status == 429:
                is_capacity_error = True
                logger.warning(f"[RATE-LIMIT] Rate limit atingido! Esperando {retry_interval * 2}s...")
                time.sleep(retry_interval)  # Espera extra

            if is_capacity_error:
                logger.info(
                    f"   [FAIL] Sem capacidade ({error_code}: {error_status}). "
                    f"Aguardando {retry_interval}s..."
                )
            else:
                # Erro desconhecido -- loga detalhes completos
                logger.error(f"   [FAIL] Erro inesperado: [{error_status}] {error_code}")
                logger.error(f"          Mensagem: {error_msg}")
                logger.error(f"          Aguardando {retry_interval}s antes de tentar novamente...")

                # Se for erro de autenticacao/autorizacao, para
                if error_status in [401, 403]:
                    logger.error("[STOP] Erro de autenticacao/autorizacao. Verifique suas credenciais.")
                    send_notification(config, f"*OCI Bot* parou por erro de autenticacao: {error_msg}")
                    sys.exit(1)

                # Se for 404 (recurso nao encontrado), para
                if error_status == 404:
                    logger.error("[STOP] Recurso nao encontrado. Verifique subnet_id, image_id, etc.")
                    send_notification(config, f"*OCI Bot* parou por recurso nao encontrado: {error_msg}")
                    sys.exit(1)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("[STOP] Bot interrompido pelo usuario.")
            sys.exit(0)

        except Exception as e:
            logger.error(f"   [FAIL] Erro nao esperado: {type(e).__name__}: {e}")
            logger.error(f"          Continuando em {retry_interval}s...")

        time.sleep(retry_interval)

    logger.info("Bot encerrado.")


def main():
    parser = argparse.ArgumentParser(
        description="OCI A1.Flex Instance Creator Bot"
    )
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="Caminho para o arquivo de configuracao (padrao: config.json)"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    run_bot(config)


if __name__ == "__main__":
    main()
